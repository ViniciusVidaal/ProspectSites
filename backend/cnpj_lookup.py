from __future__ import annotations

import json
import re
from typing import Literal

import httpx
from google import genai
from google.genai import types
from pydantic import BaseModel, Field, ValidationError

from .models import Lead


class Evidence(BaseModel):
    titulo: str = ""
    url: str = ""
    dado_confirmado: str = ""


class MatchResult(BaseModel):
    status: Literal["encontrado", "ambiguo", "nao_encontrado"]
    cnpj: str | None = None
    confianca: Literal["alta", "media", "baixa", "insuficiente"]
    justificativa: str = ""
    fontes: list[Evidence] = Field(default_factory=list)


class RegistryResult(BaseModel):
    phone: str = ""
    email: str = ""


def digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def valid_cnpj(value: str | None) -> bool:
    number = digits(value)
    if len(number) != 14 or number == number[0] * 14:
        return False

    def check(base: str, weights: list[int]) -> str:
        remainder = sum(int(n) * weight for n, weight in zip(base, weights)) % 11
        return "0" if remainder < 2 else str(11 - remainder)

    first = check(number[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    second = check(number[:12] + first, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return number[-2:] == first + second


def parse_result(text: str) -> MatchResult:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I)
    try:
        return MatchResult.model_validate_json(cleaned)
    except (ValidationError, ValueError):
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("O Gemini não devolveu um JSON válido.")
        return MatchResult.model_validate(json.loads(cleaned[start:end + 1]))


def grounded_urls(response: object) -> set[str]:
    urls: set[str] = set()
    try:
        metadata = response.candidates[0].grounding_metadata
        for chunk in metadata.grounding_chunks or []:
            web = getattr(chunk, "web", None)
            if web and getattr(web, "uri", None):
                urls.add(web.uri)
    except (AttributeError, IndexError, TypeError):
        pass
    return urls


def prompt_for(lead: Lead) -> str:
    return f"""Localize o CNPJ correto desta empresa usando pesquisa pública na web.
Nome: {lead.company_name}
Cidade: {lead.city or 'não informada'}
UF: {lead.state or 'não informada'}
Endereço: {lead.address or 'não informado'}

Compare nome, cidade, UF e endereço. Nunca invente ou complete dígitos. Retorne encontrado
somente quando o CNPJ estiver explícito em fonte pública compatível. Use ambiguo quando houver
mais de um candidato e nao_encontrado sem evidência suficiente. Confiança alta exige confirmação
forte; média admite endereço parcial; baixa não é conclusiva. Responda somente JSON com:
status, cnpj, confianca, justificativa e fontes (titulo, url, dado_confirmado)."""


def lookup_registry(lead: Lead, api_key: str, model: str) -> tuple[MatchResult, RegistryResult]:
    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        temperature=0,
    )
    response = client.models.generate_content(model=model, contents=prompt_for(lead), config=config)
    result = parse_result(response.text)
    cited = {source.url for source in result.fontes if source.url}
    grounded = grounded_urls(response)
    source_is_verified = bool(cited) and (not grounded or bool(cited.intersection(grounded)))
    if (
        result.status != "encontrado"
        or result.confianca not in {"alta", "media"}
        or not valid_cnpj(result.cnpj)
        or not source_is_verified
    ):
        return result, RegistryResult()

    cnpj = digits(result.cnpj)
    registry_response = httpx.get(
        f"https://api.opencnpj.org/{cnpj}",
        params={"datasets": "receita"},
        timeout=20,
        follow_redirects=True,
        headers={"User-Agent": "ProspectSites/2.0"},
    )
    if registry_response.status_code == 404:
        return result, RegistryResult()
    registry_response.raise_for_status()
    payload = registry_response.json()
    phones = [item for item in payload.get("telefones", []) if item.get("numero") and not item.get("is_fax")]
    phone = ""
    if phones:
        phone = digits(f"{phones[0].get('ddd', '')}{phones[0].get('numero', '')}")
        if phone and not phone.startswith("55"):
            phone = f"55{phone}"
    return result, RegistryResult(phone=phone, email=str(payload.get("email", "") or "").strip())
