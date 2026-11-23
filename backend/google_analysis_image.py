"""Render the same canvas used by the Google Analysis frontend."""
from __future__ import annotations

import base64
import os
from pathlib import Path
import re

from playwright.sync_api import sync_playwright

_ASSETS = Path(__file__).resolve().parent.parent / "frontend" / "src" / "google-analysis"


def render_analysis_png(report: dict) -> bytes:
    source = (_ASSETS / "reportImage.js").read_text(encoding="utf-8")
    source = re.sub(r"\bexport\s+(?=(?:async\s+)?function\b)", "", source)
    font = base64.b64encode((_ASSETS / "fonts" / "Inter-Variable.ttf").read_bytes()).decode("ascii")
    html = f'<style>@font-face{{font-family:ProspectReport;src:url(data:font/ttf;base64,{font}) format("truetype");font-weight:100 900}}</style>'
    with sync_playwright() as playwright:
        options = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        if os.environ.get("REPORT_CHROMIUM_PATH"):
            options["executable_path"] = os.environ["REPORT_CHROMIUM_PATH"]
        browser = playwright.chromium.launch(**options)
        try:
            page = browser.new_page()
            page.set_default_timeout(30000)
            page.route("**/*", lambda route: route.abort())
            page.set_content(html)
            page.add_script_tag(content=source)
            data_url = page.evaluate("""async report => {
                await Promise.all([500, 600, 700, 800, 900].map(weight => document.fonts.load(`${weight} 20px ProspectReport`)));
                return buildGoogleAnalysisImage(report).toDataURL('image/png');
            }""", report)
            return base64.b64decode(data_url.split(",", 1)[1], validate=True)
        finally:
            browser.close()
