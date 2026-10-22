from datetime import datetime
from zoneinfo import ZoneInfo


def today_brazil() -> str:
    return datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y")
