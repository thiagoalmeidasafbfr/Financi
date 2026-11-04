"""Agrupamentos do usuário: conjuntos de linhas da tabela mês a mês somadas com sinal (ex.: Folha)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..db import get_session
from ..models import Grouping, GroupingMember

router = APIRouter(prefix="/api/groupings", tags=["agrupamentos"])
REF_PREFIXES = ("plan:", "cat:", "debt:", "card:", "acao:")  # acao: linha de uma ação do cockpit


def _out(g: Grouping) -> dict:
    return {"id": g.id, "name": g.name, "refs": [m.ref for m in g.members]}


def _apply(g: Grouping, data: schemas.GroupingIn) -> None:
    refs = list(dict.fromkeys(r.strip() for r in data.refs if r.strip()))
    bad = [r for r in refs if not r.startswith(REF_PREFIXES)]
    if bad:
        raise HTTPException(400, f"Linha inválida: {bad[0]}")
    g.name = data.name.strip()
    g.members = [GroupingMember(ref=r) for r in refs]


@router.get("", response_model=list[schemas.GroupingOut])
def list_groupings(db: Session = Depends(get_session)):
    return [_out(g) for g in db.scalars(select(Grouping).order_by(Grouping.sort_order, Grouping.id))]


@router.post("", response_model=schemas.GroupingOut, status_code=201)
def create_grouping(data: schemas.GroupingIn, db: Session = Depends(get_session)):
    g = Grouping()
    _apply(g, data)
    db.add(g)
    db.commit()
    return _out(g)


@router.put("/{gid}", response_model=schemas.GroupingOut)
def update_grouping(gid: int, data: schemas.GroupingIn, db: Session = Depends(get_session)):
    g = db.get(Grouping, gid)
    if g is None:
        raise HTTPException(404, "Agrupamento não encontrado")
    g.members.clear()
    db.flush()
    _apply(g, data)
    db.commit()
    return _out(g)


@router.delete("/{gid}", status_code=204)
def delete_grouping(gid: int, db: Session = Depends(get_session)):
    g = db.get(Grouping, gid)
    if g is None:
        raise HTTPException(404, "Agrupamento não encontrado")
    db.delete(g)
    db.commit()
