from __future__ import annotations

import hmac

from fastapi import APIRouter, Header, HTTPException, Query

from .config import get_settings
from .crm_models import (
    CrmContactUpdate, CrmInstanceCreate, CrmInstanceUpdate, CrmStageCreate, CrmStageDelete,
    CrmStageMove, CrmStageReorder, CrmStageUpdate, HermesEvent,
)
from .crm_repository import CrmRepository
from .firestore_repository import FirestoreRepository


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
        "version": "1.1",
        "endpoint": "/api/crm/integrations/hermes/events",
        "archived_profile_endpoint": "/api/crm/integrations/hermes/prospects/{place_id}",
        "authentication": ["X-Hermes-Secret", "Authorization: Bearer <secret>"],
        "events": [
            "message.upsert", "connection.update", "contact.upsert",
            "lead.stage.changed", "heartbeat",
        ],
    }


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
            if not contact_id:
                contact_id = repo.upsert_contact(payload.instance, payload.data)["id"]
            stage_value = str(
                payload.data.get("stage_id") or payload.data.get("stage") or payload.data.get("stage_name") or ""
            )
            stage = repo.resolve_stage(stage_value)
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

