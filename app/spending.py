"""Gastos: o que já foi pago no mês, contra o previsto.

Entra como gasto:
- previsto de despesa marcado como pago à mão (não tem lançamento: o pagamento é a marcação);
- lançamento de saída numa conta (à mão, "Já paguei", ou do extrato), fora as transferências (ex.: pagar a fatura).
Previsto pago reconhecido pelo extrato não entra de novo: o lançamento do extrato já é o gasto.
Falta pagar: previstos de despesa do mês ainda pendentes ou em atraso."""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import finance as fin
from . import planned as planned_mod
from .models import Category, Transaction
from .services import accounts_for, month_plan


def _month(db: Session, person: str | None, m: date, today: date, cats: dict, acc_ids: list[int]) -> dict:
    end = fin.add_months(m, 1)
    occ = [o for o in planned_mod.occurrences(db, today, m, m, person, acc_ids) if o.kind == "despesa"]
    items, pending = [], []
    # pagos à mão contam no mês em que foram pagos (conta de outubro paga em novembro é gasto de novembro)
    window = planned_mod.occurrences(db, today, fin.add_months(m, -24), fin.add_months(m, 12), person, acc_ids)
    for o in window:
        if o.kind != "despesa" or o.status != "pago" or o.paid_auto:
            continue
        paid_month = fin.month_start(date.fromisoformat(o.paid_on or o.month))
        if paid_month != m:
            continue
        cat = cats.get(o.category_id)
        other = o.month != m.isoformat()
        items.append({"type": "previsto", "key": f"{o.planned_id}|{o.original}", "name": o.name, "date": o.paid_on or o.due, "amount": o.amount,
                      "category_id": o.category_id, "category": cat.name if cat else None, "group": cat.group if cat else "Outros",
                      "source": f"previsto de {o.month[5:7]}/{o.month[2:4]} pago" if other else "previsto pago", "occurrence": o.as_dict()})
    for o in occ:
        if o.status in ("pendente", "atrasado"):
            cat = cats.get(o.category_id)
            pending.append({**o.as_dict(), "category": cat.name if cat else None})
    from .routers.transactions import _tx_out  # o mesmo formato do Extrato (abre a mesma folha)
    q = select(Transaction).where(Transaction.account_id.in_(acc_ids), Transaction.date >= m, Transaction.date < end, Transaction.amount < 0)
    txs = db.scalars(q.order_by(Transaction.date.desc(), Transaction.id.desc())) if acc_ids else []
    for t in txs:
        cat = cats.get(t.category_id)
        if cat is not None and cat.type == "transferencia":
            continue
        items.append({"type": "lancamento", "key": str(t.id), "name": t.description, "date": t.date.isoformat(), "amount": round(-t.amount, 2),
                      "category_id": t.category_id, "category": cat.name if cat else None, "group": cat.group if cat else "Sem categoria",
                      "source": "extrato" if t.import_id else "lançado", "tx": _tx_out(t)})
    items.sort(key=lambda it: (it["date"], it["amount"]), reverse=True)
    if m == fin.month_start(today):  # no mês atual, o que ficou em atraso de meses anteriores também falta pagar
        for o in planned_mod.overdue(db, today, person, acc_ids):
            if o.kind == "despesa" and o.month < m.isoformat():
                cat = cats.get(o.category_id)
                pending.append({**o.as_dict(), "category": cat.name if cat else None})
    pending.sort(key=lambda o: (o["status"] != "atrasado", o["due"]))
    return {"items": items, "pending": pending, "spent": round(sum(it["amount"] for it in items), 2),
            "to_pay": round(sum(o["amount"] for o in pending), 2)}


def spending(db: Session, person: str | None, month: date, today: date, history: int = 6) -> dict:
    m = fin.month_start(month)
    cats = {c.id: c for c in db.scalars(select(Category))}
    acc_ids = [a.id for a in accounts_for(db, person)]
    cur = _month(db, person, m, today, cats, acc_ids)
    by_group: dict[str, float] = defaultdict(float)
    for it in cur["items"]:
        by_group[it["group"]] += it["amount"]
    # previsto do mês para comparar: contas fixas, cartões e gastos variáveis (parcelas de dívida descontadas na folha ficam fora)
    plan = month_plan(db, person, m, today)
    planned = round(sum(plan["sections"][k]["planned"] for k in ("fixas", "cartoes", "variaveis")), 2)
    hist = []
    for k in range(history - 1, -1, -1):
        hm = fin.add_months(m, -k)
        h = cur if hm == m else _month(db, person, hm, today, cats, acc_ids)
        hp = plan if hm == m else month_plan(db, person, hm, today)
        hist.append({"month": hm.isoformat(), "spent": h["spent"],
                     "planned": round(sum(hp["sections"][s]["planned"] for s in ("fixas", "cartoes", "variaveis")), 2)})
    return {
        "month": m.isoformat(), "spent": cur["spent"], "planned": planned, "to_pay": cur["to_pay"],
        "items": cur["items"], "pending": cur["pending"],
        "by_group": [{"group": g, "amount": round(v, 2)} for g, v in sorted(by_group.items(), key=lambda kv: -kv[1])],
        "history": hist,
    }
