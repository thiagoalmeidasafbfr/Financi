"""Lançamentos previstos: cadastro, fluxo futuro, atrasos e ajustes de uma ocorrência (valor, mês, pulado, pago)."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import finance as fin
from .. import planned as pl
from .. import schemas
from ..db import get_session
from ..models import Category, Planned, PlannedChange
from ..services import accounts_for
from ..text import normalize_description

router = APIRouter(prefix="/api/planned", tags=["previstos"])


def _today() -> date:
    return date.today()  # noqa: DTZ011


def _apply(p: Planned, data: schemas.PlannedIn, db: Session) -> None:
    if data.category_id is not None and db.get(Category, data.category_id) is None:
        raise HTTPException(400, "Categoria não existe")
    start = fin.month_start(data.start_month)
    end = fin.month_start(data.end_month) if data.end_month and data.recurrence == "mensal" else None
    if end and end < start:
        raise HTTPException(400, "O mês final vem antes do inicial")
    for k, v in data.model_dump().items():
        setattr(p, k, v)
    p.start_month, p.end_month = start, end
    p.match_pattern = (data.match_pattern or "").strip() or None


def _get(db: Session, pid: int) -> Planned:
    p = db.get(Planned, pid)
    if p is None:
        raise HTTPException(404, "Previsto não encontrado")
    return p


@router.get("", response_model=list[schemas.PlannedOut])
def list_planned(db: Session = Depends(get_session)):
    return db.scalars(select(Planned).order_by(Planned.start_month, Planned.name)).all()


@router.post("", response_model=schemas.PlannedOut, status_code=201)
def create_planned(data: schemas.PlannedIn, db: Session = Depends(get_session)):
    p = Planned()
    _apply(p, data, db)
    db.add(p)
    db.commit()
    return p


@router.put("/{pid}", response_model=schemas.PlannedOut)
def update_planned(pid: int, data: schemas.PlannedIn, db: Session = Depends(get_session)):
    p = _get(db, pid)
    _apply(p, data, db)
    db.commit()
    return p


@router.delete("/{pid}", status_code=204)
def delete_planned(pid: int, db: Session = Depends(get_session)):
    db.delete(_get(db, pid))
    db.commit()


@router.get("/flow")
def get_flow(months: int = 12, person: str | None = None, db: Session = Depends(get_session)):
    acc_ids = [a.id for a in accounts_for(db, person)]
    return pl.flow(db, _today(), max(1, min(months, 36)), person, acc_ids)


@router.put("/{pid}/occurrence")
def change_occurrence(pid: int, data: schemas.OccurrenceChange, db: Session = Depends(get_session)):
    """Muda só uma ocorrência. Numa previsão pontual, mover ou mudar o valor altera a própria previsão."""
    p = _get(db, pid)
    month = fin.month_start(data.month)
    sent = data.model_fields_set
    if p.recurrence == "pontual":
        if month != p.start_month:
            raise HTTPException(400, "Mês não pertence a esta previsão")
        ch = next((c for c in p.changes if c.month == month), None)
        if "moved_to" in sent and data.moved_to:
            p.start_month = fin.month_start(data.moved_to)
            if ch:
                ch.month = p.start_month
        if "amount" in sent and data.amount:
            p.amount = data.amount
        if data.reset and ch:
            db.delete(ch)
        elif sent & {"skipped", "paid"}:
            if ch is None:
                ch = PlannedChange(planned=p, month=p.start_month)
                db.add(ch)
            if "skipped" in sent:
                ch.skipped = bool(data.skipped)
            if "paid" in sent:
                ch.paid = data.paid
                ch.paid_on = _today() if data.paid else None
        db.commit()
        return {"ok": True}

    if month < pl._floor(p) or (p.end_month and month > p.end_month) or month < p.start_month:
        raise HTTPException(400, "Mês fora do período desta previsão")
    ch = next((c for c in p.changes if c.month == month), None)
    if data.reset:
        if ch:
            db.delete(ch)
        db.commit()
        return {"ok": True}
    if ch is None:
        ch = PlannedChange(planned=p, month=month)
        db.add(ch)
    if "amount" in sent:
        ch.amount = data.amount
    if "moved_to" in sent:
        target = fin.month_start(data.moved_to) if data.moved_to else None
        ch.moved_to = None if target == month else target
    if "skipped" in sent:
        ch.skipped = bool(data.skipped)
    if "paid" in sent:
        ch.paid = data.paid
        ch.paid_on = _today() if data.paid else None  # o gasto conta no mês em que foi pago
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- edição pela tabela mês a mês (toque numa célula)

class MonthEdit(BaseModel):
    """Novo valor do previsto `name` no mês. scope "mes": só neste mês; "diante": deste mês até o fim da previsão
    (ou, se não houver previsão mensal no mês, uma nova todo mês a partir dele). Valor 0 em "mes" pula o mês."""
    name: str
    month: date
    amount: float = Field(ge=0)
    scope: str = "mes"


def _norm(s: str) -> str:
    return normalize_description(s or "")


def _month_occ(db: Session, name: str, month: date) -> list[pl.Occurrence]:
    return [o for o in pl.occurrences(db, _today(), month, month) if _norm(o.name) == _norm(name)]


def _series_at(db: Session, name: str, month: date) -> Planned | None:
    """A previsão mensal de mesmo nome que cobre o mês."""
    for p in db.scalars(select(Planned).where(Planned.active.is_(True), Planned.recurrence == "mensal")
                        .order_by(Planned.start_month.desc())):
        if _norm(p.name) == _norm(name) and p.start_month <= month and (p.end_month is None or p.end_month >= month):
            return p
    return None


def _later(db: Session, name: str, month: date) -> bool:
    """Há ocorrência deste nome depois do mês? (para não sobrepor previsões ao criar uma nova série)"""
    end = fin.add_months(month, 120)
    return any(_norm(o.name) == _norm(name) for o in pl.occurrences(db, _today(), fin.add_months(month, 1), end))


@router.get("/month-info")
def month_info(name: str, month: date, db: Session = Depends(get_session)):
    m = fin.month_start(month)
    occ = _month_occ(db, name, m)
    series = _series_at(db, name, m)
    return {
        "occurrence": occ[0].as_dict() if occ else None,
        "series": {"id": series.id, "amount": series.amount, "start_month": series.start_month.isoformat(),
                   "end_month": series.end_month.isoformat() if series.end_month else None} if series else None,
        # "deste mês em diante": dentro de uma série mensal, ou criando uma nova se nada vem depois
        "can_forward": bool(series) or not _later(db, name, m),
    }


@router.post("/edit-month")
def edit_month(data: MonthEdit, db: Session = Depends(get_session)):
    m = fin.month_start(data.month)
    template = next((p for p in db.scalars(select(Planned).order_by(Planned.start_month.desc())) if _norm(p.name) == _norm(data.name)), None)
    if template is None:
        raise HTTPException(404, "Previsto não encontrado")
    occ = _month_occ(db, data.name, m)
    if data.scope == "mes":
        if occ:
            o = occ[0]
            p = _get(db, o.planned_id)
            orig = date.fromisoformat(o.original)
            if p.recurrence == "pontual":
                if data.amount > 0:
                    p.amount = data.amount
                else:
                    db.delete(p)
            else:
                ch = next((c for c in p.changes if c.month == orig), None) or PlannedChange(planned=p, month=orig)
                db.add(ch)
                ch.skipped = data.amount == 0
                ch.amount = None if data.amount == 0 or abs(data.amount - p.amount) < 0.005 else data.amount
        elif data.amount > 0:
            db.add(_clone(template, amount=data.amount, recurrence="pontual", start_month=m, end_month=None))
        db.commit()
        return {"ok": True}
    if data.scope != "diante":
        raise HTTPException(400, "Escopo inválido")
    series = _series_at(db, data.name, m)
    if series is None:
        if _later(db, data.name, m):
            raise HTTPException(400, "Já existe previsão deste nome depois deste mês: mude só este mês ou edite a previsão")
        for o in occ:  # a pontual deste mês vira parte da série nova
            p = db.get(Planned, o.planned_id)
            if p and p.recurrence == "pontual":
                db.delete(p)
        if data.amount > 0:
            db.add(_clone(template, amount=data.amount, recurrence="mensal", start_month=m, end_month=None))
        db.commit()
        return {"ok": True}
    if data.amount == 0:  # zerar daqui em diante: a previsão termina no mês anterior
        if series.start_month >= m:
            db.delete(series)
        else:
            series.end_month = fin.add_months(m, -1)
            for ch in list(series.changes):
                if ch.month >= m:
                    db.delete(ch)
        db.commit()
        return {"ok": True}
    if series.start_month >= m:
        series.amount = data.amount
        target = series
    else:
        target = _clone(series, amount=data.amount, start_month=m, end_month=series.end_month)
        db.add(target)
        series.end_month = fin.add_months(m, -1)
        for ch in list(series.changes):  # ajustes de meses daqui em diante passam para a série nova
            if ch.month >= m:
                ch.planned = target
    for ch in target.changes:
        if ch.month == m:  # o valor novo vale a partir deste mês, sem ajuste antigo por cima
            ch.amount, ch.skipped = None, False
    db.commit()
    return {"ok": True}


def _clone(p: Planned, **over) -> Planned:
    fields = {k: getattr(p, k) for k in ("name", "kind", "category_id", "amount", "recurrence", "start_month", "end_month",
                                         "due_day", "owner_id", "match_pattern", "notes", "active")}
    fields.update(over)
    q = Planned(**fields)
    q.created_at = datetime.combine(min(fields["start_month"], _today()), datetime.min.time())  # vale desde o início
    return q
