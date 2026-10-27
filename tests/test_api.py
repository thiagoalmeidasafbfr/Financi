import io


def make_scenario(client, name="Base", **kw):
    body = {"name": name, "start_month": "2026-11-01", "months": 12, "initial_balance": 1000, **kw}
    r = client.post("/api/scenarios", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def cat_id(client, name):
    return next(c["id"] for c in client.get("/api/categories").json() if c["name"] == name)


def test_default_categories_seeded(client):
    cats = client.get("/api/categories").json()
    assert any(c["kind"] == "salario" for c in cats)
    assert any(c["kind"] == "consignados" for c in cats)


def test_scenario_projection_entries_and_duplicate(client):
    sc = make_scenario(client, is_baseline=True)
    client.put(f"/api/scenarios/{sc['id']}/salary-changes", json=[{"start_month": "2026-11-01", "amount": 8000}])
    aluguel = cat_id(client, "Aluguel / financiamento imobiliário")
    r = client.post(f"/api/scenarios/{sc['id']}/entries/fill",
                    json={"category_id": aluguel, "from_month": "2026-11-01", "to_month": "2027-10-01", "amount": 2000})
    assert r.json()["updated"] == 12

    p = client.get(f"/api/scenarios/{sc['id']}/projection").json()
    assert p["series"]["receitas"][0] == 8000
    assert p["series"]["saldo_conta"][0] == 1000 + 8000 - 2000
    assert p["kpis"]["custo_moradia_medio"] == 2000

    # limpar um mês
    client.put(f"/api/scenarios/{sc['id']}/entries", json=[{"category_id": aluguel, "month": "2026-11-01", "amount": None}])
    p = client.get(f"/api/scenarios/{sc['id']}/projection").json()
    assert p["series"]["despesas_fixas"][0] == 0

    dup = client.post(f"/api/scenarios/{sc['id']}/duplicate", params={"name": "Cópia"}).json()
    p2 = client.get(f"/api/scenarios/{dup['id']}/projection").json()
    assert p2["kpis"] == p["kpis"]
    assert client.post(f"/api/scenarios/{sc['id']}/duplicate", params={"name": "Cópia"}).status_code == 409

    sk = client.get(f"/api/scenarios/{sc['id']}/sankey", params={"month": "2026-12-01"}).json()
    assert {"nodes", "links"} <= sk.keys()
    assert client.get(f"/api/scenarios/{sc['id']}/sankey", params={"month": "2030-01-01"}).status_code == 400

    cmp = client.get("/api/reports/compare").json()
    assert [s["name"] for s in cmp["scenarios"]] == ["Base", "Cópia"]


def test_only_one_baseline(client):
    a = make_scenario(client, "A", is_baseline=True)
    b = make_scenario(client, "B", is_baseline=True)
    flags = {s["id"]: s["is_baseline"] for s in client.get("/api/scenarios").json()}
    assert flags == {a["id"]: False, b["id"]: True}


def test_loans_and_payoffs_per_scenario(client):
    sc1 = make_scenario(client, "Quita")
    sc2 = make_scenario(client, "Não quita")
    loan = client.post("/api/loans", json={"name": "PAN 1", "monthly_rate": 0.0439, "installment": 364.89,
                                           "first_month": "2026-10-15", "last_month": "2027-08-01"}).json()
    assert loan["first_month"] == "2026-10-01"
    client.put(f"/api/scenarios/{sc1['id']}/payoffs", json=[{"contract_id": loan["id"], "payoff_month": "2027-02-01"}])

    t1 = client.get(f"/api/scenarios/{sc1['id']}/loans").json()
    t2 = client.get(f"/api/scenarios/{sc2['id']}/loans").json()
    assert round(t1["contracts"][0]["payoff_value"], 2) == 2158.87
    assert t2["totals"]["desembolso_quitacoes"] == 0

    p1 = client.get(f"/api/scenarios/{sc1['id']}/projection").json()
    assert round(p1["series"]["dividas"][3], 2) == 2158.87  # fev/27: quitação

    cmp = client.get("/api/reports/loans-compare").json()
    assert {s["name"] for s in cmp["scenarios"]} == {"Quita", "Não quita"}

    client.put(f"/api/scenarios/{sc1['id']}/payoffs", json=[{"contract_id": loan["id"], "payoff_month": None}])
    assert client.get(f"/api/scenarios/{sc1['id']}/payoffs").json() == []


def test_transactions_and_budget_vs_actual(client):
    sc = make_scenario(client, is_baseline=True)
    merc = cat_id(client, "Supermercado")
    client.put(f"/api/scenarios/{sc['id']}/entries", json=[{"category_id": merc, "month": "2026-11-01", "amount": 800}])
    client.post("/api/transactions", json={"date": "2026-11-05", "description": "Mercado", "amount": -650.5,
                                           "category_id": merc})
    csv = "data;descricao;valor;categoria\n10/11/2026;Feira;-1.234,50;Supermercado\n31/02/2026;ruim;10;\n"
    r = client.post("/api/transactions/import-csv", files={"file": ("x.csv", io.BytesIO(csv.encode()), "text/csv")})
    assert r.json()["created"] == 1 and len(r.json()["errors"]) == 1

    txs = client.get("/api/transactions", params={"month": "2026-11-01"}).json()
    assert len(txs) == 2
    bva = client.get("/api/reports/budget-vs-actual", params={"month": "2026-11-01"}).json()
    row = next(x for x in bva["rows"] if x["category_id"] == merc)
    assert row["planned"] == 800
    assert round(row["actual"], 2) == 1885.0
    assert round(bva["summary"]["despesa_variavel"]["diff"], 2) == 1085.0
