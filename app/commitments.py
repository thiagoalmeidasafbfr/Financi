"""Compromissos: quanto de cada mês já está comprometido, e quando alivia.

Para cada mês (do atual em diante, mês cheio):
- contas fixas: previstos de despesa mensais (aluguel, escola, plano de saúde…);
- parcelas: dívidas (consignados, empréstimos), faturas previstas de cartão e parcelas de cartão dos extratos,
  previstos do grupo Dívidas;
- pontuais: previstos de despesa de uma vez (IPVA, viagem…) e saídas das ações ligadas do Cockpit;
- variável: orçamento ou média dos últimos meses das categorias sem previsto no mês (mesma regra do Fluxo);
- renda: receitas previstas (e orçamento/média das categorias de receita sem previsto).
Comprometido = fixas + parcelas + pontuais. Alívios: quando uma conta fixa ou parcela termina ou diminui (e fica
menor nos meses seguintes), a partir de quando e quanto sobra por mês."""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import cockpit
from . import finance as fin
from . import planned as planned_mod
from .models import Category, Debt
from .services import CARD_GROUP, _card_txs, _category_totals, _months_with_data, accounts_for, budget_map

KINDS = ("fixas", "parcelas", "pontuais", "variavel")
RELIEF_MIN = 20.0       # alívio menor que isso é ruído (ajuste de centavos, mês com valor diferente)
RELIEF_HORIZON = 48     # meses olhados para achar os próximos alívios


def _lines(db: Session, person: str | None, today: date, months: int, variable: bool = True) -> tuple[list[date], dict, list[float], dict]:
    """Linhas (tipo, grupo, rótulo, ref) → valores por mês; renda por mês; e detalhes das dívidas."""
    cur = fin.month_start(today)
    ms = [fin.add_months(cur, k) for k in range(months)]
    idx = {m: i for i, m in enumerate(ms)}
    accs = accounts_for(db, person)
    acc_ids = [a.id for a in accs]
    cats = {c.id: c for c in db.scalars(select(Category))}
    eff = cockpit.effects(db, today)
    everyone = person in (None, "", "all")
    lines: dict[tuple, list[float]] = defaultdict(lambda: [0.0] * months)
    income = [0.0] * months
    debt_info: dict[str, dict] = {}

    def add(kind: str, group: str, label: str, ref: str, m: date, v: float) -> None:
        if v and m in idx:
            lines[(kind, group, label, ref)][idx[m]] += v

    # previstos (mês cheio: inclui os já pagos; pulados não contam), com as substituições das ações do Cockpit
    occ = cockpit.apply_overrides(planned_mod.occurrences(db, today, cur, ms[-1], person, acc_ids), eff)
    planned_cats: dict[date, set] = defaultdict(set)
    for o in occ:
        if o.status == "pulado":
            continue
        m = date.fromisoformat(o.month)
        if o.category_id is not None:
            planned_cats[m].add(o.category_id)
        if o.kind == "receita":
            if m in idx:
                income[idx[m]] += o.amount
            continue
        cat = cats.get(o.category_id)
        group = cat.group if cat else "Outros"
        if cat and cat.group == CARD_GROUP:
            add("parcelas", "Cartões", o.name, f"plan:{o.name}", m, o.amount)
        elif cat and cat.group == "Dívidas":
            add("parcelas", "Dívidas e parcelas", o.name, f"plan:{o.name}", m, o.amount)
        else:
            add("fixas" if o.recurrence == "mensal" else "pontuais", group, o.name, f"plan:{o.name}", m, o.amount)

    # ações do Cockpit que somam entradas/saídas (na visão de todos)
    for x in eff.extras if everyone else []:
        if x.month in idx:
            if x.kind == "receita":
                income[idx[x.month]] += x.amount
            else:
                add("pontuais", f"{cockpit.GROUP} · {x.action}", x.label, f"acao:{x.action_id}", x.month, x.amount)

    # dívidas (com a quitação, se ligada no Cockpit)
    q = select(Debt).where(Debt.active.is_(True))
    if person == "conjunto":
        q = q.where(Debt.owner_id.is_(None))
    elif person and not everyone:
        q = q.where(Debt.owner_id == int(person))
    for d in db.scalars(q.order_by(Debt.id)):
        sched = cockpit.apply_payoff(d, cockpit.schedule(d, today), eff, today)
        for m, v in sched.items():
            add("parcelas", "Dívidas e parcelas", d.name, f"debt:{d.id}", m, v)
        debt_info[f"debt:{d.id}"] = {"total": d.total_installments, "first": fin.month_start(d.first_due) if d.first_due else None,
                                     "payoff": eff.payoffs.get(d.id)}

    # parcelas de cartão que vêm dos extratos
    for a in accs:
        if a.kind == "cartao":
            txs, closing = _card_txs(db, a), a.closing_day or 1
            current = fin.invoice_month(today, closing)
            for m, v in fin.future_installments(txs, closing).items():
                if m > current:
                    add("parcelas", "Cartões", f"Parcelas no cartão · {a.name}", f"card:{a.id}", m, v)

    # variável e renda por orçamento/média (categorias sem previsto no mês), como no Fluxo
    h_start = fin.add_months(cur, -3)
    n_hist = _months_with_data(db, acc_ids, h_start, cur, 3)
    hist = {cid: v / n_hist for cid, v in _category_totals(db, acc_ids, h_start, cur).items()}
    for m in ms if variable else []:
        b = budget_map(db, m)
        for cid in set(b) | set(hist):
            cat = cats.get(cid)
            if cid in planned_cats[m] or (cat and (cat.type == "transferencia" or cat.group in ("Dívidas", CARD_GROUP))):
                continue
            if cat is not None and cat.type == "receita":
                income[idx[m]] += b[cid] if cid in b else max(0.0, hist[cid])
                continue
            v = b[cid] if cid in b else max(0.0, -hist[cid])
            ref = f"cat:{cid if cid is not None else 'none'}"
            add("variavel", cat.group if cat else "Outros", cat.name if cat else "Sem categoria", ref, m, v)
    return ms, lines, income, debt_info


def _reliefs(ms: list[date], lines: dict, debt_info: dict, today: date) -> list[dict]:
    """Quedas que se mantêm (conta fixa ou parcela que termina ou diminui) nos próximos meses."""
    out = []
    for (kind, group, label, ref), vals in lines.items():
        if kind not in ("fixas", "parcelas"):
            continue
        for i in range(1, len(vals)):
            drop = vals[i - 1] - vals[i]
            rest = vals[i:i + 3]
            if drop < RELIEF_MIN or any(v > vals[i] + 0.005 for v in rest):  # só queda que se mantém
                continue
            ends = vals[i] < 0.005
            item = {"label": label, "group": group, "kind": kind, "ref": ref, "amount": round(drop, 2),
                    "last_month": ms[i - 1].isoformat(), "from_month": ms[i].isoformat(), "ends": ends}
            info = debt_info.get(ref)
            if info and ends:
                pay = info["payoff"]
                if pay and fin.month_start(pay) == ms[i - 1]:
                    item["detail"] = f"quitação em {pay:%d/%m/%Y}"
                elif info["total"] and info["first"]:
                    n = fin.months_between(info["first"], ms[i - 1]) + 1
                    item["detail"] = f"última parcela {n}/{info['total']}"
            out.append(item)
    out.sort(key=lambda r: (r["from_month"], -r["amount"]))
    return out


def commitments(db: Session, person: str | None, today: date, months: int = 12) -> dict:
    months = max(3, min(months, 36))
    ms, lines, income, debt_info = _lines(db, person, today, months)
    rows = []
    for i, m in enumerate(ms):
        tot = {k: round(sum(v[i] for (kind, *_), v in lines.items() if kind == k), 2) for k in KINDS}
        committed = round(tot["fixas"] + tot["parcelas"] + tot["pontuais"], 2)
        total = round(committed + tot["variavel"], 2)
        rows.append({"month": m.isoformat(), **tot, "committed": committed, "total": total, "income": round(income[i], 2),
                     "margin": round(income[i] - total, 2), "pct": round(committed / income[i], 4) if income[i] > 0 else None})
    groups: dict[str, dict] = {}
    for (kind, group, label, ref), vals in lines.items():
        if not any(abs(v) > 0.005 for v in vals):
            continue
        g = groups.setdefault(group, {"group": group, "values": [0.0] * len(ms), "items": []})
        g["values"] = [a + b for a, b in zip(g["values"], vals, strict=True)]
        g["items"].append({"label": label, "kind": kind, "ref": ref, "values": [round(v, 2) for v in vals]})
    for g in groups.values():
        g["values"] = [round(v, 2) for v in g["values"]]
        g["items"].sort(key=lambda it: -sum(it["values"]))
        g["kinds"] = sorted({it["kind"] for it in g["items"]}, key=KINDS.index)
    # alívios num horizonte maior (uma parcela de 48 meses termina depois do gráfico)
    if months < RELIEF_HORIZON:
        long_ms, long_lines, _, long_debts = _lines(db, person, today, RELIEF_HORIZON, variable=False)
    else:
        long_ms, long_lines, long_debts = ms, lines, debt_info
    return {
        "months": rows,
        "groups": sorted(groups.values(), key=lambda g: -sum(g["values"])),
        "reliefs": _reliefs(long_ms, long_lines, long_debts, today)[:10],
    }
