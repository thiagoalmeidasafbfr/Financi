"""Orçamento, projeção de caixa, painel inicial e dívidas."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import ai, schemas
from .. import finance as fin
from .. import planned as planned_mod
from ..db import get_session
from ..models import Budget, Category, Debt, Transaction
from ..services import (
    accounts_for,
    balances,
    debts_summary,
    month_view,
    projection,
    suggest_budgets,
)

router = APIRouter(prefix="/api", tags=["planejamento"])


def _today() -> date:
    return date.today()  # noqa: DTZ011


# ---------------------------------------------------------------- orçamento
@router.get("/budget")
def get_budget(month: date | None = None, person: str | None = None, db: Session = Depends(get_session)):
    return month_view(db, month or _today(), person)


@router.put("/budgets")
def put_budgets(items: list[schemas.BudgetIn], db: Session = Depends(get_session)):
    for it in items:
        if db.get(Category, it.category_id) is None:
            raise HTTPException(400, f"Categoria {it.category_id} não existe")
        m = fin.month_start(it.month) if it.month else None
        cond = Budget.month.is_(None) if m is None else Budget.month == m
        row = db.scalar(select(Budget).where(Budget.category_id == it.category_id, cond))
        if it.amount is None:
            if row:
                db.delete(row)
        elif row:
            row.amount = it.amount
        else:
            db.add(Budget(category_id=it.category_id, month=m, amount=it.amount))
    db.commit()
    return {"saved": len(items)}


@router.get("/budgets")
def list_budgets(db: Session = Depends(get_session)):
    return [{"category_id": b.category_id, "month": b.month.isoformat() if b.month else None, "amount": b.amount}
            for b in db.scalars(select(Budget))]


@router.get("/budget/suggest")
def budget_suggestions(month: date | None = None, person: str | None = None, db: Session = Depends(get_session)):
    return suggest_budgets(db, month or _today(), person)


@router.get("/projection")
def get_projection(months: int = 6, person: str | None = None, db: Session = Depends(get_session)):
    return projection(db, person, _today(), max(1, min(months, 24)))


# ---------------------------------------------------------------- dívidas
@router.get("/debts/overview")
def get_debts_overview(person: str | None = None, db: Session = Depends(get_session)):
    return debts_summary(db, person, _today())


@router.get("/debts", response_model=list[schemas.DebtOut])
def list_debts(db: Session = Depends(get_session)):
    return db.scalars(select(Debt).order_by(Debt.id)).all()


@router.post("/debts", response_model=schemas.DebtOut, status_code=201)
def create_debt(data: schemas.DebtIn, db: Session = Depends(get_session)):
    d = Debt(**data.model_dump())
    db.add(d)
    db.commit()
    return d


@router.put("/debts/{did}", response_model=schemas.DebtOut)
def update_debt(did: int, data: schemas.DebtIn, db: Session = Depends(get_session)):
    d = db.get(Debt, did)
    if d is None:
        raise HTTPException(404, "Dívida não encontrada")
    for k, v in data.model_dump().items():
        setattr(d, k, v)
    db.commit()
    return d


@router.delete("/debts/{did}", status_code=204)
def delete_debt(did: int, db: Session = Depends(get_session)):
    d = db.get(Debt, did)
    if d is None:
        raise HTTPException(404, "Dívida não encontrada")
    db.delete(d)
    db.commit()


# ---------------------------------------------------------------- painel
@router.get("/dashboard")
def dashboard(person: str | None = None, month: date | None = None, db: Session = Depends(get_session)):
    today = _today()
    accs = accounts_for(db, person)
    acc_ids = [a.id for a in accs]
    m = fin.month_start(month or today)
    if month is None and acc_ids:
        # extratos chegam depois do fim do mês: sem lançamentos no mês corrente, mostra o último mês com dados
        has_current = db.scalar(select(func.count()).select_from(Transaction).where(
            Transaction.account_id.in_(acc_ids), Transaction.date >= m))
        last = db.scalar(select(func.max(Transaction.date)).where(Transaction.account_id.in_(acc_ids)))
        if not has_current and last:
            m = fin.month_start(last)
    bal = balances(db, accs)
    view = month_view(db, m, person)
    debts = debts_summary(db, person, today)
    cats = {c.id: c for c in db.scalars(select(Category))}
    # últimos 6 meses de despesas por grupo (minigráficos)
    start = fin.add_months(m, -5)
    rows = db.execute(select(Transaction.category_id, func.extract("year", Transaction.date),
                             func.extract("month", Transaction.date), func.sum(Transaction.amount))
                      .where(Transaction.account_id.in_(acc_ids), Transaction.date >= start,
                             Transaction.date < fin.add_months(m, 1))
                      .group_by(Transaction.category_id, func.extract("year", Transaction.date),
                                func.extract("month", Transaction.date))).all() if acc_ids else []
    months = [fin.add_months(start, k).isoformat() for k in range(6)]
    groups: dict[str, list[float]] = {}
    for cid, y, mo, total in rows:
        cat = cats.get(cid)
        if cat is not None and cat.type != "despesa":
            continue
        g = cat.group if cat else "Sem categoria"
        i = months.index(date(int(y), int(mo), 1).isoformat())
        groups.setdefault(g, [0.0] * 6)[i] += -float(total)
    top = sorted(groups.items(), key=lambda kv: -kv[1][-1])[:6]
    late = planned_mod.overdue(db, today, person, acc_ids)
    # panorama: projeção curta, próximos vencimentos (30 dias) e previstos do mês corrente
    proj = projection(db, person, today, 6)
    pm = [{"month": r["month"], "saldo": r["saldo"]} for r in proj["months"]]
    current = fin.month_start(today)
    occ = planned_mod.occurrences(db, today, current, fin.add_months(current, 1), person, acc_ids)
    horizon = (today + timedelta(days=30)).isoformat()
    upcoming = [o.as_dict() for o in occ if o.status == "pendente" and today.isoformat() <= o.due <= horizon][:8]
    this_month = [o for o in occ if o.month == current.isoformat() and o.status != "pulado"]
    uncategorized = db.scalar(select(func.count()).select_from(Transaction)
                              .where(Transaction.account_id.in_(acc_ids), Transaction.category_id.is_(None))) if acc_ids else 0
    return {
        "month": m.isoformat(),
        "accounts": [{"id": a.id, "name": a.name, "kind": a.kind, "owner_id": a.owner_id, "balance": bal.get(a.id, 0.0)}
                     for a in accs],
        "saldo_contas": round(sum(bal.get(a.id, 0.0) for a in accs if a.kind in ("corrente", "poupanca", "dinheiro")), 2),
        "investido": round(sum(bal.get(a.id, 0.0) for a in accs if a.kind == "investimento"), 2),
        "month_totals": view["totals"],
        "budget_rows": view["rows"][:12],
        "groups": [{"group": g, "months": months, "values": [round(v, 2) for v in vals]} for g, vals in top],
        "cards": [{"name": c["name"], "invoice": c["current_invoice"], "future_total": c["future_total"],
                   "configured": c["configured"]} for c in debts["cards"]],
        "debts_totals": debts["totals"],
        "uncategorized": uncategorized,
        "overdue": {"count": len(late), "total": round(sum(o.amount for o in late if o.kind == "despesa"), 2),
                    "items": [o.as_dict() for o in late[:5]]},
        "projecao": {"saldo_inicial": proj["saldo_inicial"], "meses": pm,
                     "menor": min(pm, key=lambda r: r["saldo"]) if pm else None},
        "proximos": upcoming,
        "previstos_mes": {"receitas": round(sum(o.amount for o in this_month if o.kind == "receita"), 2),
                          "despesas": round(sum(o.amount for o in this_month if o.kind == "despesa"), 2)},
        "ai_enabled": ai.available(),
    }
