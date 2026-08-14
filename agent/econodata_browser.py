import json
from pathlib import Path

from playwright.sync_api import sync_playwright


SEARCH_URL = "https://www.econodata.com.br/consulta-empresa/"
AGENT_DIR = Path(__file__).resolve().parent
PROFILE_DIR = AGENT_DIR / "econodata-profile"
MAP_FILE = AGENT_DIR / "econodata-page-map.json"


def map_interactive_elements(page):
    return page.locator("input, button, a, [role='button'], [role='searchbox']").evaluate_all(
        """elements => elements.slice(0, 250).map((element, index) => ({
          index,
          tag: element.tagName.toLowerCase(),
          type: element.getAttribute('type') || '',
          role: element.getAttribute('role') || '',
          name: element.getAttribute('name') || '',
          placeholder: element.getAttribute('placeholder') || '',
          ariaLabel: element.getAttribute('aria-label') || '',
          text: (element.innerText || element.textContent || '').trim().slice(0, 160)
        })).filter(item => item.placeholder || item.ariaLabel || item.text || item.name)"""
    )


def main():
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        try:
            context = playwright.chromium.launch_persistent_context(
                str(PROFILE_DIR), channel="chrome", headless=False,
                viewport={"width": 1440, "height": 900},
            )
        except Exception:
            context = playwright.chromium.launch_persistent_context(
                str(PROFILE_DIR), headless=False,
                viewport={"width": 1440, "height": 900},
            )

        page = context.pages[0] if context.pages else context.new_page()
        page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=90_000)

        print("\nNavegador da Econodata aberto.")
        print("Faça o login manualmente e chegue até a tela com o campo de busca.")
        input("Quando o campo de busca estiver visível, volte aqui e pressione ENTER... ")

        page.wait_for_timeout(2_000)
        mapping = {
            "url": page.url,
            "title": page.title(),
            "elements": map_interactive_elements(page),
        }
        MAP_FILE.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nTela mapeada com sucesso em: {MAP_FILE}")
        print("Não feche o navegador até terminar. Avise no Codex que o mapeamento foi concluído.")
        input("Pressione ENTER somente quando quiser fechar o agente... ")
        context.close()


if __name__ == "__main__":
    main()
