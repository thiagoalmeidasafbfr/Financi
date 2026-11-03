"""Lançamentos previstos: início/fim, mover ocorrência, ajustar um mês, pular, atrasos e efeito na projeção."""
from datetime import date

from app.finance import add_months, month_start

from .conftest import cat_id

TODAY = month_start(date.today())  # noqa: DTZ011


def m(k: int) -> str:
    return add_months(TODAY, k).isoformat()


def new(client, **kw):
    body = {"name": "Escola", "kind": "despesa", "amount": 900, "recurrence": "mensal", "start_month": m(1)} | kw
    r = client.post("/api/planned", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def flow(client, months=8):
    return client.get("/api/planned/flow", params={"months": months}).json()


def items(f, k):
    return f["months"][k]["items"]


def test_monthly_from_until(client):
    p = new(client, end_month=m(3))
    f = flow(client)
    assert [len(items(f, k)) for k in range(6)] == [0, 1, 1, 1, 0, 0]
    assert f["months"][1]["saidas"] == 900 and items(f, 2)[0]["status"] == "pendente"
    # sem fim: continua até o fim do horizonte
    client.put(f"/api/planned/{p['id']}", json={**{k: p[k] for k in ("name", "kind", "amount", "recurrence", "start_month")},
                                                 "end_month": None})
    assert all(len(items(flow(client), k)) == 1 for k in range(1, 8))
    # fim antes do início é recusado
    assert client.post("/api/planned", json={"name": "x", "amount": 1, "start_month": m(3), "end_month": m(1)}).status_code == 400


def test_move_one_off_and_single_occurrence(client):
    ipva = new(client, name="IPVA", amount=2400, recurrence="pontual", start_month=m(2))
    r = client.put(f"/api/planned/{ipva['id']}/occurrence", json={"month": m(2), "moved_to": m(4)})
    assert r.status_code == 200
    f = flow(client)
    assert items(f, 2) == [] and items(f, 4)[0]["name"] == "IPVA"

    escola = new(client, end_month=m(3))
    pid = escola["id"]
    client.put(f"/api/planned/{pid}/occurrence", json={"month": m(2), "moved_to": m(5)})   # só esse mês muda de lugar
    client.put(f"/api/planned/{pid}/occurrence", json={"month": m(3), "amount": 999})      # só esse mês muda de valor
    client.put(f"/api/planned/{pid}/occurrence", json={"month": m(1), "skipped": True})    # pula um mês
    f = flow(client)
    esc = {k: [o for o in items(f, k) if o["name"] == "Escola"] for k in range(7)}
    assert esc[1][0]["status"] == "pulado" and f["months"][1]["saidas"] == 0
    assert esc[2] == [] and esc[5][0]["moved"] and esc[5][0]["original"] == m(2)
    assert esc[3][0]["amount"] == 999 and esc[3][0]["changed"]
    # desfazer volta ao da série
    client.put(f"/api/planned/{pid}/occurrence", json={"month": m(2), "reset": True})
    assert len([o for o in items(flow(client), 2) if o["name"] == "Escola"]) == 1


def test_overdue_paid_and_statement_match(client):
    acc = client.post("/api/accounts", json={"name": "Conta", "opening_balance": 0}).json()["id"]
    late = new(client, name="IPTU atrasado", amount=800, recurrence="pontual", start_month=m(-1), due_day=10)
    f = flow(client)
    assert [o["name"] for o in f["overdue"]] == ["IPTU atrasado"] and f["overdue_total"] == 800
    dash = client.get("/api/dashboard").json()
    assert dash["overdue"]["count"] == 1 and dash["overdue"]["total"] == 800
    client.put(f"/api/planned/{late['id']}/occurrence", json={"month": m(-1), "paid": True})
    assert flow(client)["overdue"] == []

    # pago reconhecido no extrato pelo texto informado
    new(client, name="Condomínio", amount=650, recurrence="pontual", start_month=m(-1), due_day=5, match_pattern="CONDOMINIO")
    assert [o["name"] for o in flow(client)["overdue"]] == ["Condomínio"]
    client.post("/api/transactions", json={"account_id": acc, "date": add_months(TODAY, -1).replace(day=6).isoformat(),
                                           "amount": -650, "description": "PIX CONDOMINIO ED SOL"})
    assert flow(client)["overdue"] == []

    # série que já existia antes do cadastro não gera atraso dos meses passados
    new(client, name="Aluguel", amount=1300, start_month=m(-6), due_day=1)
    assert all(o["name"] != "Aluguel" or o["month"] >= m(0) for o in flow(client)["overdue"])


def test_projection_uses_planned(client):
    client.post("/api/accounts", json={"name": "Conta", "opening_balance": 10000})
    aluguel = cat_id(client, "Aluguel")
    client.put("/api/budgets", json=[{"category_id": aluguel, "amount": 1000}])
    new(client, name="Aluguel novo", amount=1300, category_id=aluguel, start_month=m(2))   # a partir do mês 2 o aluguel muda
    new(client, name="Multa atrasada", amount=500, recurrence="pontual", start_month=m(-1))  # em atraso
    new(client, name="Freela", kind="receita", amount=2000, recurrence="pontual", start_month=m(3))
    p = client.get("/api/projection", params={"months": 4}).json()["months"]
    assert p[0]["despesas"] == 1000 and p[0]["pendentes"] == 500        # mês 1: orçamento; atrasado sai no 1º mês
    assert p[1]["despesas"] == 1300 and "previsto" in p[1]["fonte_despesas"]  # o previsto substitui o orçamento
    assert p[2]["receitas"] == 2000 and "previsto" in p[2]["fonte_receitas"]
    assert p[0]["saldo"] == round(10000 - 1000 - 500, 2)


def test_commitment_uses_planned_income_without_statements(client):
    client.post("/api/debts", json={"name": "Acordo", "kind": "acordo", "installment": 500, "balance": 3000})
    assert client.get("/api/debts/overview").json()["totals"]["comprometimento"] is None
    new(client, name="Salário", kind="receita", amount=5000, start_month=m(0))
    assert client.get("/api/debts/overview").json()["totals"]["comprometimento"] == 0.1


def test_dashboard_overview(client):
    client.post("/api/accounts", json={"name": "Conta", "opening_balance": 5000})
    new(client, name="Salário", kind="receita", amount=8000, start_month=m(0), due_day=28)
    new(client, name="Aluguel", amount=1300, start_month=m(0), due_day=28)
    d = client.get("/api/dashboard").json()
    assert d["saldo_contas"] == 5000
    assert d["previstos_mes"] == {"receitas": 8000, "despesas": 1300}
    assert len(d["projecao"]["meses"]) == 6 and d["projecao"]["menor"]["saldo"] <= d["projecao"]["meses"][-1]["saldo"]
    assert isinstance(d["proximos"], list)


def test_dashboard_has_data_without_accounts(client):
    """A planilha de planejamento não cria conta; o Início mostra o panorama mesmo assim."""
    assert client.get("/api/dashboard").json()["has_data"] is False
    new(client, name="Aluguel", amount=1300, start_month=m(0))
    d = client.get("/api/dashboard").json()
    assert d["has_data"] is True and d["accounts"] == [] and d["previstos_mes"]["despesas"] == 1300


def test_month_by_month_table_matches_projection(client):
    import pytest
    client.post("/api/accounts", json={"name": "Conta", "opening_balance": 10000})
    aluguel, mercado = cat_id(client, "Aluguel"), cat_id(client, "Supermercado")
    client.put("/api/budgets", json=[{"category_id": aluguel, "amount": 1000}, {"category_id": mercado, "amount": 800}])
    new(client, name="Aluguel novo", amount=1300, category_id=aluguel, start_month=m(2))
    new(client, name="Salário", kind="receita", amount=7000, category_id=cat_id(client, "Salário"), start_month=m(0))
    new(client, name="Freela", kind="receita", amount=2000, recurrence="pontual", start_month=m(3))
    new(client, name="Multa", amount=500, recurrence="pontual", start_month=m(-1))
    client.post("/api/debts", json={"name": "Consignado", "kind": "consignado", "installment": 300,
                                    "first_due": f"{m(-2)[:7]}-05", "total_installments": 10})
    p = client.get("/api/projection", params={"months": 4, "detail": True}).json()
    t, rows = p["table"], p["months"]
    assert t["months"] == [r["month"] for r in rows]
    sec = {s["key"]: s for s in t["sections"]}
    for i, r in enumerate(rows):
        assert sec["entradas"]["values"][i] == pytest.approx(r["receitas"])
        assert sec["saidas"]["values"][i] + sec["dividas"]["values"][i] == pytest.approx(r["despesas"] + r["dividas"] + r["parcelas_cartao"])
        assert t["totais"]["acumulado"]["values"][i] == r["saldo"]
    # coluna "Agora": multa atrasada + salário e o que vence neste mês
    assert t["totais"]["saldo_mes"]["now"] == -rows[0]["pendentes"]
    lines = {row["label"]: row for s in t["sections"] for g in s["groups"] for row in g["rows"]}
    # orçamento da categoria e o previsto que o substitui viram linhas separadas (o previsto com o próprio nome)
    assert lines["Aluguel"]["values"][:2] == [1000, 0] and lines["Aluguel"]["sources"][0] == "orçamento"
    assert lines["Aluguel novo"]["values"][:2] == [0, 1300] and lines["Aluguel novo"]["sources"][1] == "previsto"
    assert lines["Freela"]["values"][2] == 2000 and lines["Multa"]["now"] == 500
    assert lines["Consignado"]["values"][0] == 300
    groups = [g["group"] for g in sec["saidas"]["groups"]]
    assert "Moradia" in groups and "Alimentação" in groups
