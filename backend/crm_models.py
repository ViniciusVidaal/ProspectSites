from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Literal


class CrmStageCreate(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    color: str = Field(default="#16a36a", pattern=r"^#[0-9a-fA-F]{6}$")


class CrmStageUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=60)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class CrmStageReorder(BaseModel):
    stage_ids: list[str] = Field(min_length=1, max_length=30)


class CrmStageMove(BaseModel):
    stage_id: str = Field(min_length=1, max_length=120)


class CrmContactUpdate(BaseModel):
    responsible: str | None = Field(default=None, max_length=80)


class CrmStageDelete(BaseModel):
    move_to_stage_id: str | None = Field(default=None, max_length=120)


class CrmInstanceCreate(BaseModel):
    instance_name: str = Field(min_length=2, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    label: str = Field(min_length=2, max_length=60)
    phone: str = Field(default="", max_length=30)
    color: str = Field(default="#16a36a", pattern=r"^#[0-9a-fA-F]{6}$")
    provider: Literal["hermes", "manual"] = "hermes"


class CrmInstanceUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=2, max_length=60)
    phone: str | None = Field(default=None, max_length=30)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    enabled: bool | None = None
    provider: Literal["hermes", "manual"] | None = None


class HermesEvent(BaseModel):
    """Provider-neutral envelope accepted from Hermes.

    The payload in ``data`` is intentionally extensible so Hermes can add metadata
    without requiring a synchronized ProspectSites deployment.
    """

    event: Literal[
        "message.upsert",
        "connection.update",
        "contact.upsert",
        "lead.stage.changed",
        "heartbeat",
    ]
    event_id: str = Field(min_length=4, max_length=200)
    instance: str = Field(min_length=2, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    occurred_at: str | int | float | None = None
    data: dict[str, Any] = Field(default_factory=dict)

