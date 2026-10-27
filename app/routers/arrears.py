"""Contas em atraso de cada cenário, com o plano de pagamento."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import engine as eng
from .. import schemas
from ..db import get_session
from ..models import Arrear, Scenario
from ..services import arrears_for

router = APIRouter(prefix="/api/scenarios/{scenario_id}/arrears", tags=["atrasos"])


def _scenario(db: Session, scenario_id: int) -> Scenario:
    sc = db.get(Scenario, scenario_id)
    if sc is None:
        raise HTTPException(404, "Cenário não encontrado")
    return sc


def _get(db: Session, scenario_id: int, arrear_id: int) -> Arrear:
    a = db.get(Arrear, arrear_id)
    if a is None or a.scenario_id != scenario_id:
        raise HTTPException(404, "Atraso não encontrado neste cenário")
    return a


def _fields(data: schemas.ArrearIn) -> dict:
    d = data.model_dump()
    if d["plan_start"] is not None:
        d["plan_start"] = eng.month_start(d["plan_start"])
    if d["status"] == "pago":
        d["paid_date"] = d["paid_date"] or date.today()
    return d


@router.get("")
def list_arrears(scenario_id: int, today: date | None = None, db: Session = Depends(get_session)):
    """Atrasos do cenário com valor atualizado (multa + juros até hoje) e o plano de pagamento."""
    _scenario(db, scenario_id)
    ref = today or date.today()
    calc = eng.arrears_summary(arrears_for(db, scenario_id), ref)
    by_id = {i["id"]: i for i in calc["items"]}
    rows = db.scalars(select(Arrear).where(Arrear.scenario_id == scenario_id)
                      .order_by(Arrear.status, Arrear.due_date, Arrear.id))
    items = [{**schemas.ArrearOut.model_validate(a).model_dump(mode="json"), **by_id[a.id]} for a in rows]
    return {"today": ref.isoformat(), "items": items, "totals": calc["totals"]}


@router.post("", response_model=schemas.ArrearOut, status_code=201)
def create_arrear(scenario_id: int, data: schemas.ArrearIn, db: Session = Depends(get_session)):
    _scenario(db, scenario_id)
    a = Arrear(scenario_id=scenario_id, **_fields(data))
    db.add(a)
    db.commit()
    return a


@router.put("/{arrear_id}", response_model=schemas.ArrearOut)
def update_arrear(scenario_id: int, arrear_id: int, data: schemas.ArrearIn, db: Session = Depends(get_session)):
    a = _get(db, scenario_id, arrear_id)
    for k, v in _fields(data).items():
        setattr(a, k, v)
    db.commit()
    return a


@router.delete("/{arrear_id}", status_code=204)
def delete_arrear(scenario_id: int, arrear_id: int, db: Session = Depends(get_session)):
    db.delete(_get(db, scenario_id, arrear_id))
    db.commit()
