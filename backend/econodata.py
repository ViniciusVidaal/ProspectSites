import re

import httpx

from .models import Lead


class EconodataInsufficientTokens(RuntimeError):
    pass


def normalize_cnpj(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


def valid_cnpj(value: str) -> bool:
    digits = normalize_cnpj(value)
    if len(digits) != 14 or digits == digits[0] * 14:
        return False

    def digit(base: str, weights: list[int]) -> str:
        remainder = sum(int(number) * weight for number, weight in zip(base, weights)) % 11
        return str(0 if remainder < 2 else 11 - remainder)

    first = digit(digits[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    second = digit(digits[:12] + first, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return digits[-2:] == first + second


def extract_matched_cnpj(payload: dict) -> str:
    matches = payload.get("correspondencias", [])
    if not isinstance(matches, list) or not matches:
        return ""
    first = matches[0]
    if not isinstance(first, dict):
        return ""
    candidate = normalize_cnpj(first.get("cnpj", ""))
    if valid_cnpj(candidate):
        return candidate
    return ""


class EconodataClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def find_cnpj(self, client: httpx.AsyncClient, lead: Lead) -> str:
        criteria = {"nome": lead.company_name}
        if len(lead.state.strip()) == 2:
            criteria["uf"] = lead.state.strip().upper()
        response = await client.post(
            "https://api.econodata.com.br/v4/companies/match",
            json={"criterios": criteria},
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        if response.status_code == 429:
            raise RuntimeError("A Econodata atingiu o limite de consultas da conta.")
        if response.status_code in {401, 403}:
            raise RuntimeError("A Econodata recusou a chave de acesso.")
        if response.status_code == 402:
            raise EconodataInsufficientTokens("A conta Econodata não possui tokens suficientes.")
        response.raise_for_status()
        return extract_matched_cnpj(response.json())
