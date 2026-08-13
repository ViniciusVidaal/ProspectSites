from dataclasses import dataclass, field
import re
from urllib.parse import urlparse

import httpx

from .models import Lead
from .sheets import today_brazil

PLATFORM_HOSTS = {
    "instagram.com": "Instagram",
    "facebook.com": "Facebook",
    "fb.com": "Facebook",
    "linkedin.com": "LinkedIn",
    "linktr.ee": "Linktree",
    "wa.me": "WhatsApp",
    "whatsapp.com": "WhatsApp",
    "api.whatsapp.com": "WhatsApp",
    "tiktok.com": "TikTok",
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "twitter.com": "X / Twitter",
    "x.com": "X / Twitter",
    "beacons.ai": "Beacons",
    "bio.site": "Bio Site",
    "taplink.cc": "Taplink",
    "campsite.bio": "Campsite",
    "solo.to": "Solo.to",
    "sites.google.com": "Google Sites",
    "business.site": "Google Business Site",
    "canva.site": "Canva Site",
    "wixsite.com": "Wix gratuito",
}


@dataclass
class PlacesSearchReport:
    scanned: int = 0
    eligible: list[Lead] = field(default_factory=list)
    pages: int = 0


def platform_from_url(url: str) -> str:
    if not url:
        return ""
    host = urlparse(url if "://" in url else f"https://{url}").netloc.lower()
    host = host.removeprefix("www.")
    for domain, label in PLATFORM_HOSTS.items():
        if host == domain or host.endswith(f".{domain}"):
            return label
    return ""


def whatsapp_url(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return ""
    if len(digits) in (10, 11):
        digits = f"55{digits}"
    return f"https://wa.me/{digits}"


async def search_eligible_profiles(
    api_key: str,
    query: str,
    minimum_reviews: int = 50,
    max_pages: int = 3,
) -> PlacesSearchReport:
    report = PlacesSearchReport()
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.nationalPhoneNumber,"
            "places.internationalPhoneNumber,places.websiteUri,"
            "places.userRatingCount,places.rating,places.googleMapsUri,"
            "places.businessStatus,places.formattedAddress,"
            "places.addressComponents,nextPageToken"
        ),
    }
    base_payload = {
        "textQuery": query,
        "languageCode": "pt-BR",
        "regionCode": "BR",
        "rankPreference": "RELEVANCE",
        "pageSize": 20,
        "includePureServiceAreaBusinesses": True,
    }
    page_token = ""
    seen: set[str] = set()

    async with httpx.AsyncClient(timeout=30) as client:
        for _ in range(max_pages):
            payload = dict(base_payload)
            if page_token:
                payload["pageToken"] = page_token

            response = await client.post(
                "https://places.googleapis.com/v1/places:searchText",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            report.pages += 1

            for place in data.get("places", []):
                place_id = place.get("id", "")
                if not place_id or place_id in seen:
                    continue
                seen.add(place_id)
                report.scanned += 1

                reviews = int(place.get("userRatingCount", 0) or 0)
                website = place.get("websiteUri", "")
                platform = platform_from_url(website)
                if reviews <= minimum_reviews:
                    continue
                if website and not platform:
                    continue
                if place.get("businessStatus") == "CLOSED_PERMANENTLY":
                    continue

                phone = (
                    place.get("internationalPhoneNumber")
                    or place.get("nationalPhoneNumber")
                    or ""
                )
                components = place.get("addressComponents", [])
                city = next((item.get("longText", "") for item in components if set(item.get("types", [])) & {"locality", "administrative_area_level_2"}), "")
                state = next((item.get("shortText") or item.get("longText", "") for item in components if "administrative_area_level_1" in item.get("types", [])), "")
                if not phone and platform != "Instagram":
                    continue
                report.eligible.append(
                    Lead(
                        date=today_brazil(),
                        company_name=place.get("displayName", {}).get(
                            "text", "Empresa sem nome"
                        ),
                        phone=phone,
                        whatsapp_link=whatsapp_url(phone),
                        current_site=website,
                        site_platform=platform or "Sem site",
                        review_count=reviews,
                        rating=float(place.get("rating", 0) or 0),
                        maps_link=place.get("googleMapsUri", ""),
                        place_id=place_id,
                        address=place.get("formattedAddress", ""),
                        city=city,
                        state=state,
                    )
                )

            page_token = data.get("nextPageToken", "")
            if not page_token:
                break

    report.eligible.sort(
        key=lambda lead: (-lead.review_count, -lead.rating, lead.company_name.casefold())
    )
    return report
