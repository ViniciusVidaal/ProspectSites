import asyncio
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .models import ApiKeyCreateRequest, ArchiveRequest, CnpjLookupRequest, EmailBatchRequest, EmailTemplateRequest, Job, MessageTemplateRequest, SearchRequest, SentStatusRequest
from .cnpj_lookup import digits, lookup_registry
from .gmail_sender import gmail_service, send_lead_email
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
        allow_methods=["GET", "POST", "PUT", "DELETE"],
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
def list_leads(
    include_archived: bool = False,
    pending_only: bool = True,
    limit: int = 100,
):
    try:
        return repository().list(
            include_archived=include_archived,
            pending_only=pending_only,
            limit=limit,
        )
    except Exception as exc:
        raise firestore_http_error("carregar os leads", exc) from exc


@app.get("/api/stats")
def lead_stats():
    try:
        return repository().stats()
    except Exception as exc:
        raise firestore_http_error("calcular metricas", exc) from exc


@app.get("/api/settings/message-template")
def get_message_template():
    try:
        return {"message": repository().message_template()}
    except Exception as exc:
        raise firestore_http_error("carregar a mensagem", exc) from exc


@app.put("/api/settings/message-template")
def save_message_template(request: MessageTemplateRequest):
    try:
        return {"message": repository().save_message_template(request.message)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise firestore_http_error("salvar a mensagem", exc) from exc


@app.get("/api/settings/email-template")
def get_email_template():
    try:
        return repository().email_template()
    except Exception as exc:
        raise firestore_http_error("carregar a mensagem de e-mail", exc) from exc


@app.put("/api/settings/email-template")
def save_email_template(request: EmailTemplateRequest):
    try:
        return repository().save_email_template(request.subject, request.message)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise firestore_http_error("salvar a mensagem de e-mail", exc) from exc


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


def comparable_phone(value: str) -> str:
    number = digits(value)
    if number.startswith("55") and len(number) in (12, 13):
        number = number[2:]
    return number


async def run_cnpj_lookup(job_id: str, request: CnpjLookupRequest) -> None:
    job = jobs[job_id]
    settings = get_settings()
    try:
        leads = await asyncio.to_thread(repository().get_active_pending, request.place_ids)
        job.status = "running"
        job.total = len(leads)
        if not leads:
            job.status = "completed"
            job.detail = "Nenhum lead pendente da fila atual precisa ser consultado."
            return

        found = different_phones = emails = failures = 0
        for index, lead in enumerate(leads, start=1):
            job.detail = f"Consultando CNPJ de {lead.company_name} ({index}/{len(leads)})"
            try:
                result, registry = await asyncio.to_thread(
                    lookup_registry, lead, settings.gemini_api_key or "", settings.gemini_model
                )
                accepted = result.status == "encontrado" and result.confianca in {"alta", "media"}
                owner_phone = registry.phone if (
                    accepted and registry.phone
                    and comparable_phone(registry.phone) != comparable_phone(lead.phone)
                ) else ""
                email = registry.email if accepted else ""
                await asyncio.to_thread(
                    repository().save_cnpj_contacts,
                    lead.place_id,
                    phone=owner_phone,
                    email=email,
                    confidence=result.confianca,
                    status=result.status,
                    checked_at=datetime.now(ZoneInfo("America/Sao_Paulo")).isoformat(),
                )
                found += int(accepted)
                different_phones += int(bool(owner_phone))
                emails += int(bool(email))
            except Exception:
                failures += 1
            finally:
                job.processed = index

        job.status = "completed"
        job.detail = (
            f"{found} empresa(s) confirmada(s) com confiança média/alta · "
            f"{different_phones} contato(s) diferente(s) · {emails} e-mail(s) encontrado(s)"
            + (f" · {failures} falha(s)" if failures else "")
        )
    except Exception as exc:
        job.status = "failed"
        job.detail = f"Não foi possível concluir a busca de CNPJ: {exc}"


async def run_email_batch(job_id: str, request: EmailBatchRequest) -> None:
    job = jobs[job_id]
    settings = get_settings()
    try:
        template = await asyncio.to_thread(repository().email_template)
        if not template["subject"] or not template["message"]:
            raise RuntimeError("Configure e salve a mensagem de e-mail antes de enviar.")
        leads = await asyncio.to_thread(repository().get_email_leads, request.place_ids)
        eligible = [lead for lead in leads if lead.registry_email and not lead.email_sent]
        job.status = "running"
        job.total = len(eligible)
        if not eligible:
            job.status = "completed"
            job.detail = "Nenhum lead pendente com e-mail encontrado nesta fila."
            return

        service = await asyncio.to_thread(gmail_service, settings)
        sent = failed = 0
        for index, lead in enumerate(eligible, start=1):
            job.detail = f"Enviando e-mail para {lead.company_name} ({index}/{len(eligible)})"
            try:
                claimed = await asyncio.to_thread(repository().claim_email, lead.place_id)
                if not claimed:
                    continue
                await asyncio.to_thread(
                    send_lead_email,
                    service,
                    settings,
                    lead,
                    template["subject"],
                    template["message"],
                )
                sent_at = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M")
                await asyncio.to_thread(
                    repository().finish_email, lead.place_id, sent=True, sent_at=sent_at
                )
                sent += 1
            except Exception as exc:
                await asyncio.to_thread(
                    repository().finish_email, lead.place_id, sent=False, error=str(exc)
                )
                failed += 1
            finally:
                job.processed = index
            if index < len(eligible):
                await asyncio.sleep(2)

        job.status = "completed" if not failed else "failed"
        job.detail = f"{sent} e-mail(s) enviado(s) · {failed} falha(s)"
    except Exception as exc:
        job.status = "failed"
        job.detail = f"Não foi possível concluir os envios: {exc}"


@app.on_event("startup")
async def migrate_legacy_leads() -> None:
    try:
        migrate_legacy_sheet_if_needed()
        repository().compact_legacy_archived_leads()
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


@app.post("/api/cnpj-lookup", status_code=202)
async def start_cnpj_lookup(
    request: CnpjLookupRequest,
    background_tasks: BackgroundTasks,
):
    settings = get_settings()
    if not (settings.gemini_api_key or "").strip():
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY não configurada no backend.")
    job_id = str(uuid4())
    jobs[job_id] = Job(
        id=job_id,
        kind="cnpj_lookup",
        status="queued",
        total=len(request.place_ids),
    )
    background_tasks.add_task(run_cnpj_lookup, job_id, request)
    return jobs[job_id]


@app.post("/api/email/send-batch", status_code=202)
async def start_email_batch(
    request: EmailBatchRequest,
    background_tasks: BackgroundTasks,
):
    settings = get_settings()
    gmail_values = (
        settings.gmail_client_id,
        settings.gmail_client_secret,
        settings.gmail_refresh_token,
        settings.gmail_sender_email,
    )
    if not all((value or "").strip() for value in gmail_values):
        raise HTTPException(status_code=503, detail="As credenciais do Gmail não estão completas no backend.")
    job_id = str(uuid4())
    jobs[job_id] = Job(id=job_id, kind="email_batch", status="queued", total=len(request.place_ids))
    background_tasks.add_task(run_email_batch, job_id, request)
    return jobs[job_id]


@app.post("/api/email/statuses")
def email_statuses(request: EmailBatchRequest):
    try:
        return repository().get_email_leads(request.place_ids)
    except Exception as exc:
        raise firestore_http_error("carregar os status de e-mail", exc) from exc
