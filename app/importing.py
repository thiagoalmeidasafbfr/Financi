"""Importação de extratos OFX: conta, duplicidade, categorização e saldo."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import ai
from .categorize import apply_ai, apply_rules
from .models import Account, ImportBatch, Transaction
from .ofx import parse_ofx
from .text import merchant_key, parse_installment


def find_or_create_account(db: Session, st, account_id: int | None, owner_id: int | None) -> tuple[Account, bool]:
    if account_id is not None:
        acc = db.get(Account, account_id)
        if acc is None:
            raise ValueError("Conta não encontrada")
        if st.acct_id and not acc.acct_id:  # passa a reconhecer a conta pelo OFX
            acc.acct_id, acc.bank_id = st.acct_id, st.bank_id
        return acc, False
    if st.acct_id:
        q = select(Account).where(Account.acct_id == st.acct_id)
        if st.bank_id:
            q = q.where((Account.bank_id == st.bank_id) | (Account.bank_id.is_(None)))
        acc = db.scalar(q)
        if acc:
            return acc, False
    kind = "cartao" if st.is_card else ("poupanca" if (st.acct_type or "").upper() == "SAVINGS" else "corrente")
    tail = (st.acct_id or "")[-4:]
    name = f"{'Cartão' if st.is_card else 'Conta'} {st.org or st.bank_id or ''} {tail}".replace("  ", " ").strip()
    acc = Account(name=name, institution=st.org, kind=kind, owner_id=owner_id, bank_id=st.bank_id, acct_id=st.acct_id)
    db.add(acc)
    db.flush()
    return acc, True


def import_ofx(db: Session, content: bytes, filename: str, account_id: int | None = None,
               owner_id: int | None = None, ai_client=None) -> dict:
    st = parse_ofx(content)
    acc, created = find_or_create_account(db, st, account_id, owner_id)
    is_card = acc.kind == "cartao"
    existing = set(db.scalars(select(Transaction.dedupe_key).where(Transaction.account_id == acc.id)))
    batch = ImportBatch(account_id=acc.id, filename=filename[:255], period_start=st.start, period_end=st.end,
                        total=len(st.transactions), balance=st.balance, balance_date=st.balance_date)
    db.add(batch)
    db.flush()
    new: list[Transaction] = []
    for t in st.transactions:
        if t.dedupe_key in existing:
            continue
        existing.add(t.dedupe_key)
        n, total = parse_installment(t.description, is_card=is_card)
        tx = Transaction(account_id=acc.id, date=t.date, amount=t.amount, description=t.description,
                         merchant=merchant_key(t.description), installment_n=n, installment_total=total,
                         dedupe_key=t.dedupe_key, import_id=batch.id)
        db.add(tx)
        new.append(tx)
    db.flush()
    batch.new, batch.duplicates = len(new), len(st.transactions) - len(new)
    batch.by_rule = apply_rules(db, new)
    batch.by_ai = apply_ai(db, new, client=ai_client)
    batch.uncategorized = sum(1 for t in new if t.category_id is None)

    # conta corrente/poupança: alinha o saldo ao informado pelo banco na data do extrato
    if not is_card and st.balance is not None and st.balance_date is not None:
        db.flush()
        moved = db.scalar(select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.account_id == acc.id, Transaction.date <= st.balance_date)) or 0
        acc.opening_balance = round(st.balance - float(moved), 2)
    db.commit()
    return {
        "import_id": batch.id, "account": {"id": acc.id, "name": acc.name, "kind": acc.kind, "created": created},
        "period": [st.start.isoformat() if st.start else None, st.end.isoformat() if st.end else None],
        "total": batch.total, "new": batch.new, "duplicates": batch.duplicates,
        "by_rule": batch.by_rule, "by_ai": batch.by_ai, "uncategorized": batch.uncategorized,
        "balance": st.balance, "ai_enabled": ai_client is not None or ai.available(),
    }
