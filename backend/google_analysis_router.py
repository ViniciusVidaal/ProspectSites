from __future__ import annotations

import asyncio
from datetime import datetime
from statistics import median
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from .config import get_settings
from .google_analysis_models import AnalysisJob, GoogleAnalysisLinkRequest, GoogleAnalysisRequest, GoogleCompanySearchRequest
from .google_analysis_provider import SerpApiProvider, ProviderError, ProviderNotConfigured, demo_payload, demo_search, normalize_live_evidence
from .google_analysis_repository import GoogleAnalysisRepository
from .google_analysis_scoring import methodology_payload, score_profile


router = APIRouter(prefix="/api/google-analysis", tags=["Análise Google"])
jobs: dict[str, AnalysisJob] = {}
request_jobs: dict[str, str] = {}
job_lock = asyncio.Lock()


def repository() -> GoogleAnalysisRepository:
    return GoogleAnalysisRepository(get_settings())


def provider() -> SerpApiProvider:
    settings = get_settings()
    return SerpApiProvider(settings.serpapi_api_key, settings.serpapi_timeout_seconds)


def request_key(request: GoogleAnalysisRequest) -> str:
    company_id = request.company.get("data_id") or request.company.get("place_id") or request.company.get("name")
    return "|".join([str(company_id).casefold(), request.keyword.casefold(), request.location.casefold(), str(request.depth), str(request.demo)])


@router.get("/capabilities")
def capabilities():
    settings = get_settings()
    live = bool((settings.serpapi_api_key or "").strip())
    return {
        "provider": "serpapi" if live else "demo",
        "live_configured": live,
        "demo_available": True,
        "authentication": "A aplicação atual não possui autenticação de usuários; o módulo herda o mesmo acesso do painel.",
        "methodology": methodology_payload(),
    }


@router.post("/companies/search")
async def search_companies(request: GoogleCompanySearchRequest, demo: bool = Query(default=False)):
    if demo:
        return {"items": demo_search(request.name, request.city), "provider": "demo", "demo": True}
    try:
        items = await provider().search_companies(request.name, request.city, request.refine)
        return {"items": items, "provider": "serpapi", "demo": False}
    except ProviderNotConfigured as exc:
        raise HTTPException(status_code=503, detail=f"{exc} Use o modo demonstração ou configure as credenciais no servidor.") from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/jobs", status_code=202)
async def create_analysis(request: GoogleAnalysisRequest, background_tasks: BackgroundTasks):
    key = request_key(request)
    async with job_lock:
        existing_id = request_jobs.get(key)
        if existing_id and existing_id in jobs and jobs[existing_id].status in {"pending", "processing"}:
            existing = jobs[existing_id].model_copy(update={"reused": True})
            return existing
        job_id = str(uuid4())
        jobs[job_id] = AnalysisJob(id=job_id, status="pending")
        request_jobs[key] = job_id
    background_tasks.add_task(run_analysis, job_id, key, request)
    return jobs[job_id]


@router.get("/jobs/{job_id}")
def get_analysis_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Análise não encontrada ou o servidor foi reiniciado.")
    return jobs[job_id]


async def run_analysis(job_id: str, key: str, request: GoogleAnalysisRequest) -> None:
    job = jobs[job_id]
    report_id = str(uuid4())
    try:
        job.status = "processing"
        job.stage = "Abrindo o perfil público"
        if request.demo:
            await asyncio.sleep(0.15)
            data = demo_payload(request.company, request.keyword, request.location, request.depth)
            job.completed_steps.append("Perfil demonstrativo preparado")
        else:
            live_provider = provider()
            info = await live_provider.business_info(request.company)
            job.completed_steps.append("Perfil público coletado")
            job.stage = "Comparando resultados locais"
            keyword = request.keyword or f"{request.company.get('category') or request.company['name']} em {request.location or 'Brasil'}"
            results = await asyncio.gather(
                live_provider.competitors(keyword, request.location, request.depth),
                live_provider.recent_reviews(request.company, info),
                live_provider.recent_posts(request.company, info),
                return_exceptions=True,
            )
            limitations = ["A posição representa esta palavra-chave, localização e momento; não toda a cidade."]
            searches_used = 1
            if isinstance(results[0], Exception):
                competitors, check_url = [], None
                limitations.append("A comparação competitiva falhou; os dados válidos do perfil foram preservados.")
            else:
                competitors, check_url = results[0]
                searches_used += 1
                job.completed_steps.append("Comparação competitiva coletada")
            if isinstance(results[1], Exception):
                reviews_sample = None
                limitations.append("A coleta das avaliações recentes falhou; recência e respostas ficaram não verificáveis.")
            else:
                reviews_sample = results[1]
                searches_used += int(reviews_sample is not None)
                if reviews_sample is not None:
                    job.completed_steps.append("Avaliações recentes coletadas")
            if isinstance(results[2], Exception):
                posts = None
                limitations.append("A coleta de postagens falhou; o item ficou não verificável.")
            else:
                posts = results[2]
                searches_used += int(posts is not None)
                if posts is not None:
                    job.completed_steps.append("Postagens recentes coletadas")
            identity_values = {
                str(value) for value in (
                    info.get("data_id"), info.get("data_cid"), info.get("place_id"),
                    request.company.get("data_id"), request.company.get("data_cid"), request.company.get("place_id"),
                ) if value
            }
            own = next((entry for entry in competitors if identity_values.intersection({str(entry.get("data_id") or ""), str(entry.get("data_cid") or ""), str(entry.get("place_id") or "")})), None)
            sample = [entry for entry in competitors if entry is not own and not entry.get("is_paid")]
            review_counts = [entry["review_count"] for entry in sample if isinstance(entry.get("review_count"), int)]
            data = {
                "evidence": normalize_live_evidence(info, reviews_sample, posts),
                "profile": {
                    **request.company,
                    "name": info.get("title") or request.company["name"],
                    "category": (info.get("type") or [request.company.get("category")])[0] if isinstance(info.get("type"), list) else info.get("type") or request.company.get("category"),
                    "address": info.get("address") or request.company.get("address"),
                    "rating": info.get("rating"),
                    "review_count": info.get("reviews"),
                    "maps_url": info.get("place_id_search") or request.company.get("maps_url"),
                    "data_id": info.get("data_id") or request.company.get("data_id"),
                    "data_cid": info.get("data_cid") or request.company.get("data_cid"),
                },
                "competition": {
                    "keyword": request.keyword,
                    "location": request.location,
                    "language_code": request.language_code,
                    "depth": request.depth,
                    "provider": "serpapi",
                    "position": own.get("position") if own else None,
                    "sample_size": len(sample),
                    "median_review_count": median(review_counts) if review_counts else None,
                    "competitors": sample[:10],
                    "check_url": check_url,
                },
                "cost": {
                    "searches_used": searches_used + (0 if request.company.get("from_lead") else 1),
                    "estimated_usd": round((searches_used + (0 if request.company.get("from_lead") else 1)) * 0.025, 3),
                    "actual_usd": None,
                    "basis": "equivalente ao plano Starter de US$ 25/1.000 buscas",
                },
                "limitations": limitations + ["Itens ausentes na resposta da SerpApi permanecem como não verificáveis, sem penalidade automática.", "A estimativa de custo varia conforme o plano contratado; a SerpApi não devolve custo monetário por resposta."],
            }

        job.stage = "Aplicando a metodologia ProspectSites"
        scored = score_profile(data["evidence"])
        collected_at = datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat()
        report: dict[str, Any] = {
            "id": report_id,
            "status": "partial" if any(item["state"] == "unknown" for item in scored["checklist"]) else "completed",
            "demo": request.demo,
            "provider": "demo" if request.demo else "serpapi",
            "collected_at": collected_at,
            "company": data["profile"],
            "lead_place_id": request.lead_place_id,
            "evidence": data["evidence"],
            "competition": data["competition"],
            "cost": data["cost"],
            "limitations": data["limitations"],
            **scored,
        }
        await asyncio.to_thread(repository().save, report)
        job.completed_steps.extend(["Nota e cobertura calculadas", "Relatório salvo no histórico"])
        job.report_id = report_id
        job.status = report["status"]
        job.stage = "Relatório concluído" if report["status"] == "completed" else "Relatório parcial concluído"
    except Exception as exc:
        job.status = "failed"
        job.stage = "A análise não foi concluída"
        job.error = str(exc)[:500]
    finally:
        async with job_lock:
            if request_jobs.get(key) == job_id:
                request_jobs.pop(key, None)


@router.get("/reports")
def list_reports(limit: int = Query(default=30, ge=1, le=100)):
    try:
        return {"items": repository().list(limit)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Não foi possível carregar o histórico: {exc}") from exc


@router.get("/reports/{report_id}")
def get_report(report_id: str):
    try:
        return repository().get(report_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/reports/{report_id}/link-lead")
def link_report_to_lead(report_id: str, request: GoogleAnalysisLinkRequest):
    try:
        return repository().link_lead(report_id, request.place_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
