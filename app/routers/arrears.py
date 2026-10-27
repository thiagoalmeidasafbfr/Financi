"""Contas em atraso e o plano de pagamento de cada cenário."""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import engine as eng
from .. import schemas
from ..db import get_session
from ..models import Arrear, ArrearPlan, Scenario
from ..services import arrears_for

router = APIRouter(prefix="/api", tags=["atrasos"])


def _get(db: Session, arrear_id: int) -> Arrear:
    a = db.get(Arrear, arrear_id)
    if a is None:
        raise HTTPException(404, "Atraso não encontrado")
    return a


@router.get("/arrears")
def list_arrears(scenario_id: int | None = None, today: date | None = None, db: Session = Depends(get_session)):
    """Atrasos com valor atualizado (multa + juros até hoje) e o plano do cenário informado."""
    if scenario_id is not None and db.get(Scenario, scenario_id) is None:
        raise HTTPException(404, "Cenário não encontrado")
    ref = today or date.today()
    calc = eng.arrears_summary(arrears_for(db, scenario_id), ref)
    by_id = {i["id"]: i for i in calc["items"]}
    plans = {}
    if scenario_id is not None:
        plans = {p.arrear_id: p for p in db.scalars(select(ArrearPlan).where(ArrearPlan.scenario_id == scenario_id))}
    items = []
    for a in db.scalars(select(Arrear).order_by(Arrear.status, Arrear.due_date, Arrear.id)):
        p = plans.get(a.id)
        items.append({**schemas.ArrearOut.model_validate(a).model_dump(mode="json"), **by_id[a.id],
                      "plan_start": p.start_month.isoformat() if p else None,
                      "plan_installments": p.installments if p else None})
    return {"today": ref.isoformat(), "items": items, "totals": calc["totals"]}


@router.post("/arrears", response_model=schemas.ArrearOut, status_code=201)
def create_arrear(data: schemas.ArrearIn, db: Session = Depends(get_session)):
    a = Arrear(**data.model_dump())
    db.add(a)
    db.commit()
    return a


@router.put("/arrears/{arrear_id}", response_model=schemas.ArrearOut)
def update_arrear(arrear_id: int, data: schemas.ArrearIn, db: Session = Depends(get_session)):
    a = _get(db, arrear_id)
    for k, v in data.model_dump().items():
        setattr(a, k, v)
    if a.status == "pago" and a.paid_date is None:
        a.paid_date = date.today()
    db.commit()
    return a


@router.delete("/arrears/{arrear_id}", status_code=204)
def delete_arrear(arrear_id: int, db: Session = Depends(get_session)):
    db.delete(_get(db, arrear_id))
    db.commit()


@router.put("/scenarios/{scenario_id}/arrear-plans")
def put_arrear_plans(scenario_id: int, items: list[schemas.ArrearPlanIn], db: Session = Depends(get_session)):
    if db.get(Scenario, scenario_id) is None:
        raise HTTPException(404, "Cenário não encontrado")
    for it in items:
        _get(db, it.arrear_id)
        row = db.scalar(select(ArrearPlan).where(ArrearPlan.scenario_id == scenario_id,
                                                 ArrearPlan.arrear_id == it.arrear_id))
        if it.start_month is None:
            if row:
                db.delete(row)
            continue
        if row is None:
            row = ArrearPlan(scenario_id=scenario_id, arrear_id=it.arrear_id)
            db.add(row)
        row.start_month = eng.month_start(it.start_month)
        row.installments = it.installments
    db.commit()
    return {"saved": len(items)}
