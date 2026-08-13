import asyncio
import html
import ipaddress
import random
import re
import unicodedata
from urllib.parse import urlparse

import httpx

from .models import Lead

CNPJ_PATTERN = re.compile(r"(?<!\d)(\d{2}[.\s]?\d{3}[.\s]?\d{3}(?:[/\s]?\d{4})[-\s]?\d{2})(?!\d)")
GENERIC_NAME_WORDS = {"a", "as", "da", "das", "de", "do", "dos", "e", "em", "empresa", "grupo", "ltda", "me", "sa", "servicos", "comercio", "brasil"}


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9]+", " ", value)).strip().lower()


def normalize_cnpj(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def valid_cnpj(value: str) -> bool:
    digits = normalize_cnpj(value)
    if len(digits) != 14 or digits == digits[0] * 14:
        return False

    def digit(base: str, weights: list[int]) -> str:
        remainder = sum(int(number) * weight for number, weight in zip(base, weights)) % 11
        return str(0 if remainder < 2 else 11 - remainder)

    first = digit(digits[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    second = digit(digits[:12] + first, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return digits[-2:] == first + second


def _plain_html(fragment: str) -> str:
    fragment = re.sub(r"<script\b[^>]*>.*?</script>", " ", fragment, flags=re.I | re.S)
    fragment = re.sub(r"<style\b[^>]*>.*?</style>", " ", fragment, flags=re.I | re.S)
    return html.unescape(re.sub(r"<[^>]+>", " ", fragment))


def result_texts(page: str) -> list[str]:
    blocks = re.findall(r'<div[^>]+class="[^"]*result__body[^"]*"[^>]*>(.*?)(?=<div[^>]+class="[^"]*result(?:__body|--more)[^"]*"|</body>|$)', page, flags=re.I | re.S)
    return [re.sub(r"\s+", " ", _plain_html(block)).strip() for block in blocks]


def _name_tokens(name: str) -> set[str]:
    return {token for token in normalize_text(name).split() if len(token) >= 3 and token not in GENERIC_NAME_WORDS}


def find_matching_cnpj(page: str, lead: Lead) -> str:
    return find_matching_cnpj_texts(result_texts(page), lead)


def find_matching_cnpj_texts(texts: list[str], lead: Lead) -> str:
    wanted_name = normalize_text(lead.company_name)
    wanted_tokens = _name_tokens(lead.company_name)
    city = normalize_text(lead.city)
    state = normalize_text(lead.state)
    address_tokens = {token for token in normalize_text(lead.address).split() if len(token) >= 4}
    phone_digits = re.sub(r"\D", "", lead.phone)
    phone_tail = phone_digits[-8:] if len(phone_digits) >= 8 else ""
    best: tuple[float, str] | None = None

    for text in texts:
        for occurrence in CNPJ_PATTERN.finditer(text):
            context = text[max(0, occurrence.start() - 1400):occurrence.end() + 1400]
            normalized = normalize_text(context)
            text_tokens = set(normalized.split())
            overlap = len(wanted_tokens & text_tokens) / max(1, len(wanted_tokens))
            name_match = bool(wanted_name and wanted_name in normalized) or overlap >= 0.6
            city_match = bool(city and city in normalized)
            state_match = bool(state and re.search(rf"\b{re.escape(state)}\b", normalized))
            address_match = len(address_tokens & text_tokens) >= 2
            phone_match = bool(phone_tail and phone_tail in re.sub(r"\D", "", context))
            if not name_match or not (city_match or address_match or phone_match):
                continue
            score = overlap * 4 + city_match * 4 + state_match * 2 + address_match * 2 + phone_match * 3
            candidate = normalize_cnpj(occurrence.group(1))
            if valid_cnpj(candidate) and (best is None or score > best[0]):
                best = (score, candidate)
    return best[1] if best else ""


async def lookup_cnpj_serpapi(client: httpx.AsyncClient, lead: Lead, api_key: str) -> str:
    location = " ".join(part for part in (lead.city, lead.state) if part).strip()
    phone_digits = re.sub(r"\D", "", lead.phone)
    national_phone = phone_digits[2:] if phone_digits.startswith("55") and len(phone_digits) > 11 else phone_digits
    subscriber = national_phone[2:] if len(national_phone) in {10, 11} else national_phone[-9:]
    phone = f"{subscriber[:-4]}-{subscriber[-4:]}" if len(subscriber) >= 8 else subscriber
    query = f'"{lead.company_name}" {location} CNPJ'
    if phone:
        query = f'"{lead.company_name}" "{phone}" {location} CNPJ'
    response = await client.get(
        "https://serpapi.com/search.json",
        params={
            "engine": "google",
            "q": query,
            "google_domain": "google.com.br",
            "gl": "br",
            "hl": "pt-br",
            "num": 10,
            "api_key": api_key,
        },
    )
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        raise RuntimeError(f"SerpApi: {data['error']}")
    texts = []
    organic_results = data.get("organic_results", [])
    for result in organic_results:
        rich = result.get("rich_snippet", {})
        texts.append(" ".join(str(value) for value in (
            result.get("title", ""), result.get("snippet", ""),
            result.get("link", ""), rich,
        )))
    match = find_matching_cnpj_texts(texts, lead)
    if match:
        return match

    for result in organic_results[:4]:
        url = result.get("link", "")
        if not _safe_public_url(url):
            continue
        try:
            async with client.stream("GET", url) as page_response:
                page_response.raise_for_status()
                content_type = page_response.headers.get("content-type", "").lower()
                if "text/html" not in content_type and "text/plain" not in content_type:
                    continue
                chunks = []
                size = 0
                async for chunk in page_response.aiter_bytes():
                    size += len(chunk)
                    if size > 2_000_000:
                        break
                    chunks.append(chunk)
            page_text = _plain_html(b"".join(chunks).decode("utf-8", errors="ignore"))
            match = find_matching_cnpj_texts([page_text], lead)
            if match:
                return match
        except httpx.HTTPError:
            continue
    return ""


def _safe_public_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        if parsed.hostname.lower() in {"localhost", "localhost.localdomain"}:
            return False
        try:
            address = ipaddress.ip_address(parsed.hostname)
            return not (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved)
        except ValueError:
            return True
    except ValueError:
        return False


async def lookup_cnpj(client: httpx.AsyncClient, lead: Lead, max_queries: int | None = None) -> str:
    location = " ".join(part for part in (lead.city, lead.state) if part).strip()
    queries = [f'"{lead.company_name}" {location} CNPJ']
    if lead.address and normalize_text(lead.address) != normalize_text(location):
        queries.append(f'"{lead.company_name}" "{lead.address}" CNPJ')
    for query in queries[:max_queries]:
        try:
            response = await client.get("https://html.duckduckgo.com/html/", params={"q": query, "kl": "br-pt"})
            response.raise_for_status()
            match = find_matching_cnpj(response.text, lead)
            if match:
                return match
        except httpx.HTTPError:
            return ""
    return ""


async def enrich_leads_with_cnpj(
    leads: list[Lead], concurrency: int = 2, delay_range: tuple[float, float] = (0.35, 0.9),
    max_queries: int | None = None,
    serpapi_api_key: str = "",
) -> int:
    semaphore = asyncio.Semaphore(max(1, concurrency))
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Accept-Language": "pt-BR,pt;q=0.9"}
    async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True) as client:
        async def enrich(lead: Lead) -> bool:
            async with semaphore:
                await asyncio.sleep(random.uniform(*delay_range))
                try:
                    if serpapi_api_key:
                        cnpj = await lookup_cnpj_serpapi(client, lead, serpapi_api_key)
                    else:
                        cnpj = await lookup_cnpj(client, lead, max_queries=max_queries)
                except (httpx.HTTPError, RuntimeError, ValueError):
                    cnpj = ""
                lead.cnpj = cnpj
                lead.cnpj_captured = bool(cnpj)
                return bool(cnpj)

        return sum(await asyncio.gather(*(enrich(lead) for lead in leads)))
