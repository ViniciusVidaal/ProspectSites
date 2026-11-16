from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class GoogleCompanySearchRequest(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    address: str = Field(min_length=5, max_length=260)


class GoogleAnalysisRequest(BaseModel):
    company: dict[str, Any]
    keyword: str = Field(default="", max_length=240)
    location: str = Field(default="", max_length=180)
    language_code: str = Field(default="pt", max_length=8)
    depth: int = Field(default=20, ge=10, le=20)
    lead_place_id: str | None = Field(default=None, max_length=200)
    demo: bool = False

    @model_validator(mode="after")
    def validate_company(self):
        if not str(self.company.get("name") or "").strip():
            raise ValueError("A empresa selecionada precisa ter um nome.")
        return self


class GoogleAnalysisLinkRequest(BaseModel):
    place_id: str = Field(min_length=2, max_length=200)


class AnalysisJob(BaseModel):
    id: str
    status: Literal["pending", "processing", "completed", "partial", "failed"]
    stage: str = "Preparando a análise"
    completed_steps: list[str] = Field(default_factory=list)
    report_id: str | None = None
    error: str | None = None
    reused: bool = False
