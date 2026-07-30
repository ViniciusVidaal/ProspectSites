import re
from urllib.parse import urlparse

import httpx

from .models import Lead
from .sheets import today_brazil

SOCIAL_HOSTS = {
    "wa.me",
    "api.whatsapp.com",
    "whatsapp.com",
    "instagram.com",
    "facebook.com",
    "fb.com",
    "linktr.ee",
    "beacons.ai",
    "bio.site",
    "taplink.cc",
}


def is_qualifying_url(url: str) -> bool:
    if not url:
        return True
    host = urlparse(url if "://" in url else f"https://{url}").netloc.lower()
    host = host.removeprefix("www.")
    return any(host == item or host.endswith(f".{item}") for item in SOCIAL_HOSTS)


def whatsapp_url(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return ""
    if len(digits) in (10, 11):
        digits = f"55{digits}"
    return f"https://wa.me/{digits}"


async def enrich_company(api_key: str, company: str, city: str) -> Lead | None:
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.nationalPhoneNumber,places.websiteUri"
        ),
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://places.googleapis.com/v1/places:searchText",
            headers=headers,
            json={"textQuery": f"{company}, {city}", "languageCode": "pt-BR"},
        )
        response.raise_for_status()
    places = response.json().get("places", [])
    if not places:
        return None
    place = places[0]
    site = place.get("websiteUri", "")
    if site and not is_qualifying_url(site):
        return None
    phone = place.get("nationalPhoneNumber", "")
    return Lead(
        date=today_brazil(),
        company_name=place.get("displayName", {}).get("text", company),
        phone=phone,
        whatsapp_link=whatsapp_url(phone),
        current_site=site,
        place_id=place["id"],
    )

