"""Ponte entre o banco de dados e o motor de projeção."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import engine as eng
from .models import (
    Arrear,
    Category,
    InflationRate,
    LoanContract,
    MonthSetting,
    PlanEntry,
    SalaryChange,
    Scenario,
)

# Categorias padrão (mesmas linhas da planilha). (nome, grupo, tipo, tag)
DEFAULT_CATEGORIES = [
    ("Salário líquido", "receita", "salario", None),
    ("13º salário", "receita", "decimo_terceiro", None),
    ("Férias (1/3 constitucional)", "receita", "ferias", None),
    ("Restituição IR / renda extra", "receita", "restituicao_ir", None),
    ("Bônus / outras receitas", "receita", "bonus", None),
    ("Receita livre", "receita", "manual", None),
    ("Aluguel / financiamento imobiliário", "despesa_fixa", "manual", "moradia"),
    ("Condomínio", "despesa_fixa", "manual", "moradia"),
    ("IPTU", "despesa_fixa", "manual", "moradia"),
    ("Energia elétrica", "despesa_fixa", "manual", "moradia"),
    ("Água", "despesa_fixa", "manual", "moradia"),
    ("Gás", "despesa_fixa", "manual", "moradia"),
    ("Internet / TV", "despesa_fixa", "manual", "moradia"),
    ("Celular", "despesa_fixa", "manual", None),
    ("Plano de saúde", "despesa_fixa", "manual", "saude"),
    ("Plano odontológico", "despesa_fixa", "manual", "saude"),
    ("Seguros (auto / vida / residencial)", "despesa_fixa", "manual", None),
    ("Assinaturas (streaming, apps)", "despesa_fixa", "manual", None),
    ("Academia", "despesa_fixa", "manual", None),
    ("Consignados em folha", "divida", "consignados", None),
    ("Quitação antecipada de consignados", "divida", "quitacao", None),
    ("Pagamento de atrasos", "divida", "atrasos", None),
    ("Supermercado", "despesa_variavel", "manual", None),
    ("Feira / padaria", "despesa_variavel", "manual", None),
    ("Combustível", "despesa_variavel", "manual", None),
    ("Transporte (app, ônibus, estacionamento)", "despesa_variavel", "manual", None),
    ("Farmácia / coparticipação saúde", "despesa_variavel", "manual", "saude"),
    ("Restaurantes / delivery", "despesa_variavel", "manual", None),
    ("Lazer", "despesa_variavel", "manual", None),
    ("Vestuário", "despesa_variavel", "manual", None),
    ("Cuidados pessoais", "despesa_variavel", "manual", None),
    ("Presentes", "despesa_variavel", "manual", None),
    ("Manutenção (casa / carro)", "despesa_variavel", "manual", None),
    ("Pets", "despesa_variavel", "manual", None),
    ("Outros", "despesa_variavel", "manual", None),
    ("Reserva de emergência", "investimento", "manual", None),
    ("Previdência privada", "investimento", "manual", None),
    ("Investimentos", "investimento", "manual", None),
]


def seed_categories(db: Session) -> None:
    if db.scalar(select(Category.id).limit(1)) is None:
        for i, (name, group, kind, tag) in enumerate(DEFAULT_CATEGORIES):
            db.add(Category(name=name, group=group, kind=kind, tag=tag, sort_order=i * 10))
        db.commit()
        return
    # bancos criados por versões anteriores: garante as linhas calculadas que surgiram depois
    kinds = set(db.scalars(select(Category.kind)))
    for i, (name, group, kind, tag) in enumerate(DEFAULT_CATEGORIES):
        if kind != "manual" and kind not in kinds:
            db.add(Category(name=name, group=group, kind=kind, tag=tag, sort_order=i * 10))
    db.commit()


SCENARIO_PARAMS = [
    "start_month", "months", "initial_balance", "debt_limit_pct", "fgts_initial", "fgts_rate_yearly",
    "fgts_aliquot", "gross_salary", "bonus_salaries", "bonus_month", "ir_amount", "ir_month", "vacation_month",
    "thirteenth_first_year", "thirteenth_last_year", "thirteenth_month_1", "thirteenth_month_2",
    "apply_inflation", "inflation_month", "invest_mode", "invest_pct", "min_balance", "invest_return_monthly", "initial_invested",
]


def loans_for(db: Session, scenario_id: int) -> list[eng.LoanIn]:
    return [
        eng.LoanIn(id=c.id, name=c.name, installment=c.installment, first_month=c.first_month,
                   last_month=c.last_month, monthly_rate=c.monthly_rate, payoff_month=c.payoff_month)
        for c in db.scalars(select(LoanContract).where(LoanContract.scenario_id == scenario_id)
                            .order_by(LoanContract.id))
    ]


def arrears_for(db: Session, scenario_id: int) -> list[eng.ArrearIn]:
    return [
        eng.ArrearIn(id=a.id, description=a.description, amount=a.amount, due_month=a.due_date,
                     fine_pct=a.fine_pct or 0.0, interest_monthly=a.interest_monthly or 0.0,
                     negotiated_amount=a.negotiated_amount, status=a.status, creditor=a.creditor,
                     plan_start=a.plan_start, plan_installments=a.plan_installments or 1)
        for a in db.scalars(select(Arrear).where(Arrear.scenario_id == scenario_id).order_by(Arrear.id))
    ]


def scenario_input(db: Session, sc: Scenario) -> eng.ScenarioIn:
    cats = db.scalars(select(Category)).all()
    # categorias inativas só aparecem se ainda tiverem valores neste cenário
    used = {e.category_id for e in sc.entries}
    return eng.ScenarioIn(
        **{k: getattr(sc, k) for k in SCENARIO_PARAMS},
        categories=[eng.CategoryIn(id=c.id, name=c.name, group=c.group, kind=c.kind, tag=c.tag,
                                   sort_order=c.sort_order) for c in cats if c.active or c.id in used],
        entries={(e.category_id, e.month): e.amount for e in sc.entries},
        salary_changes=[eng.SalaryChangeIn(s.start_month, s.amount, s.pct) for s in sc.salary_changes],
        inflation=[eng.InflationIn(r.year, r.fixed_pct, r.variable_pct) for r in sc.inflation_rates],
        month_settings=[eng.MonthSettingIn(m.month, m.invest_pct, m.min_balance, m.invest_return,
                                           m.gross_salary, m.manual_redemption) for m in sc.month_settings],
        loans=loans_for(db, sc.id),
        arrears=arrears_for(db, sc.id),
    )


def project_scenario(db: Session, sc: Scenario, start=None, end=None) -> dict:
    """Projeção do cenário; com start/end, recortada nesse período (KPIs e totais do período)."""
    inp = scenario_input(db, sc)
    result = eng.project(inp)
    result["horizon"] = {"start": result["months"][0], "end": result["months"][-1]} if result["months"] else None
    if start or end:
        result = eng.slice_projection(result, inp, start, end)
    result["scenario"] = {"id": sc.id, "name": sc.name}
    return result


def _copy(obj):
    """Cópia de uma linha filha do cenário (sem id e sem o vínculo com o cenário de origem)."""
    cols = {c.key: getattr(obj, c.key) for c in obj.__table__.columns if c.key not in ("id", "scenario_id")}
    return type(obj)(**cols)


def duplicate_scenario(db: Session, sc: Scenario, new_name: str) -> Scenario:
    """Cópia completa e independente: valores, premissas, parâmetros mensais, consignados e atrasos."""
    clone = Scenario(name=new_name, description=sc.description,
                     **{k: getattr(sc, k) for k in SCENARIO_PARAMS})
    clone.entries = [PlanEntry(category_id=e.category_id, month=e.month, amount=e.amount) for e in sc.entries]
    clone.salary_changes = [SalaryChange(start_month=s.start_month, amount=s.amount, pct=s.pct)
                            for s in sc.salary_changes]
    clone.inflation_rates = [InflationRate(year=r.year, fixed_pct=r.fixed_pct, variable_pct=r.variable_pct)
                             for r in sc.inflation_rates]
    clone.month_settings = [MonthSetting(month=m.month, invest_pct=m.invest_pct, min_balance=m.min_balance,
                                         invest_return=m.invest_return, gross_salary=m.gross_salary,
                                         manual_redemption=m.manual_redemption) for m in sc.month_settings]
    clone.loans = [_copy(x) for x in sc.loans]
    clone.arrears = [_copy(x) for x in sc.arrears]
    db.add(clone)
    db.commit()
    return clone
