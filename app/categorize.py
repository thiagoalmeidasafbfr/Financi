"""Categorização: regras (aprendidas > manuais > IA > padrão) e, para o que sobrar, IA."""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ai
from .models import Account, Category, Rule, Transaction
from .text import normalize_description

# ordem de prioridade entre regras do tipo "contains" (as exatas sempre vêm antes)
SOURCE_RANK = {"aprendida": 0, "manual": 0, "ia": 1, "padrao": 2}
AI_RULE_CONFIDENCE = 0.9  # acima disso a resposta da IA vira regra para as próximas importações


@dataclass
class _Compiled:
    rule: Rule
    regex: re.Pattern


class RuleSet:
    def __init__(self, rules: list[Rule]):
        self.exact = {r.pattern: r for r in rules if r.match == "exact"}
        contains = [r for r in rules if r.match == "contains"]
        # mais específicas primeiro: prioridade da origem, depois o trecho mais longo
        contains.sort(key=lambda r: (SOURCE_RANK.get(r.source, 3), -len(r.pattern.strip())))
        self.contains = [_Compiled(r, _regex(r.pattern)) for r in contains]

    def match(self, merchant: str, description: str) -> Rule | None:
        if merchant in self.exact:
            return self.exact[merchant]
        hay = f"{normalize_description(description)} | {merchant}"
        for c in self.contains:
            if c.regex.search(hay):
                return c.rule
        return None


def _regex(pattern: str) -> re.Pattern:
    """Trecho no começo de uma palavra ('DROGA' pega 'DROGASIL'); terminado em espaço exige a palavra inteira."""
    p = normalize_description(pattern)
    tail = r"\b" if pattern.endswith(" ") else ""
    return re.compile(r"(?<![A-Z0-9])" + re.escape(p) + tail)


def load_rules(db: Session) -> RuleSet:
    return RuleSet(list(db.scalars(select(Rule))))


def apply_rules(db: Session, txs: list[Transaction], rules: RuleSet | None = None) -> int:
    rules = rules or load_rules(db)
    n = 0
    for tx in txs:
        r = rules.match(tx.merchant, tx.description)
        if r:
            tx.category_id = r.category_id
            tx.categorized_by = "padrao" if r.source == "padrao" else "regra"
            tx.confidence = None
            r.hits = (r.hits or 0) + 1
            n += 1
    return n


def apply_ai(db: Session, txs: list[Transaction], client=None) -> int:
    """Categoriza por IA os lançamentos sem categoria; resposta muito confiante vira regra."""
    pending = [t for t in txs if t.category_id is None]
    if not pending or (client is None and not ai.available()):
        return 0
    cats = list(db.scalars(select(Category).where(Category.active.is_(True))))
    by_name = {c.name: c for c in cats}
    kinds = {a.id: a.kind for a in db.scalars(select(Account))}
    items = [{"i": i, "descricao": t.description, "valor": t.amount, "data": t.date.isoformat(),
              "conta": kinds.get(t.account_id, "corrente")} for i, t in enumerate(pending)]
    result = ai.categorize(items, [{"name": c.name, "type": c.type, "group": c.group} for c in cats], client=client)
    n = 0
    known = {(r.pattern, r.match) for r in db.scalars(select(Rule))}
    for i, (name, conf) in result.items():
        cat = by_name.get(name)
        if not cat:
            continue
        t = pending[i]
        t.category_id, t.categorized_by, t.confidence = cat.id, "ia", conf
        n += 1
        if conf >= AI_RULE_CONFIDENCE and (t.merchant, "exact") not in known:
            db.add(Rule(pattern=t.merchant, match="exact", category_id=cat.id, source="ia"))
            known.add((t.merchant, "exact"))
    return n


def learn(db: Session, tx: Transaction, category_id: int, apply_to_similar: bool = True) -> int:
    """Correção manual: vira regra do estabelecimento e corrige os lançamentos parecidos ainda não revisados."""
    rule = db.scalar(select(Rule).where(Rule.pattern == tx.merchant, Rule.match == "exact"))
    if rule is None:
        rule = Rule(pattern=tx.merchant, match="exact", category_id=category_id, source="aprendida")
        db.add(rule)
    else:
        rule.category_id, rule.source = category_id, "aprendida"
    tx.category_id, tx.categorized_by, tx.confidence, tx.reviewed = category_id, "manual", None, True
    if not apply_to_similar:
        return 0
    similar = db.scalars(select(Transaction).where(
        Transaction.merchant == tx.merchant, Transaction.id != tx.id, Transaction.reviewed.is_(False))).all()
    for s in similar:
        s.category_id, s.categorized_by, s.confidence = category_id, "regra", None
    return len(similar)
