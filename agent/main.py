import asyncio
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scraper import scrape_sponsored_businesses

load_dotenv(Path(__file__).with_name(".env"))

API_URL = os.getenv(
    "API_URL", "https://prospect-sites-api.onrender.com"
).rstrip("/")
AGENT_TOKEN = os.getenv("AGENT_TOKEN", "").strip()
POLL_SECONDS = max(2, int(os.getenv("POLL_SECONDS", "3")))


def headers() -> dict[str, str]:
    return {"X-Agent-Token": AGENT_TOKEN}


def fail_task(client: httpx.Client, job_id: str, detail: str) -> None:
    try:
        client.post(
            f"{API_URL}/api/agent/tasks/{job_id}/fail",
            headers=headers(),
            json={"detail": detail[:500]},
            timeout=30,
        )
    except httpx.HTTPError:
        pass


def main() -> None:
    if not AGENT_TOKEN:
        raise SystemExit(
            "Configure AGENT_TOKEN no arquivo agent/.env antes de iniciar."
        )

    print("Prospect Agent iniciado")
    print(f"Servidor: {API_URL}")
    print("Aguardando pesquisas. Mantenha esta janela aberta.")

    with httpx.Client(timeout=40) as client:
        while True:
            try:
                client.post(
                    f"{API_URL}/api/agent/heartbeat",
                    headers=headers(),
                ).raise_for_status()
                response = client.get(
                    f"{API_URL}/api/agent/tasks/next",
                    headers=headers(),
                )
                response.raise_for_status()
                task = response.json()
                job_id = task.get("id")
                query = task.get("query")

                if not job_id:
                    time.sleep(POLL_SECONDS)
                    continue

                print(f"Pesquisando: {query}")
                try:
                    report = asyncio.run(
                        scrape_sponsored_businesses(
                            query,
                            headless=False,
                            serpapi_api_key="",
                        )
                    )
                    payload = {
                        "businesses": [
                            {
                                "name": item.name,
                                "destination": item.destination,
                            }
                            for item in report.businesses
                        ],
                        "marker_count": report.marker_count,
                        "pages_explored": report.pages_explored,
                        "detail": report.blocked_reason,
                    }
                    for business in report.businesses:
                        destination = business.destination or "destino não exposto"
                        print(f"  - {business.name} | {destination}")
                    result = client.post(
                        f"{API_URL}/api/agent/tasks/{job_id}/complete",
                        headers=headers(),
                        json=payload,
                        timeout=120,
                    )
                    result.raise_for_status()
                    print(
                        f"Concluído: {len(report.businesses)} patrocinado(s)"
                    )
                except Exception as exc:
                    print(f"Falha na pesquisa: {exc}")
                    fail_task(client, job_id, str(exc))
            except httpx.HTTPStatusError as exc:
                print(
                    f"Servidor recusou a conexão: "
                    f"{exc.response.status_code}"
                )
                time.sleep(8)
            except httpx.HTTPError as exc:
                print(f"Servidor indisponível: {exc}")
                time.sleep(8)


if __name__ == "__main__":
    main()
