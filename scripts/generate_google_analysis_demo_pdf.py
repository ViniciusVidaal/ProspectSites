from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.google_analysis_pdf import build_report_pdf
from backend.google_analysis_provider import demo_payload
from backend.google_analysis_scoring import score_profile


def main() -> None:
    company = {
        "name": "Empresa Demonstração ProspectSites",
        "category": "Agência de marketing digital",
        "address": "Brasília, DF",
        "rating": 4.8,
        "review_count": 38,
        "place_id": "demo-profile-001",
    }
    data = demo_payload(company, "agência de marketing digital em Brasília", "Brasília, DF", 20)
    report = {
        "id": "demo-report",
        "demo": True,
        "collected_at": "2026-11-16T12:00:00-03:00",
        "company": data["profile"],
        "competition": data["competition"],
        "limitations": data["limitations"],
        **score_profile(data["evidence"]),
    }
    destination = PROJECT_ROOT / "output/pdf/analise-google-prospectsites-demonstracao.pdf"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(build_report_pdf(report))
    print(destination.resolve())


if __name__ == "__main__":
    main()
