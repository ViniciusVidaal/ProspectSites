from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Response

from backend import google_analysis_router as google_router
from backend.google_analysis_provider import SerpApiProvider, demo_payload, normalize_live_evidence
from backend.google_analysis_models import AnalysisJob, GoogleAnalysisRequest
from backend.google_analysis_router import local_competitors, neighborhood_from_address, resolve_competitive_query
from backend.google_analysis_scoring import RULES, score_profile
from backend.models import Lead


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


def test_demo_supplies_five_competitors_for_the_share_image():
    competitors = demo_report()["competition"]["competitors"]
    assert len(competitors) == 5
    assert all(item.get("address") for item in competitors)


def test_lead_api_exposes_saved_location_fields():
    lead = Lead(date="16/11/2026", company_name="Empresa", place_id="place-1", address="Rua A, 10", neighborhood="Asa Sul", city="Brasília", state="DF")
    payload = lead.model_dump()
    assert payload["address"] == "Rua A, 10"
    assert payload["neighborhood"] == "Asa Sul"
    assert payload["city"] == "Brasília"
    assert payload["state"] == "DF"


def test_competitive_query_replaces_frontend_placeholders_with_profile_data():
    request = GoogleAnalysisRequest(
        company={"name": "Posto da Torre", "category": "Categoria a confirmar", "address": "Localização a confirmar", "city": "Brasília", "state": "DF", "from_lead": True},
        keyword="Posto da Torre em Localização a confirmar",
        location="Localização a confirmar",
    )
    keyword, location, category, neighborhood = resolve_competitive_query(request, {
        "title": "Posto da Torre",
        "type": "Posto de combustível",
        "address": "s/n Asa Sul 05 F 10 - Asa Sul, Brasília - DF, 70300-300",
    })
    assert keyword == "Posto de combustível"
    assert location == "Asa Sul, Brasília, DF"
    assert category == "Posto de combustível"
    assert neighborhood == "Asa Sul"


def test_vicente_pires_scope_excludes_competitors_from_other_neighborhoods():
    address = "St. Hab. Vicente Pires loja 3 VICENTE PIRES - Vicente Pires, Brasília - DF, 72007-535"
    assert neighborhood_from_address(address) == "Vicente Pires"
    entries = [
        {"position": 1, "name": "JP do Gás Vicente Pires", "place_id": "own", "address": address},
        {"position": 2, "name": "Gás Local", "place_id": "local", "address": "Rua 10 - Vicente Pires, Brasília - DF"},
        {"position": 3, "name": "Gás Asa Sul", "place_id": "asa", "address": "CLS 210 - Asa Sul, Brasília - DF"},
        {"position": 4, "name": "Gás Ponte Alta", "place_id": "gama", "address": "Ponte Alta Norte (Gama), Brasília - DF"},
    ]
    filtered = local_competitors(entries, "Vicente Pires", {"own"}, "JP do Gás Vicente Pires")
    assert [item["name"] for item in filtered] == ["JP do Gás Vicente Pires", "Gás Local"]
    assert [item["position"] for item in filtered] == [1, 2]


def test_manual_company_search_uses_name_and_full_address():
    provider = SerpApiProvider("x" * 32)
    provider._get = AsyncMock(return_value={"local_results": []})
    asyncio.run(provider.search_companies(
        "JP do Gás Vicente Pires",
        "St. Hab. Vicente Pires loja 3 - Vicente Pires, Brasília - DF, 72007-535",
    ))
    params = provider._get.await_args.args[0]
    assert params["q"] == "JP do Gás Vicente Pires St. Hab. Vicente Pires loja 3 - Vicente Pires, Brasília - DF, 72007-535"


def test_completed_analysis_is_transient_and_consumed_once():
    google_router.jobs.clear()
    google_router.request_jobs.clear()
    google_router.transient_reports.clear()
    job_id = "transient-job"
    google_router.jobs[job_id] = AnalysisJob(id=job_id, status="pending")
    request = GoogleAnalysisRequest(
        company={"name": "Empresa Temporária", "address": "Brasília, DF", "place_id": "demo-profile"},
        keyword="empresa",
        location="Brasília, DF",
        demo=True,
    )

    asyncio.run(google_router.run_analysis(job_id, "request-key", request))
    report_id = google_router.jobs[job_id].report_id
    assert report_id in google_router.transient_reports

    response = Response()
    report = google_router.consume_report(report_id, response)
    assert report["company"]["name"] == "Empresa Temporária"
    assert report_id not in google_router.transient_reports
    assert job_id not in google_router.jobs
    assert response.headers["cache-control"] == "no-store"
    with pytest.raises(HTTPException) as exc:
        google_router.consume_report(report_id, Response())
    assert exc.value.status_code == 404
