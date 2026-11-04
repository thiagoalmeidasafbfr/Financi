"""Cockpit: ações que, ligadas, mudam o fluxo projetado e o plano do mês. Desligadas, não mudam nada.

Ajuste: linhas que somam uma entrada ou saída num mês, ou substituem o valor de um previsto num mês (0 zera).
O valor de cada linha é fixo ou uma fração de outro previsto (ex.: 1/3 do Salário de nov/26), então acompanha
mudanças no previsto de referência.

Quitação: paga a dívida num mês escolhido. O valor é a parcela daquele mês mais o valor presente das seguintes,
com os juros do contrato (se a parcela do mês atual já foi descontada, só o valor presente das seguintes);
as parcelas depois disso deixam de existir."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import finance as fin
from . import planned as planned_mod
from .models import Action, ActionLine, Debt
from .text import normalize_description

GROUP = "Cockpit"


def norm(name: str | None) -> str:
    return normalize_description(name or "")


@dataclass
class Extra:
    """Entrada ou saída somada por uma linha de ajuste."""
    action_id: int
    action: str
    label: str
    month: date
    kind: str      # receita | despesa
    amount: float  # positivo


@dataclass
class Effects:
    overrides: dict[tuple[str, date], float] = field(default_factory=dict)  # (previsto, mês) → novo valor
    extras: list[Extra] = field(default_factory=list)
    payoffs: dict[int, date] = field(default_factory=dict)                  # dívida → mês da quitação

    def __bool__(self) -> bool:
        return bool(self.overrides or self.extras or self.payoffs)


class Bases:
    """Valor de cada previsto por mês (antes das ações), para as frações e para o efeito das substituições."""

    def __init__(self, db: Session, today: date, months: list[date]):
        self.values: dict[tuple[str, date], float] = defaultdict(float)
        self.names: dict[str, str] = {}
        if not months:
            return
        for o in planned_mod.occurrences(db, today, min(months), max(months), None, None):
            if o.status != "pulado":
                self.values[(norm(o.name), date.fromisoformat(o.month))] += o.amount
                self.names[norm(o.name)] = o.name

    def get(self, name: str | None, month: date) -> float | None:
        key = (norm(name), month)
        return round(self.values[key], 2) if key in self.values else None


def load(db: Session, active_only: bool = True) -> list[Action]:
    q = select(Action).options(selectinload(Action.lines)).order_by(Action.kind, Action.sort_order, Action.id)
    if active_only:
        q = q.where(Action.active.is_(True))
    return list(db.scalars(q))


def _months(actions: list[Action]) -> list[date]:
    out = set()
    for a in actions:
        for ln in a.lines:
            out.add(ln.month)
            out.add(ln.base_month or ln.month)
    return sorted(out)


def line_value(ln: ActionLine, bases: Bases) -> float | None:
    """Valor da linha: fixo, ou fração do previsto de referência (None se a referência não existe naquele mês)."""
    if ln.factor is not None:
        v = bases.get(ln.base, ln.base_month or ln.month) if ln.base else None
        return None if v is None else round(ln.factor * v, 2)
    return round(ln.amount, 2) if ln.amount is not None else None


def effects(db: Session, today: date, actions: list[Action] | None = None) -> Effects:
    """O que as ações ligadas (ou as informadas) mudam no fluxo."""
    actions = load(db) if actions is None else actions
    eff = Effects()
    if not actions:
        return eff
    bases = Bases(db, today, _months(actions))
    for a in actions:
        if a.kind == "quitacao":
            if a.debt_id and a.month:
                eff.payoffs[a.debt_id] = max(fin.month_start(a.month), fin.month_start(today))
            continue
        for ln in a.lines:
            v = line_value(ln, bases)
            if v is None:
                continue
            if ln.op == "substituir":
                if ln.target:
                    eff.overrides[(norm(ln.target), ln.month)] = max(0.0, v)
            elif v:
                eff.extras.append(Extra(a.id, a.name, ln.label, ln.month, "receita" if ln.direction == "entrada" else "despesa", abs(v)))
    return eff


def apply_overrides(items: list, eff: Effects) -> list:
    """Ocorrências de previstos com os valores substituídos (valor 0 tira a ocorrência)."""
    if not eff.overrides:
        return items
    out, done = [], set()
    for o in items:
        key = (norm(o.name), date.fromisoformat(o.month))
        if key not in eff.overrides:
            out.append(o)
            continue
        if key in done:  # dois previstos de mesmo nome no mês: o valor novo vale uma vez só
            continue
        done.add(key)
        if eff.overrides[key] > 0.005:
            out.append(replace(o, amount=eff.overrides[key], changed=True))
    return out


def schedule(d: Debt, today: date) -> dict[date, float]:
    return fin.loan_schedule(d.installment, d.first_due, d.total_installments, today=today, rate=d.monthly_rate, balance=d.balance)


def payoff_value(d: Debt, month: date, today: date) -> float:
    """Quanto custa quitar no mês: parcela do mês + valor presente das seguintes (a juros do contrato)."""
    sched = schedule(d, today)
    cur = fin.month_start(today)
    month = max(fin.month_start(month), cur)
    rest = sorted(m for m in sched if m >= month)
    if month == cur and d.first_due and fin.day_in_month(cur, d.first_due.day) < today:
        rest = [m for m in rest if m > cur]  # a parcela deste mês já foi descontada
        return round(fin.present_value(d.installment, d.monthly_rate, len(rest)), 2)
    if not rest:
        return 0.0
    return round(d.installment + fin.present_value(d.installment, d.monthly_rate, len(rest) - 1), 2)


def apply_payoff(d: Debt, sched: dict[date, float], eff: Effects, today: date) -> dict[date, float]:
    """Cronograma da dívida com a quitação: até o mês anterior igual; no mês, o valor de quitação; depois, nada."""
    if d.id not in eff.payoffs:
        return sched
    month = eff.payoffs[d.id]
    value = payoff_value(d, month, today)
    out = {m: v for m, v in sched.items() if m < month}
    if value:
        out[month] = value
    return out


def payoff_info(d: Debt, month: date, today: date) -> dict:
    """Para o cockpit: valor de quitação, parcelas evitadas, juros economizados e quanto sobra por mês depois."""
    sched = schedule(d, today)
    cur = fin.month_start(today)
    month = max(fin.month_start(month), cur)
    value = payoff_value(d, month, today)
    already = month == cur and d.first_due and fin.day_in_month(cur, d.first_due.day) < today
    avoided = sum(v for m, v in sched.items() if m > month or (m == month and not already))
    return {"payoff": value, "avoided": round(avoided, 2), "interest_saved": round(max(0.0, avoided - value), 2),
            "installments_left": sum(1 for m in sched if m > month or (m == month and not already)),
            "end_month": max(sched).isoformat() if sched else None}


def impact(db: Session, today: date, a: Action, bases: Bases | None = None) -> dict:
    """Efeito da ação no caixa, mês a mês (com sinal: + entra, − sai), e as linhas com o valor calculado."""
    by: dict[date, float] = defaultdict(float)
    lines = []
    if a.kind == "quitacao":
        d = db.get(Debt, a.debt_id) if a.debt_id else None
        if d and a.month:
            sched = schedule(d, today)
            after = apply_payoff(d, sched, Effects(payoffs={d.id: max(fin.month_start(a.month), fin.month_start(today))}), today)
            for m in set(sched) | set(after):
                delta = sched.get(m, 0.0) - after.get(m, 0.0)
                if m == fin.month_start(today) and d.first_due and fin.day_in_month(m, d.first_due.day) < today:
                    delta = -after.get(m, 0.0)  # a parcela deste mês já saiu (não muda): só a quitação conta agora
                if abs(delta) > 0.005:
                    by[m] += delta
    else:
        bases = bases or Bases(db, today, _months([a]))
        for ln in a.lines:
            v = line_value(ln, bases)
            problem = None
            delta = 0.0
            if v is None:
                problem = f"“{ln.base}” não tem valor em {ln.base_month or ln.month:%m/%Y}" if ln.factor is not None else "sem valor"
            elif ln.op == "substituir":
                before = bases.get(ln.target, ln.month)
                if before is None:
                    problem = f"“{ln.target}” não existe em {ln.month:%m/%Y}"
                else:
                    delta = max(0.0, v) - before
            else:
                delta = abs(v) if ln.direction == "entrada" else -abs(v)
            if delta:
                by[ln.month] += delta
            lines.append({**line_out(ln), "value": v, "delta": round(delta, 2), "problem": problem})
    months = sorted(by)
    return {"by_month": [{"month": m.isoformat(), "value": round(by[m], 2)} for m in months if abs(by[m]) > 0.005],
            "total": round(sum(by.values()), 2), "lines": lines}


def line_out(ln: ActionLine) -> dict:
    return {"id": ln.id, "month": ln.month.isoformat(), "label": ln.label, "op": ln.op, "direction": ln.direction,
            "amount": ln.amount, "factor": ln.factor, "base": ln.base,
            "base_month": ln.base_month.isoformat() if ln.base_month else None, "target": ln.target}
