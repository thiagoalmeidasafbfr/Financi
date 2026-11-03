"""Cadastros: pessoas, contas, categorias e regras de categorização."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import schemas
from ..categorize import apply_rules
from ..db import get_session
from ..models import Account, Category, Person, Rule, Transaction
from ..services import accounts_for, balances

router = APIRouter(prefix="/api", tags=["cadastros"])


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Já existe um registro com esses dados") from None


def _get(db: Session, model, item_id: int):
    obj = db.get(model, item_id)
    if obj is None:
        raise HTTPException(404, "Registro não encontrado")
    return obj


# ---------------------------------------------------------------- pessoas
@router.get("/people", response_model=list[schemas.PersonOut])
def list_people(db: Session = Depends(get_session)):
    return db.scalars(select(Person).order_by(Person.id)).all()


@router.post("/people", response_model=schemas.PersonOut, status_code=201)
def create_person(data: schemas.PersonIn, db: Session = Depends(get_session)):
    p = Person(name=data.name.strip())
    db.add(p)
    _commit(db)
    return p


@router.put("/people/{pid}", response_model=schemas.PersonOut)
def update_person(pid: int, data: schemas.PersonIn, db: Session = Depends(get_session)):
    p = _get(db, Person, pid)
    p.name = data.name.strip()
    _commit(db)
    return p


@router.delete("/people/{pid}", status_code=204)
def delete_person(pid: int, db: Session = Depends(get_session)):
    db.delete(_get(db, Person, pid))
    db.commit()


# ---------------------------------------------------------------- contas
@router.get("/accounts", response_model=list[schemas.AccountOut])
def list_accounts(person: str | None = None, include_inactive: bool = False, db: Session = Depends(get_session)):
    accs = accounts_for(db, person)
    if include_inactive:
        accs += list(db.scalars(select(Account).where(Account.active.is_(False))))
    bal = balances(db, accs)
    return [schemas.AccountOut.model_validate(a).model_copy(update={"balance": bal.get(a.id)}) for a in accs]


@router.post("/accounts", response_model=schemas.AccountOut, status_code=201)
def create_account(data: schemas.AccountIn, db: Session = Depends(get_session)):
    a = Account(**data.model_dump())
    db.add(a)
    _commit(db)
    return a


@router.put("/accounts/{aid}", response_model=schemas.AccountOut)
def update_account(aid: int, data: schemas.AccountIn, db: Session = Depends(get_session)):
    a = _get(db, Account, aid)
    for k, v in data.model_dump().items():
        setattr(a, k, v)
    _commit(db)
    return a


@router.delete("/accounts/{aid}", status_code=204)
def delete_account(aid: int, db: Session = Depends(get_session)):
    """Apaga a conta e todos os lançamentos dela."""
    db.delete(_get(db, Account, aid))
    db.commit()


# ---------------------------------------------------------------- categorias
@router.get("/categories", response_model=list[schemas.CategoryOut])
def list_categories(db: Session = Depends(get_session)):
    return db.scalars(select(Category).order_by(Category.type, Category.sort_order, Category.name)).all()


@router.post("/categories", response_model=schemas.CategoryOut, status_code=201)
def create_category(data: schemas.CategoryIn, db: Session = Depends(get_session)):
    c = Category(**data.model_dump())
    db.add(c)
    _commit(db)
    return c


@router.put("/categories/{cid}", response_model=schemas.CategoryOut)
def update_category(cid: int, data: schemas.CategoryIn, db: Session = Depends(get_session)):
    c = _get(db, Category, cid)
    for k, v in data.model_dump().items():
        setattr(c, k, v)
    _commit(db)
    return c


@router.delete("/categories/{cid}", status_code=204)
def delete_category(cid: int, db: Session = Depends(get_session)):
    """Os lançamentos da categoria ficam sem categoria; as regras dela são apagadas."""
    db.delete(_get(db, Category, cid))
    db.commit()


# ---------------------------------------------------------------- regras
@router.get("/rules", response_model=list[schemas.RuleOut])
def list_rules(source: str | None = None, db: Session = Depends(get_session)):
    q = select(Rule).order_by(Rule.source, Rule.pattern)
    if source:
        q = q.where(Rule.source == source)
    return db.scalars(q).all()


@router.post("/rules", response_model=schemas.RuleOut, status_code=201)
def create_rule(data: schemas.RuleIn, db: Session = Depends(get_session)):
    _get(db, Category, data.category_id)
    r = Rule(pattern=data.pattern.upper().strip() + (" " if data.pattern.endswith(" ") else ""),
             match=data.match, category_id=data.category_id, source="manual")
    db.add(r)
    _commit(db)
    return r


@router.put("/rules/{rid}", response_model=schemas.RuleOut)
def update_rule(rid: int, data: schemas.RuleIn, db: Session = Depends(get_session)):
    r = _get(db, Rule, rid)
    r.pattern, r.match, r.category_id, r.source = data.pattern.upper(), data.match, data.category_id, "manual"
    _commit(db)
    return r


@router.delete("/rules/{rid}", status_code=204)
def delete_rule(rid: int, db: Session = Depends(get_session)):
    db.delete(_get(db, Rule, rid))
    db.commit()


@router.post("/rules/apply")
def reapply_rules(db: Session = Depends(get_session)):
    """Reaplica as regras aos lançamentos ainda sem categoria."""
    txs = list(db.scalars(select(Transaction).where(Transaction.category_id.is_(None))))
    n = apply_rules(db, txs)
    db.commit()
    return {"checked": len(txs), "categorized": n}
