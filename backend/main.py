import asyncio
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .models import Job, SearchRequest
from .places import search_eligible_profiles
from .sheets import SheetsRepository

app = FastAPI(title="Prospect Sites API", version="2.0.0")
jobs: dict[str, Job] = {}

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
        }
    except RuntimeError as exc:
        return {"status": "configuration_required", "detail": str(exc)}


@app.get("/api/leads")
def list_leads():
    try:
        return repository().list()
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Falha no Google Sheets: {exc}"
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
            minimum_reviews=50,
            max_pages=3,
        )
        job.total = report.scanned
        job.processed = report.scanned
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
            f"{report.pages} página(s) consultada(s)"
        )
    except Exception as exc:
        job.status = "failed"
        job.detail = str(exc)


@app.post("/api/search", status_code=202)
async def start_search(
    request: SearchRequest, background_tasks: BackgroundTasks
):
    job_id = str(uuid4())
    jobs[job_id] = Job(id=job_id, kind="search", status="queued")
    background_tasks.add_task(run_search, job_id, request)
    return jobs[job_id]
