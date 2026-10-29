from __future__ import annotations

import base64
from email.message import EmailMessage

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from .config import Settings
from .models import Lead


GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


def personalize(value: str, lead: Lead) -> str:
    replacements = {
        "[empresa]": lead.company_name,
        "[avaliações]": f"{lead.review_count:,}".replace(",", "."),
        "[nota]": f"{lead.rating:.1f}".replace(".", ","),
    }
    result = value
    for placeholder, replacement in replacements.items():
        result = result.replace(placeholder, replacement).replace(placeholder.upper(), replacement)
        result = result.replace(placeholder.capitalize(), replacement)
    return result


def gmail_service(settings: Settings):
    required = {
        "GMAIL_CLIENT_ID": settings.gmail_client_id,
        "GMAIL_CLIENT_SECRET": settings.gmail_client_secret,
        "GMAIL_REFRESH_TOKEN": settings.gmail_refresh_token,
        "GMAIL_SENDER_EMAIL": settings.gmail_sender_email,
    }
    missing = [name for name, value in required.items() if not (value or "").strip()]
    if missing:
        raise RuntimeError(f"Variáveis do Gmail ausentes: {', '.join(missing)}")
    credentials = Credentials(
        token=None,
        refresh_token=settings.gmail_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.gmail_client_id,
        client_secret=settings.gmail_client_secret,
        scopes=[GMAIL_SEND_SCOPE],
    )
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def send_lead_email(service, settings: Settings, lead: Lead, subject: str, body: str) -> str:
    if not lead.registry_email:
        raise ValueError("Lead sem e-mail cadastral.")
    message = EmailMessage()
    message["To"] = lead.registry_email
    message["From"] = f"{settings.gmail_sender_name} <{settings.gmail_sender_email}>"
    message["Subject"] = personalize(subject, lead).replace("\r", " ").replace("\n", " ")
    message.set_content(personalize(body, lead))
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    response = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return str(response.get("id", ""))
