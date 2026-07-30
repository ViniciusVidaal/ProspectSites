import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .models import (
    AgentFailure,
    AgentResult,
    Job,
    SearchRequest,
    SendRequest,
)
from .places import enrich_company, is_qualifying_url
from .scraper import SponsoredBusiness, scrape_sponsored_businesses
from .sheets import SheetsRepository
from .whatsapp import send_messages

app = FastAPI(title="Prospect Sites API", version="1.0.0")
jobs: dict[str, Job] = {}
search_tasks: dict[str, str] = {}
agent_last_seen: datetime | None = None

try:
    _settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_settings.frontend_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
except RuntimeError:
    # Permite que /health explique a configuração faltante.
    app.add_middleware(CORSMiddleware, allow_origins=[], allow_methods=["GET"])


def repository() -> SheetsRepository:
    return SheetsRepository(get_settings())


def require_agent(x_agent_token: str | None = Header(default=None)) -> None:
    expected = get_settings().agent_token
    if not expected or x_agent_token != expected:
        raise HTTPException(status_code=401, detail="Agente não autorizado.")


def agent_is_online() -> bool:
    if not agent_last_seen:
        return False
    return (datetime.now(timezone.utc) - agent_last_seen).total_seconds() < 20


@app.get("/")
def root():
    return {
        "name": "Prospect Sites API",
        "status": "online",
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
        }
    except RuntimeError as exc:
        return {"status": "configuration_required", "detail": str(exc)}


@app.get("/api/agent/status")
def get_agent_status():
    return {
        "online": agent_is_online(),
        "last_seen": agent_last_seen.isoformat() if agent_last_seen else None,
    }


@app.post("/api/agent/heartbeat", dependencies=[])
def agent_heartbeat(x_agent_token: str | None = Header(default=None)):
    require_agent(x_agent_token)
    global agent_last_seen
    agent_last_seen = datetime.now(timezone.utc)
    return {"status": "ok"}


@app.get("/api/agent/tasks/next")
def next_agent_task(x_agent_token: str | None = Header(default=None)):
    require_agent(x_agent_token)
    global agent_last_seen
    agent_last_seen = datetime.now(timezone.utc)
    for job_id, query in search_tasks.items():
        job = jobs.get(job_id)
        if job and job.status == "queued":
            job.status = "running"
            job.detail = "Pesquisa enviada ao navegador local"
            return {"id": job_id, "query": query}
    return {"id": None, "query": None}


@app.post("/api/agent/tasks/{job_id}/complete")
async def complete_agent_task(
    job_id: str,
    result: AgentResult,
    x_agent_token: str | None = Header(default=None),
):
    require_agent(x_agent_token)
    job = jobs.get(job_id)
    query = search_tasks.get(job_id)
    if not job or not query:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")

    try:
        settings = get_settings()
        sponsored = [
            SponsoredBusiness(name=item.name, destination=item.destination)
            for item in result.businesses
        ]
        qualified = [
            item for item in sponsored if is_qualifying_url(item.destination)
        ]
        job.total = len(qualified)
        enriched = []
        for index, item in enumerate(qualified, start=1):
            lead = await enrich_company(
                settings.places_api_key, item.name, query
            )
            if lead:
                enriched.append(lead)
            job.processed = index
            job.detail = f"Enriquecendo {index} de {len(qualified)}"

        inserted = await asyncio.to_thread(repository().append_new, enriched)
        job.status = "completed"
        job.detail = (
            f"{len(inserted)} novo(s) salvo(s) · "
            f"{len(sponsored)} patrocinado(s) detectado(s) · "
            f"{len(qualified)} qualificado(s) · navegador local"
        )
        search_tasks.pop(job_id, None)
        return job
    except Exception as exc:
        job.status = "failed"
        job.detail = str(exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/agent/tasks/{job_id}/fail")
def fail_agent_task(
    job_id: str,
    failure: AgentFailure,
    x_agent_token: str | None = Header(default=None),
):
    require_agent(x_agent_token)
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    job.status = "failed"
    job.detail = failure.detail
    search_tasks.pop(job_id, None)
    return job


@app.get("/api/leads")
def list_leads():
    try:
        return repository().list()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha no Google Sheets: {exc}") from exc


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    return jobs[job_id]


async def run_search(job_id: str, request: SearchRequest) -> None:
    job = jobs[job_id]
    try:
        job.status = "running"
        settings = get_settings()
        scrape_report = await scrape_sponsored_businesses(
            request.query, settings.headless, settings.serpapi_api_key
        )
        sponsored = scrape_report.businesses
        qualified = [item for item in sponsored if is_qualifying_url(item.destination)]
        job.total = len(qualified)
        enriched = []
        for index, item in enumerate(qualified, start=1):
            lead = await enrich_company(
                settings.places_api_key, item.name, request.query
            )
            if lead:
                enriched.append(lead)
            job.processed = index
            job.detail = f"Enriquecendo {index} de {len(qualified)}"
        inserted = await asyncio.to_thread(repository().append_new, enriched)
        job.status = "completed"
        diagnostic = (
            f" · {scrape_report.blocked_reason}"
            if scrape_report.blocked_reason
            else (
                f" · {scrape_report.marker_count} anúncio(s) retornado(s) "
                f"via {scrape_report.source}"
                + (
                    f" · localização: {scrape_report.location}"
                    if scrape_report.location
                    else " · localização não identificada"
                )
            )
        )
        job.detail = (
            f"{len(inserted)} novo(s) salvo(s) · "
            f"{len(sponsored)} patrocinado(s) detectado(s) · "
            f"{len(qualified)} qualificado(s)"
            f"{diagnostic}"
        )
    except Exception as exc:
        job.status = "failed"
        job.detail = str(exc)


@app.post("/api/search", status_code=202)
async def start_search(request: SearchRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid4())
    jobs[job_id] = Job(id=job_id, kind="search", status="queued")
    settings = get_settings()
    if settings.search_mode == "agent":
        if not settings.agent_token:
            jobs.pop(job_id, None)
            raise HTTPException(
                status_code=503,
                detail="AGENT_TOKEN não configurado no servidor.",
            )
        search_tasks[job_id] = request.query
        jobs[job_id].detail = "Aguardando o navegador local"
    else:
        background_tasks.add_task(run_search, job_id, request)
    return jobs[job_id]


async def run_send(job_id: str, request: SendRequest) -> None:
    job = jobs[job_id]
    try:
        job.status = "running"
        settings = get_settings()
        available = {lead.place_id: lead for lead in await asyncio.to_thread(repository().list)}
        selected = [available[item] for item in request.place_ids if item in available]
        if not selected:
            raise ValueError("Nenhum lead válido selecionado.")
        job.total = len(selected)

        def progress(processed: int, total: int, detail: str) -> None:
            job.processed = processed
            job.total = total
            job.detail = detail

        await send_messages(
            selected,
            request.message,
            request.delay_seconds,
            str(settings.whatsapp_profile_dir),
            progress,
        )
        job.status = "completed"
        job.detail = "Fila finalizada"
    except Exception as exc:
        job.status = "failed"
        job.detail = str(exc)


@app.post("/api/send", status_code=202)
async def start_send(request: SendRequest, background_tasks: BackgroundTasks):
    if not request.confirmed:
        raise HTTPException(
            status_code=400,
            detail="Confirme o envio e verifique o consentimento dos destinatários.",
        )
    job_id = str(uuid4())
    jobs[job_id] = Job(id=job_id, kind="send", status="queued")
    background_tasks.add_task(run_send, job_id, request)
    return jobs[job_id]
