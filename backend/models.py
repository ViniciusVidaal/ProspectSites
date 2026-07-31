from pydantic import BaseModel, Field, model_validator


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=200)


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


class ArchiveRequest(BaseModel):
    place_ids: list[str] = Field(min_length=1, max_length=500)


class Job(BaseModel):
    id: str
    kind: str
    status: str
    detail: str = ""
    processed: int = 0
    total: int = 0
