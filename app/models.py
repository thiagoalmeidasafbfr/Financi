"""Modelo de dados da plataforma de finanças pessoais.

  Person ── Account ── Transaction ── Category
              │            └─ ImportBatch (extrato OFX de onde veio)
              └─ (cartão: dia de fechamento/vencimento, limite)
  Rule      texto do estabelecimento → categoria (aprendida com as correções)
  Budget    orçamento por categoria (padrão mensal ou de um mês específico)
  Debt      empréstimos, consignados, financiamentos... (cartões são contas)
  Planned   lançamentos previstos (mensais com início/fim ou pontuais) e PlannedChange (ajuste de um mês)
  Grouping  agrupamentos do usuário (ex.: Folha = salário − descontos), só para visualizar o líquido
  Passkey   biometria (Face ID, digital) cadastrada em cada aparelho para abrir o app
  Meta      versão do esquema já criado no banco (a subida pula a criação quando nada mudou)
"""
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
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

ACCOUNT_KINDS = ("corrente", "poupanca", "cartao", "investimento", "dinheiro")
CATEGORY_TYPES = ("despesa", "receita", "transferencia")
DEBT_KINDS = ("emprestimo", "consignado", "financiamento", "cheque_especial", "acordo", "outro")
# quem decidiu a categoria de um lançamento
CATEGORIZED_BY = ("regra", "padrao", "ia", "manual")


class Person(Base):
    __tablename__ = "fin_people"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)


class Account(Base):
    __tablename__ = "fin_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    institution: Mapped[str | None] = mapped_column(String(120), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="corrente")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("fin_people.id", ondelete="SET NULL"), nullable=True)  # vazio = conjunta
    # identificação no OFX, para reconhecer a conta na próxima importação
    bank_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    acct_id: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    opening_balance: Mapped[float] = mapped_column(Money, default=0)
    # cartão de crédito
    closing_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    due_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    credit_limit: Mapped[float | None] = mapped_column(Money, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    owner: Mapped[Person | None] = relationship()


class Category(Base):
    __tablename__ = "fin_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    group: Mapped[str] = mapped_column(String(60))  # ex.: Moradia, Alimentação
    type: Mapped[str] = mapped_column(String(20), default="despesa")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("name", "type", name="uq_category_name_type"),)


class ImportBatch(Base):
    __tablename__ = "fin_imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("fin_accounts.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    new: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    by_rule: Mapped[int] = mapped_column(Integer, default=0)
    by_ai: Mapped[int] = mapped_column(Integer, default=0)
    uncategorized: Mapped[int] = mapped_column(Integer, default=0)
    balance: Mapped[float | None] = mapped_column(Money, nullable=True)  # saldo informado pelo banco
    balance_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class Transaction(Base):
    """Lançamento. Valor com sinal: negativo = saída (gasto, compra no cartão), positivo = entrada."""

    __tablename__ = "fin_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("fin_accounts.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[float] = mapped_column(Money)
    description: Mapped[str] = mapped_column(String(255))  # como veio do banco
    merchant: Mapped[str] = mapped_column(String(120), index=True)  # chave normalizada p/ regras
    category_id: Mapped[int | None] = mapped_column(ForeignKey("fin_categories.id", ondelete="SET NULL"), nullable=True)
    categorized_by: Mapped[str | None] = mapped_column(String(10), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # da IA
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    installment_n: Mapped[int | None] = mapped_column(Integer, nullable=True)  # parcela 3 de 10
    installment_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(120))
    import_id: Mapped[int | None] = mapped_column(ForeignKey("fin_imports.id", ondelete="SET NULL"), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    account: Mapped[Account] = relationship()
    category: Mapped[Category | None] = relationship()

    __table_args__ = (UniqueConstraint("account_id", "dedupe_key", name="uq_tx_dedupe"),)


class Rule(Base):
    """Estabelecimento → categoria. `exact` compara com a chave inteira; `contains` procura o trecho."""

    __tablename__ = "fin_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    pattern: Mapped[str] = mapped_column(String(120))
    match: Mapped[str] = mapped_column(String(10), default="exact")  # exact | contains
    category_id: Mapped[int] = mapped_column(ForeignKey("fin_categories.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(12), default="aprendida")  # aprendida | manual | padrao | ia
    hits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    category: Mapped[Category] = relationship()

    __table_args__ = (UniqueConstraint("pattern", "match", name="uq_rule_pattern"),)


class Budget(Base):
    """Orçamento mensal de uma categoria. month vazio = vale para todo mês (padrão)."""

    __tablename__ = "fin_budgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("fin_categories.id", ondelete="CASCADE"))
    month: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[float] = mapped_column(Money)

    __table_args__ = (UniqueConstraint("category_id", "month", name="uq_budget"),)


class Debt(Base):
    """Dívida parcelada ou rotativa (cartões ficam em Account, com fatura calculada dos lançamentos)."""

    __tablename__ = "fin_debts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20), default="emprestimo")
    creditor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("fin_people.id", ondelete="SET NULL"), nullable=True)
    installment: Mapped[float] = mapped_column(Money, default=0)  # parcela mensal
    monthly_rate: Mapped[float | None] = mapped_column(Rate, nullable=True)  # juros a.m.
    first_due: Mapped[date | None] = mapped_column(Date, nullable=True)  # 1ª parcela
    total_installments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    balance: Mapped[float | None] = mapped_column(Money, nullable=True)  # saldo devedor informado (rotativo/acordo)
    match_pattern: Mapped[str | None] = mapped_column(String(120), nullable=True)  # reconhece o pagamento no extrato
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    owner: Mapped[Person | None] = relationship()


class Planned(Base):
    """Lançamento previsto: mensal (de um mês até outro, ou sem fim) ou pontual (um mês só).

    Gera as ocorrências do fluxo futuro e entra na projeção; ocorrência vencida e não paga fica em atraso."""

    __tablename__ = "fin_planned"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(10), default="despesa")  # despesa | receita
    category_id: Mapped[int | None] = mapped_column(ForeignKey("fin_categories.id", ondelete="SET NULL"), nullable=True)
    amount: Mapped[float] = mapped_column(Money)  # sempre positivo; o tipo diz se entra ou sai
    recurrence: Mapped[str] = mapped_column(String(10), default="mensal")  # mensal | pontual
    start_month: Mapped[date] = mapped_column(Date)
    end_month: Mapped[date | None] = mapped_column(Date, nullable=True)  # vazio = sem fim
    due_day: Mapped[int | None] = mapped_column(Integer, nullable=True)  # vazio = fim do mês
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("fin_people.id", ondelete="SET NULL"), nullable=True)
    match_pattern: Mapped[str | None] = mapped_column(String(120), nullable=True)  # reconhece o pagamento no extrato
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    changes: Mapped[list["PlannedChange"]] = relationship(back_populates="planned", cascade="all, delete-orphan")


class PlannedChange(Base):
    """Ajuste de uma ocorrência (identificada pelo mês original): outro valor, outro mês, pulada ou paga."""

    __tablename__ = "fin_planned_changes"
    __table_args__ = (UniqueConstraint("planned_id", "month", name="uq_fin_planned_change"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    planned_id: Mapped[int] = mapped_column(ForeignKey("fin_planned.id", ondelete="CASCADE"), index=True)
    month: Mapped[date] = mapped_column(Date)  # mês original da ocorrência
    amount: Mapped[float | None] = mapped_column(Money, nullable=True)
    moved_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    skipped: Mapped[bool] = mapped_column(Boolean, default=False)
    paid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # vazio = automático pelo extrato

    planned: Mapped[Planned] = relationship(back_populates="changes")


class Grouping(Base):
    """Agrupamento definido pelo usuário (ex.: "Folha"): soma com sinal de linhas da tabela mês a mês.

    É só uma visão: não muda totais nem projeção. Cada membro é a referência de uma linha da tabela
    ("plan:<nome do previsto>", "cat:<id>", "debt:<id>", "card:<id da conta>")."""

    __tablename__ = "fin_groupings"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    members: Mapped[list["GroupingMember"]] = relationship(back_populates="grouping", cascade="all, delete-orphan",
                                                           order_by="GroupingMember.id")


class GroupingMember(Base):
    __tablename__ = "fin_grouping_members"
    __table_args__ = (UniqueConstraint("grouping_id", "ref", name="uq_fin_grouping_member"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    grouping_id: Mapped[int] = mapped_column(ForeignKey("fin_groupings.id", ondelete="CASCADE"), index=True)
    ref: Mapped[str] = mapped_column(String(160))

    grouping: Mapped[Grouping] = relationship(back_populates="members")


class Passkey(Base):
    """Credencial WebAuthn (passkey) de um aparelho: a chave pública que confere o Face ID / digital."""

    __tablename__ = "fin_passkeys"

    id: Mapped[int] = mapped_column(primary_key=True)
    credential_id: Mapped[str] = mapped_column(String(512), unique=True)  # base64url, sem "="
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)


class Meta(Base):
    __tablename__ = "fin_meta"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))
