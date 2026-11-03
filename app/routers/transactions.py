"""Lançamentos e importação de extratos OFX."""
import uuid
from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import planilha, schemas
from ..categorize import apply_ai, learn
from ..db import get_session
from ..finance import add_months, month_start
from ..importing import import_ofx
from ..models import Account, Category, ImportBatch, Person, Transaction
from ..ofx import OFXError
from ..services import accounts_for
from ..text import merchant_key, parse_installment

router = APIRouter(prefix="/api", tags=["lançamentos"])

MAX_UPLOAD = 4 * 1024 * 1024  # limite de requisição das funções do Vercel é 4,5 MB


def _tx_out(t: Transaction) -> dict:
    return {
        "id": t.id, "account_id": t.account_id, "date": t.date.isoformat(), "amount": t.amount,
        "description": t.description, "merchant": t.merchant, "category_id": t.category_id,
        "categorized_by": t.categorized_by, "confidence": t.confidence, "reviewed": t.reviewed,
        "installment": [t.installment_n, t.installment_total] if t.installment_total else None,
        "notes": t.notes, "import_id": t.import_id,
    }


@router.get("/transactions")
def list_transactions(month: date | None = None, person: str | None = None, account_id: int | None = None,
                      category_id: int | None = None, status: str | None = None, q: str | None = None,
                      limit: int = 500, db: Session = Depends(get_session)):
    """status: sem_categoria | revisar (sem categoria ou IA pouco confiante) | ia."""
    acc_ids = [a.id for a in accounts_for(db, person)]
    query = select(Transaction).where(Transaction.account_id.in_(acc_ids))
    if account_id:
        query = query.where(Transaction.account_id == account_id)
    if month:
        m = month_start(month)
        query = query.where(Transaction.date >= m, Transaction.date < add_months(m, 1))
    if category_id:
        query = query.where(Transaction.category_id == category_id)
    if status == "sem_categoria":
        query = query.where(Transaction.category_id.is_(None))
    elif status == "revisar":
        query = query.where(Transaction.reviewed.is_(False), or_(
            Transaction.category_id.is_(None),
            (Transaction.categorized_by == "ia") & (func.coalesce(Transaction.confidence, 0) < 0.8)))
    elif status == "ia":
        query = query.where(Transaction.categorized_by == "ia")
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Transaction.description.ilike(like), Transaction.merchant.ilike(like),
                                Transaction.notes.ilike(like)))
    rows = db.scalars(query.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(min(limit, 2000))).all()
    return [_tx_out(t) for t in rows]


@router.post("/transactions", status_code=201)
def create_transaction(data: schemas.TransactionIn, db: Session = Depends(get_session)):
    acc = db.get(Account, data.account_id)
    if acc is None:
        raise HTTPException(404, "Conta não encontrada")
    n, total = parse_installment(data.description, acc.kind == "cartao")
    t = Transaction(account_id=acc.id, date=data.date, amount=round(data.amount, 2), description=data.description,
                    merchant=merchant_key(data.description), category_id=data.category_id,
                    categorized_by="manual" if data.category_id else None, reviewed=bool(data.category_id),
                    installment_n=n, installment_total=total, notes=data.notes, dedupe_key=f"manual-{uuid.uuid4().hex}")
    db.add(t)
    db.commit()
    return _tx_out(t)


@router.patch("/transactions/{tid}")
def patch_transaction(tid: int, data: schemas.TransactionPatch, db: Session = Depends(get_session)):
    """Mudar a categoria cria uma regra para o estabelecimento e corrige os lançamentos parecidos."""
    t = db.get(Transaction, tid)
    if t is None:
        raise HTTPException(404, "Lançamento não encontrado")
    fields = data.model_dump(exclude_unset=True)
    similar = 0
    if "category_id" in fields:
        if data.category_id is None:
            t.category_id, t.categorized_by, t.confidence = None, None, None
        else:
            if db.get(Category, data.category_id) is None:
                raise HTTPException(400, "Categoria não existe")
            if data.learn:
                similar = learn(db, t, data.category_id)
            else:
                t.category_id, t.categorized_by, t.confidence, t.reviewed = data.category_id, "manual", None, True
    if "notes" in fields:
        t.notes = data.notes
    if data.reviewed is not None:
        t.reviewed = data.reviewed
    db.commit()
    return {"transaction": _tx_out(t), "similar_updated": similar}


@router.post("/transactions/bulk-category")
def bulk_category(data: schemas.BulkCategory, db: Session = Depends(get_session)):
    if db.get(Category, data.category_id) is None:
        raise HTTPException(400, "Categoria não existe")
    txs = db.scalars(select(Transaction).where(Transaction.id.in_(data.ids))).all()
    similar = 0
    for t in txs:
        if data.learn:
            similar += learn(db, t, data.category_id)
        else:
            t.category_id, t.categorized_by, t.reviewed = data.category_id, "manual", True
    db.commit()
    return {"updated": len(txs), "similar_updated": similar}


@router.delete("/transactions/{tid}", status_code=204)
def delete_transaction(tid: int, db: Session = Depends(get_session)):
    t = db.get(Transaction, tid)
    if t is None:
        raise HTTPException(404, "Lançamento não encontrado")
    db.delete(t)
    db.commit()


@router.post("/transactions/categorize-ai")
def categorize_pending_with_ai(db: Session = Depends(get_session)):
    """Manda para a IA os lançamentos ainda sem categoria (ex.: importados antes de configurar a chave)."""
    txs = list(db.scalars(select(Transaction).where(Transaction.category_id.is_(None)).limit(600)))
    n = apply_ai(db, txs)
    db.commit()
    return {"checked": len(txs), "categorized": n}


# ---------------------------------------------------------------- importação
@router.post("/imports")
async def upload_ofx(file: UploadFile = File(...), account_id: int | None = Form(None),
                     owner_id: int | None = Form(None), db: Session = Depends(get_session)):
    content = await file.read()
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "Arquivo maior que 4 MB; exporte um período menor")
    try:
        return import_ofx(db, content, file.filename or "extrato.ofx", account_id=account_id, owner_id=owner_id)
    except (OFXError, ValueError) as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from None


@router.get("/imports")
def list_imports(db: Session = Depends(get_session)):
    names = {a.id: a.name for a in db.scalars(select(Account))}
    rows = db.scalars(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(100)).all()
    return [{"id": b.id, "account_id": b.account_id, "account": names.get(b.account_id), "filename": b.filename,
             "created_at": b.created_at.isoformat() if b.created_at else None,
             "period": [b.period_start.isoformat() if b.period_start else None,
                        b.period_end.isoformat() if b.period_end else None],
             "total": b.total, "new": b.new, "duplicates": b.duplicates, "by_rule": b.by_rule, "by_ai": b.by_ai,
             "uncategorized": b.uncategorized} for b in rows]


@router.delete("/imports/{iid}", status_code=204)
def undo_import(iid: int, db: Session = Depends(get_session)):
    """Desfaz uma importação: apaga os lançamentos que ela trouxe."""
    b = db.get(ImportBatch, iid)
    if b is None:
        raise HTTPException(404, "Importação não encontrada")
    for t in db.scalars(select(Transaction).where(Transaction.import_id == iid)):
        db.delete(t)
    db.delete(b)
    db.commit()


# ---------------------------------------------------------------- planilha de planejamento (modelo .xlsx)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/imports/modelo")
def download_template(db: Session = Depends(get_session)):
    """Modelo .xlsx com as abas Previstos, Atrasos, Dívidas e Orçamento (listas com as categorias e pessoas do app)."""
    cats = db.scalars(select(Category).order_by(Category.type, Category.sort_order, Category.name)).all()
    people = db.scalars(select(Person).order_by(Person.name)).all()
    return Response(planilha.build_template(list(cats), list(people)), media_type=XLSX,
                    headers={"Content-Disposition": 'attachment; filename="modelo-financi.xlsx"'})


@router.post("/imports/planilha")
async def upload_planilha(file: UploadFile = File(...), replace: bool = Form(True), db: Session = Depends(get_session)):
    """Importa a planilha do modelo. Com replace, o que veio de uma planilha anterior é substituído."""
    content = await file.read()
    if len(content) > MAX_UPLOAD:
        raise HTTPException(413, "Arquivo maior que 4 MB")
    try:
        res = planilha.import_workbook(db, content, replace=replace)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from None
    return asdict(res)
