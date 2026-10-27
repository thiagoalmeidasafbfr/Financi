"""Motor de projeção do fluxo de caixa.

Reproduz a lógica da aba "Fluxo Mensal - BR" da planilha original:

  receitas − (despesas fixas + dívidas + despesas variáveis) = saldo operacional
  saldo disponível = saldo anterior em conta + saldo operacional
  investimento automático = max(0, disponível − aportes manuais − saldo mínimo) × % a investir
  resgate automático cobre o que faltar para manter o saldo mínimo em conta
  saldo em conta = disponível − investimentos + resgates

É um módulo puro (sem banco de dados) para ser testável isoladamente.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

GROUP_LABELS = {
    "receita": "Receitas",
    "despesa_fixa": "Despesas fixas",
    "divida": "Empréstimos e dívidas",
    "despesa_variavel": "Despesas variáveis",
    "investimento": "Investimentos e reserva",
}


# --------------------------------------------------------------------------- datas

def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def add_months(d: date, n: int) -> date:
    idx = d.year * 12 + (d.month - 1) + n
    return date(idx // 12, idx % 12 + 1, 1)


def months_between(a: date, b: date) -> int:
    """Número de meses de a até b (b − a)."""
    return (b.year - a.year) * 12 + (b.month - a.month)


# --------------------------------------------------------------------------- entradas

@dataclass
class CategoryIn:
    id: int
    name: str
    group: str
    kind: str = "manual"
    tag: str | None = None
    sort_order: int = 0


@dataclass
class SalaryChangeIn:
    start_month: date
    amount: float | None = None
    pct: float | None = None


@dataclass
class InflationIn:
    year: int
    fixed_pct: float = 0.0
    variable_pct: float = 0.0


@dataclass
class MonthSettingIn:
    month: date
    invest_pct: float | None = None
    min_balance: float | None = None
    invest_return: float | None = None
    gross_salary: float | None = None
    manual_redemption: float | None = None


@dataclass
class LoanIn:
    id: int
    name: str
    installment: float
    first_month: date
    last_month: date
    monthly_rate: float | None = None
    payoff_month: date | None = None


@dataclass
class ArrearIn:
    id: int
    description: str
    amount: float
    due_month: date | None = None
    fine_pct: float = 0.0
    interest_monthly: float = 0.0
    negotiated_amount: float | None = None
    status: str = "aberto"
    creditor: str | None = None
    plan_start: date | None = None
    plan_installments: int = 1


@dataclass
class ScenarioIn:
    start_month: date
    months: int = 26
    initial_balance: float = 0.0
    debt_limit_pct: float = 0.30
    fgts_initial: float = 0.0
    fgts_rate_yearly: float = 0.03
    fgts_aliquot: float = 0.08
    gross_salary: float = 0.0
    bonus_salaries: float = 0.0
    bonus_month: int | None = None
    ir_amount: float = 0.0
    ir_month: int | None = None
    vacation_month: int | None = None
    thirteenth_first_year: int | None = None
    thirteenth_last_year: int | None = None
    thirteenth_month_1: int = 11
    thirteenth_month_2: int = 12
    apply_inflation: bool = False
    inflation_month: int = 6
    invest_mode: str = "excedente"
    invest_pct: float = 0.0
    min_balance: float = 0.0
    invest_return_monthly: float = 0.01
    initial_invested: float = 0.0
    categories: list[CategoryIn] = field(default_factory=list)
    # {(category_id, month): valor}
    entries: dict[tuple[int, date], float] = field(default_factory=dict)
    salary_changes: list[SalaryChangeIn] = field(default_factory=list)
    inflation: list[InflationIn] = field(default_factory=list)
    month_settings: list[MonthSettingIn] = field(default_factory=list)
    loans: list[LoanIn] = field(default_factory=list)
    arrears: list[ArrearIn] = field(default_factory=list)


# --------------------------------------------------------------------------- empréstimos

def loan_installment(loan: LoanIn, m: date) -> float:
    """Parcela descontada no mês m (zero após a quitação)."""
    if loan.first_month <= m <= loan.last_month and (loan.payoff_month is None or m < loan.payoff_month):
        return loan.installment
    return 0.0


def loan_payoff_analysis(loan: LoanIn) -> dict:
    """Valor presente das parcelas restantes na data da quitação (aba Quitações)."""
    if loan.payoff_month is None:
        return {"remaining": 0, "payoff_value": 0.0, "interest_saved": 0.0, "months_equivalent": None}
    ref = max(loan.payoff_month, loan.first_month)
    n = max(0, months_between(ref, loan.last_month) + 1)
    r = loan.monthly_rate or 0.0
    if n == 0:
        value = 0.0
    elif r > 0:
        value = loan.installment * (1 - (1 + r) ** -n) / r
    else:
        value = loan.installment * n
    return {
        "remaining": n,
        "payoff_value": value,
        "interest_saved": loan.installment * n - value,
        "months_equivalent": (value / loan.installment) if n and loan.installment else None,
    }


def best_payoffs(loans: list[LoanIn], month: date, budget: float, min_remaining: int = 0) -> dict:
    """Combinação de quitações no mês que libera a MAIOR parcela mensal cabendo no valor disponível.

    Testa todas as combinações (até 20 contratos); empate fica com a mais barata. Contratos que
    terminam em até `min_remaining` parcelas ficam de fora (liberam parcela por pouco tempo)."""
    month = month_start(month)
    candidates, skipped = [], []
    for loan in loans:
        if month > month_start(loan.last_month):
            continue  # já terminou
        if loan.payoff_month is not None and month_start(loan.payoff_month) < month:
            continue  # já quitado antes deste mês
        a = loan_payoff_analysis(LoanIn(**{**loan.__dict__, "payoff_month": month}))
        c = {"id": loan.id, "name": loan.name, "installment": loan.installment, "monthly_rate": loan.monthly_rate,
             "remaining": a["remaining"], "value": a["payoff_value"], "interest_saved": a["interest_saved"],
             "per_thousand": loan.installment / a["payoff_value"] * 1000 if a["payoff_value"] else 0.0,
             "scheduled_month": loan.payoff_month.isoformat() if loan.payoff_month else None}
        (skipped if a["remaining"] <= min_remaining else candidates).append(c)

    best: tuple = (0.0, 0.0, ())  # (parcela liberada, -custo, ids)
    if len(candidates) <= 20:
        for mask in range(1, 1 << len(candidates)):
            chosen = [c for i, c in enumerate(candidates) if mask >> i & 1]
            cost = sum(c["value"] for c in chosen)
            if cost > budget + 0.005:
                continue
            key = (round(sum(c["installment"] for c in chosen), 2), -cost, tuple(c["id"] for c in chosen))
            if key[:2] > best[:2]:
                best = key
    else:  # muitos contratos: guloso pela parcela liberada por real
        cost, ids = 0.0, []
        for c in sorted(candidates, key=lambda c: -c["per_thousand"]):
            if cost + c["value"] <= budget + 0.005:
                cost += c["value"]
                ids.append(c["id"])
        best = (sum(c["installment"] for c in candidates if c["id"] in ids), -cost, tuple(ids))

    selected = [c for c in candidates if c["id"] in best[2]]
    total_cost = sum(c["value"] for c in selected)
    freed = sum(c["installment"] for c in selected)
    for c in candidates + skipped:
        c["selected"] = c["id"] in best[2]
    return {
        "month": month.isoformat(), "budget": budget, "min_remaining": min_remaining,
        "selected": selected,
        "totals": {"parcela_liberada": freed, "valor_quitacao": total_cost, "sobra": budget - total_cost,
                   "por_mil": freed / total_cost * 1000 if total_cost else 0.0,
                   "juros_evitados": sum(c["interest_saved"] for c in selected)},
        "candidates": sorted(candidates, key=lambda c: -c["per_thousand"]),
        "skipped": skipped,
    }


def payoff_planner(projection: dict, loans: list[LoanIn]) -> dict:
    """Mês a mês da conta + valor para quitar cada contrato em cada mês do horizonte.

    `fits` indica se a quitação cabe no saldo total (conta + investimentos) do mês;
    a quitação já agendada naquele mês é devolvida ao saldo para não se autoexcluir."""
    s = projection["series"]
    months = [date.fromisoformat(m) for m in projection["months"]]
    quit_row = next((r["values"] for r in projection["rows"] if r["kind"] == "quitacao"), [0.0] * len(months))
    contracts = []
    for loan in loans:
        cells = []
        for i, m in enumerate(months):
            if m > month_start(loan.last_month):
                cells.append(None)
                continue
            a = loan_payoff_analysis(LoanIn(**{**loan.__dict__, "payoff_month": m}))
            scheduled = loan.payoff_month is not None and month_start(loan.payoff_month) == m
            room = s["saldo_total"][i] + (a["payoff_value"] if scheduled else 0.0)
            cells.append({"value": a["payoff_value"], "remaining": a["remaining"],
                          "interest_saved": a["interest_saved"], "scheduled": scheduled,
                          "fits": a["payoff_value"] <= room + 0.005})
        # custo-benefício no mês de referência: o agendado ou, sem agendamento, o primeiro mês possível
        ref_i = next((i for i, c in enumerate(cells) if c and c["scheduled"]), None)
        if ref_i is None:
            ref_i = next((i for i, c in enumerate(cells) if c and c["value"] > 0), None)
        ref = None
        if ref_i is not None:
            c = cells[ref_i]
            ref = {"month": projection["months"][ref_i], "value": c["value"],
                   # R$ de parcela liberada por mês para cada R$ investido na quitação
                   "monthly_return": loan.installment / c["value"],
                   # economia total (parcelas evitadas − quitação) ÷ valor investido
                   "total_gain": c["interest_saved"] / c["value"]}
        contracts.append({"id": loan.id, "name": loan.name, "installment": loan.installment,
                          "monthly_rate": loan.monthly_rate, "last_month": loan.last_month.isoformat(),
                          "payoff_month": loan.payoff_month.isoformat() if loan.payoff_month else None,
                          "ref": ref, "cells": cells})
    consig = next((r["values"] for r in projection["rows"] if r["kind"] == "consignados"), [0.0] * len(months))
    return {
        "months": projection["months"],
        "account": {
            "receitas": s["receitas"],
            "despesas_sem_quitacoes": [d - q for d, q in zip(s["total_despesas"], quit_row)],
            "parcelas_consignados": consig,
            "quitacoes": quit_row,
            "investimentos": s["investimentos"],
            "resgates": [a + b for a, b in zip(s["inv_resgate_manual"], s["inv_resgate_automatico"])],
            "saldo_conta": s["saldo_conta"],
            "saldo_investido": s["inv_saldo_fim"],
            "saldo_total": s["saldo_total"],
        },
        "contracts": contracts,
    }


# --------------------------------------------------------------------------- atrasos

def arrear_months_late(a: ArrearIn, at: date) -> int:
    if a.due_month is None:
        return 0
    return max(0, months_between(month_start(a.due_month), month_start(at)))


def arrear_value(a: ArrearIn, at: date) -> float:
    """Valor a pagar em `at`: acordo negociado, ou original + multa + juros simples de mora."""
    if a.status == "pago":
        return 0.0
    if a.negotiated_amount is not None:
        return a.negotiated_amount
    return a.amount * (1 + a.fine_pct) + a.amount * a.interest_monthly * arrear_months_late(a, at)


def arrear_schedule(a: ArrearIn) -> dict[date, float]:
    """Parcelas do plano de pagamento: valor na data de início dividido em parcelas iguais."""
    if a.plan_start is None or a.status == "pago":
        return {}
    n = max(1, a.plan_installments)
    start = month_start(a.plan_start)
    each = arrear_value(a, start) / n
    return {add_months(start, i): each for i in range(n)}


def arrears_summary(arrears: list[ArrearIn], today: date) -> dict:
    items, open_items = [], [a for a in arrears if a.status != "pago"]
    for a in arrears:
        sched = arrear_schedule(a)
        items.append({
            "id": a.id, "months_late": arrear_months_late(a, today), "updated_value": arrear_value(a, today),
            "charges": arrear_value(a, today) - a.amount if a.status != "pago" and a.negotiated_amount is None else 0.0,
            "plan_total": sum(sched.values()), "plan_installment": next(iter(sched.values()), 0.0),
            "plan_end": max(sched).isoformat() if sched else None,
        })
    late = [arrear_months_late(a, today) for a in open_items if a.due_month]
    return {
        "items": items,
        "totals": {
            "em_aberto": len(open_items),
            "valor_original": sum(a.amount for a in open_items),
            "valor_atualizado": sum(arrear_value(a, today) for a in open_items),
            "planejado": sum(i["plan_total"] for i in items),
            "sem_plano": sum(arrear_value(a, today) for a in open_items if a.plan_start is None),
            "mais_antigo_meses": max(late) if late else 0,
        },
    }


# --------------------------------------------------------------------------- projeção

def salary_schedule(changes: list[SalaryChangeIn]) -> list[tuple[date, float]]:
    """Resolve reajustes em (mês inicial, salário resultante)."""
    out: list[tuple[date, float]] = []
    prev = 0.0
    for ch in sorted(changes, key=lambda c: c.start_month):
        if ch.amount is not None:
            value = ch.amount
        elif ch.pct is not None:
            value = prev * (1 + ch.pct)
        else:
            continue
        out.append((month_start(ch.start_month), value))
        prev = value
    return out


def _salary_at(schedule: list[tuple[date, float]], m: date) -> float:
    value = 0.0
    for start, v in schedule:
        if start <= m:
            value = v
        else:
            break
    return value


def project(sc: ScenarioIn) -> dict:
    start = month_start(sc.start_month)
    months = [add_months(start, i) for i in range(sc.months)]
    n = len(months)
    cats = sorted(sc.categories, key=lambda c: (list(GROUP_LABELS).index(c.group), c.sort_order, c.id))

    sched = salary_schedule(sc.salary_changes)
    infl = {r.year: r for r in sc.inflation}
    settings = {month_start(s.month): s for s in sc.month_settings}
    entry = sc.entries.get

    # fatores de inflação acumulados (aplicados no mês de reajuste)
    f_fix, f_var = [], []
    cf = cv = 1.0
    for m in months:
        if m.month == sc.inflation_month and m.year in infl:
            cf *= 1 + infl[m.year].fixed_pct
            cv *= 1 + infl[m.year].variable_pct
        f_fix.append(cf)
        f_var.append(cv)

    # salário efetivo (override da linha "salario" tem prioridade)
    salary_cats = [c for c in cats if c.kind == "salario"]
    salary = []
    for m in months:
        v = _salary_at(sched, m)
        for c in salary_cats:
            ov = entry((c.id, m))
            if ov is not None:
                v = ov
        salary.append(v)

    # parcelas e quitações
    loan_rows = []
    installments = [0.0] * n
    payoffs = [0.0] * n
    for loan in sc.loans:
        values = [loan_installment(loan, m) for m in months]
        analysis = loan_payoff_analysis(loan)
        pay = [0.0] * n
        if loan.payoff_month is not None and month_start(loan.payoff_month) in months:
            pay[months.index(month_start(loan.payoff_month))] = analysis["payoff_value"]
        for i in range(n):
            installments[i] += values[i]
            payoffs[i] += pay[i]
        loan_rows.append({"id": loan.id, "name": loan.name, "installments": values, "payoff": pay, **analysis,
                          "payoff_month": loan.payoff_month.isoformat() if loan.payoff_month else None})

    # pagamentos de contas em atraso (planos do cenário)
    arrear_payments = [0.0] * n
    for a in sc.arrears:
        for m, v in arrear_schedule(a).items():
            if m in months:
                arrear_payments[months.index(m)] += v

    def auto_value(c: CategoryIn, i: int, m: date) -> float:
        s = salary[i]
        if c.kind == "salario":
            return s
        if c.kind == "decimo_terceiro":
            y1, y2 = sc.thirteenth_first_year, sc.thirteenth_last_year
            if y1 and y2 and y1 <= m.year <= y2 and m.month in (sc.thirteenth_month_1, sc.thirteenth_month_2):
                return s / 2
            return 0.0
        if c.kind == "ferias":
            return s / 3 if m.month == sc.vacation_month else 0.0
        if c.kind == "restituicao_ir":
            return sc.ir_amount if m.month == sc.ir_month else 0.0
        if c.kind == "bonus":
            return sc.bonus_salaries * s if m.month == sc.bonus_month else 0.0
        if c.kind == "consignados":
            return installments[i]
        if c.kind == "quitacao":
            return payoffs[i]
        if c.kind == "atrasos":
            return arrear_payments[i]
        return 0.0

    rows = []
    for c in cats:
        values, overridden = [], []
        for i, m in enumerate(months):
            ov = entry((c.id, m))
            if c.kind == "manual":
                v = ov or 0.0
                if sc.apply_inflation and c.group == "despesa_fixa":
                    v *= f_fix[i]
                elif sc.apply_inflation and c.group == "despesa_variavel":
                    v *= f_var[i]
                overridden.append(False)
            else:
                v = ov if ov is not None else auto_value(c, i, m)
                overridden.append(ov is not None)
            values.append(v)
        rows.append({
            "category_id": c.id, "name": c.name, "group": c.group, "kind": c.kind, "tag": c.tag,
            "values": values, "overridden": overridden, "total": sum(values),
            "average": sum(values) / n if n else 0.0,
        })

    def group_sum(group: str) -> list[float]:
        return [sum(r["values"][i] for r in rows if r["group"] == group) for i in range(n)]

    receitas = group_sum("receita")
    fixas = group_sum("despesa_fixa")
    dividas = group_sum("divida")
    variaveis = group_sum("despesa_variavel")
    inv_manual = group_sum("investimento")

    keys = ["receitas", "despesas_fixas", "dividas", "despesas_variaveis", "total_despesas", "saldo_operacional",
            "saldo_disponivel", "investimentos", "saldo_livre", "saldo_conta", "saldo_total",
            "inv_base", "inv_automatico", "inv_aporte", "inv_rentabilidade", "inv_saldo_inicio", "inv_rendimento",
            "inv_resgate_manual", "inv_resgate_automatico", "inv_saldo_fim", "inv_rendimento_acumulado",
            "pct_investir", "saldo_minimo",
            "fgts_salario_bruto", "fgts_deposito", "fgts_rendimento", "fgts_saldo",
            "pct_fixas", "pct_dividas", "pct_variaveis", "pct_investimento", "alerta_dividas"]
    s = {k: [] for k in keys}

    balance = sc.initial_balance
    invested = sc.initial_invested
    fgts = sc.fgts_initial
    acc_income = 0.0
    pct, min_bal, ret, gross = sc.invest_pct, sc.min_balance, sc.invest_return_monthly, sc.gross_salary
    fgts_monthly = (1 + sc.fgts_rate_yearly) ** (1 / 12) - 1

    for i, m in enumerate(months):
        st = settings.get(m)
        red_manual = 0.0
        if st:
            pct = st.invest_pct if st.invest_pct is not None else pct
            min_bal = st.min_balance if st.min_balance is not None else min_bal
            ret = st.invest_return if st.invest_return is not None else ret
            gross = st.gross_salary if st.gross_salary is not None else gross
            red_manual = st.manual_redemption or 0.0

        total_exp = fixas[i] + dividas[i] + variaveis[i]
        op = receitas[i] - total_exp
        avail = balance + op
        if sc.invest_mode == "saldo_mes":
            base = max(0.0, min(op - inv_manual[i], avail - inv_manual[i]))
        else:
            base = max(0.0, avail - inv_manual[i] - min_bal)
        auto = base * pct
        total_inv = inv_manual[i] + auto

        inv_start = invested
        income = inv_start * ret
        red_auto = max(0.0, min(inv_start + total_inv + income - red_manual,
                                max(0.0, min_bal - (avail - total_inv + red_manual))))
        invested = inv_start + total_inv + income - red_manual - red_auto
        acc_income += income

        free = op - total_inv + red_manual + red_auto
        balance = avail - total_inv + red_manual + red_auto

        deposit = gross * sc.fgts_aliquot
        f_income = fgts * fgts_monthly
        fgts = fgts + deposit + f_income

        rec = receitas[i]
        pct_div = dividas[i] / rec if rec else 0.0
        for k, v in (
            ("receitas", rec), ("despesas_fixas", fixas[i]), ("dividas", dividas[i]),
            ("despesas_variaveis", variaveis[i]), ("total_despesas", total_exp), ("saldo_operacional", op),
            ("saldo_disponivel", avail), ("investimentos", total_inv), ("saldo_livre", free),
            ("saldo_conta", balance), ("saldo_total", balance + invested),
            ("inv_base", base), ("inv_automatico", auto), ("inv_aporte", total_inv), ("inv_rentabilidade", ret),
            ("inv_saldo_inicio", inv_start), ("inv_rendimento", income), ("inv_resgate_manual", red_manual),
            ("inv_resgate_automatico", red_auto), ("inv_saldo_fim", invested),
            ("inv_rendimento_acumulado", acc_income), ("pct_investir", pct), ("saldo_minimo", min_bal),
            ("fgts_salario_bruto", gross), ("fgts_deposito", deposit), ("fgts_rendimento", f_income),
            ("fgts_saldo", fgts),
            ("pct_fixas", fixas[i] / rec if rec else 0.0), ("pct_dividas", pct_div),
            ("pct_variaveis", variaveis[i] / rec if rec else 0.0),
            ("pct_investimento", total_inv / rec if rec else 0.0),
            ("alerta_dividas", pct_div > sc.debt_limit_pct),
        ):
            s[k].append(v)

    return {
        "months": [m.isoformat() for m in months],
        "rows": rows,
        "series": s,
        "loans": loan_rows,
        "kpis": compute_kpis(months, rows, s, sc),
        "waterfall": waterfall(s, sc.initial_balance + sc.initial_invested),
        "period": {"start": months[0].isoformat() if months else None,
                   "end": months[-1].isoformat() if months else None},
    }


def waterfall(s: dict, start_total: float) -> dict:
    """Ponte do saldo total (conta + investimentos) no período. Investir e resgatar só movem dinheiro
    entre conta e investimentos, então: final = inicial + receitas − despesas + rendimentos."""
    steps = [
        ("receitas", "Receitas", sum(s["receitas"])),
        ("despesas_fixas", "Despesas fixas", -sum(s["despesas_fixas"])),
        ("dividas", "Empréstimos e dívidas", -sum(s["dividas"])),
        ("despesas_variaveis", "Despesas variáveis", -sum(s["despesas_variaveis"])),
        ("rendimento", "Rendimentos", sum(s["inv_rendimento"])),
    ]
    end = s["saldo_total"][-1] if s["saldo_total"] else start_total
    return {"start": start_total, "end": end,
            "steps": [{"key": k, "label": label, "value": v} for k, label, v in steps]}


def slice_projection(proj: dict, sc: ScenarioIn, start: date | None, end: date | None) -> dict:
    """Recorta a projeção no período [start, end] e recalcula totais, KPIs e a ponte de saldos.
    Os saldos iniciais do período são os saldos do fim do mês anterior."""
    months = [date.fromisoformat(m) for m in proj["months"]]
    if not months:
        return proj
    lo = month_start(start) if start else months[0]
    hi = month_start(end) if end else months[-1]
    idx = [i for i, m in enumerate(months) if lo <= m <= hi]
    if not idx:
        raise ValueError("Período fora do horizonte do cenário")
    a, b = idx[0], idx[-1] + 1
    n = b - a
    rows = []
    for r in proj["rows"]:
        vals = r["values"][a:b]
        rows.append({**r, "values": vals, "overridden": r["overridden"][a:b], "total": sum(vals),
                     "average": sum(vals) / n})
    s = {k: v[a:b] for k, v in proj["series"].items()}
    prev = a - 1
    base = replace(
        sc,
        initial_balance=proj["series"]["saldo_conta"][prev] if prev >= 0 else sc.initial_balance,
        initial_invested=proj["series"]["inv_saldo_fim"][prev] if prev >= 0 else sc.initial_invested,
        fgts_initial=proj["series"]["fgts_saldo"][prev] if prev >= 0 else sc.fgts_initial,
    )
    sub_months = months[a:b]
    return {
        **proj,
        "months": [m.isoformat() for m in sub_months],
        "rows": rows,
        "series": s,
        "kpis": compute_kpis(sub_months, rows, s, base),
        "waterfall": waterfall(s, base.initial_balance + base.initial_invested),
        "period": {"start": sub_months[0].isoformat(), "end": sub_months[-1].isoformat()},
        "horizon": {"start": proj["months"][0], "end": proj["months"][-1]},
    }


def compute_kpis(months: list[date], rows: list[dict], s: dict, sc: ScenarioIn) -> dict:
    n = len(months) or 1
    conta = s["saldo_conta"]
    min_conta = min(conta) if conta else 0.0
    rec_total = sum(s["receitas"])

    def tag_total(tag: str) -> float:
        return sum(r["total"] for r in rows if r["tag"] == tag)

    parcelas = sum(r["total"] for r in rows if r["group"] == "divida" and r["kind"] not in ("quitacao", "atrasos"))
    atrasos = sum(r["total"] for r in rows if r["kind"] == "atrasos")
    quitacoes = sum(r["total"] for r in rows if r["kind"] == "quitacao")
    last_debt = None
    for m, v in zip(months, s["dividas"]):
        if v > 0:
            last_debt = m.isoformat()

    final_conta = conta[-1] if conta else sc.initial_balance
    final_inv = s["inv_saldo_fim"][-1] if conta else sc.initial_invested
    final_fgts = s["fgts_saldo"][-1] if conta else sc.fgts_initial
    return {
        "mes_inicial": months[0].isoformat() if months else None,
        "mes_final": months[-1].isoformat() if months else None,
        "n_meses": len(months),
        "saldo_inicial_conta": sc.initial_balance,
        "saldo_final_conta": final_conta,
        "saldo_final_investido": final_inv,
        "saldo_inicial_fgts": sc.fgts_initial,
        "saldo_final_fgts": final_fgts,
        "patrimonio_final": final_conta + final_inv + final_fgts,
        "menor_saldo_conta": min_conta,
        "mes_menor_saldo": months[conta.index(min_conta)].isoformat() if conta else None,
        "meses_saldo_negativo": sum(1 for v in conta if v < -0.005),
        "receita_media": rec_total / n,
        "despesa_media": sum(s["total_despesas"]) / n,
        "custo_moradia_medio": tag_total("moradia") / n,
        "pct_renda_moradia": (tag_total("moradia") / n) / (rec_total / n) if rec_total else 0.0,
        "custo_saude_medio": tag_total("saude") / n,
        "despesa_variavel_media": sum(s["despesas_variaveis"]) / n,
        "saldo_livre_medio": sum(s["saldo_livre"]) / n,
        "taxa_poupanca": sum(s["saldo_livre"]) / rec_total if rec_total else 0.0,
        "total_parcelas": parcelas,
        "total_quitacoes": quitacoes,
        "total_atrasos_pagos": atrasos,
        "total_dividas": sum(s["dividas"]),
        "pct_renda_dividas": sum(s["dividas"]) / rec_total if rec_total else 0.0,
        "ultimo_mes_com_parcela": last_debt,
        "meses_acima_limite_dividas": sum(1 for a in s["alerta_dividas"] if a),
        "total_investido": sum(s["investimentos"]),
        "rendimento_acumulado": s["inv_rendimento_acumulado"][-1] if conta else 0.0,
    }


# --------------------------------------------------------------------------- análises

def loans_timeline(loans: list[LoanIn]) -> dict:
    """Linha do tempo completa dos consignados (do 1º ao último desconto, sem
    limitar ao horizonte do cenário): parcelas sem e com quitação, desembolso
    das quitações e economia acumulada líquida (parcelas evitadas − desembolso)."""
    if not loans:
        zero = {k: 0.0 for k in ("parcelas_sem_quitacao", "parcelas_com_quitacao", "desembolso_quitacoes",
                                 "parcelas_evitadas", "economia_liquida", "parcela_mensal_liberada")}
        return {"months": [], "contracts": [], "installments_without_payoff": [], "installments_with_payoff": [],
                "payoff_disbursement": [], "cumulative_net_saving": [], "totals": {**zero, "mes_payback": None}}
    first = min(month_start(l.first_month) for l in loans)
    last = max(month_start(l.last_month) for l in loans)
    for l in loans:
        if l.payoff_month:
            first = min(first, month_start(l.payoff_month))
    months = [add_months(first, i) for i in range(months_between(first, last) + 1)]
    n = len(months)

    sem = [0.0] * n
    com = [0.0] * n
    desemb = [0.0] * n
    contracts = []
    for l in loans:
        original = LoanIn(**{**l.__dict__, "payoff_month": None})
        a = loan_payoff_analysis(l)
        row_sem = [loan_installment(original, m) for m in months]
        row_com = [loan_installment(l, m) for m in months]
        row_pay = [0.0] * n
        if l.payoff_month:
            row_pay[months.index(month_start(l.payoff_month))] = a["payoff_value"]
        for i in range(n):
            sem[i] += row_sem[i]
            com[i] += row_com[i]
            desemb[i] += row_pay[i]
        avoided = sum(row_sem) - sum(row_com)
        contracts.append({
            "id": l.id, "name": l.name, "installment": l.installment, "monthly_rate": l.monthly_rate,
            "first_month": l.first_month.isoformat(), "last_month": l.last_month.isoformat(),
            "payoff_month": l.payoff_month.isoformat() if l.payoff_month else None,
            "remaining": a["remaining"], "payoff_value": a["payoff_value"],
            "installments_avoided": avoided, "interest_saved": avoided - a["payoff_value"] if l.payoff_month else 0.0,
            "months_equivalent": a["months_equivalent"],
            "monthly_return": (l.installment / a["payoff_value"]) if a["payoff_value"] else None,
            "total_original": sum(row_sem), "total_with_payoff": sum(row_com) + a["payoff_value"],
        })

    acc, cum = 0.0, []
    for i in range(n):
        acc += sem[i] - com[i] - desemb[i]
        cum.append(acc)
    break_even = None
    if any(desemb):
        first_pay = next(i for i, v in enumerate(desemb) if v)
        for i in range(first_pay, n):
            if cum[i] >= -0.005:
                break_even = months[i].isoformat()
                break

    total_sem, total_com, total_pay = sum(sem), sum(com), sum(desemb)
    return {
        "months": [m.isoformat() for m in months],
        "installments_without_payoff": sem,
        "installments_with_payoff": com,
        "payoff_disbursement": desemb,
        "cumulative_net_saving": cum,
        "contracts": contracts,
        "totals": {
            "parcelas_sem_quitacao": total_sem,
            "parcelas_com_quitacao": total_com,
            "desembolso_quitacoes": total_pay,
            "parcelas_evitadas": total_sem - total_com,
            "economia_liquida": total_sem - total_com - total_pay,
            "parcela_mensal_liberada": sum(l.installment for l in loans if l.payoff_month),
            "mes_payback": break_even,
        },
    }


def sankey(projection: dict, month_index: int | None = None, min_share: float = 0.01) -> dict:
    """Fluxo do dinheiro: fontes de receita → Receitas → grupos → categorias.

    month_index=None soma todo o horizonte; caso contrário usa um único mês.
    Categorias com menos de `min_share` das entradas viram "Outros (grupo)"."""
    s = projection["series"]
    pick = (lambda vals: sum(vals)) if month_index is None else (lambda vals: vals[month_index])
    short = {"receita": "receitas", "despesa_fixa": "fixas", "divida": "dívidas",
             "despesa_variavel": "variáveis", "investimento": "investimentos"}

    nodes: dict[str, dict] = {}
    used: set[str] = set()

    def node(key: str, label: str, group: str, depth: int) -> str:
        if key not in nodes:
            name = label
            if name in used:
                name = f"{label} ({short.get(group, group)})"
            k = 2
            while name in used:
                name = f"{label} ({k})"
                k += 1
            used.add(name)
            nodes[key] = {"name": name, "group": group, "depth": depth}
        return nodes[key]["name"]

    links = []

    def link(src: str, dst: str, value: float):
        if value > 0.005:
            links.append({"source": src, "target": dst, "value": round(value, 2)})

    rows = projection["rows"]
    receitas = pick(s["receitas"])
    resgates = pick(s["inv_resgate_manual"]) + pick(s["inv_resgate_automatico"])
    outflows = pick(s["total_despesas"]) + pick(s["investimentos"])
    entradas = receitas + resgates
    threshold = max(entradas, outflows) * min_share

    hub = node("hub", "Receitas", "receita", 1)
    small_in = 0.0
    for r in rows:
        if r["group"] == "receita":
            v = pick(r["values"])
            if 0 < v < threshold:
                small_in += v
            else:
                link(node(f"c{r['category_id']}", r["name"], "receita", 0), hub, v)
    link(node("outras_rec", "Outras receitas", "receita", 0), hub, small_in)
    if resgates > 0.005:
        link(node("resgates", "Resgates de investimentos", "outros", 0), hub, resgates)
    if outflows > entradas + 0.005:
        link(node("deficit", "Saldo anterior em conta / déficit", "outros", 0), hub, outflows - entradas)

    for group in ("despesa_fixa", "divida", "despesa_variavel", "investimento"):
        g = node(f"g_{group}", GROUP_LABELS[group], group, 2)
        items = [(f"c{r['category_id']}", r["name"], pick(r["values"])) for r in rows if r["group"] == group]
        if group == "investimento":
            items.append(("auto_inv", "Investimento automático", pick(s["inv_automatico"])))
        total = sum(v for _, _, v in items)
        small = 0.0
        for key, name, v in items:
            if 0 < v < threshold:
                small += v
            else:
                link(g, node(key, name, group, 3), v)
        link(g, node(f"outros_{group}", f"Outros ({short[group]})", group, 3), small)
        link(hub, g, total)

    sobra = entradas - outflows
    if sobra > 0.005:
        link(hub, node("sobra", "Sobra em conta", "sobra", 2), sobra)

    used_names = {l["source"] for l in links} | {l["target"] for l in links}
    return {"nodes": [n for n in nodes.values() if n["name"] in used_names], "links": links}
