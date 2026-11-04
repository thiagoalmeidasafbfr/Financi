"""Consultas que juntam banco e cálculos: saldos, orçamento, projeção, cartões e dívidas."""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import cockpit
from . import finance as fin
from . import planned as planned_mod
from .models import Account, Action, Budget, Category, Debt, Grouping, Transaction

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
        "payoff_month": _payoff_month(db, d.id),
    }


def _payoff_month(db: Session, debt_id: int) -> str | None:
    """Mês da quitação ligada no Cockpit (para mostrar e ligar as telas)."""
    a = db.scalar(select(Action).where(Action.kind == "quitacao", Action.debt_id == debt_id, Action.active.is_(True)))
    return a.month.isoformat() if a and a.month else None


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
    if not income:  # sem extratos com receita: usa as receitas previstas do mês
        m = fin.month_start(today)
        income = sum(o.amount for o in planned_mod.occurrences(db, today, m, m, person, [a.id for a in accs])
                     if o.kind == "receita" and o.status != "pulado")
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

def projection(db: Session, person: str | None, today: date, months: int = 6, detail: bool = False,
               actions: bool | cockpit.Effects = True) -> dict:
    """Caixa dos próximos meses: saldo atual + receitas previstas − despesas orçadas − dívidas − parcelas de cartão.

    Cada categoria usa o orçamento do mês; categoria sem orçamento usa a média dos últimos meses com extrato
    (até 3). Lançamentos previstos da categoria naquele mês substituem orçamento e média; previstos sem categoria
    somam. O que está em atraso ou ainda vence no mês atual sai no primeiro mês projetado. O grupo Dívidas fica
    de fora porque as parcelas vêm do módulo de dívidas.

    Com detail, devolve também a tabela mês a mês (uma linha por categoria, previsto sem categoria, dívida e cartão),
    montada com os mesmos números da projeção.

    As ações ligadas do cockpit entram (actions=False ignora; ou passe os efeitos já calculados): substituem
    previstos, somam entradas/saídas (só na visão de todos) e quitam dívidas."""
    eff = actions if isinstance(actions, cockpit.Effects) else (cockpit.effects(db, today) if actions else cockpit.Effects())
    everyone = person in (None, "", "all")
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

    # tabela: chave da linha → {seção, grupo, rótulo, valores por mês, fonte por mês, "agora"}
    lines: dict[tuple, dict] = {}

    def cell(key: tuple, section: str, group: str, label: str, i: int | None, value: float, source: str) -> None:
        if not detail or not value:
            return
        row = lines.setdefault(key, {"section": section, "group": group, "label": label, "now": 0.0,
                                     "values": [0.0] * months, "sources": [""] * months})
        if i is None:
            row["now"] += value
        else:
            row["values"][i] += value
            row["sources"][i] = source if not row["sources"][i] or row["sources"][i] == source else "misto"

    def cat_line(cid: int | None, k: str) -> tuple[tuple, str, str, str]:
        cat = cats.get(cid)
        section = "entradas" if k == "receita" else "saidas"
        if cat is None:
            return ("cat", None), section, "Outros", "Sem categoria (média)"
        group = "Receitas" if k == "receita" else cat.group
        return ("cat", cid), section, group, cat.name

    def planned_line(o) -> tuple[tuple, str, str, str]:
        """Cada previsto é uma linha com o seu nome (previstos de mesmo nome, como os períodos do salário, juntam)."""
        section = "entradas" if o.kind == "receita" else "saidas"
        cat = cats.get(o.category_id)
        if cat is not None and cat.group == "Dívidas" and o.kind == "despesa":
            section, group = "dividas", "Dívidas e parcelas"
        elif o.kind == "receita":
            group = "Receitas"
        else:
            group = cat.group if cat is not None else "Outros previstos"
        return ("plan", section, group, o.name), section, group, o.name

    debt_q = select(Debt).where(Debt.active.is_(True))
    if person == "conjunto":
        debt_q = debt_q.where(Debt.owner_id.is_(None))
    elif person and person != "all":
        debt_q = debt_q.where(Debt.owner_id == int(person))
    debt_sched: dict[date, float] = defaultdict(float)
    debt_rows: list[tuple[Debt, dict[date, float]]] = []
    for d in db.scalars(debt_q.order_by(Debt.id)):
        sched = cockpit.apply_payoff(d, cockpit.schedule(d, today), eff, today)
        debt_rows.append((d, sched))
        for m, v in sched.items():
            debt_sched[m] += v
    card_sched: dict[date, float] = defaultdict(float)
    card_rows: list[tuple[Account, dict[date, float]]] = []
    open_invoices = 0.0
    for a in accs:
        if a.kind == "cartao":
            txs, closing = _card_txs(db, a), a.closing_day or 1
            current = fin.invoice_month(today, closing)
            open_invoices += fin.card_invoices(txs, closing).get(current, 0.0)
            future = {m: v for m, v in fin.future_installments(txs, closing).items() if m > current}
            card_rows.append((a, future))
            for m, v in future.items():
                card_sched[m] += v
    # o que já foi gasto no cartão e ainda não foi pago sai do saldo de partida
    start_balance -= open_invoices

    items_by_month, pending_items = planned_mod.projection_items(db, today, months + 1, person, acc_ids)
    items_by_month = {m: cockpit.apply_overrides(v, eff) for m, v in items_by_month.items()}
    pending_items = cockpit.apply_overrides(pending_items, eff)
    pending = round(sum(o.amount if o.kind == "receita" else -o.amount for o in pending_items), 2)
    for o in pending_items:
        key, section, group, label = planned_line(o)
        cell(key, section, group, label, None, o.amount, "previsto")

    def action_line(x) -> tuple[tuple, str, str, str]:
        return ("acao", x.action_id, x.label), "entradas" if x.kind == "receita" else "saidas", f"{cockpit.GROUP} · {x.action}", x.label

    extras_by_month: dict[date, list] = defaultdict(list)
    for x in eff.extras if everyone else []:
        if x.month <= fin.month_start(today):  # mês atual ou passado: entra agora, como os pendentes
            pending = round(pending + (x.amount if x.kind == "receita" else -x.amount), 2)
            cell(*action_line(x), None, x.amount, "ação")
        else:
            extras_by_month[x.month].append(x)
    # parcela de dívida que ainda vence neste mês também sai agora (ex.: consignado descontado no dia 5, hoje é dia 3)
    cur = fin.month_start(today)
    for d, sched in debt_rows:
        v = sched.get(cur, 0.0)
        paying_off_now = eff.payoffs.get(d.id) == cur  # quitação neste mês sai agora, mesmo depois do vencimento
        if v and (paying_off_now or (d.first_due and fin.day_in_month(cur, d.first_due.day) >= today)):
            pending = round(pending - v, 2)
            cell(("debt", d.id), "dividas", "Dívidas e parcelas", d.name, None, v, "dívida")
    order = ("orçamento", "média", "previsto", "ação")

    rows, running = [], start_balance
    for i in range(months):
        m = fin.add_months(first, i)
        b = budget_map(db, m)
        items = items_by_month.get(m.isoformat(), [])
        planned_cats = {o.category_id for o in items if o.category_id is not None}
        tot = {"receita": 0.0, "despesa": 0.0}
        used = {"receita": set(), "despesa": set()}  # fontes usadas: orçamento, média e/ou previsto
        for cid in set(b) | set(hist):
            k = kind(cid)
            if k is None or cid in planned_cats:  # o previsto da categoria substitui orçamento e média no mês
                continue
            key, section, group, label = cat_line(cid, k)
            if cid in b:
                tot[k] += b[cid]
                used[k].add("orçamento")
                cell(key, section, group, label, i, b[cid], "orçamento")
            else:
                v = hist[cid] if k == "receita" else -hist[cid]
                tot[k] += v
                used[k].add("média")
                cell(key, section, group, label, i, v, "média")
        for o in items:
            tot[o.kind] += o.amount
            used[o.kind].add("previsto")
            key, section, group, label = planned_line(o)
            cell(key, section, group, label, i, o.amount, "previsto")
        for x in extras_by_month.get(m, []):
            tot[x.kind] += x.amount
            used[x.kind].add("ação")
            cell(*action_line(x), i, x.amount, "ação")
        inc, exp = max(0.0, tot["receita"]), max(0.0, tot["despesa"])
        src = {k: " + ".join(x for x in order if x in v) or "média" for k, v in used.items()}
        debts, cards = debt_sched.get(m, 0.0), card_sched.get(m, 0.0)
        for d, sched in debt_rows:
            cell(("debt", d.id), "dividas", "Dívidas e parcelas", d.name, i, sched.get(m, 0.0), "dívida")
        for a, sched in card_rows:
            cell(("card", a.id), "dividas", "Dívidas e parcelas", f"Parcelas no cartão · {a.name}", i, sched.get(m, 0.0), "cartão")
        pend = pending if i == 0 else 0.0  # atrasados e o que ainda vence neste mês (com sinal: entrada +, saída −)
        running += inc - exp - debts - cards + pend
        rows.append({"month": m.isoformat(), "receitas": round(inc, 2), "despesas": round(exp, 2),
                     "dividas": round(debts, 2), "parcelas_cartao": round(cards, 2), "pendentes": round(-pend, 2),
                     "saldo": round(running, 2), "fonte_receitas": src["receita"], "fonte_despesas": src["despesa"]})
    out = {"saldo_atual": round(start_balance + open_invoices, 2), "faturas_abertas": round(open_invoices, 2),
           "saldo_inicial": round(start_balance, 2), "months": rows}
    if detail:
        out["table"] = _table(lines, rows, start_balance, pending)
        out["table"]["groupings"] = _groupings(db, out["table"])
    return out


def _table(lines: dict[tuple, dict], rows: list[dict], start_balance: float, pending: float) -> dict:
    """Linhas agrupadas por seção e grupo, com subtotais e os totais do mês (iguais aos da projeção)."""
    def rnd(xs):
        return [round(x, 2) for x in xs]

    for key, r in lines.items():
        r["ref"] = _ref(key)

    sections = []
    for sec in ("entradas", "saidas", "dividas"):
        sec_lines = [r for r in lines.values() if r["section"] == sec]
        groups: dict[str, list[dict]] = defaultdict(list)
        for r in sec_lines:
            groups[r["group"]].append(r)
        out_groups = []
        for g, rs in sorted(groups.items(), key=lambda kv: (-sum(sum(r["values"]) + r["now"] for r in kv[1]), kv[0])):
            rs.sort(key=lambda r: -(sum(r["values"]) + r["now"]))
            out_groups.append({
                "group": g,
                "now": round(sum(r["now"] for r in rs), 2),
                "values": rnd([sum(r["values"][i] for r in rs) for i in range(len(rows))]),
                "rows": [{"label": r["label"], "ref": r["ref"], "now": round(r["now"], 2), "values": rnd(r["values"]),
                          "sources": r["sources"]} for r in rs],
            })
        sections.append({"key": sec, "groups": out_groups,
                         "now": round(sum(g["now"] for g in out_groups), 2),
                         "values": rnd([sum(g["values"][i] for g in out_groups) for i in range(len(rows))])})
    entradas = [r["receitas"] for r in rows]
    saidas = [r["despesas"] + r["dividas"] + r["parcelas_cartao"] for r in rows]
    now_in = next(s["now"] for s in sections if s["key"] == "entradas")
    now_out = sum(s["now"] for s in sections if s["key"] != "entradas")
    return {
        "months": [r["month"] for r in rows],
        "sections": sections,
        "saldo_inicial": round(start_balance, 2),
        "totais": {
            "entradas": {"now": round(now_in, 2), "values": rnd(entradas)},
            "saidas": {"now": round(now_out, 2), "values": rnd(saidas)},
            "saldo_mes": {"now": round(pending, 2), "values": rnd([e - s for e, s in zip(entradas, saidas, strict=True)])},
            "acumulado": {"now": round(start_balance + pending, 2), "values": [r["saldo"] for r in rows]},
        },
    }


def _ref(key: tuple) -> str:
    """Referência estável de uma linha da tabela (usada pelos agrupamentos)."""
    if key[0] == "cat":
        return f"cat:{key[1] if key[1] is not None else 'none'}"
    if key[0] == "plan":
        return f"plan:{key[-1]}"
    return f"{key[0]}:{key[1]}"


def _groupings(db: Session, table: dict) -> list[dict]:
    """Soma com sinal (entradas +, saídas e dívidas −) das linhas de cada agrupamento, mês a mês."""
    n = len(table["months"])
    by_ref: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for s in table["sections"]:
        sign = 1 if s["key"] == "entradas" else -1
        for g in s["groups"]:
            for r in g["rows"]:
                by_ref[r["ref"]].append((sign, r))
    out = []
    for gr in db.scalars(select(Grouping).order_by(Grouping.sort_order, Grouping.id)):
        rows = []
        for m in gr.members:
            for sign, r in by_ref.get(m.ref, []):
                rows.append({"label": r["label"], "ref": r["ref"], "now": round(sign * r["now"], 2),
                             "values": [round(sign * v, 2) for v in r["values"]]})
        out.append({"id": gr.id, "name": gr.name, "refs": [m.ref for m in gr.members], "rows": rows,
                    "now": round(sum(r["now"] for r in rows), 2),
                    "values": [round(sum(r["values"][i] for r in rows), 2) for i in range(n)]})
    return out


# ---------------------------------------------------------------- plano do mês (visão Mês do Planejamento)

def month_plan(db: Session, person: str | None, month: date, today: date) -> dict:
    """Plano de um mês num modelo só (como Monarch/Simplifi):

    Entradas − Contas fixas − Dívidas e parcelas − Gastos variáveis = Sobra prevista.
    Entradas e contas fixas vêm dos previstos; dívidas, das parcelas (dívidas, cartão e previstos do grupo Dívidas);
    gastos variáveis, do orçamento das categorias sem previsto no mês (e das que tiveram gasto). Cada linha traz
    o realizado: previsto pago, gasto do extrato na categoria. Agrupamentos entram só como informação."""
    m = fin.month_start(month)
    current = fin.month_start(today)
    accs = accounts_for(db, person)
    acc_ids = [a.id for a in accs]
    cats = {c.id: c for c in db.scalars(select(Category))}
    eff = cockpit.effects(db, today)
    occ = cockpit.apply_overrides(planned_mod.occurrences(db, today, m, m, person, acc_ids), eff)
    actual = _category_totals(db, acc_ids, m, fin.add_months(m, 1))
    budgets = budget_map(db, m)
    month_specific = {b.category_id for b in db.scalars(select(Budget).where(Budget.month == m))}

    def is_debt_cat(cid):
        return cid in cats and cats[cid].group == "Dívidas"

    entradas, fixas, dividas, variaveis = [], [], [], []
    planned_cats = {o.category_id for o in occ if o.category_id is not None and o.status != "pulado"}
    for o in occ:
        row = {"type": "previsto", **o.as_dict(), "category": cats[o.category_id].name if o.category_id in cats else None,
               "actual": o.amount if o.status == "pago" else 0.0}
        if o.kind == "receita":
            entradas.append(row)
        elif is_debt_cat(o.category_id):
            dividas.append(row)
        else:
            fixas.append(row)
    # ações ligadas do cockpit que somam entradas/saídas neste mês (na visão de todos)
    if person in (None, "", "all"):
        for x in eff.extras:
            if x.month == m:
                row = {"type": "acao", "action_id": x.action_id, "name": x.label, "action": x.action, "kind": x.kind,
                       "amount": round(x.amount, 2), "actual": 0.0, "status": "pendente"}
                (entradas if x.kind == "receita" else fixas).append(row)

    # parcelas de dívidas e de cartão que caem no mês
    debt_q = select(Debt).where(Debt.active.is_(True))
    if person == "conjunto":
        debt_q = debt_q.where(Debt.owner_id.is_(None))
    elif person and person != "all":
        debt_q = debt_q.where(Debt.owner_id == int(person))
    for d in db.scalars(debt_q.order_by(Debt.id)):
        v = cockpit.apply_payoff(d, cockpit.schedule(d, today), eff, today).get(m)
        if v:
            n = fin.months_between(fin.month_start(d.first_due), m) + 1 if d.first_due else None
            due = fin.day_in_month(m, d.first_due.day).isoformat() if d.first_due else None
            if eff.payoffs.get(d.id) == m:
                n = None  # quitação: o saldo inteiro neste mês
            dividas.append({"type": "divida", "debt_id": d.id, "amount": round(v, 2), "due": due,
                            "name": f"{d.name} · quitação" if eff.payoffs.get(d.id) == m else d.name,
                            "installment_n": n, "installment_total": d.total_installments, "actual": 0.0,
                            "status": "pago" if due and due < today.isoformat() else "pendente"})
    for a in accs:
        if a.kind == "cartao":
            v = fin.future_installments(_card_txs(db, a), a.closing_day or 1).get(m)
            if v:
                dividas.append({"type": "cartao", "account_id": a.id, "name": f"Parcelas no cartão · {a.name}",
                                "amount": round(v, 2), "due": None, "actual": 0.0, "status": "pendente"})

    # orçamento: receitas sem previsto somam às entradas; despesas viram gastos variáveis
    shown = set()
    for cid, amount in budgets.items():
        cat = cats.get(cid)
        if cat is None or cat.type == "transferencia" or is_debt_cat(cid) or cid in planned_cats:
            continue
        spent = _actual(cat, actual.get(cid, 0.0))
        row = {"type": "orcamento", "category_id": cid, "name": cat.name, "group": cat.group, "amount": round(amount, 2),
               "actual": round(spent, 2), "scope": "mes" if cid in month_specific else "padrao"}
        (entradas if cat.type == "receita" else variaveis).append(row)
        shown.add(cid)
    for cid, signed in actual.items():  # gasto sem orçamento também aparece (onde o dinheiro foi)
        cat = cats.get(cid)
        if cid in shown or cid in planned_cats or (cat and (cat.type != "despesa" or is_debt_cat(cid))):
            continue
        spent = _actual(cat, signed)
        if spent > 0.005:
            variaveis.append({"type": "orcamento", "category_id": cid, "name": cat.name if cat else "Sem categoria",
                              "group": cat.group if cat else "Outros", "amount": 0.0, "actual": round(spent, 2), "scope": None})
    variaveis.sort(key=lambda r: (-max(r["amount"], r["actual"]), r["name"]))

    def live(rows):
        return [r for r in rows if r.get("status") != "pulado"]

    def total(rows, key="amount"):
        return round(sum(r[key] for r in live(rows)), 2)

    received = round(sum(_actual(cats.get(cid), v) for cid, v in actual.items() if cid in cats and cats[cid].type == "receita"), 2)
    sec = {
        "entradas": {"planned": total(entradas), "actual": max(received, total(entradas, "actual")), "items": entradas},
        "fixas": {"planned": total(fixas), "actual": total(fixas, "actual"), "items": fixas},
        "dividas": {"planned": total(dividas), "actual": total(dividas, "actual"), "items": dividas},
        "variaveis": {"planned": total(variaveis), "actual": total(variaveis, "actual"), "items": variaveis},
    }
    saidas = sec["fixas"]["planned"] + sec["dividas"]["planned"] + sec["variaveis"]["planned"]
    late = [o.as_dict() for o in planned_mod.overdue(db, today, person, acc_ids) if o.month < m.isoformat()] if m == current else []

    # agrupamentos (informativos): soma com sinal das linhas do mês
    refs: dict[str, float] = defaultdict(float)
    for r in live(entradas):
        ref = {"previsto": f"plan:{r['name']}", "acao": f"acao:{r.get('action_id')}"}.get(r["type"], f"cat:{r.get('category_id')}")
        refs[ref] += r["amount"]
    for r in live(fixas) + live(dividas) + variaveis:
        key = {"previsto": lambda r: f"plan:{r['name']}", "divida": lambda r: f"debt:{r['debt_id']}",
               "acao": lambda r: f"acao:{r['action_id']}",
               "cartao": lambda r: f"card:{r['account_id']}", "orcamento": lambda r: f"cat:{r['category_id']}"}[r["type"]](r)
        refs[key] -= r["amount"]
    groupings = [{"id": g.id, "name": g.name, "value": round(sum(refs.get(mm.ref, 0.0) for mm in g.members), 2)}
                 for g in db.scalars(select(Grouping).order_by(Grouping.sort_order, Grouping.id))]

    return {
        "month": m.isoformat(), "is_current": m == current, "is_past": m < current,
        "sections": sec,
        "entradas": sec["entradas"]["planned"], "saidas": round(saidas, 2),
        "sobra": round(sec["entradas"]["planned"] - saidas, 2),
        "atrasos": late, "atrasos_total": round(sum(o["amount"] for o in late if o["kind"] == "despesa"), 2),
        "groupings": groupings,
    }


def month_balance(db: Session, person: str | None, month: date, today: date) -> dict:
    """Saldo acumulado no fim do mês (o mesmo da linha "Saldo acumulado" do Fluxo) e com quanto o mês começa.

    Mês futuro: projeção. Mês atual: contas menos faturas abertas, mais o que ainda entra/sai no mês.
    Mês passado: saldo realizado das contas no fim do mês (sem projeção)."""
    m, cur = fin.month_start(month), fin.month_start(today)
    if m < cur:
        accs = [a for a in accounts_for(db, person) if a.kind in LIQUID]
        now = sum(balances(db, accs).values())

        def after(d: date) -> float:
            if not accs:
                return 0.0
            return float(db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.account_id.in_([a.id for a in accs]), Transaction.date >= d)) or 0.0)
        return {"kind": "realizado", "end": round(now - after(fin.add_months(m, 1)), 2), "start": round(now - after(m), 2)}
    k = fin.months_between(cur, m)
    p = projection(db, person, today, max(k, 1))
    now_end = round(p["saldo_inicial"] - p["months"][0]["pendentes"], 2)  # fim do mês atual
    if k == 0:
        return {"kind": "previsto", "end": now_end, "start": p["saldo_atual"]}
    rows = p["months"]
    return {"kind": "previsto", "end": rows[k - 1]["saldo"], "start": rows[k - 2]["saldo"] if k > 1 else now_end}
