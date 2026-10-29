import re

from pydantic import BaseModel, Field, model_validator


class SearchRequest(BaseModel):
    query: str | None = Field(default=None, max_length=200)
    niche: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    minimum_reviews: int = Field(default=50, ge=0, le=100000)

    @model_validator(mode="after")
    def normalize_query(self):
        term = (self.query or "").strip()
        if not term:
            term = " ".join(
                part.strip()
                for part in (self.niche or "", self.city or "")
                if part.strip()
            )
        if len(term) < 2:
            raise ValueError("Informe uma palavra-chave com pelo menos 2 caracteres.")
        self.query = term
        return self


class Lead(BaseModel):
    date: str
    company_name: str
    phone: str = ""
    whatsapp_link: str = ""
    current_site: str = ""
    site_platform: str = ""
    review_count: int = 0
    rating: float = 0
    maps_link: str = ""
    place_id: str
    sent: bool = False
    sent_at: str = ""
    archived: bool = False
    cnpj: str = Field(default="", exclude=True)
    cnpj_captured: bool = False
    cnpj_phone: str = ""
    registry_email: str = ""
    cnpj_confidence: str = ""
    cnpj_status: str = ""
    cnpj_checked: bool = False
    cnpj_lookup_at: str = ""
    email_sent: bool = False
    email_sent_at: str = ""
    email_status: str = "pending"
    email_error: str = ""
    address: str = Field(default="", exclude=True)
    city: str = Field(default="", exclude=True)
    state: str = Field(default="", exclude=True)

    @model_validator(mode="after")
    def normalize_cnpj(self):
        self.cnpj = re.sub(r"\D", "", self.cnpj)
        self.cnpj_captured = len(self.cnpj) == 14
        return self


class ArchiveRequest(BaseModel):
    place_ids: list[str] = Field(min_length=1, max_length=500)


class CnpjLookupRequest(BaseModel):
    place_ids: list[str] = Field(min_length=1, max_length=100)


class EmailBatchRequest(BaseModel):
    place_ids: list[str] = Field(min_length=1, max_length=100)


class SentStatusRequest(BaseModel):
    sent: bool


class MessageTemplateRequest(BaseModel):
    message: str = Field(min_length=1, max_length=3000)


class EmailTemplateRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=10000)


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    api_key: str = Field(min_length=20, max_length=300)
    make_active: bool = True


class Job(BaseModel):
    id: str
    kind: str
    status: str
    detail: str = ""
    processed: int = 0
    total: int = 0
