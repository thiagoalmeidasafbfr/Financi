from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class PersonOut(PersonIn, ORM):
    id: int


class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    institution: str | None = None
    kind: str = Field("corrente", pattern="^(corrente|poupanca|cartao|investimento|dinheiro)$")
    owner_id: int | None = None
    opening_balance: float = 0
    closing_day: int | None = Field(None, ge=1, le=31)
    due_day: int | None = Field(None, ge=1, le=31)
    credit_limit: float | None = None
    active: bool = True


class AccountOut(AccountIn, ORM):
    id: int
    acct_id: str | None = None
    balance: float | None = None


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    group: str = Field(min_length=1, max_length=60)
    type: str = Field("despesa", pattern="^(despesa|receita|transferencia)$")
    sort_order: int = 0
    active: bool = True


class CategoryOut(CategoryIn, ORM):
    id: int


class RuleIn(BaseModel):
    pattern: str = Field(min_length=2, max_length=120)
    match: str = Field("contains", pattern="^(exact|contains)$")
    category_id: int


class RuleOut(ORM):
    id: int
    pattern: str
    match: str
    category_id: int
    source: str
    hits: int


class TransactionIn(BaseModel):
    account_id: int
    date: date
    amount: float
    description: str = Field(min_length=1, max_length=255)
    category_id: int | None = None
    notes: str | None = None


class TransactionPatch(BaseModel):
    category_id: int | None = None
    notes: str | None = None
    reviewed: bool | None = None
    learn: bool = True  # corrigir a categoria cria regra e corrige os parecidos


class BulkCategory(BaseModel):
    ids: list[int]
    category_id: int
    learn: bool = True


class BudgetIn(BaseModel):
    category_id: int
    month: date | None = None  # vazio = padrão para todo mês
    amount: float | None = Field(None, ge=0)  # None remove


class DebtIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field("emprestimo", pattern="^(emprestimo|consignado|financiamento|cheque_especial|acordo|outro)$")
    creditor: str | None = None
    owner_id: int | None = None
    installment: float = Field(0, ge=0)
    monthly_rate: float | None = Field(None, ge=0, le=1)
    first_due: date | None = None
    total_installments: int | None = Field(None, ge=1, le=600)
    balance: float | None = None
    match_pattern: str | None = None
    notes: str | None = None
    active: bool = True


class DebtOut(DebtIn, ORM):
    id: int
