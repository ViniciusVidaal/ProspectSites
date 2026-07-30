import logging
from dataclasses import dataclass, field
from urllib.parse import quote_plus, urlparse

from playwright.async_api import Page, async_playwright

logger = logging.getLogger(__name__)

SPONSORED_LABELS = {
    "patrocinado",
    "sponsored",
    "anúncio",
    "anuncio",
    "ad",
}

IGNORED_NAMES = {
    "patrocinado",
    "sponsored",
    "anúncio",
    "anuncio",
    "ad",
    "site",
    "website",
    "ligar",
    "call",
    "rotas",
    "directions",
    "mais",
    "more",
}


@dataclass
class SponsoredBusiness:
    name: str
    destination: str = ""


@dataclass
class ScrapeReport:
    businesses: list[SponsoredBusiness] = field(default_factory=list)
    marker_count: int = 0
    page_title: str = ""
    final_url: str = ""
    blocked_reason: str = ""


def _is_google_tracking_url(url: str) -> bool:
    if not url:
        return False
    host = urlparse(url).netloc.lower()
    return (
        "googleadservices." in host
        or "google." in host
        or "gstatic." in host
    )


async def _accept_consent(page: Page) -> None:
    selectors = [
        "button:has-text('Aceitar tudo')",
        "button:has-text('Accept all')",
        "button:has-text('Concordo')",
        "button:has-text('I agree')",
    ]
    for selector in selectors:
        button = page.locator(selector).first
        if await button.count() and await button.is_visible():
            await button.click()
            await page.wait_for_timeout(1200)
            return


async def _extract_candidates(page: Page) -> tuple[list[dict], int]:
    return await page.evaluate(
        """
        (labels) => {
          const normalized = (value) =>
            (value || "").replace(/\\s+/g, " ").trim();
          const labelSet = new Set(labels);
          const all = Array.from(document.querySelectorAll("body *"));
          const markers = all.filter((element) => {
            const text = normalized(element.textContent).toLocaleLowerCase("pt-BR");
            return labelSet.has(text) && element.children.length <= 3;
          });

          const containers = [];
          const seenContainers = new Set();

          for (const marker of markers) {
            let current = marker;
            let selected = null;

            for (let depth = 0; current && depth < 9; depth += 1) {
              const text = normalized(current.innerText);
              const anchors = current.querySelectorAll("a[href]");
              const headings = current.querySelectorAll(
                "h3, [role='heading'], [aria-level]"
              );

              if (
                anchors.length > 0 &&
                (headings.length > 0 || text.length >= 20) &&
                text.length <= 1800
              ) {
                selected = current;
              }

              if (selected && text.length >= 70) break;
              current = current.parentElement;
            }

            if (selected && !seenContainers.has(selected)) {
              seenContainers.add(selected);
              containers.push(selected);
            }
          }

          const candidates = [];
          for (const container of containers) {
            const headings = Array.from(
              container.querySelectorAll("h3, [role='heading'], [aria-level]")
            )
              .map((element) => normalized(element.innerText))
              .filter(Boolean);

            const anchors = Array.from(container.querySelectorAll("a[href]"))
              .map((anchor) => ({
                href: anchor.href || "",
                text: normalized(
                  anchor.innerText ||
                  anchor.getAttribute("aria-label") ||
                  anchor.getAttribute("title")
                ),
              }))
              .filter((anchor) => anchor.text);

            candidates.push({
              headings,
              anchors,
              text: normalized(container.innerText),
            });
          }

          return [candidates, markers.length];
        }
        """,
        list(SPONSORED_LABELS),
    )


def _business_from_candidate(candidate: dict) -> SponsoredBusiness | None:
    names = candidate.get("headings", [])
    anchors = candidate.get("anchors", [])

    if not names:
        names = [
            anchor.get("text", "").splitlines()[0].strip()
            for anchor in anchors
        ]

    name = next(
        (
            item.strip()
            for item in names
            if item.strip()
            and item.strip().lower() not in IGNORED_NAMES
            and 2 <= len(item.strip()) <= 140
        ),
        "",
    )
    if not name:
        return None

    destination = next(
        (
            anchor.get("href", "")
            for anchor in anchors
            if anchor.get("href", "").startswith("http")
            and not _is_google_tracking_url(anchor.get("href", ""))
        ),
        "",
    )
    return SponsoredBusiness(name=name, destination=destination)


async def scrape_sponsored_businesses(
    search_term: str, headless: bool
) -> ScrapeReport:
    query = quote_plus(search_term)
    report = ScrapeReport()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=headless,
            args=[
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        page = await browser.new_page(
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1440, "height": 1200},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            extra_http_headers={"Accept-Language": "pt-BR,pt;q=0.9"},
        )

        await page.goto(
            f"https://www.google.com/search?q={query}&hl=pt-BR&gl=br&pws=0",
            wait_until="domcontentloaded",
            timeout=45000,
        )
        await _accept_consent(page)
        await page.wait_for_timeout(3500)

        report.page_title = await page.title()
        report.final_url = page.url
        body_text = (await page.locator("body").inner_text()).lower()

        if "detected unusual traffic" in body_text or "tráfego incomum" in body_text:
            report.blocked_reason = "Google bloqueou o IP do Render por tráfego incomum"
        elif "não sou um robô" in body_text or "i'm not a robot" in body_text:
            report.blocked_reason = "Google apresentou CAPTCHA"
        elif "before you continue to google" in body_text:
            report.blocked_reason = "Tela de consentimento do Google não foi liberada"

        raw_candidates, report.marker_count = await _extract_candidates(page)
        seen: set[str] = set()

        for candidate in raw_candidates:
            business = _business_from_candidate(candidate)
            if not business:
                continue
            key = business.name.casefold()
            if key in seen:
                continue
            seen.add(key)
            report.businesses.append(business)

        logger.info(
            "Google scrape query=%r title=%r url=%r markers=%s businesses=%s blocked=%r",
            search_term,
            report.page_title,
            report.final_url,
            report.marker_count,
            len(report.businesses),
            report.blocked_reason,
        )
        await browser.close()

    return report
