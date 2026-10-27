from datetime import date

import pytest

from app import engine as eng

CATS = [
    eng.CategoryIn(1, "Salário", "receita", "salario"),
    eng.CategoryIn(2, "13º", "receita", "decimo_terceiro"),
    eng.CategoryIn(3, "Férias", "receita", "ferias"),
    eng.CategoryIn(4, "Bônus", "receita", "bonus"),
    eng.CategoryIn(5, "Aluguel", "despesa_fixa", tag="moradia"),
    eng.CategoryIn(6, "Mercado", "despesa_variavel"),
    eng.CategoryIn(7, "Consignados", "divida", "consignados"),
    eng.CategoryIn(8, "Quitação", "divida", "quitacao"),
    eng.CategoryIn(9, "Reserva", "investimento"),
]
START = date(2026, 11, 1)


def scenario(**kw) -> eng.ScenarioIn:
    base = dict(start_month=START, months=14, categories=CATS,
                salary_changes=[eng.SalaryChangeIn(START, 10000), eng.SalaryChangeIn(date(2027, 6, 1), None, 0.10)],
                thirteenth_first_year=2027, thirteenth_last_year=2027, vacation_month=9,
                bonus_salaries=1.0, bonus_month=3, invest_return_monthly=0.0)
    base.update(kw)
    return eng.ScenarioIn(**base)


def test_month_helpers():
    assert eng.add_months(date(2026, 11, 1), 3) == date(2027, 2, 1)
    assert eng.months_between(date(2026, 11, 1), date(2027, 2, 1)) == 3


def test_salary_schedule_and_extra_income():
    p = eng.project(scenario())
    rows = {r["name"]: r["values"] for r in p["rows"]}
    m = p["months"]
    assert rows["Salário"][0] == 10000
    assert rows["Salário"][m.index("2027-06-01")] == pytest.approx(11000)  # reajuste de 10%
    assert rows["13º"][m.index("2027-11-01")] == pytest.approx(5500)
    assert rows["13º"][m.index("2027-12-01")] == pytest.approx(5500)
    assert rows["13º"][m.index("2026-11-01")] == 0  # fora dos anos configurados
    assert rows["Férias"][m.index("2027-09-01")] == pytest.approx(11000 / 3)
    assert rows["Bônus"][m.index("2027-03-01")] == pytest.approx(10000)


def test_override_wins_over_calculated_value():
    sc = scenario(entries={(1, START): 3500.0, (2, date(2027, 11, 1)): 0.0})
    p = eng.project(sc)
    rows = {r["name"]: r for r in p["rows"]}
    assert rows["Salário"]["values"][0] == 3500
    assert rows["Salário"]["overridden"][0] is True
    assert rows["13º"]["values"][p["months"].index("2027-11-01")] == 0


def test_balance_and_auto_investment_with_min_balance():
    sc = scenario(entries={(5, m): 3000.0 for m in [eng.add_months(START, i) for i in range(14)]},
                  invest_pct=0.5, min_balance=1000)
    p = eng.project(sc)
    s = p["series"]
    # mês 1: disponível 7000, base = 7000 - 1000 = 6000, investe 50%
    assert s["saldo_disponivel"][0] == pytest.approx(7000)
    assert s["inv_automatico"][0] == pytest.approx(3000)
    assert s["saldo_conta"][0] == pytest.approx(4000)
    # conservação: conta + investido = saldo inicial + soma dos saldos operacionais (rentab. zero)
    for i in range(len(p["months"])):
        assert s["saldo_total"][i] == pytest.approx(sum(s["saldo_operacional"][: i + 1]))


def test_auto_redemption_keeps_min_balance():
    big = {(6, date(2027, 1, 1)): 15000.0}  # cabe no saldo investido (19.500)
    sc = scenario(entries=big, invest_pct=1.0, min_balance=500, salary_changes=[eng.SalaryChangeIn(START, 10000)],
                  bonus_salaries=0)
    s = eng.project(sc)["series"]
    i = 2  # jan/27
    assert s["inv_resgate_automatico"][i] > 0
    assert s["saldo_conta"][i] == pytest.approx(500)


def test_loan_payoff_present_value_and_installments():
    loan = eng.LoanIn(1, "PAN", 364.89, date(2026, 10, 1), date(2027, 8, 1), 0.0439, payoff_month=date(2027, 2, 1))
    a = eng.loan_payoff_analysis(loan)
    assert a["remaining"] == 7
    assert a["payoff_value"] == pytest.approx(2158.87, abs=0.01)  # mesmo valor da aba Quitações
    assert a["interest_saved"] == pytest.approx(395.36, abs=0.01)
    assert eng.loan_installment(loan, date(2027, 1, 1)) == 364.89
    assert eng.loan_installment(loan, date(2027, 2, 1)) == 0

    p = eng.project(scenario(loans=[loan]))
    rows = {r["name"]: r["values"] for r in p["rows"]}
    m = p["months"]
    assert rows["Consignados"][m.index("2027-01-01")] == pytest.approx(364.89)
    assert rows["Quitação"][m.index("2027-02-01")] == pytest.approx(2158.87, abs=0.01)


def test_loans_timeline_payback():
    loans = [eng.LoanIn(1, "A", 500, date(2026, 11, 1), date(2028, 10, 1), 0.03, payoff_month=date(2027, 1, 1)),
             eng.LoanIn(2, "B", 100, date(2026, 11, 1), date(2027, 4, 1), 0.02)]
    t = eng.loans_timeline(loans)
    tot = t["totals"]
    assert tot["parcelas_evitadas"] == pytest.approx(500 * 22)
    assert tot["economia_liquida"] == pytest.approx(tot["parcelas_evitadas"] - tot["desembolso_quitacoes"])
    assert tot["economia_liquida"] > 0
    assert t["cumulative_net_saving"][-1] == pytest.approx(tot["economia_liquida"])
    assert tot["mes_payback"] is not None
    contract_b = next(c for c in t["contracts"] if c["name"] == "B")
    assert contract_b["payoff_month"] is None and contract_b["installments_avoided"] == 0


def test_sankey_flows_balance_at_hub():
    sc = scenario(entries={(5, eng.add_months(START, i)): 2500.0 for i in range(14)}, invest_pct=0.3)
    p = eng.project(sc)
    sk = eng.sankey(p)
    inflow = sum(l["value"] for l in sk["links"] if l["target"] == "Receitas")
    outflow = sum(l["value"] for l in sk["links"] if l["source"] == "Receitas")
    assert inflow == pytest.approx(outflow, abs=0.05)
    names = [n["name"] for n in sk["nodes"]]
    assert len(names) == len(set(names))
    # cada grupo distribui exatamente o que recebe
    for g in ("Despesas fixas", "Investimentos e reserva"):
        gin = sum(l["value"] for l in sk["links"] if l["target"] == g)
        gout = sum(l["value"] for l in sk["links"] if l["source"] == g)
        assert gin == pytest.approx(gout, abs=0.05)


def test_sankey_single_month_with_deficit():
    sc = scenario(entries={(6, date(2027, 1, 1)): 30000.0})
    p = eng.project(sc)
    sk = eng.sankey(p, p["months"].index("2027-01-01"))
    assert any(l["source"] == "Saldo anterior em conta / déficit" for l in sk["links"])


def test_inflation_applied_only_when_enabled():
    entries = {(5, eng.add_months(START, i)): 1000.0 for i in range(14)}
    infl = [eng.InflationIn(2027, 0.05, 0.0)]
    off = eng.project(scenario(entries=entries, inflation=infl))
    on = eng.project(scenario(entries=entries, inflation=infl, apply_inflation=True, inflation_month=6))
    m = on["months"]
    rent = lambda p: next(r for r in p["rows"] if r["name"] == "Aluguel")["values"]  # noqa: E731
    assert rent(off)[m.index("2027-07-01")] == 1000
    assert rent(on)[m.index("2027-05-01")] == 1000
    assert rent(on)[m.index("2027-06-01")] == pytest.approx(1050)


def test_arrear_value_with_fine_interest_and_agreement():
    a = eng.ArrearIn(1, "Aluguel", 1300, due_month=date(2026, 8, 1), fine_pct=0.02, interest_monthly=0.01)
    assert eng.arrear_months_late(a, date(2026, 11, 15)) == 3
    assert eng.arrear_value(a, date(2026, 11, 1)) == pytest.approx(1300 * 1.02 + 1300 * 0.01 * 3)
    a.negotiated_amount = 1200
    assert eng.arrear_value(a, date(2027, 6, 1)) == 1200
    a.status = "pago"
    assert eng.arrear_value(a, date(2027, 6, 1)) == 0


def test_arrear_plan_enters_cash_flow():
    cats = CATS + [eng.CategoryIn(10, "Atrasos", "divida", "atrasos")]
    a = eng.ArrearIn(1, "Aluguel", 1200, due_month=date(2026, 10, 1), interest_monthly=0.01,
                     plan_start=date(2026, 12, 1), plan_installments=3)
    p = eng.project(scenario(categories=cats, arrears=[a]))
    row = next(r for r in p["rows"] if r["kind"] == "atrasos")
    each = (1200 + 1200 * 0.01 * 2) / 3  # juros até o início do plano (2 meses)
    assert row["values"][:5] == pytest.approx([0, each, each, each, 0])
    assert p["kpis"]["total_atrasos_pagos"] == pytest.approx(each * 3)
    assert p["kpis"]["total_parcelas"] == 0  # atrasos não contam como parcela de empréstimo
    s = eng.arrears_summary([a, eng.ArrearIn(2, "IPTU", 72)], date(2026, 11, 1))
    assert s["totals"]["em_aberto"] == 2
    assert s["totals"]["sem_plano"] == 72
    assert s["totals"]["planejado"] == pytest.approx(each * 3)


def test_payoff_planner_cells_and_fit():
    loan = eng.LoanIn(1, "PAN", 364.89, date(2026, 10, 1), date(2027, 8, 1), 0.0439, payoff_month=date(2027, 2, 1))
    sc = scenario(loans=[loan], categories=CATS)
    pl = eng.payoff_planner(eng.project(sc), [loan])
    m = pl["months"]
    cells = pl["contracts"][0]["cells"]
    feb = cells[m.index("2027-02-01")]
    assert feb["scheduled"] and round(feb["value"], 2) == 2158.87
    assert cells[m.index("2027-08-01")]["remaining"] == 1
    assert cells[m.index("2027-09-01")] is None  # contrato já terminou
    assert pl["account"]["quitacoes"][m.index("2027-02-01")] == pytest.approx(2158.87, abs=0.01)
    # com salário de 10 mil e sem despesas, qualquer quitação cabe no saldo
    assert all(c["fits"] for c in cells if c)
    # custo-benefício no mês agendado (mesmos números da aba Quitações)
    ref = pl["contracts"][0]["ref"]
    assert ref["month"] == "2027-02-01"
    assert ref["monthly_return"] * 1000 == pytest.approx(364.89 / 2158.87 * 1000, abs=0.01)
    assert ref["total_gain"] == pytest.approx(395.36 / 2158.87, abs=1e-4)


def test_best_payoffs_maximizes_freed_installment_within_budget():
    m = date(2026, 12, 1)
    loans = [
        eng.LoanIn(1, "A", 400, date(2026, 1, 1), date(2028, 12, 1), 0.03),   # caro, libera 400
        eng.LoanIn(2, "B", 250, date(2026, 1, 1), date(2027, 12, 1), 0.03),   # libera 250
        eng.LoanIn(3, "C", 200, date(2026, 1, 1), date(2027, 10, 1), 0.03),   # libera 200
        eng.LoanIn(4, "D", 500, date(2026, 1, 1), date(2027, 1, 1), 0.03),    # termina em 2 meses
    ]
    vals = {l.id: eng.loan_payoff_analysis(eng.LoanIn(**{**l.__dict__, "payoff_month": m}))["payoff_value"] for l in loans}
    budget = vals[2] + vals[3] + 1  # cabe B+C (450/mês) mas não A+qualquer outro
    r = eng.best_payoffs(loans, m, budget, min_remaining=3)
    assert {c["id"] for c in r["selected"]} == {2, 3}
    assert r["totals"]["parcela_liberada"] == 450
    assert [c["id"] for c in r["skipped"]] == [4]
    # sem o filtro, D (500/mês, barato porque termina logo) entra
    r = eng.best_payoffs(loans, m, budget, min_remaining=0)
    assert 4 in {c["id"] for c in r["selected"]}
    assert r["totals"]["valor_quitacao"] <= budget
    # contrato já quitado antes do mês não é candidato
    loans[0].payoff_month = date(2026, 11, 1)
    assert 1 not in {c["id"] for c in eng.best_payoffs(loans, m, 1e9)["candidates"]}
