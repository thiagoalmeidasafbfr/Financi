from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import engine as eng
from ..db import get_session
from ..models import Category, Scenario, Transaction
from ..services import loans_for, project_scenario

router = APIRouter(prefix="/api/reports", tags=["relatórios"])

COMPARE_SERIES = ["receitas", "total_despesas", "dividas", "saldo_livre", "saldo_conta", "inv_saldo_fim",
                  "saldo_total", "fgts_saldo"]


def _scenarios(db: Session, ids: str | None) -> list[Scenario]:
    q = select(Scenario).order_by(Scenario.id)
    if ids:
        q = q.where(Scenario.id.in_([int(i) for i in ids.split(",") if i.strip()]))
    return db.scalars(q).all()


@router.get("/compare")
def compare(ids: str | None = Query(None, description="ids separados por vírgula; vazio = todos"),
            db: Session = Depends(get_session)):
    """KPIs e séries mensais lado a lado. Meses alinhados pela união dos horizontes."""
    out, all_months = [], set()
    for sc in _scenarios(db, ids):
        p = project_scenario(db, sc)
        all_months.update(p["months"])
        out.append({
            "id": sc.id, "name": sc.name, "kpis": p["kpis"], "months": p["months"],
            "series": {k: p["series"][k] for k in COMPARE_SERIES},
            "groups": {g: sum(r["total"] for r in p["rows"] if r["group"] == g) for g in eng.GROUP_LABELS},
            "auto_investment": sum(p["series"]["inv_automatico"]),
        })
    months = sorted(all_months)
    for sc in out:
        idx = {m: i for i, m in enumerate(sc["months"])}
        sc["aligned"] = {k: [v[idx[m]] if m in idx else None for m in months] for k, v in sc["series"].items()}
        del sc["series"]
    return {"months": months, "scenarios": out}


@router.get("/loans-compare")
def loans_compare(ids: str | None = None, db: Session = Depends(get_session)):
    """Quitação de cada consignado por cenário: mês, desembolso, parcelas evitadas e economia."""
    scenarios = _scenarios(db, ids)
    per = []
    for sc in scenarios:
        t = eng.loans_timeline(loans_for(db, sc.id))
        per.append({"id": sc.id, "name": sc.name, "totals": t["totals"], "contracts": t["contracts"],
                    "months": t["months"], "installments_with_payoff": t["installments_with_payoff"],
                    "installments_without_payoff": t["installments_without_payoff"],
                    "payoff_disbursement": t["payoff_disbursement"],
                    "cumulative_net_saving": t["cumulative_net_saving"]})
    return {"scenarios": per}


@router.get("/budget-vs-actual")
def budget_vs_actual(month: date, scenario_id: int | None = None, db: Session = Depends(get_session)):
    """Planejado (cenário base) x realizado (lançamentos) por categoria no mês."""
    sc = db.get(Scenario, scenario_id) if scenario_id else \
        db.scalar(select(Scenario).where(Scenario.is_baseline.is_(True))) or db.scalar(select(Scenario))
    if sc is None:
        raise HTTPException(404, "Nenhum cenário cadastrado")
    m = eng.month_start(month)
    p = project_scenario(db, sc)
    key = m.isoformat()
    idx = p["months"].index(key) if key in p["months"] else None

    txs = db.scalars(select(Transaction).where(Transaction.date >= m,
                                               Transaction.date < eng.add_months(m, 1))).all()
    cats = {c.id: c for c in db.scalars(select(Category))}
    actual: dict[int | None, float] = {}
    for t in txs:
        actual[t.category_id] = actual.get(t.category_id, 0.0) + t.amount

    rows = []
    for r in p["rows"]:
        planned = r["values"][idx] if idx is not None else 0.0
        sign = 1 if r["group"] == "receita" else -1
        real = sign * actual.pop(r["category_id"], 0.0) + 0.0  # evita -0,00
        if planned or real:
            rows.append({"category_id": r["category_id"], "name": r["name"], "group": r["group"],
                         "planned": planned, "actual": real, "diff": real - planned})
    for cid, v in actual.items():  # categorias sem linha no cenário / sem categoria
        c = cats.get(cid)
        group = c.group if c else ("receita" if v > 0 else "despesa_variavel")
        rows.append({"category_id": cid, "name": c.name if c else "(sem categoria)", "group": group,
                     "planned": 0.0, "actual": v if group == "receita" else -v,
                     "diff": v if group == "receita" else -v})

    summary = {}
    for g in eng.GROUP_LABELS:
        gp = sum(r["planned"] for r in rows if r["group"] == g)
        ga = sum(r["actual"] for r in rows if r["group"] == g)
        summary[g] = {"planned": gp, "actual": ga, "diff": ga - gp}
    return {"scenario": {"id": sc.id, "name": sc.name}, "month": key, "in_horizon": idx is not None,
            "rows": rows, "summary": summary}
