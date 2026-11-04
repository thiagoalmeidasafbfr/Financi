"""Lançamento rápido (despesa ou receita, já acontecida ou prevista): categorias mais usadas e palpite de categoria."""
from collections import Counter
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..categorize import load_rules
from ..db import get_session
from ..models import Account, Category, Planned, Transaction
from ..text import merchant_key, normalize_description

router = APIRouter(prefix="/api/quick", tags=["lançamento rápido"])

# completam a lista quando ainda há pouco histórico
DEFAULTS = {
    "despesa": ["Supermercado", "Restaurantes", "Delivery", "Combustível", "Farmácia", "Apps de transporte", "Lazer e passeios",
                "Compras online"],
    "receita": ["Salário", "Freelance e extras", "Reembolsos", "Bônus e PLR", "Rendimentos", "Outras receitas"],
}
TOP = 8


@router.get("")
def quick(db: Session = Depends(get_session)):
    """Categorias mais usadas por tipo (últimos 6 meses e previstos) e a conta usada no último lançamento à mão."""
    since = date.today() - timedelta(days=180)  # noqa: DTZ011
    uses = Counter(dict(db.execute(select(Transaction.category_id, func.count()).where(
        Transaction.date >= since, Transaction.category_id.is_not(None)).group_by(Transaction.category_id)).all()))
    uses.update(c for c in db.scalars(select(Planned.category_id).where(Planned.category_id.is_not(None))))
    cats = list(db.scalars(select(Category).where(Category.active.is_(True)).order_by(Category.sort_order, Category.name)))
    frequent = {}
    for kind, names in DEFAULTS.items():
        mine = [c for c in cats if c.type == kind]
        ranked = sorted((c for c in mine if uses[c.id]), key=lambda c: -uses[c.id])
        ranked += [c for n in names for c in mine if c.name == n and c not in ranked]
        frequent[kind] = [c.id for c in ranked[:TOP]]
    last = db.scalar(select(Transaction.account_id).where(Transaction.dedupe_key.like("manual-%"))
                     .order_by(Transaction.id.desc()).limit(1))
    if last is None:
        last = db.scalar(select(Account.id).where(Account.active.is_(True)).order_by(Account.kind == "cartao", Account.id).limit(1))
    return {"frequent": frequent, "account_id": last}


@router.get("/guess")
def guess(description: str, kind: str = "despesa", db: Session = Depends(get_session)):
    """Categoria provável pela descrição: um previsto com o mesmo nome ou as regras de categorização."""
    text = description.strip()
    if len(text) < 3:
        return {"category_id": None}
    want = normalize_description(text)
    for p in db.scalars(select(Planned).where(Planned.category_id.is_not(None), Planned.kind == kind)):
        if normalize_description(p.name) == want:
            return {"category_id": p.category_id}
    rule = load_rules(db).match(merchant_key(text), text)
    if rule:
        cat = db.get(Category, rule.category_id)
        if cat and cat.type == kind:
            return {"category_id": cat.id}
    return {"category_id": None}
