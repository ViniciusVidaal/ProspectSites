from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from .config import Settings
from .models import Lead

HEADERS = [
    "Data",
    "Nome da Empresa",
    "Telefone",
    "Link WhatsApp",
    "Site Atual",
    "Plataforma",
    "Avaliações",
    "Nota",
    "Google Maps",
    "Place ID",
    "Enviado",
    "Data do Envio",
    "Arquivado",
    "CNPJ",
]


class SheetsRepository:
    def __init__(self, settings: Settings):
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        if settings.service_account_info:
            credentials = Credentials.from_service_account_info(
                settings.service_account_info,
                scopes=scopes,
            )
        elif settings.service_account_file:
            credentials = Credentials.from_service_account_file(
                str(settings.service_account_file),
                scopes=scopes,
            )
        else:
            raise RuntimeError("Credencial da conta de serviço não configurada.")
        self.service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        self.spreadsheet_id = settings.spreadsheet_id
        self.sheet_name = settings.sheet_name

    def ensure_sheet(self) -> None:
        metadata = self.service.spreadsheets().get(
            spreadsheetId=self.spreadsheet_id
        ).execute()
        titles = {sheet["properties"]["title"] for sheet in metadata.get("sheets", [])}
        if self.sheet_name not in titles:
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=self.spreadsheet_id,
                body={
                    "requests": [
                        {"addSheet": {"properties": {"title": self.sheet_name}}}
                    ]
                },
            ).execute()

        header_range = f"'{self.sheet_name}'!A1:N1"
        current = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id, range=header_range
        ).execute().get("values", [])
        if not current or current[0] != HEADERS:
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=header_range,
                valueInputOption="RAW",
                body={"values": [HEADERS]},
            ).execute()

    def list(self, include_archived: bool = False) -> list[Lead]:
        self.ensure_sheet()
        rows = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{self.sheet_name}'!A2:N",
        ).execute().get("values", [])
        leads = []
        for row in rows:
            if len(row) > 5 and row[5] and (len(row) <= 9 or not row[9]):
                legacy_archived = (
                    len(row) > 12
                    and str(row[12]).strip().lower() in {"sim", "true", "1", "arquivado"}
                )
                legacy_contactable = bool(
                    (row[2] if len(row) > 2 else "")
                    or "instagram.com" in (row[4] if len(row) > 4 else "").lower()
                )
                if include_archived or (not legacy_archived and legacy_contactable):
                    leads.append(
                        Lead(
                        date=row[0] if len(row) > 0 else "",
                        company_name=row[1] if len(row) > 1 else "",
                        phone=row[2] if len(row) > 2 else "",
                        whatsapp_link=row[3] if len(row) > 3 else "",
                        current_site=row[4] if len(row) > 4 else "",
                            place_id=row[5],
                            archived=legacy_archived,
                        )
                    )
                continue
            padded = row + [""] * (14 - len(row))
            if padded[9]:
                lead = Lead(
                        date=padded[0],
                        company_name=padded[1],
                        phone=padded[2],
                        whatsapp_link=padded[3],
                        current_site=padded[4],
                        site_platform=padded[5],
                        review_count=int(padded[6] or 0),
                        rating=float(str(padded[7] or 0).replace(",", ".")),
                        maps_link=padded[8],
                        place_id=padded[9],
                        sent=str(padded[10]).strip().lower() in {
                            "sim", "true", "1", "enviado"
                        },
                        sent_at=padded[11],
                        archived=str(padded[12]).strip().lower() in {
                            "sim", "true", "1", "arquivado"
                        },
                        cnpj=padded[13],
                    )
                contactable = bool(
                    lead.phone or (
                        lead.site_platform == "Instagram" and lead.current_site
                    )
                )
                if include_archived or (not lead.archived and contactable):
                    leads.append(lead)
        unique: dict[str, Lead] = {}
        for lead in leads:
            current = unique.get(lead.place_id)
            if current is None or (current.archived and not lead.archived):
                unique[lead.place_id] = lead
        return sorted(
            unique.values(),
            key=lambda lead: (-lead.review_count, -lead.rating, lead.company_name.casefold()),
        )

    def append_new(self, leads: list[Lead]) -> list[Lead]:
        existing = {lead.place_id for lead in self.list(include_archived=True)}
        fresh = [lead for lead in leads if lead.place_id not in existing]
        if not fresh:
            return []
        values = [
            [
                lead.date,
                lead.company_name,
                lead.phone,
                lead.whatsapp_link,
                lead.current_site,
                lead.site_platform,
                lead.review_count,
                lead.rating,
                lead.maps_link,
                lead.place_id,
                "Sim" if lead.sent else "Não",
                lead.sent_at,
                "Sim" if lead.archived else "NÃ£o",
                lead.cnpj,
            ]
            for lead in fresh
        ]
        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{self.sheet_name}'!A:N",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": values},
        ).execute()
        return fresh

    def mark_sent(self, place_id: str) -> Lead:
        self.ensure_sheet()
        rows = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{self.sheet_name}'!A2:N",
        ).execute().get("values", [])
        row_number = next(
            (
                index + 2
                for index, row in enumerate(rows)
                if (
                    (len(row) > 9 and row[9] == place_id)
                    or (
                        len(row) > 5
                        and (len(row) <= 9 or not row[9])
                        and row[5] == place_id
                    )
                )
            ),
            None,
        )
        if row_number is None:
            raise KeyError("Lead não encontrado na planilha.")

        lead = next(
            (item for item in self.list() if item.place_id == place_id),
            None,
        )
        if not lead:
            raise KeyError("Lead não encontrado.")

        sent_at = datetime.now(
            ZoneInfo("America/Sao_Paulo")
        ).strftime("%d/%m/%Y %H:%M")
        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{self.sheet_name}'!K{row_number}:L{row_number}",
            valueInputOption="RAW",
            body={"values": [["Sim", sent_at]]},
        ).execute()
        return lead.model_copy(update={"sent": True, "sent_at": sent_at})

    def archive(self, place_id: str) -> None:
        self.ensure_sheet()
        rows = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{self.sheet_name}'!A2:J",
        ).execute().get("values", [])
        row_number = next(
            (
                index + 2
                for index, row in enumerate(rows)
                if (
                    (len(row) > 9 and row[9] == place_id)
                    or (
                        len(row) > 5
                        and (len(row) <= 9 or not row[9])
                        and row[5] == place_id
                    )
                )
            ),
            None,
        )
        if row_number is None:
            raise KeyError("Lead não encontrado na planilha.")

        self.service.spreadsheets().values().update(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{self.sheet_name}'!M{row_number}",
            valueInputOption="RAW",
            body={"values": [["Sim"]]},
        ).execute()

    def archive_many(self, place_ids: list[str]) -> int:
        self.ensure_sheet()
        requested = set(dict.fromkeys(place_ids))
        rows = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{self.sheet_name}'!A2:J",
        ).execute().get("values", [])
        row_numbers = [
            index + 2
            for index, row in enumerate(rows)
            if (
                (len(row) > 9 and row[9] in requested)
                or (
                    len(row) > 5
                    and (len(row) <= 9 or not row[9])
                    and row[5] in requested
                )
            )
        ]
        if not row_numbers:
            return 0
        self.service.spreadsheets().values().batchUpdate(
            spreadsheetId=self.spreadsheet_id,
            body={
                "valueInputOption": "RAW",
                "data": [
                    {
                        "range": f"'{self.sheet_name}'!M{row_number}",
                        "values": [["Sim"]],
                    }
                    for row_number in row_numbers
                ],
            },
        ).execute()
        return len(row_numbers)

    def stats(self) -> dict[str, int]:
        leads = self.list(include_archived=True)
        today = today_brazil()
        return {
            "total": len(leads),
            "active": sum(not lead.archived for lead in leads),
            "sent": sum(lead.sent for lead in leads),
            "sent_today": sum(
                lead.sent and lead.sent_at.startswith(today) for lead in leads
            ),
            "archived": sum(lead.archived for lead in leads),
        }


def today_brazil() -> str:
    return datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y")
