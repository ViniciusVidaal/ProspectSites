from functools import lru_cache
import json
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


class Settings(BaseModel):
    places_api_key: str
    serpapi_api_key: str = ""
    spreadsheet_id: str
    service_account_file: Path | None = None
    service_account_info: dict | None = None
    sheet_name: str
    frontend_origins: list[str]
    headless: bool
    whatsapp_profile_dir: Path


@lru_cache
def get_settings() -> Settings:
    import os

    required = {
        "GOOGLE_PLACES_API_KEY": os.getenv("GOOGLE_PLACES_API_KEY"),
        "GOOGLE_SPREADSHEET_ID": os.getenv("GOOGLE_SPREADSHEET_ID"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"Variáveis ausentes: {', '.join(missing)}")

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
    else:
        raise RuntimeError(
            "Configure GOOGLE_SERVICE_ACCOUNT_JSON ou GOOGLE_SERVICE_ACCOUNT_FILE."
        )

    return Settings(
        places_api_key=required["GOOGLE_PLACES_API_KEY"],
        serpapi_api_key=os.getenv("SERPAPI_API_KEY", ""),
        spreadsheet_id=required["GOOGLE_SPREADSHEET_ID"],
        service_account_file=service_file,
        service_account_info=service_info,
        sheet_name=os.getenv("GOOGLE_SHEET_NAME", "Leads"),
        frontend_origins=[
            item.strip()
            for item in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",")
            if item.strip()
        ],
        headless=os.getenv("HEADLESS", "false").lower() == "true",
        whatsapp_profile_dir=Path(
            os.getenv("WHATSAPP_PROFILE_DIR", "./whatsapp-profile")
        ).resolve(),
    )
