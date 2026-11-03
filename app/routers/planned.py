"""Lançamentos previstos: cadastro, fluxo futuro, atrasos e ajustes de uma ocorrência (valor, mês, pulado, pago)."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import finance as fin
from .. import planned as pl
from .. import schemas
from ..db import get_session
from ..models import Category, Planned, PlannedChange
from ..services import accounts_for

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
    db.commit()
    return {"ok": True}
