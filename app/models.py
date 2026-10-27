"""Modelo de dados.

Planejamento (tudo pertence ao cenário; duplicar copia tudo):
  Scenario ─┬─ PlanEntry      valor planejado por categoria × mês (ou override de linha automática)
            ├─ SalaryChange   reajustes do salário líquido
            ├─ InflationRate  inflação anual das despesas
            ├─ MonthSetting   parâmetros mês a mês (% a investir, saldo mínimo, rentabilidade...)
            ├─ LoanContract   consignados, com o mês de quitação antecipada
            └─ Arrear         contas em atraso, com o plano de pagamento

Compartilhado entre cenários:
  Category (nomes das linhas)

Realizado (controle do dia a dia):
  Account ─ Transaction ─ Category
"""
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

Money = Numeric(14, 2, asdecimal=False)
Rate = Numeric(12, 6, asdecimal=False)

# Grupos de categoria (seções da planilha)
GROUPS = ("receita", "despesa_fixa", "divida", "despesa_variavel", "investimento")

# Tipos de linha: "manual" = valor digitado; os demais são calculados pelo motor
# a partir das premissas do cenário e podem ser sobrescritos mês a mês.
KINDS = (
    "manual",
    "salario",
    "decimo_terceiro",
    "ferias",
    "restituicao_ir",
    "bonus",
    "consignados",
    "quitacao",
    "atrasos",
)

ARREAR_STATUS = ("aberto", "negociado", "pago")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    group: Mapped[str] = mapped_column(String(30))
    kind: Mapped[str] = mapped_column(String(30), default="manual")
    # marcador opcional usado em KPIs: "moradia", "saude"
    tag: Mapped[str | None] = mapped_column(String(30), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("name", "group", name="uq_category_name_group"),)


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)

    start_month: Mapped[date] = mapped_column(Date)
    months: Mapped[int] = mapped_column(Integer, default=26)
    initial_balance: Mapped[float] = mapped_column(Money, default=0)
    debt_limit_pct: Mapped[float] = mapped_column(Rate, default=0.30)

    # FGTS (referência, não entra no saldo em conta)
    fgts_initial: Mapped[float] = mapped_column(Money, default=0)
    fgts_rate_yearly: Mapped[float] = mapped_column(Rate, default=0.03)
    fgts_aliquot: Mapped[float] = mapped_column(Rate, default=0.08)
    gross_salary: Mapped[float] = mapped_column(Money, default=0)

    # Premissas de receitas extras
    bonus_salaries: Mapped[float] = mapped_column(Rate, default=0)
    bonus_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ir_amount: Mapped[float] = mapped_column(Money, default=0)
    ir_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vacation_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thirteenth_first_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thirteenth_last_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    thirteenth_month_1: Mapped[int] = mapped_column(Integer, default=11)
    thirteenth_month_2: Mapped[int] = mapped_column(Integer, default=12)

    # Reajuste das despesas
    apply_inflation: Mapped[bool] = mapped_column(Boolean, default=False)
    inflation_month: Mapped[int] = mapped_column(Integer, default=6)

    # Módulo de investimentos (valores padrão; podem variar mês a mês em MonthSetting)
    # "excedente": % do saldo disponível acima do saldo mínimo (aba BR)
    # "saldo_mes": % da sobra positiva do mês (abas antigas)
    invest_mode: Mapped[str] = mapped_column(String(20), default="excedente")
    invest_pct: Mapped[float] = mapped_column(Rate, default=0)
    min_balance: Mapped[float] = mapped_column(Money, default=0)
    invest_return_monthly: Mapped[float] = mapped_column(Rate, default=0.01)
    initial_invested: Mapped[float] = mapped_column(Money, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    entries: Mapped[list["PlanEntry"]] = relationship(cascade="all, delete-orphan", back_populates="scenario")
    salary_changes: Mapped[list["SalaryChange"]] = relationship(cascade="all, delete-orphan", order_by="SalaryChange.start_month")
    inflation_rates: Mapped[list["InflationRate"]] = relationship(cascade="all, delete-orphan", order_by="InflationRate.year")
    month_settings: Mapped[list["MonthSetting"]] = relationship(cascade="all, delete-orphan", order_by="MonthSetting.month")
    loans: Mapped[list["LoanContract"]] = relationship(cascade="all, delete-orphan", order_by="LoanContract.id")
    arrears: Mapped[list["Arrear"]] = relationship(cascade="all, delete-orphan", order_by="Arrear.id")


class PlanEntry(Base):
    __tablename__ = "plan_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    month: Mapped[date] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Money)

    scenario: Mapped[Scenario] = relationship(back_populates="entries")

    __table_args__ = (UniqueConstraint("scenario_id", "category_id", "month", name="uq_entry"),)


class SalaryChange(Base):
    __tablename__ = "salary_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    start_month: Mapped[date] = mapped_column(Date)
    amount: Mapped[float | None] = mapped_column(Money, nullable=True)
    pct: Mapped[float | None] = mapped_column(Rate, nullable=True)


class InflationRate(Base):
    __tablename__ = "inflation_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    fixed_pct: Mapped[float] = mapped_column(Rate, default=0)
    variable_pct: Mapped[float] = mapped_column(Rate, default=0)


class MonthSetting(Base):
    """Parâmetros mensais. Campos nulos herdam o valor do mês anterior
    (ou o padrão do cenário), exceto o resgate manual, que vale só no mês."""

    __tablename__ = "month_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    month: Mapped[date] = mapped_column(Date)
    invest_pct: Mapped[float | None] = mapped_column(Rate, nullable=True)
    min_balance: Mapped[float | None] = mapped_column(Money, nullable=True)
    invest_return: Mapped[float | None] = mapped_column(Rate, nullable=True)
    gross_salary: Mapped[float | None] = mapped_column(Money, nullable=True)
    manual_redemption: Mapped[float | None] = mapped_column(Money, nullable=True)

    __table_args__ = (UniqueConstraint("scenario_id", "month", name="uq_month_setting"),)


class LoanContract(Base):
    """Consignado/empréstimo de um cenário (cada cenário tem a sua cópia: editar ou excluir
    num cenário não afeta os outros)."""

    __tablename__ = "scenario_loans"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    creditor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    monthly_rate: Mapped[float | None] = mapped_column(Rate, nullable=True)
    installment: Mapped[float] = mapped_column(Money)
    first_month: Mapped[date] = mapped_column(Date)
    last_month: Mapped[date] = mapped_column(Date)
    payoff_month: Mapped[date | None] = mapped_column(Date, nullable=True)  # quitação antecipada
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (UniqueConstraint("scenario_id", "name", name="uq_scenario_loan_name"),)


class Arrear(Base):
    """Conta em atraso (aluguel, cartão, condomínio...) de um cenário, com o plano de pagamento."""

    __tablename__ = "scenario_arrears"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    description: Mapped[str] = mapped_column(String(160))
    creditor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    owner: Mapped[str | None] = mapped_column(String(80), nullable=True)  # responsável
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # vencimento original
    amount: Mapped[float] = mapped_column(Money)  # valor original em atraso
    fine_pct: Mapped[float] = mapped_column(Rate, default=0)  # multa (uma vez)
    interest_monthly: Mapped[float] = mapped_column(Rate, default=0)  # juros de mora simples, % a.m.
    negotiated_amount: Mapped[float | None] = mapped_column(Money, nullable=True)  # acordo fechado
    status: Mapped[str] = mapped_column(String(20), default="aberto")
    paid_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    plan_start: Mapped[date | None] = mapped_column(Date, nullable=True)  # início do pagamento
    plan_installments: Mapped[int] = mapped_column(Integer, default=1)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    type: Mapped[str] = mapped_column(String(30), default="corrente")  # corrente, investimento, cartao, dinheiro
    opening_balance: Mapped[float] = mapped_column(Money, default=0)


class Transaction(Base):
    """Lançamento realizado. Valor com sinal: positivo = entrada, negativo = saída."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(String(255))
    amount: Mapped[float] = mapped_column(Money)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
