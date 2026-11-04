"""Cockpit: ações com liga/desliga (ajustes e quitação de dívidas) e o efeito delas no saldo projetado."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import cockpit, services
from .. import finance as fin
from ..db import get_session
from ..models import Action, ActionLine, Debt, Planned

router = APIRouter(prefix="/api/cockpit", tags=["cockpit"])


class LineIn(BaseModel):
    month: date
    label: str = Field(min_length=1, max_length=120)
    op: str = "somar"                  # somar | substituir
    direction: str = "entrada"         # entrada | saida (somar)
    amount: float | None = None
    factor: float | None = None
    base: str | None = None
    base_month: date | None = None
    target: str | None = None


class ActionIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    notes: str | None = None
    active: bool | None = None
    lines: list[LineIn] = []


class ToggleIn(BaseModel):
    active: bool


class PayoffIn(BaseModel):
    active: bool
    month: date | None = None


def _check_line(ln: LineIn) -> None:
    if ln.op not in ("somar", "substituir") or ln.direction not in ("entrada", "saida"):
        raise HTTPException(400, "Linha inválida")
    if ln.factor is None and ln.amount is None:
        raise HTTPException(400, f"“{ln.label}”: informe o valor ou a fração de um previsto")
    if ln.factor is not None and not ln.base:
        raise HTTPException(400, f"“{ln.label}”: escolha o previsto de referência")
    if ln.op == "substituir" and not ln.target:
        raise HTTPException(400, f"“{ln.label}”: escolha o previsto a substituir")


def _set_lines(a: Action, lines: list[LineIn]) -> None:
    for ln in lines:
        _check_line(ln)
    a.lines.clear()
    for i, ln in enumerate(lines):
        a.lines.append(ActionLine(
            position=i, month=fin.month_start(ln.month), label=ln.label.strip(), op=ln.op, direction=ln.direction,
            amount=abs(ln.amount) if ln.amount is not None else None, factor=ln.factor, base=ln.base,
            base_month=fin.month_start(ln.base_month) if ln.base_month else None, target=ln.target))


@router.get("")
def overview(months: int = 18, db: Session = Depends(get_session)):
    """Saldo projetado sem e com as ações ligadas, cada ação com o seu efeito e a quitação de cada dívida."""
    months = max(3, min(months, 48))
    today = date.today()  # noqa: DTZ011
    base = services.projection(db, None, today, months, actions=False)
    eff = cockpit.effects(db, today)
    with_ = services.projection(db, None, today, months, actions=eff) if eff else base
    series_base = [r["saldo"] for r in base["months"]]
    series_with = [r["saldo"] for r in with_["months"]]
    month_list = [r["month"] for r in base["months"]]

    def low(xs):
        i = min(range(len(xs)), key=xs.__getitem__)
        return {"value": xs[i], "month": month_list[i]}

    all_actions = cockpit.load(db, active_only=False)
    adjust = [a for a in all_actions if a.kind == "ajuste"]
    bases = cockpit.Bases(db, today, cockpit._months(adjust))
    actions = []
    for a in adjust:
        imp = cockpit.impact(db, today, a, bases)
        actions.append({"id": a.id, "name": a.name, "notes": a.notes, "active": a.active, "lines": imp["lines"],
                        "impact": {"total": imp["total"], "by_month": imp["by_month"]}})

    by_debt = {a.debt_id: a for a in all_actions if a.kind == "quitacao"}
    payoffs = []
    cur = fin.month_start(today)
    for d in db.scalars(select(Debt).where(Debt.active.is_(True)).order_by(Debt.id)):
        sched = cockpit.schedule(d, today)
        if not any(m >= cur for m in sched):
            continue
        a = by_debt.get(d.id)
        month = max(fin.month_start(a.month), cur) if a and a.month else fin.add_months(cur, 1)
        payoffs.append({"debt_id": d.id, "name": d.name, "creditor": d.creditor, "kind": d.kind, "installment": d.installment,
                        "monthly_rate": d.monthly_rate, "active": bool(a and a.active), "month": month.isoformat(),
                        **cockpit.payoff_info(d, month, today)})
    names = sorted({(p.name, p.kind) for p in db.scalars(select(Planned).where(Planned.active.is_(True)))})
    return {
        "months": month_list, "base": series_base, "with": series_with,
        "summary": {"final_base": series_base[-1], "final_with": series_with[-1], "low_base": low(series_base),
                    "low_with": low(series_with), "active": sum(1 for a in all_actions if a.active)},
        "actions": actions, "payoffs": payoffs,
        "previstos": [{"name": n, "kind": k} for n, k in names],
    }


@router.post("/actions", status_code=201)
def create_action(data: ActionIn, db: Session = Depends(get_session)):
    a = Action(name=data.name.strip(), notes=data.notes, kind="ajuste", active=bool(data.active),
               sort_order=(db.query(Action).count() + 1))
    _set_lines(a, data.lines)
    db.add(a)
    db.commit()
    return {"id": a.id}


def _get(db: Session, aid: int) -> Action:
    a = db.get(Action, aid)
    if a is None or a.kind != "ajuste":
        raise HTTPException(404, "Ação não encontrada")
    return a


@router.put("/actions/{aid}")
def update_action(aid: int, data: ActionIn, db: Session = Depends(get_session)):
    a = _get(db, aid)
    a.name, a.notes = data.name.strip(), data.notes
    if data.active is not None:
        a.active = data.active
    _set_lines(a, data.lines)
    db.commit()
    return {"id": a.id}


@router.patch("/actions/{aid}")
def toggle_action(aid: int, data: ToggleIn, db: Session = Depends(get_session)):
    a = _get(db, aid)
    a.active = data.active
    db.commit()
    return {"id": a.id, "active": a.active}


@router.delete("/actions/{aid}", status_code=204)
def delete_action(aid: int, db: Session = Depends(get_session)):
    db.delete(_get(db, aid))
    db.commit()


@router.put("/payoffs/{debt_id}")
def set_payoff(debt_id: int, data: PayoffIn, db: Session = Depends(get_session)):
    """Liga/desliga a quitação de uma dívida e escolhe o mês (uma ação por dívida)."""
    d = db.get(Debt, debt_id)
    if d is None:
        raise HTTPException(404, "Dívida não encontrada")
    a = db.scalar(select(Action).where(Action.kind == "quitacao", Action.debt_id == debt_id))
    if a is None:
        a = Action(name=f"Quitar {d.name}", kind="quitacao", debt_id=d.id)
        db.add(a)
    a.active = data.active
    if data.month:
        a.month = fin.month_start(data.month)
    elif a.month is None:
        a.month = fin.add_months(fin.month_start(date.today()), 1)  # noqa: DTZ011
    db.commit()
    return {"debt_id": d.id, "active": a.active, "month": a.month.isoformat()}


@router.get("/payoffs/{debt_id}")
def get_payoff(debt_id: int, month: date | None = None, db: Session = Depends(get_session)):
    """Quitação de uma dívida: se está ligada, em que mês, e quanto custa quitar em `month` (ou no mês marcado)."""
    d = db.get(Debt, debt_id)
    if d is None:
        raise HTTPException(404, "Dívida não encontrada")
    a = db.scalar(select(Action).where(Action.kind == "quitacao", Action.debt_id == debt_id))
    today = date.today()  # noqa: DTZ011
    cur = fin.month_start(today)
    when = fin.month_start(month) if month else (a.month if a and a.month else fin.add_months(cur, 1))
    when = max(when, cur)
    return {"debt_id": d.id, "name": d.name, "installment": d.installment, "active": bool(a and a.active),
            "month": a.month.isoformat() if a and a.month else None, "preview_month": when.isoformat(),
            **cockpit.payoff_info(d, when, today)}
