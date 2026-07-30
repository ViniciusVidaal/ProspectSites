import asyncio
from collections.abc import Callable
from urllib.parse import quote

from playwright.async_api import async_playwright

from .models import Lead


async def send_messages(
    leads: list[Lead],
    message: str,
    delay_seconds: int,
    profile_dir: str,
    on_progress: Callable[[int, int, str], None],
) -> None:
    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            profile_dir,
            headless=False,
            viewport={"width": 1280, "height": 820},
        )
        page = context.pages[0] if context.pages else await context.new_page()
        total = len(leads)
        for index, lead in enumerate(leads, start=1):
            if not lead.whatsapp_link:
                on_progress(index, total, f"{lead.company_name}: sem telefone")
                continue
            phone = lead.whatsapp_link.rstrip("/").split("/")[-1]
            url = f"https://web.whatsapp.com/send?phone={phone}&text={quote(message)}"
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:
                send = page.locator("button[aria-label='Enviar'], button[aria-label='Send']")
                await send.wait_for(state="visible", timeout=120000)
                await send.click()
                on_progress(index, total, f"Enviado para {lead.company_name}")
            except Exception:
                on_progress(index, total, f"Falha ao abrir {lead.company_name}")
            if index < total:
                await asyncio.sleep(delay_seconds)
        await context.close()

