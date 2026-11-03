"""Categorização por IA (Claude) dos lançamentos que nenhuma regra reconheceu.

Só roda com ANTHROPIC_API_KEY configurada; sem ela (ou em qualquer erro) devolve vazio e a
importação segue só com as regras."""
from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("financi.ai")

MODEL = "claude-opus-5-5"
BATCH = 60  # lançamentos por requisição

SYSTEM = (
    "Você categoriza lançamentos de extratos bancários e faturas de cartão brasileiros de uma família. "
    "Para cada lançamento escolha a categoria mais provável da lista fornecida, usando o nome do "
    "estabelecimento, o tipo de conta e o sinal do valor (negativo = saída, positivo = entrada). "
    "Pagamentos de fatura de cartão e transferências entre contas próprias são do tipo transferência, "
    "não despesa nem receita. Use \"Sem categoria\" quando não houver pistas suficientes; não invente. "
    "Em confidence informe de 0 a 1 o quanto você tem certeza."
)


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _schema(category_names: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "i": {"type": "integer"},
                        "category": {"type": "string", "enum": [*category_names, "Sem categoria"]},
                        "confidence": {"type": "number"},
                    },
                    "required": ["i", "category", "confidence"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }


def categorize(items: list[dict], categories: list[dict], client=None) -> dict[int, tuple[str, float]]:
    """items: [{i, descricao, valor, data, conta}] → {i: (nome da categoria, confiança)}.

    categories: [{name, type, group}]. `client` permite injetar um cliente nos testes."""
    if not items or (client is None and not available()):
        return {}
    if client is None:
        import anthropic

        client = anthropic.Anthropic()
    names = [c["name"] for c in categories]
    catalog = "\n".join(f"- {c['name']} ({c['type']}, grupo {c['group']})" for c in categories)
    out: dict[int, tuple[str, float]] = {}
    for start in range(0, len(items), BATCH):
        chunk = items[start:start + BATCH]
        prompt = (f"Categorias disponíveis:\n{catalog}\n\nLançamentos (JSON):\n"
                  f"{json.dumps(chunk, ensure_ascii=False)}\n\nResponda com um item por lançamento, usando o mesmo i.")
        try:
            response = client.beta.messages.create(
                model=MODEL,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",  # se o modelo recusar, a API refaz no modelo de fallback recomendado
                system=SYSTEM,
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": _schema(names)}},
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # noqa: BLE001  (a IA é opcional: qualquer falha cai nas regras)
            log.warning("categorização por IA falhou: %s", exc)
            continue
        if response.stop_reason in ("refusal", "max_tokens"):
            log.warning("IA não categorizou o lote (stop_reason=%s)", response.stop_reason)
            continue
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            log.warning("resposta da IA não é JSON válido")
            continue
        valid = {it["i"] for it in chunk}
        for row in data.get("items", []):
            if row.get("i") in valid and row.get("category") in names:
                out[row["i"]] = (row["category"], float(row.get("confidence") or 0))
    return out
