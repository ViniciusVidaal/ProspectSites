from pydantic import BaseModel, Field, field_validator, model_validator


class SearchRequest(BaseModel):
    query: str | None = Field(default=None, max_length=200)
    niche: str | None = Field(default=None, max_length=100)
    city: str | None = Field(default=None, max_length=100)

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
    place_id: str


class SendRequest(BaseModel):
    place_ids: list[str] = Field(min_length=1, max_length=50)
    message: str = Field(min_length=1, max_length=2000)
    delay_seconds: int = Field(default=30, ge=10, le=3600)
    confirmed: bool = False

    @field_validator("place_ids")
    @classmethod
    def unique_ids(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class Job(BaseModel):
    id: str
    kind: str
    status: str
    detail: str = ""
    processed: int = 0
    total: int = 0


class AgentBusiness(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    destination: str = Field(default="", max_length=2000)


class AgentResult(BaseModel):
    businesses: list[AgentBusiness] = Field(default_factory=list, max_length=50)
    marker_count: int = Field(default=0, ge=0)
    detail: str = Field(default="", max_length=500)


class AgentFailure(BaseModel):
    detail: str = Field(min_length=1, max_length=500)
