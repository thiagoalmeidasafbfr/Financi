"""Lançamentos previstos: ocorrências no fluxo futuro, situação (pago, pendente, em atraso, pulado) e ajustes por mês."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from . import finance as fin
from .models import Planned, Transaction

# ocorrências mensais anteriores ao cadastro não viram atraso (quem cadastra "aluguel desde janeiro" quer dizer que já paga);
# para registrar algo atrasado, cadastre uma ocorrência pontual no mês em que venceu
FAR = date(1900, 1, 1)


@dataclass
class Occurrence:
    planned_id: int
    name: str
    kind: str
    category_id: int | None
    owner_id: int | None
    recurrence: str
    month: str          # mês em que cai (depois de mover)
    original: str       # mês original (identifica a ocorrência)
    amount: float       # positivo
    due: str
    status: str         # pago | pendente | atrasado | pulado
    paid_auto: bool     # pago reconhecido pelo extrato
    moved: bool
    changed: bool       # valor diferente da série
    start_month: str
    end_month: str | None

    def as_dict(self) -> dict:
        return asdict(self)


def _floor(p: Planned) -> date:
    """Primeiro mês que conta: mensal começa no cadastro se o início estiver no passado; pontual vale sempre."""
    if p.recurrence == "pontual":
        return p.start_month
    created = fin.month_start(p.created_at.date()) if p.created_at else p.start_month
    return max(p.start_month, created)


def _before_signup(p: Planned, orig: date) -> bool:
    """Série que já existia antes do cadastro: a parcela do mês do cadastro que venceu antes dele não conta."""
    if p.recurrence != "mensal" or not p.created_at:
        return False
    created = p.created_at.date()
    return p.start_month < fin.month_start(created) == orig and fin.day_in_month(orig, p.due_day or 31) < created


def _originals(p: Planned, until: date) -> list[date]:
    if p.recurrence == "pontual":
        return [p.start_month]
    last = min(p.end_month, until) if p.end_month else until
    first = _floor(p)
    return [fin.add_months(first, k) for k in range(fin.months_between(first, last) + 1)] if last >= first else []


def _paid_by_statement(db: Session, p: Planned, month: date, account_ids: list[int] | None) -> bool:
    """Procura no extrato do mês um lançamento com o texto informado e o sinal do previsto."""
    if not p.match_pattern:
        return False
    like = f"%{p.match_pattern.strip()}%"
    q = select(Transaction.id).where(
        Transaction.date >= month, Transaction.date < fin.add_months(month, 1),
        or_(Transaction.description.ilike(like), Transaction.merchant.ilike(like)),
        Transaction.amount < 0 if p.kind == "despesa" else Transaction.amount > 0,
    )
    if account_ids is not None:
        q = q.where(Transaction.account_id.in_(account_ids))
    return db.scalar(q.limit(1)) is not None


def load(db: Session, person: str | None = None) -> list[Planned]:
    q = select(Planned).where(Planned.active.is_(True)).options(selectinload(Planned.changes)).order_by(Planned.id)
    if person == "conjunto":
        q = q.where(Planned.owner_id.is_(None))
    elif person and person != "all":
        q = q.where(Planned.owner_id == int(person))
    return list(db.scalars(q))


def occurrences(db: Session, today: date, start: date | None, end: date, person: str | None = None,
                account_ids: list[int] | None = None) -> list[Occurrence]:
    """Ocorrências que caem entre start e end (meses, inclusive), já com mudanças de mês, valor e situação."""
    start = start or FAR
    current = fin.month_start(today)
    out: list[Occurrence] = []
    for p in load(db, person):
        changes = {c.month: c for c in p.changes}
        originals = set(_originals(p, end)) | set(changes)  # mudanças cobrem ocorrências movidas de fora do intervalo
        for orig in sorted(originals):
            if orig < _floor(p) or (p.recurrence == "mensal" and p.end_month and orig > p.end_month):
                continue
            if p.recurrence == "pontual" and orig != p.start_month:
                continue
            if _before_signup(p, orig):
                continue
            ch = changes.get(orig)
            month = ch.moved_to if ch and ch.moved_to else orig
            if not (start <= month <= end):
                continue
            amount = ch.amount if ch and ch.amount is not None else p.amount
            due = fin.day_in_month(month, p.due_day or 31)
            paid_auto = False
            if ch and ch.skipped:
                status = "pulado"
            elif ch and ch.paid is not None:
                status = "pago" if ch.paid else ("atrasado" if due < today else "pendente")
            else:
                paid_auto = month <= current and _paid_by_statement(db, p, month, account_ids)
                status = "pago" if paid_auto else ("atrasado" if due < today else "pendente")
            out.append(Occurrence(
                planned_id=p.id, name=p.name, kind=p.kind, category_id=p.category_id, owner_id=p.owner_id,
                recurrence=p.recurrence, month=month.isoformat(), original=orig.isoformat(), amount=round(float(amount), 2),
                due=due.isoformat(), status=status, paid_auto=paid_auto, moved=month != orig,
                changed=bool(ch and ch.amount is not None), start_month=p.start_month.isoformat(),
                end_month=p.end_month.isoformat() if p.end_month else None,
            ))
    out.sort(key=lambda o: (o.month, o.due, o.name))
    return out


def overdue(db: Session, today: date, person: str | None = None, account_ids: list[int] | None = None) -> list[Occurrence]:
    """Tudo o que venceu e não foi pago (de qualquer mês até hoje)."""
    return [o for o in occurrences(db, today, None, fin.month_start(today), person, account_ids) if o.status == "atrasado"]


def flow(db: Session, today: date, months: int, person: str | None = None, account_ids: list[int] | None = None) -> dict:
    """Fluxo futuro mês a mês (a partir do mês atual) e a lista do que está em atraso."""
    first = fin.month_start(today)
    last = fin.add_months(first, months - 1)
    occ = occurrences(db, today, first, last, person, account_ids)
    late = [o for o in overdue(db, today, person, account_ids) if o.month < first.isoformat()]
    rows = []
    for k in range(months):
        m = fin.add_months(first, k).isoformat()
        items = [o for o in occ if o.month == m]
        live = [o for o in items if o.status != "pulado"]
        ins = sum(o.amount for o in live if o.kind == "receita")
        outs = sum(o.amount for o in live if o.kind == "despesa")
        rows.append({"month": m, "items": [o.as_dict() for o in items], "entradas": round(ins, 2), "saidas": round(outs, 2),
                     "saldo": round(ins - outs, 2)})
    late_all = late + [o for o in occ if o.status == "atrasado"]
    return {
        "overdue": [o.as_dict() for o in late_all],
        "overdue_total": round(sum(o.amount for o in late_all if o.kind == "despesa"), 2),
        "months": rows,
    }


def projection_items(db: Session, today: date, months: int, person: str | None = None,
                     account_ids: list[int] | None = None) -> tuple[dict[str, list[Occurrence]], list[Occurrence]]:
    """Para a projeção: ocorrências não pagas por mês futuro; e as pendentes agora (atrasadas + o que ainda vence
    no mês atual), que saem do caixa no primeiro mês projetado."""
    current = fin.month_start(today).isoformat()
    occ = occurrences(db, today, None, fin.add_months(fin.month_start(today), months), person, account_ids)
    by_month: dict[str, list[Occurrence]] = {}
    pending: list[Occurrence] = []
    for o in occ:
        if o.status in ("pago", "pulado"):
            continue
        if o.month <= current:
            pending.append(o)
        else:
            by_month.setdefault(o.month, []).append(o)
    return by_month, pending
