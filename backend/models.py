from pydantic import BaseModel, Field, field_validator


class SearchRequest(BaseModel):
    niche: str = Field(min_length=2, max_length=100)
    city: str = Field(min_length=2, max_length=100)


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

