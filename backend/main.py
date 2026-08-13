import asyncio
from uuid import uuid4

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .cnpj import enrich_leads_with_cnpj
from .models import ArchiveRequest, Job, SearchRequest
from .places import hydrate_lead_location, search_eligible_profiles
from .sheets import SheetsRepository

app = FastAPI(title="Prospect Sites API", version="2.0.0")
jobs: dict[str, Job] = {}

try:
    _settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_settings.frontend_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )
except RuntimeError:
    app.add_middleware(CORSMiddleware, allow_origins=[], allow_methods=["GET"])


def repository() -> SheetsRepository:
    return SheetsRepository(get_settings())


@app.get("/")
def root():
    return {
        "name": "Prospect Sites API",
        "status": "online",
        "version": "2.0.0",
        "health": "/health",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    try:
        settings = get_settings()
        return {
            "status": "ok",
            "credentials": bool(
                settings.service_account_info
                or (
                    settings.service_account_file
                    and settings.service_account_file.is_file()
                )
            ),
            "search": "google_places",
            "cnpj_search": "serpapi" if settings.serpapi_api_key else "duckduckgo",
        }
    except RuntimeError as exc:
        return {"status": "configuration_required", "detail": str(exc)}


@app.get("/api/leads")
def list_leads(include_archived: bool = True):
    try:
        leads = repository().list(include_archived=include_archived)
        return [
            lead.model_copy(update={"sent": lead.sent or lead.archived})
            for lead in leads
        ]
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Falha no Google Sheets: {exc}"
        ) from exc


@app.get("/api/stats")
def lead_stats():
    try:
        return repository().stats()
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Falha ao calcular métricas: {exc}"
        ) from exc


@app.post("/api/leads/{place_id}/sent")
def mark_lead_sent(place_id: str):
    try:
        return repository().mark_sent(place_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Falha ao atualizar Google Sheets: {exc}"
        ) from exc


@app.delete("/api/leads/{place_id}")
def delete_lead(place_id: str):
    try:
        repository().archive(place_id)
        return {"status": "archived", "place_id": place_id}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Falha ao arquivar no Google Sheets: {exc}"
        ) from exc


@app.post("/api/leads/archive")
def archive_leads(request: ArchiveRequest):
    try:
        count = repository().archive_many(request.place_ids)
        return {"status": "archived", "count": count}
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Falha ao arquivar no Google Sheets: {exc}"
        ) from exc


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    return jobs[job_id]


async def run_search(job_id: str, request: SearchRequest) -> None:
    job = jobs[job_id]
    try:
        job.status = "running"
        job.detail = "Consultando perfis no Google"
        settings = get_settings()
        report = await search_eligible_profiles(
            settings.places_api_key,
            request.query,
            minimum_reviews=request.minimum_reviews,
            max_pages=3,
        )
        job.total = report.scanned
        job.processed = report.scanned
        job.detail = "Identificando CNPJs por nome e localização"
        captured_cnpjs = await enrich_leads_with_cnpj(
            report.eligible, serpapi_api_key=settings.serpapi_api_key
        )
        inserted = await asyncio.to_thread(
            repository().append_new, report.eligible
        )
        duplicates = len(report.eligible) - len(inserted)
        job.status = "completed"
        job.detail = (
            f"{len(inserted)} novo(s) salvo(s) · "
            f"{report.scanned} perfil(is) analisado(s) · "
            f"{len(report.eligible)} qualificado(s) · "
            f"{duplicates} duplicado(s) · "
            f"{captured_cnpjs} CNPJ(s) capturado(s) · "
            f"{report.pages} página(s) consultada(s) · "
            f"mais de {request.minimum_reviews} avaliações"
        )
    except Exception as exc:
        job.status = "failed"
        job.detail = str(exc)


async def run_cnpj_backfill(job_id: str) -> None:
    job = jobs[job_id]
    try:
        job.status = "running"
        job.detail = "Carregando leads ativos e arquivados"
        settings = get_settings()
        leads = await asyncio.to_thread(repository().list, True)
        pending = [
            lead for lead in leads
            if not lead.cnpj and (lead.phone or (lead.site_platform == "Instagram" and lead.current_site))
        ]
        job.total = len(pending)
        captured = 0
        async with httpx.AsyncClient(timeout=8) as places_client:
            for start in range(0, len(pending), 5):
                batch = pending[start:start + 5]
                job.detail = f"Localizando empresas {start + 1}-{min(start + len(batch), job.total)} de {job.total}"
                location_semaphore = asyncio.Semaphore(1)

                async def locate(lead):
                    try:
                        async with location_semaphore:
                            await asyncio.sleep(1.1)
                            return await hydrate_lead_location(places_client, settings.places_api_key, lead)
                    except httpx.HTTPError:
                        return lead

                located = await asyncio.gather(*(locate(lead) for lead in batch))
                await asyncio.to_thread(repository().update_enrichment, located)
                ready = [lead for lead in located if lead.city and lead.state]
                if not ready:
                    job.processed = min(start + len(batch), job.total)
                    job.detail = f"{job.processed}/{job.total} analisado(s) · aguardando localização dos demais"
                    continue
                job.detail = f"Buscando CNPJs {start + 1}-{min(start + len(batch), job.total)} de {job.total}"
                found = await enrich_leads_with_cnpj(
                    ready,
                    concurrency=2,
                    delay_range=(1.5, 3.0) if settings.serpapi_api_key else (3.0, 6.0),
                    max_queries=1,
                    serpapi_api_key=settings.serpapi_api_key,
                )
                captured += found
                await asyncio.to_thread(repository().update_enrichment, ready)
                job.processed = min(start + len(batch), job.total)
                job.detail = f"{job.processed}/{job.total} analisado(s) · {captured} CNPJ(s) capturado(s)"
        job.status = "completed"
        job.detail = f"{job.total} lead(s) analisado(s) · {captured} CNPJ(s) capturado(s)"
    except Exception as exc:
        job.status = "failed"
        job.detail = str(exc)


@app.post("/api/cnpj/backfill", status_code=202)
async def start_cnpj_backfill(background_tasks: BackgroundTasks):
    if not get_settings().serpapi_api_key:
        raise HTTPException(
            status_code=503,
            detail="Configure SERPAPI_API_KEY no Render para buscar CNPJs sem bloqueio do DuckDuckGo.",
        )
    if any(job.kind == "cnpj_backfill" and job.status in {"queued", "running"} for job in jobs.values()):
        raise HTTPException(status_code=409, detail="A busca de CNPJs já está em andamento.")
    job_id = str(uuid4())
    jobs[job_id] = Job(id=job_id, kind="cnpj_backfill", status="queued")
    background_tasks.add_task(run_cnpj_backfill, job_id)
    return jobs[job_id]


@app.post("/api/search", status_code=202)
async def start_search(
    request: SearchRequest,
    background_tasks: BackgroundTasks,
):
    job_id = str(uuid4())
    jobs[job_id] = Job(id=job_id, kind="search", status="queued")
    background_tasks.add_task(run_search, job_id, request)
    return jobs[job_id]
