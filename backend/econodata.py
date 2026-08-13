import re
from typing import Any

import httpx

from .models import Lead


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


def extract_first_cnpj(payload: Any) -> str:
    if isinstance(payload, dict):
        prioritized = [value for key, value in payload.items() if "cnpj" in str(key).lower()]
        remaining = [value for key, value in payload.items() if "cnpj" not in str(key).lower()]
        for value in prioritized + remaining:
            candidate = extract_first_cnpj(value)
            if candidate:
                return candidate
    elif isinstance(payload, list):
        for value in payload:
            candidate = extract_first_cnpj(value)
            if candidate:
                return candidate
    elif isinstance(payload, (str, int)):
        candidate = normalize_cnpj(str(payload))
        if valid_cnpj(candidate):
            return candidate
    return ""


class EconodataClient:
    def __init__(self, api_url: str, api_key: str, auth_header: str = "Authorization", auth_scheme: str = "Bearer", query_param: str = "nome"):
        self.api_url = api_url
        self.api_key = api_key
        self.auth_header = auth_header
        self.auth_scheme = auth_scheme
        self.query_param = query_param

    async def find_cnpj(self, client: httpx.AsyncClient, lead: Lead) -> str:
        credential = f"{self.auth_scheme} {self.api_key}".strip()
        response = await client.get(
            self.api_url,
            params={self.query_param: lead.company_name},
            headers={self.auth_header: credential},
        )
        if response.status_code == 429:
            raise RuntimeError("A Econodata atingiu o limite de consultas da conta.")
        if response.status_code in {401, 403}:
            raise RuntimeError("A Econodata recusou a chave de acesso.")
        response.raise_for_status()
        return extract_first_cnpj(response.json())
