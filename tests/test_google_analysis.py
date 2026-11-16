from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from backend.google_analysis_pdf import build_report_pdf
from backend.google_analysis_provider import demo_payload, normalize_live_evidence
from backend.google_analysis_scoring import RULES, score_profile


def demo_report():
    company = {
        "name": "Empresa Demonstração",
        "category": "Agência de marketing digital",
        "address": "Brasília, DF",
        "rating": 4.8,
        "review_count": 38,
        "place_id": "demo-profile-001",
    }
    data = demo_payload(company, "agência de marketing digital em Brasília", "Brasília, DF", 20)
    return {
        "id": "demo-report",
        "demo": True,
        "collected_at": "2026-11-16T12:00:00-03:00",
        "company": data["profile"],
        "competition": data["competition"],
        "limitations": data["limitations"],
        **score_profile(data["evidence"]),
    }


def test_weights_sum_to_100():
    assert len(RULES) == 16
    assert sum(rule.weight for rule in RULES) == 100


def test_score_is_deterministic_and_fully_covered_for_demo():
    first = demo_report()
    second = demo_report()
    assert first["score"] == second["score"]
    assert first["coverage"] == 100
    assert first["score_reliable"] is True
    assert len(first["checklist"]) == 16
    assert len(first["priorities"]) <= 3


def test_unknown_items_do_not_receive_zero():
    result = score_profile({"primary_category": {"state": "good", "evidence": "Confirmada"}})
    assert result["score"] == 100
    assert result["coverage"] == 8
    assert result["score_reliable"] is False
    unknown = next(item for item in result["checklist"] if item["key"] == "phone")
    assert unknown["points"] is None


def test_missing_serpapi_fields_stay_unknown():
    evidence = normalize_live_evidence({"title": "Perfil parcial"})
    assert evidence["products_services"]["state"] == "unknown"
    assert evidence["verification"]["state"] == "unknown"
    assert evidence["photos"]["state"] == "unknown"
    assert evidence["review_recency"]["state"] == "unknown"


def test_pdf_is_downloadable_and_contains_selectable_text():
    pdf = build_report_pdf(demo_report())
    assert pdf.startswith(b"%PDF")
    reader = PdfReader(BytesIO(pdf))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "ProspectSites" in text
    assert "Empresa Demonstra" in text
    assert "DOCUMENTO DE DEMONSTRA" in text
