from __future__ import annotations

import hmac

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Response

from .config import get_settings
from .crm_models import (
    CrmContactUpdate, CrmInstanceCreate, CrmInstanceUpdate, CrmStageCreate, CrmStageDelete,
    CrmStageMove, CrmStageReorder, CrmStageUpdate, HermesEvent, HermesProspectLookup, HermesAnalysisRequest,
)
from .crm_repository import CrmRepository, normalize_phone, stable_id
from .firestore_repository import FirestoreRepository
from .google_analysis_models import GoogleAnalysisRequest
from .google_analysis_image import render_analysis_png
from . import google_analysis_router


router = APIRouter(prefix="/api/crm", tags=["CRM"])


def repository() -> CrmRepository:
    return CrmRepository(get_settings())


def lead_repository() -> FirestoreRepository:
    return FirestoreRepository(get_settings())


@router.get("/dashboard")
def dashboard(instance_name: str = ""):
    return repository().dashboard(instance_name)


@router.get("/contacts")
def contacts(
    instance_name: str = "", stage_id: str = "", query: str = "",
    limit: int = Query(default=250, ge=1, le=500),
):
    return repository().list_contacts(instance_name=instance_name, stage_id=stage_id, query=query, limit=limit)


@router.get("/contacts/{contact_id}/messages")
def messages(contact_id: str, limit: int = Query(default=300, ge=1, le=500)):
    return repository().list_messages(contact_id, limit)


@router.get("/contacts/{contact_id}/activities")
def activities(contact_id: str, limit: int = Query(default=100, ge=1, le=200)):
    return repository().list_activities(contact_id, limit)


@router.patch("/contacts/{contact_id}")
def update_contact(contact_id: str, request: CrmContactUpdate):
    values = request.model_dump(exclude_none=True)
    if not values:
        raise HTTPException(status_code=422, detail="Nenhuma alteração foi informada.")
    if "responsible" in values:
        values["responsible"] = values["responsible"].strip()
    try:
        return repository().update_contact(contact_id, values)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/contacts/{contact_id}/stage")
def move_contact(contact_id: str, request: CrmStageMove):
    try:
        return repository().move_contact(contact_id, request.stage_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/stages", status_code=201)
def create_stage(request: CrmStageCreate):
    return repository().create_stage(request.name, request.color)


@router.put("/stages/reorder")
def reorder_stages(request: CrmStageReorder):
    try:
        return repository().reorder_stages(request.stage_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/stages/{stage_id}")
def update_stage(stage_id: str, request: CrmStageUpdate):
    values = request.model_dump(exclude_none=True)
    try:
        return repository().update_stage(stage_id, values)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/stages/{stage_id}/delete")
def delete_stage(stage_id: str, request: CrmStageDelete):
    try:
        repository().delete_stage(stage_id, request.move_to_stage_id)
        return {"deleted": True}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/instances", status_code=201)
def create_instance(request: CrmInstanceCreate):
    return repository().save_instance(request.instance_name, request.model_dump(exclude={"instance_name"}))


@router.patch("/instances/{instance_name}")
def update_instance(instance_name: str, request: CrmInstanceUpdate):
    return repository().save_instance(instance_name, request.model_dump(exclude_none=True))


@router.delete("/instances/{instance_name}")
def delete_instance(instance_name: str):
    repository().delete_instance(instance_name)
    return {"deleted": True}


def authenticate_hermes(x_hermes_secret: str | None, authorization: str | None) -> None:
    settings = get_settings()
    expected = (settings.hermes_webhook_secret or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="HERMES_WEBHOOK_SECRET ainda não foi configurado no backend.")
    bearer = authorization[7:].strip() if (authorization or "").lower().startswith("bearer ") else ""
    supplied = (x_hermes_secret or bearer).strip()
    if not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail="Evento do Hermes não autorizado.")


@router.get("/integrations/hermes/contract")
def hermes_contract():
    return {
        "version": "1.2",
        "endpoint": "/api/crm/integrations/hermes/events",
        "archived_profile_endpoint": "/api/crm/integrations/hermes/prospects/{place_id}",
        "phone_lookup_endpoint": "/api/crm/integrations/hermes/prospects/lookup",
        "stages_endpoint": "/api/crm/integrations/hermes/stages",
        "analysis_endpoint": "/api/crm/integrations/hermes/analysis/jobs",
        "authentication": ["X-Hermes-Secret", "Authorization: Bearer <secret>"],
        "events": [
            "message.upsert", "connection.update", "contact.upsert",
            "lead.stage.changed", "heartbeat",
        ],
    }


@router.post("/integrations/hermes/prospects/lookup")
def hermes_lookup_prospect(
    payload: HermesProspectLookup,
    response: Response,
    x_hermes_secret: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    authenticate_hermes(x_hermes_secret, authorization)
    response.headers["Cache-Control"] = "no-store"
    try:
        return lead_repository().find_prospects_by_phone(payload.phone)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/integrations/hermes/stages")
def hermes_stages(
    x_hermes_secret: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    authenticate_hermes(x_hermes_secret, authorization)
    return repository().list_stages()


@router.post("/integrations/hermes/analysis/jobs", status_code=202)
async def hermes_start_analysis(
    payload: HermesAnalysisRequest,
    background_tasks: BackgroundTasks,
    x_hermes_secret: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    authenticate_hermes(x_hermes_secret, authorization)
    if not payload.customer_accepted:
        raise HTTPException(status_code=422, detail="A análise exige a aceitação do cliente.")
    try:
        matches = lead_repository().find_prospects_by_phone(payload.phone)
        match = next((item for item in matches["matches"] if item["place_id"] == payload.place_id), None)
        if not match:
            raise HTTPException(status_code=409, detail="O telefone não foi confirmado para esse lead; confirme os dados antes de analisar.")
        if len(matches["matches"]) != 1 or matches["active_scan_limited"] or matches["archived_results_limited"]:
            raise HTTPException(status_code=409, detail="A identificação é ambígua ou a busca está incompleta; confirme o lead com a equipe.")
        company = {
            "name": match["company_name"], "place_id": match["place_id"],
            "address": match["address"], "neighborhood": match["neighborhood"],
            "city": match["city"], "state": match["state"],
            "maps_url": match["maps_link"], "from_lead": True,
        }
        request = GoogleAnalysisRequest(company=company, keyword=payload.keyword, location=payload.location,
                                        lead_place_id=payload.place_id, demo=False)
        return await google_analysis_router.create_analysis(request, background_tasks)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/integrations/hermes/analysis/jobs/{job_id}")
def hermes_analysis_status(job_id: str, x_hermes_secret: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    authenticate_hermes(x_hermes_secret, authorization)
    return google_analysis_router.get_analysis_job(job_id)


@router.get("/integrations/hermes/analysis/reports/{report_id}")
def hermes_analysis_report(report_id: str, response: Response, x_hermes_secret: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    authenticate_hermes(x_hermes_secret, authorization)
    return google_analysis_router.consume_report(report_id, response)


@router.get("/integrations/hermes/analysis/reports/{report_id}/image.png")
def hermes_analysis_image(
    report_id: str,
    place_id: str = Query(min_length=1, max_length=200),
    x_hermes_secret: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    authenticate_hermes(x_hermes_secret, authorization)
    report = google_analysis_router.transient_reports.get(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Análise temporária não encontrada ou já descartada.")
    if report.get("lead_place_id") != place_id:
        raise HTTPException(status_code=409, detail="O relatório não corresponde ao lead informado.")
    return Response(content=render_analysis_png(report), media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/integrations/hermes/prospects/{place_id}")
def hermes_archived_prospect(
    place_id: str,
    x_hermes_secret: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    authenticate_hermes(x_hermes_secret, authorization)
    try:
        return lead_repository().get_prospect_profile(place_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/integrations/hermes/events", status_code=202)
def hermes_event(
    payload: HermesEvent,
    x_hermes_secret: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    authenticate_hermes(x_hermes_secret, authorization)
    repo = repository()
    if not repo.begin_integration_event(payload.event_id, payload.event, payload.instance):
        return {"accepted": True, "duplicate": True, "event_id": payload.event_id}
    try:
        if payload.event == "message.upsert":
            result = repo.ingest_normalized_message(payload.instance, payload.data, payload.occurred_at)
        elif payload.event == "connection.update":
            state = str(payload.data.get("state") or payload.data.get("status") or "unknown")
            result = repo.save_instance(payload.instance, {
                "status": state, "provider": "hermes", "last_event_at": payload.occurred_at,
            })
        elif payload.event == "contact.upsert":
            result = repo.upsert_contact(payload.instance, payload.data)
        elif payload.event == "lead.stage.changed":
            contact_id = str(payload.data.get("contact_id") or "")
            stage_value = str(
                payload.data.get("stage_id") or payload.data.get("stage") or payload.data.get("stage_name") or ""
            )
            stage = repo.resolve_stage(stage_value)
            contact_data = dict(payload.data)
            place_id = str(contact_data.get("lead_place_id") or "").strip()
            if place_id:
                lookup = lead_repository().find_prospects_by_phone(str(contact_data.get("phone") or ""))
                match = next((item for item in lookup["matches"] if item["place_id"] == place_id), None)
                if not match or lookup["requires_confirmation"]:
                    raise ValueError("Lead não confirmado pelo telefone ou identificação ambígua; nenhum card foi movido.")
                if contact_id and contact_id != stable_id(normalize_phone(str(contact_data.get("phone") or ""))):
                    raise ValueError("O card informado não corresponde ao telefone confirmado.")
                contact_data["name"] = match["company_name"]
            if not contact_id:
                contact_id = repo.upsert_contact(payload.instance, contact_data)["id"]
            result = repo.move_contact(
                contact_id,
                stage["id"],
                actor="hermes",
                reason=str(payload.data.get("reason") or ""),
                source_event_id=payload.event_id,
            )
        else:
            result = repo.save_instance(payload.instance, {
                "status": str(payload.data.get("status") or "connected"),
                "provider": "hermes",
                "last_event_at": payload.occurred_at,
            })
        repo.finish_integration_event(payload.event_id)
        return {"accepted": True, "duplicate": False, "event_id": payload.event_id, "result": result}
    except (KeyError, ValueError) as exc:
        repo.finish_integration_event(payload.event_id, status="failed", detail=str(exc))
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        repo.finish_integration_event(payload.event_id, status="failed", detail=str(exc))
        raise HTTPException(status_code=500, detail="Falha ao processar o evento do Hermes.") from exc

