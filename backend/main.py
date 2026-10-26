import asyncio
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .models import ApiKeyCreateRequest, ArchiveRequest, Job, SearchRequest, SentStatusRequest
from .api_key_repository import ApiKeyRepository
from .firestore_repository import FirestoreRepository
from .places import PlacesQuotaExceeded, PlacesRequestFailed, search_eligible_profiles
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


def repository() -> FirestoreRepository:
    return FirestoreRepository(get_settings())


def api_keys() -> ApiKeyRepository:
    settings = get_settings()
    repository()
    return ApiKeyRepository(settings)


def firestore_http_error(action: str, exc: Exception) -> HTTPException:
    if "quota" in str(exc).casefold():
        return HTTPException(
            status_code=429,
            detail=(
                "O Firebase atingiu o limite diário de leituras. Seus leads já salvos continuam seguros. "
                "Tente novamente após a renovação diária do Firebase."
            ),
        )
    return HTTPException(status_code=502, detail=f"Falha ao {action}: {exc}")


def migrate_legacy_sheet_if_needed() -> int:
    """Imports the existing Google Sheet exactly once and never alters it."""
    settings = get_settings()
    if repository().count() or not settings.spreadsheet_id:
        return 0
    legacy_leads = SheetsRepository(settings).list(
        include_archived=True,
        ensure_sheet=False,
    )
    return len(repository().append_new(legacy_leads))


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
            "database": "firestore",
            "firebase_credentials": bool(settings.firebase_service_account_info),
            "legacy_sheet_migration_available": bool(
                settings.spreadsheet_id
                and (settings.service_account_info or settings.service_account_file)
            ),
            "search": "google_places",
        }
    except RuntimeError as exc:
        return {"status": "configuration_required", "detail": str(exc)}


@app.get("/api/leads")
def list_leads(include_archived: bool = False, limit: int = 1000):
    try:
        leads = repository().list(include_archived=include_archived, limit=limit)
        return [
            lead.model_copy(update={"sent": lead.sent or lead.archived})
            for lead in leads
        ]
    except Exception as exc:
        raise firestore_http_error("carregar os leads", exc) from exc


@app.get("/api/stats")
def lead_stats():
    try:
        return repository().stats()
    except Exception as exc:
        raise firestore_http_error("calcular metricas", exc) from exc


@app.get("/api/leads/history")
def list_lead_history(
    query: str = "",
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 20,
    cursor: str | None = None,
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="A data inicial não pode ser posterior à data final.",
        )
    try:
        items, next_cursor = repository().list_history(
            query=query.strip(),
            start_date=start_date,
            end_date=end_date,
            limit=max(1, min(limit, 50)),
            cursor=cursor,
        )
        return {"items": items, "next_cursor": next_cursor}
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao carregar o histórico de leads: {exc}",
        ) from exc


@app.get("/api/settings/api-keys")
def list_api_keys():
    try:
        return api_keys().list_public()
    except Exception:
        raise HTTPException(status_code=503, detail="Não foi possível carregar as configurações de API agora.")


@app.post("/api/settings/api-keys")
def add_api_key(request: ApiKeyCreateRequest):
    try:
        return api_keys().add(request.name, request.api_key, request.make_active)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        raise HTTPException(status_code=503, detail="Não foi possível salvar a API. Tente novamente.")


@app.post("/api/settings/api-keys/{key_id}/activate")
def activate_api_key(key_id: str):
    try:
        api_keys().activate(key_id)
        return {"status": "active", "id": key_id}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        raise HTTPException(status_code=503, detail="Não foi possível ativar esta API. Tente novamente.")


@app.delete("/api/settings/api-keys/{key_id}")
def delete_api_key(key_id: str):
    try:
        return api_keys().delete(key_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Não foi possível excluir esta API. Tente novamente.",
        )


@app.post("/api/leads/{place_id}/sent")
def mark_lead_sent(place_id: str):
    try:
        return repository().mark_sent(place_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise firestore_http_error("atualizar o lead", exc) from exc


@app.post("/api/leads/{place_id}/sent-status")
def set_lead_sent_status(place_id: str, request: SentStatusRequest):
    try:
        return repository().set_sent_status(place_id, request.sent)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise firestore_http_error("atualizar o lead", exc) from exc


@app.delete("/api/leads/{place_id}")
def delete_lead(place_id: str):
    try:
        repository().archive(place_id)
        return {"status": "archived", "place_id": place_id}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Falha ao arquivar o lead: {exc}"
        ) from exc


@app.get("/api/history/deletions")
def deletion_history():
    try:
        return repository().deletion_history()
    except Exception:
        raise HTTPException(status_code=503, detail="Não foi possível carregar o histórico de exclusões agora.")


@app.post("/api/leads/{place_id}/restore")
def restore_lead(place_id: str):
    try:
        repository().restore(place_id)
        return {"status": "restored", "place_id": place_id}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception:
        raise HTTPException(status_code=503, detail="Não foi possível restaurar este lead agora. Tente novamente.")


@app.post("/api/leads/archive")
def archive_leads(request: ArchiveRequest):
    try:
        count = repository().archive_many(request.place_ids)
        return {"status": "archived", "count": count}
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Falha ao arquivar os leads: {exc}"
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
        key_repository = api_keys()
        key_value, key_id = key_repository.active()
        report = await search_eligible_profiles(
            key_value,
            request.query,
            minimum_reviews=request.minimum_reviews,
            max_pages=3,
            on_successful_request=lambda: key_repository.record_usage(key_id),
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
            f"{report.pages} página(s) consultada(s) · "
            f"mais de {request.minimum_reviews} avaliações"
        )
    except PlacesQuotaExceeded as exc:
        api_keys().mark_exhausted(key_id, str(exc))
        job.status = "failed"
        job.detail = "Esta API do Google Maps atingiu o limite de uso. Abra Configurações, escolha outra API autorizada e tente novamente."
    except PlacesRequestFailed as exc:
        job.status = "failed"
        job.detail = str(exc)
    except RuntimeError as exc:
        job.status = "failed"
        job.detail = str(exc) if "Nenhuma API cadastrada" in str(exc) else "Não foi possível concluir a pesquisa agora. Confira sua conexão e tente novamente."
    except Exception:
        job.status = "failed"
        job.detail = "Não foi possível concluir a pesquisa agora. Confira sua conexão e tente novamente."


@app.on_event("startup")
async def migrate_legacy_leads() -> None:
    try:
        migrate_legacy_sheet_if_needed()
    except Exception as exc:
        # The app remains online for new research if the legacy source is unavailable.
        print(f"Migração inicial da planilha não concluída: {exc}")


@app.post("/api/search", status_code=202)
async def start_search(
    request: SearchRequest,
    background_tasks: BackgroundTasks,
):
    job_id = str(uuid4())
    jobs[job_id] = Job(id=job_id, kind="search", status="queued")
    background_tasks.add_task(run_search, job_id, request)
    return jobs[job_id]
