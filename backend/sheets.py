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
    "Place ID",
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

        header_range = f"'{self.sheet_name}'!A1:F1"
        current = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id, range=header_range
        ).execute().get("values", [])
        if not current:
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
            range=f"'{self.sheet_name}'!A2:F",
        ).execute().get("values", [])
        leads = []
        for row in rows:
            padded = row + [""] * (6 - len(row))
            if padded[5]:
                leads.append(
                    Lead(
                        date=padded[0],
                        company_name=padded[1],
                        phone=padded[2],
                        whatsapp_link=padded[3],
                        current_site=padded[4],
                        place_id=padded[5],
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
                lead.place_id,
            ]
            for lead in fresh
        ]
        self.service.spreadsheets().values().append(
            spreadsheetId=self.spreadsheet_id,
            range=f"'{self.sheet_name}'!A:F",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": values},
        ).execute()
        return fresh


def today_brazil() -> str:
    return datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y")
