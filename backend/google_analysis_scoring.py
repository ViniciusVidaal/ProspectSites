"""Deterministic and versioned Google Business Profile scoring for ProspectSites."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


METHODOLOGY_VERSION = "1.0.0"
MINIMUM_COVERAGE = 60.0


@dataclass(frozen=True)
class Rule:
    key: str
    label: str
    weight: int
    action: str


RULES = (
    Rule("primary_category", "Categoria principal", 8, "Confirme se a categoria principal representa o serviço mais importante."),
    Rule("additional_categories", "Categorias adicionais", 5, "Inclua apenas categorias adicionais realmente oferecidas pelo negócio."),
    Rule("description", "Descrição", 7, "Escreva uma descrição clara, específica e fiel ao negócio."),
    Rule("phone", "Telefone", 6, "Cadastre um telefone ativo e acompanhe as chamadas recebidas."),
    Rule("website", "Site ou link", 6, "Adicione um link oficial, rápido e compatível com celular."),
    Rule("hours", "Horário", 7, "Mantenha horários regulares e especiais atualizados."),
    Rule("location", "Endereço ou área de serviço", 6, "Revise o endereço ou configure corretamente a área de atendimento."),
    Rule("products_services", "Produtos e serviços", 7, "Apresente os principais produtos ou serviços quando o recurso estiver disponível."),
    Rule("attributes", "Atributos", 4, "Preencha somente atributos verdadeiros e relevantes."),
    Rule("photos", "Fotos", 7, "Publique fotos atuais, nítidas e representativas do negócio."),
    Rule("verification", "Situação de verificação", 5, "Confirme a propriedade do perfil pelos meios oficiais do Google."),
    Rule("posts", "Postagens recentes", 6, "Use postagens para divulgar novidades e informações atuais."),
    Rule("rating", "Nota dos clientes", 7, "Investigue padrões nas avaliações e corrija causas recorrentes."),
    Rule("review_volume", "Quantidade de avaliações", 7, "Crie um processo ético e contínuo para solicitar avaliações reais."),
    Rule("review_recency", "Recência das avaliações", 7, "Busque avaliações recentes de clientes reais sem oferecer incentivos indevidos."),
    Rule("review_responses", "Respostas às avaliações", 5, "Responda avaliações recentes com contexto e cordialidade."),
)


VALID_STATES = {"good", "improve", "absent", "unknown", "not_applicable"}
STATE_LABELS = {
    "good": "Em dia",
    "improve": "Pode melhorar",
    "absent": "Ausência confirmada",
    "unknown": "Não foi possível verificar",
    "not_applicable": "Não se aplica",
}
STATE_FACTOR = {"good": 1.0, "improve": 0.5, "absent": 0.0}


def score_profile(evidence: dict[str, dict[str, Any]]) -> dict[str, Any]:
    checklist: list[dict[str, Any]] = []
    earned = evaluable = 0.0

    for rule in RULES:
        item = evidence.get(rule.key, {})
        state = str(item.get("state", "unknown"))
        if state not in VALID_STATES:
            state = "unknown"
        factor = STATE_FACTOR.get(state)
        points = round(rule.weight * factor, 2) if factor is not None else None
        if factor is not None:
            evaluable += rule.weight
            earned += points or 0
        checklist.append({
            "key": rule.key,
            "label": rule.label,
            "weight": rule.weight,
            "state": state,
            "state_label": STATE_LABELS[state],
            "points": points,
            "evidence": item.get("evidence") or "O fornecedor não devolveu evidência suficiente.",
            "value": item.get("value"),
            "action": item.get("action") or rule.action,
            "source": item.get("source") or "ProspectSites",
        })

    coverage = round(evaluable, 1)
    score = round(100 * earned / evaluable) if evaluable else None
    reliable = score is not None and coverage >= MINIMUM_COVERAGE
    priorities = [
        {
            "key": item["key"],
            "title": item["label"],
            "reason": item["evidence"],
            "action": item["action"],
            "impact": item["weight"],
        }
        for item in sorted(
            (entry for entry in checklist if entry["state"] in {"absent", "improve"}),
            key=lambda entry: (entry["key"] != "website", entry["state"] != "absent", -entry["weight"]),
        )[:3]
    ]
    if not priorities or priorities[0]["key"] != "website":
        website = next(item for item in checklist if item["key"] == "website")
        priorities.insert(0, {
            "key": "website", "title": "Site profissional",
            "reason": website["evidence"],
            "action": "Avalie um site profissional para apresentar a empresa e seus serviços.",
            "impact": website["weight"],
        })
        priorities = priorities[:3]
    return {
        "score": score,
        "coverage": coverage,
        "score_reliable": reliable,
        "minimum_coverage": MINIMUM_COVERAGE,
        "methodology_version": METHODOLOGY_VERSION,
        "checklist": checklist,
        "priorities": priorities,
        "improvements_count": sum(item["state"] in {"absent", "improve"} for item in checklist),
        "summary": (
            "Os dados avaliáveis indicam uma presença local forte, com oportunidades objetivas de melhoria."
            if reliable and (score or 0) >= 75
            else "Há oportunidades importantes para fortalecer a presença local."
            if reliable
            else "A coleta foi parcial. Consulte a cobertura e as limitações antes de interpretar o resultado."
        ),
    }


def methodology_payload() -> dict[str, Any]:
    return {
        "version": METHODOLOGY_VERSION,
        "minimum_coverage": MINIMUM_COVERAGE,
        "formula": "100 x pontos obtidos / pontos máximos avaliáveis",
        "coverage_formula": "pesos avaliáveis / 100",
        "rules": [{"key": rule.key, "label": rule.label, "weight": rule.weight} for rule in RULES],
        "disclaimer": "Os pesos são uma metodologia própria da ProspectSites e não são fatores oficiais de ranqueamento do Google.",
    }
