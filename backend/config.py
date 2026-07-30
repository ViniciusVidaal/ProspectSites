from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


class Settings(BaseModel):
    places_api_key: str
    spreadsheet_id: str
    service_account_file: Path
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
        "GOOGLE_SERVICE_ACCOUNT_FILE": os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"Variáveis ausentes: {', '.join(missing)}")

    service_file = Path(required["GOOGLE_SERVICE_ACCOUNT_FILE"]).expanduser().resolve()
    if not service_file.is_file():
        raise RuntimeError("Arquivo da conta de serviço não encontrado.")

    return Settings(
        places_api_key=required["GOOGLE_PLACES_API_KEY"],
        spreadsheet_id=required["GOOGLE_SPREADSHEET_ID"],
        service_account_file=service_file,
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

