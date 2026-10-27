"""Lançamentos realizados (controle do dia a dia)."""
import csv
import io
import re
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import engine as eng
from .. import schemas
from ..db import get_session
from ..models import Account, Category, Transaction

router = APIRouter(prefix="/api/transactions", tags=["lançamentos"])


@router.get("", response_model=list[schemas.TransactionOut])
def list_transactions(month: date | None = None, category_id: int | None = None, account_id: int | None = None,
                      db: Session = Depends(get_session)):
    q = select(Transaction).order_by(Transaction.date.desc(), Transaction.id.desc())
    if month is not None:
        start = eng.month_start(month)
        q = q.where(Transaction.date >= start, Transaction.date < eng.add_months(start, 1))
    if category_id is not None:
        q = q.where(Transaction.category_id == category_id)
    if account_id is not None:
        q = q.where(Transaction.account_id == account_id)
    return db.scalars(q).all()


@router.post("", response_model=schemas.TransactionOut, status_code=201)
def create_transaction(data: schemas.TransactionIn, db: Session = Depends(get_session)):
    tx = Transaction(**data.model_dump())
    db.add(tx)
    db.commit()
    return tx


@router.put("/{tx_id}", response_model=schemas.TransactionOut)
def update_transaction(tx_id: int, data: schemas.TransactionIn, db: Session = Depends(get_session)):
    tx = db.get(Transaction, tx_id)
    if tx is None:
        raise HTTPException(404, "Lançamento não encontrado")
    for k, v in data.model_dump().items():
        setattr(tx, k, v)
    db.commit()
    return tx


@router.delete("/{tx_id}", status_code=204)
def delete_transaction(tx_id: int, db: Session = Depends(get_session)):
    tx = db.get(Transaction, tx_id)
    if tx is None:
        raise HTTPException(404, "Lançamento não encontrado")
    db.delete(tx)
    db.commit()


def parse_brl(text: str) -> float:
    """Aceita '1.234,56', '-1234.56', 'R$ 1.234,56'."""
    t = re.sub(r"[^\d,.\-]", "", text.strip())
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    return float(t)


def parse_date(text: str) -> date:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError(f"data inválida: {text!r}")


@router.post("/import-csv")
async def import_csv(file: UploadFile = File(...), db: Session = Depends(get_session)):
    """CSV com cabeçalho: data, descricao, valor[, categoria][, conta].
    Separador ';' ou ','. Valores negativos = saídas. Categorias/contas são
    associadas pelo nome (sem diferenciar maiúsculas)."""
    raw = (await file.read()).decode("utf-8-sig")
    dialect = csv.Sniffer().sniff(raw.splitlines()[0], delimiters=";,\t")
    reader = csv.DictReader(io.StringIO(raw), dialect=dialect)
    cats = {c.name.lower(): c.id for c in db.scalars(select(Category))}
    accs = {a.name.lower(): a.id for a in db.scalars(select(Account))}
    created, errors = 0, []
    for line, row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        try:
            tx = Transaction(
                date=parse_date(row["data"]),
                description=row.get("descricao") or row.get("descrição") or "",
                amount=parse_brl(row["valor"]),
                category_id=cats.get(row.get("categoria", "").lower()),
                account_id=accs.get(row.get("conta", "").lower()),
            )
        except (KeyError, ValueError) as exc:
            errors.append(f"linha {line}: {exc}")
            continue
        db.add(tx)
        created += 1
    db.commit()
    return {"created": created, "errors": errors}
