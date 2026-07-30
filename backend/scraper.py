from dataclasses import dataclass
from urllib.parse import quote_plus

from playwright.async_api import async_playwright


@dataclass
class SponsoredBusiness:
    name: str
    destination: str


async def scrape_sponsored_businesses(
    search_term: str, headless: bool
) -> list[SponsoredBusiness]:
    query = quote_plus(search_term)
    results: list[SponsoredBusiness] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=headless)
        page = await browser.new_page(
            locale="pt-BR",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/131 Safari/537.36"
            ),
        )
        await page.goto(
            f"https://www.google.com/search?q={query}&hl=pt-BR",
            wait_until="domcontentloaded",
            timeout=45000,
        )
        await page.wait_for_timeout(2500)

        # Os marcadores e a árvore do Google mudam com frequência. Limitamos a
        # coleta aos blocos que contêm explicitamente "Patrocinado".
        sponsored = page.locator(
            "div:has-text('Patrocinado'), div:has-text('Sponsored')"
        )
        count = min(await sponsored.count(), 30)
        seen: set[tuple[str, str]] = set()
        for index in range(count):
            block = sponsored.nth(index)
            text = (await block.inner_text()).strip()
            if len(text) > 1500:
                continue
            anchors = block.locator("a[href]")
            for link_index in range(min(await anchors.count(), 10)):
                anchor = anchors.nth(link_index)
                href = await anchor.get_attribute("href") or ""
                label = (await anchor.inner_text()).strip()
                if not href.startswith("http") or not label:
                    continue
                if "google." in href or "gstatic." in href:
                    continue
                name = label.splitlines()[0].strip()
                item = (name, href)
                if item not in seen:
                    seen.add(item)
                    results.append(SponsoredBusiness(name=name, destination=href))
        await browser.close()
    return results
