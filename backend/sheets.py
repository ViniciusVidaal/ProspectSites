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

        header_range = f"'{self.sheet_name}'!A1:L1"
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

    def list(self) -> list[Lead]:
        self.ensure_sheet()
        rows = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{self.sheet_name}'!A2:L",
        ).execute().get("values", [])
        leads = []
        for row in rows:
            if len(row) <= 6 and len(row) > 5 and row[5]:
                leads.append(
                    Lead(
                        date=row[0] if len(row) > 0 else "",
                        company_name=row[1] if len(row) > 1 else "",
                        phone=row[2] if len(row) > 2 else "",
                        whatsapp_link=row[3] if len(row) > 3 else "",
                        current_site=row[4] if len(row) > 4 else "",
                        place_id=row[5],
                    )
                )
                continue
            padded = row + [""] * (12 - len(row))
            if padded[9]:
                leads.append(
                    Lead(
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
                    )
                )
        return leads

    def append_new(self, leads: list[Lead]) -> list[Lead]:
        existing = {lead.place_id for lead in self.list()}
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
            ]
            for lead in fresh
        ]
        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{self.sheet_name}'!A:L",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": values},
        ).execute()
        return fresh

    def mark_sent(self, place_id: str) -> Lead:
        leads = self.list()
        lead = next((item for item in leads if item.place_id == place_id), None)
        if not lead:
            raise KeyError("Lead não encontrado.")

        values = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{self.sheet_name}'!J2:J",
        ).execute().get("values", [])
        row_number = next(
            (
                index + 2
                for index, row in enumerate(values)
                if row and row[0] == place_id
            ),
            None,
        )
        if row_number is None:
            raise KeyError("Lead não encontrado na planilha.")

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


def today_brazil() -> str:
    return datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y")
