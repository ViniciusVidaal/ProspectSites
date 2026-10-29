from functools import lru_cache
import json
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()
load_dotenv(".env.local", override=False)


class Settings(BaseModel):
    places_api_key: str
    firebase_service_account_info: dict
    settings_admin_password: str | None = None
    spreadsheet_id: str | None = None
    service_account_file: Path | None = None
    service_account_info: dict | None = None
    sheet_name: str
    frontend_origins: list[str]
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    gmail_client_id: str | None = None
    gmail_client_secret: str | None = None
    gmail_refresh_token: str | None = None
    gmail_sender_email: str | None = None
    gmail_sender_name: str = "Prospect Sites"


@lru_cache
def get_settings() -> Settings:
    import os

    required = {
        "GOOGLE_PLACES_API_KEY": os.getenv("GOOGLE_PLACES_API_KEY"),
        "FIREBASE_SERVICE_ACCOUNT_JSON": os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"Variáveis ausentes: {', '.join(missing)}")

    firebase_json = required["FIREBASE_SERVICE_ACCOUNT_JSON"]
    try:
        firebase_service_account_info = json.loads(firebase_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON contém JSON inválido.") from exc
    if not firebase_service_account_info.get("private_key") or not firebase_service_account_info.get("client_email"):
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON está incompleto.")

    service_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    service_file_value = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    service_info = None
    service_file = None

    if service_json:
        try:
            service_info = json.loads(service_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON contém JSON inválido.") from exc
        if not service_info.get("private_key") or not service_info.get("client_email"):
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON está incompleto.")
    elif service_file_value:
        service_file = Path(service_file_value).expanduser().resolve()
        if not service_file.is_file():
            raise RuntimeError("Arquivo da conta de serviço não encontrado.")
    return Settings(
        places_api_key=required["GOOGLE_PLACES_API_KEY"],
        firebase_service_account_info=firebase_service_account_info,
        settings_admin_password=os.getenv("SETTINGS_ADMIN_PASSWORD"),
        spreadsheet_id=os.getenv("GOOGLE_SPREADSHEET_ID"),
        service_account_file=service_file,
        service_account_info=service_info,
        sheet_name=os.getenv("GOOGLE_SHEET_NAME", "Leads"),
        frontend_origins=[
            item.strip()
            for item in os.getenv(
                "FRONTEND_ORIGINS", "http://localhost:5173"
            ).split(",")
            if item.strip()
        ],
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        gmail_client_id=os.getenv("GMAIL_CLIENT_ID"),
        gmail_client_secret=os.getenv("GMAIL_CLIENT_SECRET"),
        gmail_refresh_token=os.getenv("GMAIL_REFRESH_TOKEN"),
        gmail_sender_email=os.getenv("GMAIL_SENDER_EMAIL"),
        gmail_sender_name=os.getenv("GMAIL_SENDER_NAME", "Prospect Sites"),
    )
