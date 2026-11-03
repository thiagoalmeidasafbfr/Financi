"""Consultas que juntam banco e cálculos: saldos, orçamento, projeção, cartões e dívidas."""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import finance as fin
from . import planned as planned_mod
from .models import Account, Budget, Category, Debt, Transaction

LIQUID = ("corrente", "poupanca", "dinheiro")


# ---------------------------------------------------------------- filtros

def accounts_for(db: Session, person: str | None) -> list[Account]:
    """person: None/'all' = todas, 'conjunto' = sem titular, '<id>' = da pessoa."""
    q = select(Account).where(Account.active.is_(True)).order_by(Account.kind, Account.name)
    if person == "conjunto":
        q = q.where(Account.owner_id.is_(None))
    elif person and person != "all":
        q = q.where(Account.owner_id == int(person))
    return list(db.scalars(q))


def balances(db: Session, accounts: list[Account]) -> dict[int, float]:
    if not accounts:
        return {}
    rows = db.execute(select(Transaction.account_id, func.coalesce(func.sum(Transaction.amount), 0))
                      .where(Transaction.account_id.in_([a.id for a in accounts]))
                      .group_by(Transaction.account_id)).all()
    moved = {aid: float(v) for aid, v in rows}
    return {a.id: round((a.opening_balance or 0) + moved.get(a.id, 0.0), 2) for a in accounts}


def _category_totals(db: Session, account_ids: list[int], start: date, end: date) -> dict[int | None, float]:
    """Soma com sinal por categoria entre start (incl.) e end (excl.)."""
    if not account_ids:
        return {}
    rows = db.execute(select(Transaction.category_id, func.sum(Transaction.amount))
                      .where(Transaction.account_id.in_(account_ids), Transaction.date >= start, Transaction.date < end)
                      .group_by(Transaction.category_id)).all()
    return {cid: float(v) for cid, v in rows}


def _months_with_data(db: Session, account_ids: list[int], start: date, end: date, cap: int) -> int:
    """Quantos meses do intervalo têm lançamentos (1..cap). Evita dividir a média por meses sem extrato."""
    if not account_ids:
        return 1
    first = db.scalar(select(func.min(Transaction.date)).where(
        Transaction.account_id.in_(account_ids), Transaction.date >= start, Transaction.date < end))
    if first is None:
        return 1
    return max(1, min(cap, fin.months_between(fin.month_start(first), end)))


def _actual(cat: Category | None, signed: float) -> float:
    """Valor realizado positivo: despesa = saída líquida, receita = entrada líquida."""
    if cat is None or cat.type == "despesa":
        return -signed
    return signed


# ---------------------------------------------------------------- orçamento

def budget_map(db: Session, month: date) -> dict[int, float]:
    out: dict[int, float] = {}
    for b in db.scalars(select(Budget).where(Budget.month.is_(None))):
        out[b.category_id] = b.amount
    for b in db.scalars(select(Budget).where(Budget.month == month)):
        out[b.category_id] = b.amount
    return out


def month_view(db: Session, month: date, person: str | None) -> dict:
    """Orçado × realizado por categoria no mês (transferências ficam de fora dos totais)."""
    m = fin.month_start(month)
    accs = accounts_for(db, person)
    totals = _category_totals(db, [a.id for a in accs], m, fin.add_months(m, 1))
    budgets = budget_map(db, m)
    cats = {c.id: c for c in db.scalars(select(Category))}
    rows = []
    for cid in set(totals) | set(budgets):
        cat = cats.get(cid)
        if cat is not None and cat.type == "transferencia":
            continue
        actual = _actual(cat, totals.get(cid, 0.0))
        planned = budgets.get(cid, 0.0)
        if abs(actual) < 0.005 and not planned:
            continue
        rows.append({"category_id": cid, "name": cat.name if cat else "Sem categoria",
                     "group": cat.group if cat else "Sem categoria", "type": cat.type if cat else "despesa",
                     "planned": planned, "actual": round(actual, 2), "remaining": round(planned - actual, 2)})
    rows.sort(key=lambda r: (r["type"] != "receita", -max(r["actual"], r["planned"])))
    exp = [r for r in rows if r["type"] == "despesa"]
    inc = [r for r in rows if r["type"] == "receita"]
    return {
        "month": m.isoformat(), "rows": rows,
        "totals": {"despesas": round(sum(r["actual"] for r in exp), 2), "despesas_orcadas": sum(r["planned"] for r in exp),
                   "receitas": round(sum(r["actual"] for r in inc), 2), "receitas_previstas": sum(r["planned"] for r in inc),
                   "sem_categoria": round(sum(r["actual"] for r in rows if r["category_id"] is None), 2)},
    }


def suggest_budgets(db: Session, month: date, person: str | None, months_back: int = 3) -> list[dict]:
    """Média dos últimos meses fechados por categoria, arredondada para dezena."""
    m = fin.month_start(month)
    start = fin.add_months(m, -months_back)
    accs = accounts_for(db, person)
    acc_ids = [a.id for a in accs]
    totals = _category_totals(db, acc_ids, start, m)
    n = _months_with_data(db, acc_ids, start, m, months_back)
    cats = {c.id: c for c in db.scalars(select(Category))}
    out = []
    for cid, signed in totals.items():
        cat = cats.get(cid)
        if cat is None or cat.type == "transferencia":
            continue
        avg = _actual(cat, signed) / n
        if avg > 1:
            out.append({"category_id": cid, "name": cat.name, "type": cat.type, "amount": round(avg / 10) * 10 or 10})
    return sorted(out, key=lambda r: -r["amount"])


# ---------------------------------------------------------------- cartões e dívidas

def _card_txs(db: Session, acc: Account) -> list[fin.CardTx]:
    pay_ids = {c.id for c in db.scalars(select(Category).where(Category.type == "transferencia"))}
    return [fin.CardTx(t.date, t.amount, t.merchant, t.category_id in pay_ids, t.installment_n, t.installment_total)
            for t in db.scalars(select(Transaction).where(Transaction.account_id == acc.id))]


def card_overview(db: Session, acc: Account, today: date) -> dict:
    closing, due = acc.closing_day or 1, acc.due_day or 10
    txs = _card_txs(db, acc)
    invoices = fin.card_invoices(txs, closing)
    future = fin.future_installments(txs, closing)
    current = fin.invoice_month(today, closing)
    upcoming = {m: v for m, v in future.items() if m > current}
    used = invoices.get(current, 0.0) + sum(upcoming.values())
    last = sorted(invoices.items())[-6:]
    return {
        "account_id": acc.id, "name": acc.name, "owner_id": acc.owner_id, "closing_day": acc.closing_day,
        "due_day": acc.due_day, "limit": acc.credit_limit, "configured": bool(acc.closing_day and acc.due_day),
        "current_invoice": {"month": current.isoformat(), "amount": round(invoices.get(current, 0.0), 2),
                            "due": fin.due_date(current, closing, due).isoformat()},
        "history": [{"month": m.isoformat(), "amount": round(v, 2)} for m, v in last],
        "future_installments": [{"month": m.isoformat(), "amount": round(v, 2)} for m, v in sorted(upcoming.items())],
        "future_total": round(sum(upcoming.values()), 2),
        "limit_used": round(used, 2),
        "limit_available": round(acc.credit_limit - used, 2) if acc.credit_limit else None,
    }


def debt_overview(db: Session, d: Debt, today: date) -> dict:
    st = fin.loan_status(d.installment, d.monthly_rate, d.first_due, d.total_installments, today,
                         informed_balance=d.balance)
    last_payment = None
    if d.match_pattern:
        pat = f"%{d.match_pattern.upper()}%"
        t = db.scalar(select(Transaction).where(Transaction.merchant.like(pat) | Transaction.description.ilike(pat))
                      .order_by(Transaction.date.desc()).limit(1))
        if t:
            last_payment = {"date": t.date.isoformat(), "amount": t.amount, "description": t.description}
    return {
        "id": d.id, "name": d.name, "kind": d.kind, "creditor": d.creditor, "owner_id": d.owner_id,
        "installment": d.installment, "monthly_rate": d.monthly_rate, "total_installments": d.total_installments,
        "first_due": d.first_due.isoformat() if d.first_due else None, "paid": st.paid, "remaining": st.remaining,
        "balance": st.balance, "interest_remaining": st.interest_remaining, "payoff_now": st.balance,
        "end_month": st.end_month.isoformat() if st.end_month else None,
        "next_due": st.next_due.isoformat() if st.next_due else None, "last_payment": last_payment,
        "notes": d.notes, "active": d.active, "match_pattern": d.match_pattern, "informed_balance": d.balance,
    }


def avg_income(db: Session, accounts: list[Account], today: date, months_back: int = 3) -> float:
    m = fin.month_start(today)
    acc_ids = [a.id for a in accounts]
    start = fin.add_months(m, -months_back)
    totals = _category_totals(db, acc_ids, start, m)
    cats = {c.id: c for c in db.scalars(select(Category))}
    n = _months_with_data(db, acc_ids, start, m, months_back)
    return sum(v for cid, v in totals.items() if cats.get(cid) and cats[cid].type == "receita") / n


def debts_summary(db: Session, person: str | None, today: date) -> dict:
    accs = accounts_for(db, person)
    owners = {a.owner_id for a in accs}
    cards = [card_overview(db, a, today) for a in accs if a.kind == "cartao"]
    q = select(Debt).where(Debt.active.is_(True))
    if person == "conjunto":
        q = q.where(Debt.owner_id.is_(None))
    elif person and person != "all":
        q = q.where(Debt.owner_id == int(person))
    debts = [debt_overview(db, d, today) for d in db.scalars(q.order_by(Debt.id))]
    month_installments = sum(d["installment"] for d in debts if d["remaining"] > 0)
    income = avg_income(db, accs, today)
    open_debts = [d for d in debts if d["balance"] > 0]
    return {
        "cards": cards, "debts": debts,
        "totals": {
            "saldo_devedor": round(sum(d["balance"] for d in debts), 2),
            "faturas_abertas": round(sum(c["current_invoice"]["amount"] for c in cards), 2),
            "parcelas_cartao_futuras": round(sum(c["future_total"] for c in cards), 2),
            "parcelas_mes": round(month_installments, 2),
            "renda_media": round(income, 2),
            "comprometimento": round(month_installments / income, 4) if income > 0 else None,
        },
        # ordem sugerida para quitar: avalanche (maior juro primeiro) e bola de neve (menor saldo primeiro)
        "avalanche": [d["id"] for d in sorted(open_debts, key=lambda d: -(d["monthly_rate"] or 0))],
        "snowball": [d["id"] for d in sorted(open_debts, key=lambda d: d["balance"])],
        "owners": sorted(o for o in owners if o is not None),
    }


# ---------------------------------------------------------------- projeção

def projection(db: Session, person: str | None, today: date, months: int = 6) -> dict:
    """Caixa dos próximos meses: saldo atual + receitas previstas − despesas orçadas − dívidas − parcelas de cartão.

    Cada categoria usa o orçamento do mês; categoria sem orçamento usa a média dos últimos meses com extrato
    (até 3). Lançamentos previstos da categoria naquele mês substituem orçamento e média; previstos sem categoria
    somam. O que está em atraso ou ainda vence no mês atual sai no primeiro mês projetado. O grupo Dívidas fica
    de fora porque as parcelas vêm do módulo de dívidas."""
    accs = accounts_for(db, person)
    acc_ids = [a.id for a in accs]
    bal = balances(db, accs)
    start_balance = sum(v for a in accs if a.kind in LIQUID for v in [bal.get(a.id, 0.0)])
    cats = {c.id: c for c in db.scalars(select(Category))}
    first = fin.add_months(fin.month_start(today), 1)
    h_start, h_end = fin.add_months(fin.month_start(today), -3), fin.month_start(today)
    n_hist = _months_with_data(db, acc_ids, h_start, h_end, 3)
    hist = {cid: v / n_hist for cid, v in _category_totals(db, acc_ids, h_start, h_end).items()}

    def kind(cid: int | None) -> str | None:
        """'receita', 'despesa' (sem categoria conta como despesa) ou None para o que não entra."""
        cat = cats.get(cid)
        if cat is None:
            return "despesa" if cid is None else None
        if cat.type == "transferencia" or cat.group == "Dívidas":
            return None
        return cat.type

    debt_q = select(Debt).where(Debt.active.is_(True))
    if person == "conjunto":
        debt_q = debt_q.where(Debt.owner_id.is_(None))
    elif person and person != "all":
        debt_q = debt_q.where(Debt.owner_id == int(person))
    debt_sched: dict[date, float] = defaultdict(float)
    for d in db.scalars(debt_q):
        for m, v in fin.loan_schedule(d.installment, d.first_due, d.total_installments, today=today,
                                      rate=d.monthly_rate, balance=d.balance).items():
            debt_sched[m] += v
    card_sched: dict[date, float] = defaultdict(float)
    open_invoices = 0.0
    for a in accs:
        if a.kind == "cartao":
            txs, closing = _card_txs(db, a), a.closing_day or 1
            current = fin.invoice_month(today, closing)
            open_invoices += fin.card_invoices(txs, closing).get(current, 0.0)
            for m, v in fin.future_installments(txs, closing).items():
                if m > current:
                    card_sched[m] += v
    # o que já foi gasto no cartão e ainda não foi pago sai do saldo de partida
    start_balance -= open_invoices

    plan_by_month, pending = planned_mod.projection_inputs(db, today, months + 1, person, acc_ids)
    order = ("orçamento", "média", "previsto")

    rows, running = [], start_balance
    for i in range(months):
        m = fin.add_months(first, i)
        b = budget_map(db, m)
        pm = plan_by_month.get(m.isoformat(), {})
        planned_cats = {cid for (_, cid) in pm if cid is not None}
        tot = {"receita": 0.0, "despesa": 0.0}
        used = {"receita": set(), "despesa": set()}  # fontes usadas: orçamento, média e/ou previsto
        for cid in set(b) | set(hist):
            k = kind(cid)
            if k is None or cid in planned_cats:  # o previsto da categoria substitui orçamento e média no mês
                continue
            if cid in b:
                tot[k] += b[cid]
                used[k].add("orçamento")
            else:
                tot[k] += hist[cid] if k == "receita" else -hist[cid]
                used[k].add("média")
        for (pk, _cid), v in pm.items():
            tot[pk] += v
            used[pk].add("previsto")
        inc, exp = max(0.0, tot["receita"]), max(0.0, tot["despesa"])
        src = {k: " + ".join(x for x in order if x in v) or "média" for k, v in used.items()}
        debts, cards = debt_sched.get(m, 0.0), card_sched.get(m, 0.0)
        pend = pending if i == 0 else 0.0  # atrasados e o que ainda vence neste mês (com sinal: entrada +, saída −)
        running += inc - exp - debts - cards + pend
        rows.append({"month": m.isoformat(), "receitas": round(inc, 2), "despesas": round(exp, 2),
                     "dividas": round(debts, 2), "parcelas_cartao": round(cards, 2), "pendentes": round(-pend, 2),
                     "saldo": round(running, 2), "fonte_receitas": src["receita"], "fonte_despesas": src["despesa"]})
    return {"saldo_atual": round(start_balance + open_invoices, 2), "faturas_abertas": round(open_invoices, 2),
            "saldo_inicial": round(start_balance, 2), "months": rows}
