from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CategoryIn(BaseModel):
    name: str
    group: str = Field(pattern="^(receita|despesa_fixa|divida|despesa_variavel|investimento)$")
    kind: str = "manual"
    tag: str | None = None
    sort_order: int = 0
    active: bool = True


class CategoryOut(CategoryIn, ORM):
    id: int


class ScenarioBase(BaseModel):
    name: str
    description: str | None = None
    is_baseline: bool = False
    start_month: date
    months: int = Field(26, ge=1, le=240)
    initial_balance: float = 0
    debt_limit_pct: float = 0.30
    fgts_initial: float = 0
    fgts_rate_yearly: float = 0.03
    fgts_aliquot: float = 0.08
    gross_salary: float = 0
    bonus_salaries: float = 0
    bonus_month: int | None = Field(None, ge=1, le=12)
    ir_amount: float = 0
    ir_month: int | None = Field(None, ge=1, le=12)
    vacation_month: int | None = Field(None, ge=1, le=12)
    thirteenth_first_year: int | None = None
    thirteenth_last_year: int | None = None
    thirteenth_month_1: int = Field(11, ge=1, le=12)
    thirteenth_month_2: int = Field(12, ge=1, le=12)
    apply_inflation: bool = False
    inflation_month: int = Field(6, ge=1, le=12)
    invest_mode: str = Field("excedente", pattern="^(excedente|saldo_mes)$")
    invest_pct: float = 0
    min_balance: float = 0
    invest_return_monthly: float = 0.01
    initial_invested: float = 0


class ScenarioOut(ScenarioBase, ORM):
    id: int


class EntryIn(BaseModel):
    category_id: int
    month: date
    amount: float | None  # None remove o valor (linha automática volta a ser calculada)


class FillIn(BaseModel):
    category_id: int
    from_month: date
    to_month: date
    amount: float | None


class SalaryChangeIn(BaseModel):
    start_month: date
    amount: float | None = None
    pct: float | None = None


class InflationIn(BaseModel):
    year: int
    fixed_pct: float = 0
    variable_pct: float = 0


class MonthSettingIn(BaseModel):
    month: date
    invest_pct: float | None = None
    min_balance: float | None = None
    invest_return: float | None = None
    gross_salary: float | None = None
    manual_redemption: float | None = None


class LoanIn(BaseModel):
    name: str
    creditor: str | None = None
    monthly_rate: float | None = None
    installment: float
    first_month: date
    last_month: date
    notes: str | None = None


class LoanOut(LoanIn, ORM):
    id: int


class PayoffIn(BaseModel):
    contract_id: int
    payoff_month: date | None  # None = não quitar neste cenário


class AccountIn(BaseModel):
    name: str
    type: str = "corrente"
    opening_balance: float = 0


class AccountOut(AccountIn, ORM):
    id: int


class TransactionIn(BaseModel):
    date: date
    description: str
    amount: float
    category_id: int | None = None
    account_id: int | None = None
    notes: str | None = None


class TransactionOut(TransactionIn, ORM):
    id: int


class ArrearIn(BaseModel):
    description: str
    creditor: str | None = None
    owner: str | None = None
    category_id: int | None = None
    due_date: date | None = None
    amount: float = Field(ge=0)
    fine_pct: float = 0
    interest_monthly: float = 0
    negotiated_amount: float | None = None
    status: str = Field("aberto", pattern="^(aberto|negociado|pago)$")
    paid_date: date | None = None
    notes: str | None = None


class ArrearOut(ArrearIn, ORM):
    id: int


class ArrearPlanIn(BaseModel):
    arrear_id: int
    start_month: date | None  # None = sem plano de pagamento neste cenário
    installments: int = Field(1, ge=1, le=120)
