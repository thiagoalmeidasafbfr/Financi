from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import engine as eng
from .. import schemas
from ..db import get_session
from ..models import (
    InflationRate,
    LoanContract,
    LoanPayoff,
    MonthSetting,
    PlanEntry,
    SalaryChange,
    Scenario,
)
from ..services import duplicate_scenario, loans_for, project_scenario

router = APIRouter(prefix="/api/scenarios", tags=["cenários"])


def _get(db: Session, scenario_id: int) -> Scenario:
    sc = db.get(Scenario, scenario_id)
    if sc is None:
        raise HTTPException(404, "Cenário não encontrado")
    return sc


def _clear_other_baselines(db: Session, sc: Scenario) -> None:
    if sc.is_baseline:
        for other in db.scalars(select(Scenario).where(Scenario.id != sc.id, Scenario.is_baseline.is_(True))):
            other.is_baseline = False


@router.get("", response_model=list[schemas.ScenarioOut])
def list_scenarios(db: Session = Depends(get_session)):
    return db.scalars(select(Scenario).order_by(Scenario.id)).all()


@router.post("", response_model=schemas.ScenarioOut, status_code=201)
def create_scenario(data: schemas.ScenarioBase, db: Session = Depends(get_session)):
    sc = Scenario(**data.model_dump())
    sc.start_month = eng.month_start(sc.start_month)
    db.add(sc)
    db.flush()
    _clear_other_baselines(db, sc)
    db.commit()
    return sc


@router.get("/{scenario_id}", response_model=schemas.ScenarioOut)
def get_scenario(scenario_id: int, db: Session = Depends(get_session)):
    return _get(db, scenario_id)


@router.put("/{scenario_id}", response_model=schemas.ScenarioOut)
def update_scenario(scenario_id: int, data: schemas.ScenarioBase, db: Session = Depends(get_session)):
    sc = _get(db, scenario_id)
    for k, v in data.model_dump().items():
        setattr(sc, k, v)
    sc.start_month = eng.month_start(sc.start_month)
    _clear_other_baselines(db, sc)
    db.commit()
    return sc


@router.delete("/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: int, db: Session = Depends(get_session)):
    db.delete(_get(db, scenario_id))
    db.commit()


@router.post("/{scenario_id}/duplicate", response_model=schemas.ScenarioOut, status_code=201)
def duplicate(scenario_id: int, name: str, db: Session = Depends(get_session)):
    if db.scalar(select(Scenario.id).where(Scenario.name == name)):
        raise HTTPException(409, "Já existe um cenário com esse nome")
    return duplicate_scenario(db, _get(db, scenario_id), name)


# ----------------------------------------------------------------- projeção e análises

@router.get("/{scenario_id}/projection")
def projection(scenario_id: int, db: Session = Depends(get_session)):
    return project_scenario(db, _get(db, scenario_id))


@router.get("/{scenario_id}/sankey")
def sankey(scenario_id: int, month: date | None = None, db: Session = Depends(get_session)):
    proj = project_scenario(db, _get(db, scenario_id))
    idx = None
    if month is not None:
        key = eng.month_start(month).isoformat()
        if key not in proj["months"]:
            raise HTTPException(400, "Mês fora do horizonte do cenário")
        idx = proj["months"].index(key)
    return eng.sankey(proj, idx)


@router.get("/{scenario_id}/loans")
def loans_analysis(scenario_id: int, db: Session = Depends(get_session)):
    _get(db, scenario_id)
    return eng.loans_timeline(loans_for(db, scenario_id))


@router.get("/{scenario_id}/payoff-suggestion")
def payoff_suggestion(scenario_id: int, month: date, budget: float | None = None, min_remaining: int = 3,
                      db: Session = Depends(get_session)):
    """Quitações que liberam a maior parcela mensal cabendo no valor disponível.
    Sem `budget`, usa o saldo total (conta + investimentos) do mês, devolvendo as quitações já agendadas nele."""
    proj = project_scenario(db, _get(db, scenario_id))
    loans = loans_for(db, scenario_id)
    m = eng.month_start(month)
    available = None
    if m.isoformat() in proj["months"]:
        i = proj["months"].index(m.isoformat())
        quit_row = next((r["values"][i] for r in proj["rows"] if r["kind"] == "quitacao"), 0.0)
        available = max(0.0, proj["series"]["saldo_total"][i] + quit_row)
    result = eng.best_payoffs(loans, m, budget if budget is not None else (available or 0.0), min_remaining)
    result["available"] = available
    return result


@router.get("/{scenario_id}/payoff-planner")
def payoff_planner(scenario_id: int, db: Session = Depends(get_session)):
    """Mês a mês da conta e valor de quitação de cada contrato em cada mês do cenário."""
    proj = project_scenario(db, _get(db, scenario_id))
    return eng.payoff_planner(proj, loans_for(db, scenario_id))


# ----------------------------------------------------------------- valores planejados

@router.get("/{scenario_id}/entries", response_model=list[schemas.EntryIn])
def list_entries(scenario_id: int, db: Session = Depends(get_session)):
    return [schemas.EntryIn(category_id=e.category_id, month=e.month, amount=e.amount)
            for e in _get(db, scenario_id).entries]


def _upsert(db: Session, scenario_id: int, category_id: int, month: date, amount: float | None) -> None:
    month = eng.month_start(month)
    row = db.scalar(select(PlanEntry).where(PlanEntry.scenario_id == scenario_id,
                                            PlanEntry.category_id == category_id, PlanEntry.month == month))
    if amount is None:
        if row:
            db.delete(row)
    elif row:
        row.amount = amount
    else:
        db.add(PlanEntry(scenario_id=scenario_id, category_id=category_id, month=month, amount=amount))


@router.put("/{scenario_id}/entries")
def upsert_entries(scenario_id: int, items: list[schemas.EntryIn], db: Session = Depends(get_session)):
    _get(db, scenario_id)
    for it in items:
        _upsert(db, scenario_id, it.category_id, it.month, it.amount)
    db.commit()
    return {"updated": len(items)}


@router.post("/{scenario_id}/entries/fill")
def fill_entries(scenario_id: int, data: schemas.FillIn, db: Session = Depends(get_session)):
    """Repete um valor (ou limpa, com amount=null) em um intervalo de meses."""
    _get(db, scenario_id)
    m, end, count = eng.month_start(data.from_month), eng.month_start(data.to_month), 0
    while m <= end:
        _upsert(db, scenario_id, data.category_id, m, data.amount)
        m = eng.add_months(m, 1)
        count += 1
    db.commit()
    return {"updated": count}


# ----------------------------------------------------------------- premissas (listas)

@router.get("/{scenario_id}/salary-changes", response_model=list[schemas.SalaryChangeIn])
def get_salary(scenario_id: int, db: Session = Depends(get_session)):
    return _get(db, scenario_id).salary_changes


@router.put("/{scenario_id}/salary-changes")
def put_salary(scenario_id: int, items: list[schemas.SalaryChangeIn], db: Session = Depends(get_session)):
    sc = _get(db, scenario_id)
    db.execute(delete(SalaryChange).where(SalaryChange.scenario_id == sc.id))
    for it in items:
        db.add(SalaryChange(scenario_id=sc.id, start_month=eng.month_start(it.start_month),
                            amount=it.amount, pct=it.pct))
    db.commit()
    return {"saved": len(items)}


@router.get("/{scenario_id}/inflation", response_model=list[schemas.InflationIn])
def get_inflation(scenario_id: int, db: Session = Depends(get_session)):
    return _get(db, scenario_id).inflation_rates


@router.put("/{scenario_id}/inflation")
def put_inflation(scenario_id: int, items: list[schemas.InflationIn], db: Session = Depends(get_session)):
    sc = _get(db, scenario_id)
    db.execute(delete(InflationRate).where(InflationRate.scenario_id == sc.id))
    for it in items:
        db.add(InflationRate(scenario_id=sc.id, **it.model_dump()))
    db.commit()
    return {"saved": len(items)}


@router.get("/{scenario_id}/month-settings", response_model=list[schemas.MonthSettingIn])
def get_month_settings(scenario_id: int, db: Session = Depends(get_session)):
    return _get(db, scenario_id).month_settings


@router.put("/{scenario_id}/month-settings")
def put_month_settings(scenario_id: int, items: list[schemas.MonthSettingIn], db: Session = Depends(get_session)):
    sc = _get(db, scenario_id)
    db.execute(delete(MonthSetting).where(MonthSetting.scenario_id == sc.id))
    for it in items:
        data = it.model_dump()
        data["month"] = eng.month_start(it.month)
        if any(v is not None for k, v in data.items() if k != "month"):
            db.add(MonthSetting(scenario_id=sc.id, **data))
    db.commit()
    return {"saved": len(items)}


@router.get("/{scenario_id}/payoffs", response_model=list[schemas.PayoffIn])
def get_payoffs(scenario_id: int, db: Session = Depends(get_session)):
    return [schemas.PayoffIn(contract_id=p.contract_id, payoff_month=p.payoff_month)
            for p in _get(db, scenario_id).payoffs]


@router.put("/{scenario_id}/payoffs")
def put_payoffs(scenario_id: int, items: list[schemas.PayoffIn], db: Session = Depends(get_session)):
    sc = _get(db, scenario_id)
    for it in items:
        if db.get(LoanContract, it.contract_id) is None:
            raise HTTPException(400, f"Contrato {it.contract_id} não existe")
        row = db.scalar(select(LoanPayoff).where(LoanPayoff.scenario_id == sc.id,
                                                 LoanPayoff.contract_id == it.contract_id))
        if it.payoff_month is None:
            if row:
                db.delete(row)
        elif row:
            row.payoff_month = eng.month_start(it.payoff_month)
        else:
            db.add(LoanPayoff(scenario_id=sc.id, contract_id=it.contract_id,
                              payoff_month=eng.month_start(it.payoff_month)))
    db.commit()
    return {"saved": len(items)}
