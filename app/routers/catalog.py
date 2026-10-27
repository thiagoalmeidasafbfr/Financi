"""Cadastros compartilhados: categorias, contratos de empréstimo e contas."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import engine as eng
from .. import schemas
from ..db import get_session
from ..models import KINDS, Account, Category, LoanContract

router = APIRouter(prefix="/api", tags=["cadastros"])


def _crud(path: str, model, schema_in, schema_out, order, prepare=lambda d: d):
    @router.get(f"/{path}", response_model=list[schema_out], name=f"list_{path}")
    def list_items(db: Session = Depends(get_session)):
        return db.scalars(select(model).order_by(*order)).all()

    @router.post(f"/{path}", response_model=schema_out, status_code=201, name=f"create_{path}")
    def create_item(data: schema_in, db: Session = Depends(get_session)):
        obj = model(**prepare(data.model_dump()))
        db.add(obj)
        _commit(db)
        return obj

    @router.put(f"/{path}/{{item_id}}", response_model=schema_out, name=f"update_{path}")
    def update_item(item_id: int, data: schema_in, db: Session = Depends(get_session)):
        obj = db.get(model, item_id)
        if obj is None:
            raise HTTPException(404, "Registro não encontrado")
        for k, v in prepare(data.model_dump()).items():
            setattr(obj, k, v)
        _commit(db)
        return obj

    @router.delete(f"/{path}/{{item_id}}", status_code=204, name=f"delete_{path}")
    def delete_item(item_id: int, db: Session = Depends(get_session)):
        obj = db.get(model, item_id)
        if obj is None:
            raise HTTPException(404, "Registro não encontrado")
        db.delete(obj)
        db.commit()


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Já existe um registro com esse nome") from None


def _check_category(d: dict) -> dict:
    if d["kind"] not in KINDS:
        raise HTTPException(400, f"Tipo inválido. Use um de: {', '.join(KINDS)}")
    return d


def _normalize_loan(d: dict) -> dict:
    d["first_month"] = eng.month_start(d["first_month"])
    d["last_month"] = eng.month_start(d["last_month"])
    return d


_crud("categories", Category, schemas.CategoryIn, schemas.CategoryOut,
      (Category.group, Category.sort_order, Category.id), _check_category)
_crud("loans", LoanContract, schemas.LoanIn, schemas.LoanOut, (LoanContract.id,), _normalize_loan)
_crud("accounts", Account, schemas.AccountIn, schemas.AccountOut, (Account.name,))
