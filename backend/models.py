from pydantic import BaseModel, Field, model_validator


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
    site_platform: str = ""
    review_count: int = 0
    rating: float = 0
    maps_link: str = ""
    place_id: str


class Job(BaseModel):
    id: str
    kind: str
    status: str
    detail: str = ""
    processed: int = 0
    total: int = 0
