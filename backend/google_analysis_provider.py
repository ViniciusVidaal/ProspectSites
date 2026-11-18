"""SerpApi adapter and deterministic demo fixture.

Missing fields remain unknown unless the selected SerpApi engine explicitly confirms absence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any
from urllib.parse import quote_plus

import httpx


class ProviderError(RuntimeError):
    pass


class ProviderNotConfigured(ProviderError):
    pass


class SerpApiQuotaExceeded(ProviderError):
    pass


class SerpApiCredentialError(ProviderError):
    pass


class SerpApiProvider:
    base_url = "https://serpapi.com/search.json"

    def __init__(self, api_key: str | None, timeout: float = 30.0):
        if not (api_key or "").strip():
            raise ProviderNotConfigured("SERPAPI_API_KEY não está configurada.")
        self.api_key = api_key.strip()
        self.timeout = timeout

    @staticmethod
    def _raise_for_provider_error(status_code: int, message: str) -> None:
        normalized = (message or "").casefold()
        quota_terms = ("run out of searches", "out of searches", "quota", "too many requests", "limit reached")
        credential_terms = ("invalid api key", "api key is invalid", "unauthorized", "not authorized", "authentication")
        if status_code == 429 or any(term in normalized for term in quota_terms):
            raise SerpApiQuotaExceeded("A SerpApi atingiu o limite de buscas desta chave.")
        if status_code in (401, 403) or any(term in normalized for term in credential_terms):
            raise SerpApiCredentialError("A chave da SerpApi foi recusada.")

    async def _request(self, params: dict[str, Any], api_key: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(self.base_url, params={**params, "api_key": api_key, "output": "json"})
                self._raise_for_provider_error(response.status_code, response.text)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(f"Falha ao consultar a SerpApi: {exc}") from exc
        if payload.get("error"):
            self._raise_for_provider_error(response.status_code, str(payload["error"]))
            raise ProviderError(str(payload["error"]))
        if (payload.get("search_metadata") or {}).get("status") == "Error":
            raise ProviderError("A SerpApi não concluiu a consulta.")
        return payload

    async def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self._request(params, self.api_key)

    @staticmethod
    def _company(item: dict[str, Any]) -> dict[str, Any]:
        categories = item.get("types") or []
        category = item.get("type")
        if isinstance(category, list):
            category = category[0] if category else None
        coordinates = item.get("gps_coordinates") or {}
        return {
            "name": item.get("title") or "Empresa sem nome",
            "category": category or (categories[0] if categories else "Categoria não informada"),
            "address": item.get("address") or "Endereço não informado",
            "rating": item.get("rating"),
            "review_count": item.get("reviews"),
            "place_id": item.get("place_id") or item.get("data_id"),
            "data_id": item.get("data_id"),
            "data_cid": item.get("data_cid"),
            "maps_url": item.get("place_id_search"),
            "latitude": coordinates.get("latitude"),
            "longitude": coordinates.get("longitude"),
            "provider": "serpapi",
        }

    async def search_companies(self, name: str, address: str = "") -> list[dict[str, Any]]:
        query = " ".join(part.strip() for part in (name, address) if part.strip())
        payload = await self._get({"engine": "google_maps", "type": "search", "q": query, "hl": "pt-BR", "gl": "br"})
        results = payload.get("local_results") or []
        if not results and isinstance(payload.get("place_results"), dict) and payload["place_results"].get("title"):
            results = [payload["place_results"]]
        return [self._company(item) for item in results[:10]]

    async def business_info(self, company: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {"engine": "google_maps", "hl": "pt-BR", "gl": "br"}
        if company.get("place_id") and not str(company["place_id"]).startswith("demo-"):
            params["place_id"] = company["place_id"]
        elif company.get("data_id") and company.get("latitude") is not None and company.get("longitude") is not None:
            params.update({"type": "place", "data": f"!4m5!3m4!1s{company['data_id']}!8m2!3d{company['latitude']}!4d{company['longitude']}"})
        else:
            params.update({"type": "search", "q": company["name"]})
        payload = await self._get(params)
        item = payload.get("place_results")
        if not item:
            matches = payload.get("local_results") or []
            item = matches[0] if matches else None
        if not item:
            raise ProviderError("O perfil selecionado não foi devolvido pela SerpApi.")
        return item

    async def competitors(self, keyword: str, location: str, depth: int) -> tuple[list[dict[str, Any]], str | None]:
        query = " ".join(part.strip() for part in (keyword, location) if part.strip())
        payload = await self._get({"engine": "google_maps", "type": "search", "q": query, "hl": "pt-BR", "gl": "br"})
        entries = [{
            "position": item.get("position"), "name": item.get("title"), "rating": item.get("rating"),
            "review_count": item.get("reviews"), "data_id": item.get("data_id"), "data_cid": item.get("data_cid"),
            "place_id": item.get("place_id"), "address": item.get("address"), "category": item.get("type"), "is_paid": False,
        } for item in (payload.get("local_results") or [])[:depth]]
        return entries, (payload.get("search_metadata") or {}).get("google_maps_url")

    async def recent_reviews(self, company: dict[str, Any], info: dict[str, Any]) -> list[dict[str, Any]] | None:
        data_id = info.get("data_id") or company.get("data_id")
        place_id = info.get("place_id") or company.get("place_id")
        if not data_id and not place_id:
            return None
        params: dict[str, Any] = {"engine": "google_maps_reviews", "hl": "pt-BR", "sort_by": "newestFirst", "num": 20}
        params["data_id" if data_id else "place_id"] = data_id or place_id
        return (await self._get(params)).get("reviews") or []

    async def recent_posts(self, company: dict[str, Any], info: dict[str, Any]) -> list[dict[str, Any]] | None:
        data_id = info.get("data_id") or company.get("data_id")
        if not data_id:
            return None
        return (await self._get({"engine": "google_maps_posts", "data_id": data_id, "hl": "pt-BR"})).get("posts") or []


class RotatingSerpApiProvider(SerpApiProvider):
    def __init__(self, key_repository, timeout: float = 30.0):
        self.key_repository = key_repository
        self.timeout = timeout
        self.api_key = ""

    async def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        attempted: set[str] = set()
        while True:
            try:
                api_key, key_id = self.key_repository.active()
            except RuntimeError as exc:
                raise ProviderNotConfigured(str(exc)) from exc
            attempt_id = key_id or "environment"
            if attempt_id in attempted:
                raise ProviderError("Todas as chaves disponíveis da SerpApi falharam nesta consulta.")
            attempted.add(attempt_id)
            try:
                payload = await self._request(params, api_key)
                self.key_repository.record_usage(key_id)
                return payload
            except SerpApiQuotaExceeded as exc:
                if self.key_repository.failover(key_id, str(exc)):
                    continue
                raise
            except SerpApiCredentialError as exc:
                if self.key_repository.failover(key_id, str(exc), invalid=True):
                    continue
                raise


def demo_search(name: str, address: str = "") -> list[dict[str, Any]]:
    base_address = address.strip() or "Brasília, DF"
    return [
        {"name": name.strip() or "Empresa Demonstração", "category": "Agência de marketing digital", "address": base_address, "rating": 4.8, "review_count": 38, "place_id": "demo-profile-001", "data_id": "demo-data-001", "maps_url": "https://www.google.com/maps/search/?api=1&query=" + quote_plus(f"{name} {base_address}"), "provider": "demo", "demo": True},
        {"name": f"{name.strip()} Centro", "category": "Serviços empresariais", "address": base_address, "rating": 4.5, "review_count": 17, "place_id": "demo-profile-002", "data_id": "demo-data-002", "maps_url": "https://www.google.com/maps/search/?api=1&query=" + quote_plus(f"{name} {base_address}"), "provider": "demo", "demo": True},
    ]


def _status(value: bool | None, *, weak: bool = False) -> str:
    if value is None:
        return "unknown"
    if not value:
        return "absent"
    return "improve" if weak else "good"


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_live_evidence(item: dict[str, Any], reviews_sample: list[dict[str, Any]] | None = None, posts: list[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    categories = item.get("type") or item.get("types") or []
    if isinstance(categories, str):
        categories = [categories]
    description = item.get("description") or ""
    hours = item.get("hours") or item.get("operating_hours")
    extensions = item.get("extensions") or []
    images = item.get("images")
    rating = item.get("rating")
    review_count = item.get("reviews")
    latest_review = reviews_sample[0] if reviews_sample else None
    latest_date = _parse_iso((latest_review or {}).get("iso_date"))
    days_since_review = (datetime.now(timezone.utc) - latest_date).days if latest_date else None
    responded = sum(bool(review.get("response")) for review in (reviews_sample or []))
    sample_size = len(reviews_sample or [])
    latest_post = posts[0] if posts else None
    post_date = _parse_iso((latest_post or {}).get("posted_at"))
    days_since_post = (datetime.now(timezone.utc) - post_date).days if post_date else None
    source = "SerpApi Google Maps"
    return {
        "primary_category": {"state": _status(bool(categories)), "value": categories[0] if categories else None, "evidence": "Categoria principal devolvida pelo perfil." if categories else "Categoria não devolvida.", "source": source},
        "additional_categories": {"state": "good" if len(categories) > 1 else "improve" if categories else "unknown", "value": max(0, len(categories) - 1), "evidence": f"{max(0, len(categories)-1)} categoria(s) adicional(is) devolvida(s)." if categories else "Categorias adicionais não verificadas.", "source": source},
        "description": {"state": _status(bool(description), weak=bool(description) and len(description) < 120), "value": len(description), "evidence": f"Descrição devolvida com {len(description)} caracteres." if description else "Descrição não devolvida.", "source": source},
        "phone": {"state": _status(bool(item.get("phone"))), "value": item.get("phone"), "evidence": "Telefone público devolvido pelo perfil." if item.get("phone") else "Telefone não devolvido.", "source": source},
        "website": {"state": _status(bool(item.get("website"))), "value": item.get("website"), "evidence": "Site público devolvido pelo perfil." if item.get("website") else "Site não devolvido.", "source": source},
        "hours": {"state": _status(bool(hours)), "value": hours, "evidence": "Horários públicos devolvidos pelo perfil." if hours else "Horários não devolvidos.", "source": source},
        "location": {"state": "good" if item.get("address") else "unknown", "value": item.get("address"), "evidence": "Endereço público devolvido." if item.get("address") else "Sem evidência para diferenciar endereço ausente de empresa de área de serviço.", "source": source},
        "products_services": {"state": "unknown", "evidence": "A resposta não garante cobertura completa de produtos e serviços.", "source": source},
        "attributes": {"state": "good" if extensions else "unknown", "value": len(extensions), "evidence": f"{len(extensions)} grupo(s) de atributos devolvido(s)." if extensions else "Atributos não verificados.", "source": source},
        "photos": {"state": "unknown", "value": len(images) if isinstance(images, list) else None, "evidence": f"O endpoint devolveu uma amostra de {len(images)} imagem(ns), não uma contagem total garantida." if isinstance(images, list) else "A contagem total de fotos não foi devolvida.", "source": source},
        "verification": {"state": "unknown", "evidence": "A SerpApi não forneceu evidência explícita de verificação neste resultado.", "source": source},
        "posts": {"state": "good" if days_since_post is not None and days_since_post <= 30 else "improve" if days_since_post is not None else "absent" if posts == [] else "unknown", "value": days_since_post, "evidence": f"Postagem mais recente observada há {days_since_post} dia(s)." if days_since_post is not None else "Nenhuma postagem foi devolvida pela consulta." if posts == [] else "Postagens não puderam ser verificadas.", "source": "SerpApi Google Maps Posts"},
        "rating": {"state": "good" if isinstance(rating, (int, float)) and rating >= 4.5 else "improve" if isinstance(rating, (int, float)) else "unknown", "value": rating, "evidence": f"Nota pública observada: {rating}." if rating is not None else "Nota não devolvida.", "source": source},
        "review_volume": {"state": "good" if isinstance(review_count, int) and review_count >= 20 else "improve" if isinstance(review_count, int) and review_count > 0 else "unknown", "value": review_count, "evidence": f"{review_count} avaliações observadas; compare com a mediana local." if review_count is not None else "Quantidade não devolvida.", "source": source},
        "review_recency": {"state": "good" if days_since_review is not None and days_since_review <= 60 else "improve" if days_since_review is not None else "unknown", "value": days_since_review, "evidence": f"Avaliação mais recente da amostra publicada há {days_since_review} dia(s)." if days_since_review is not None else "Amostra recente não disponível.", "source": "SerpApi Google Maps Reviews"},
        "review_responses": {"state": "good" if sample_size and responded / sample_size >= .8 else "improve" if sample_size else "unknown", "value": f"{responded}/{sample_size}" if sample_size else None, "evidence": f"{responded} de {sample_size} avaliações mais recentes analisadas têm resposta." if sample_size else "Amostra de respostas não disponível.", "source": "SerpApi Google Maps Reviews"},
    }


def demo_payload(company: dict[str, Any], keyword: str, location: str, depth: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    reviews = int(company.get("review_count") or 38)
    rating = float(company.get("rating") or 4.8)
    evidence = {
        "primary_category": {"state": "good", "value": company.get("category"), "evidence": "Categoria principal identificada no perfil demonstrativo."},
        "additional_categories": {"state": "improve", "value": 1, "evidence": "Uma categoria adicional foi identificada; revise se há outras categorias realmente aplicáveis."},
        "description": {"state": "good", "value": 412, "evidence": "Descrição demonstrativa com 412 caracteres e informações específicas do negócio."},
        "phone": {"state": "good", "value": "(00) 00000-0000", "evidence": "Telefone presente no conjunto de demonstração."},
        "website": {"state": "good", "value": "https://exemplo.com.br", "evidence": "Site presente no conjunto de demonstração."},
        "hours": {"state": "good", "value": "Segunda a sexta", "evidence": "Horários informados para cinco dias."},
        "location": {"state": "good", "value": company.get("address"), "evidence": "Endereço identificado no conjunto de demonstração."},
        "products_services": {"state": "absent", "value": 0, "evidence": "A fixture confirma ausência de produtos e serviços; esta afirmação vale apenas para a demonstração."},
        "attributes": {"state": "improve", "value": 1, "evidence": "Um atributo foi identificado; confirme se outros atributos verdadeiros são relevantes."},
        "photos": {"state": "good", "value": 34, "evidence": "A fixture contém uma contagem total demonstrativa de 34 fotos."},
        "verification": {"state": "good", "value": True, "evidence": "A fixture fornece evidência explícita de perfil reivindicado."},
        "posts": {"state": "improve", "value": (now - timedelta(days=47)).date().isoformat(), "evidence": "Última postagem demonstrativa observada há 47 dias."},
        "rating": {"state": "good", "value": rating, "evidence": f"Nota demonstrativa observada: {rating:.1f}."},
        "review_volume": {"state": "good", "value": reviews, "evidence": f"{reviews} avaliações contra mediana demonstrativa de 12 concorrentes."},
        "review_recency": {"state": "improve", "value": 94, "evidence": "Avaliação mais recente da fixture foi publicada há 94 dias."},
        "review_responses": {"state": "good", "value": "17/20", "evidence": "17 de 20 avaliações demonstrativas analisadas possuem resposta."},
    }
    competitors = [
        {"position": 1, "name": company.get("name"), "rating": rating, "review_count": reviews, "place_id": company.get("place_id"), "is_paid": False},
        {"position": 2, "name": "Concorrente Aurora", "address": f"Centro, {location or 'Brasil'}", "category": company.get("category"), "rating": 4.7, "review_count": 21, "place_id": "demo-comp-1", "is_paid": False},
        {"position": 3, "name": "Concorrente Horizonte", "address": f"Região Norte, {location or 'Brasil'}", "category": company.get("category"), "rating": 4.6, "review_count": 12, "place_id": "demo-comp-2", "is_paid": False},
        {"position": 4, "name": "Concorrente Prisma", "address": f"Região Sul, {location or 'Brasil'}", "category": company.get("category"), "rating": 4.3, "review_count": 8, "place_id": "demo-comp-3", "is_paid": False},
        {"position": 5, "name": "Concorrente Vértice", "address": f"Região Leste, {location or 'Brasil'}", "category": company.get("category"), "rating": 4.2, "review_count": 7, "place_id": "demo-comp-4", "is_paid": False},
        {"position": 6, "name": "Concorrente Origem", "address": f"Região Oeste, {location or 'Brasil'}", "category": company.get("category"), "rating": 4.1, "review_count": 5, "place_id": "demo-comp-5", "is_paid": False},
    ]
    return {
        "evidence": evidence,
        "profile": {**company, "rating": rating, "review_count": reviews, "maps_url": company.get("maps_url") or "https://www.google.com/maps"},
        "competition": {"keyword": keyword or f"{company.get('category', 'empresa')} em {location or 'Brasil'}", "location": location or "Brasil", "language_code": "pt", "depth": depth, "provider": "demo", "position": 1, "sample_size": len(competitors), "median_review_count": median([entry["review_count"] for entry in competitors[1:]]), "competitors": competitors[1:]},
        "cost": {"searches_used": 0, "estimated_usd": 0, "actual_usd": 0},
        "limitations": ["Relatório demonstrativo: nenhum dado foi consultado em fornecedor externo.", "Nomes, métricas e concorrentes são fictícios e servem apenas para validar a experiência."],
    }
