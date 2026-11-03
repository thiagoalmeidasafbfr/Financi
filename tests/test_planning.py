from datetime import date

from app.finance import add_months, month_start
from tests.conftest import cat_id, upload

TODAY = month_start(date.today())  # noqa: DTZ011


def add_tx(client, acc, d, amount, desc, cat=None):
    return client.post("/api/transactions", json={"account_id": acc, "date": d.isoformat(), "amount": amount,
                                                   "description": desc, "category_id": cat}).json()


def test_people_accounts_person_filter(client):
    ana = client.post("/api/people", json={"name": "Ana"}).json()
    bruno = client.post("/api/people", json={"name": "Bruno"}).json()
    a1 = client.post("/api/accounts", json={"name": "Conta Ana", "owner_id": ana["id"], "opening_balance": 100}).json()
    client.post("/api/accounts", json={"name": "Conta Bruno", "owner_id": bruno["id"]})
    client.post("/api/accounts", json={"name": "Conta conjunta", "opening_balance": 50})
    assert [a["name"] for a in client.get("/api/accounts", params={"person": ana["id"]}).json()] == ["Conta Ana"]
    assert [a["name"] for a in client.get("/api/accounts", params={"person": "conjunto"}).json()] == ["Conta conjunta"]
    assert len(client.get("/api/accounts").json()) == 3
    add_tx(client, a1["id"], TODAY, -30, "Mercado")
    assert next(a for a in client.get("/api/accounts").json() if a["id"] == a1["id"])["balance"] == 70
    assert client.post("/api/people", json={"name": "Ana"}).status_code == 409


def test_budget_month_view_and_suggestion(client):
    acc = client.post("/api/accounts", json={"name": "Conta"}).json()["id"]
    sup, sal, fat = cat_id(client, "Supermercado"), cat_id(client, "Salário"), cat_id(client, "Pagamento de fatura")
    for k in (1, 2, 3):  # três meses fechados antes do atual
        m = add_months(TODAY, -k)
        add_tx(client, acc, m, -600 - 30 * k, "Mercado", sup)
        add_tx(client, acc, m, 8000, "Salário", sal)
    add_tx(client, acc, TODAY, -400, "Mercado", sup)
    add_tx(client, acc, TODAY, -2000, "Fatura", fat)  # transferência não conta como gasto
    client.put("/api/budgets", json=[{"category_id": sup, "amount": 700}, {"category_id": sal, "amount": 8000}])
    v = client.get("/api/budget").json()
    row = next(r for r in v["rows"] if r["category_id"] == sup)
    assert (row["planned"], row["actual"], row["remaining"]) == (700, 400, 300)
    assert v["totals"]["despesas"] == 400 and all(r["category_id"] != fat for r in v["rows"])
    # orçamento de um mês específico substitui o padrão
    client.put("/api/budgets", json=[{"category_id": sup, "month": TODAY.isoformat(), "amount": 900}])
    assert next(r for r in client.get("/api/budget").json()["rows"] if r["category_id"] == sup)["planned"] == 900
    sug = {s["name"]: s["amount"] for s in client.get("/api/budget/suggest").json()}
    assert sug["Supermercado"] == 660 and sug["Salário"] == 8000


def test_debts_cards_projection_and_dashboard(client):
    upload(client, "cartao.ofx")
    card = next(a for a in client.get("/api/accounts").json() if a["kind"] == "cartao")
    client.put(f"/api/accounts/{card['id']}", json={**{k: card[k] for k in ("name", "kind", "owner_id")},
                                                    "closing_day": 25, "due_day": 5, "credit_limit": 5000})
    conta = client.post("/api/accounts", json={"name": "Conta", "opening_balance": 10000}).json()["id"]
    first = add_months(TODAY, -2)
    loan = client.post("/api/debts", json={"name": "Consignado", "kind": "consignado", "installment": 312.07,
                                            "monthly_rate": 0.042, "first_due": first.replace(day=5).isoformat(),
                                            "total_installments": 24}).json()
    client.post("/api/debts", json={"name": "Acordo cartão antigo", "kind": "acordo", "balance": 2500})
    # acordo sem prazo, mas com parcela: 1.200 / 500 = 3 parcelas a partir do mês que vem
    client.post("/api/debts", json={"name": "Acordo loja", "kind": "acordo", "balance": 1200, "installment": 500})
    ov = client.get("/api/debts/overview").json()
    d = next(x for x in ov["debts"] if x["id"] == loan["id"])
    assert d["remaining"] in (21, 22) and d["balance"] > 0
    assert ov["totals"]["saldo_devedor"] > 2500
    c = ov["cards"][0]
    assert c["configured"] and c["future_total"] > 0  # parcelas 4..10 e 3..6 das compras parceladas
    assert ov["avalanche"][0] == loan["id"]  # juros maior primeiro (o acordo não tem taxa)
    loja = next(x for x in ov["debts"] if x["name"] == "Acordo loja")
    assert loja["remaining"] == 3 and loja["end_month"] == add_months(TODAY, 3).isoformat()
    assert ov["totals"]["parcelas_mes"] == round(312.07 + 500, 2)

    budget_sup = cat_id(client, "Supermercado")
    client.put("/api/budgets", json=[{"category_id": budget_sup, "amount": 1000},
                                     {"category_id": cat_id(client, "Salário"), "amount": 6000}])
    p = client.get("/api/projection", params={"months": 3}).json()
    assert p["saldo_atual"] == 10000 and len(p["months"]) == 3
    m1 = p["months"][0]
    # Supermercado vem do orçamento; as outras categorias do cartão, da média dos meses com extrato
    assert m1["receitas"] == 6000 and m1["despesas"] > 1000 and m1["fonte_despesas"] == "orçamento + média"
    assert m1["dividas"] == round(312.07 + 500, 2) and p["months"][2]["dividas"] == round(312.07 + 500, 2)
    assert m1["saldo"] == round(p["saldo_inicial"] + 6000 - m1["despesas"] - m1["dividas"] - m1["parcelas_cartao"], 2)

    dash = client.get("/api/dashboard").json()
    assert dash["saldo_contas"] == 10000 and dash["cards"] and "uncategorized" in dash
    assert conta


def test_auth_and_status(client, monkeypatch):
    import base64
    assert client.get("/api/status").json()["ai"] is False
    monkeypatch.setenv("FINANCI_PASSWORD", "s3gredo")
    assert client.get("/api/people").status_code == 401
    ok = {"Authorization": "Basic " + base64.b64encode(b"financi:s3gredo").decode()}
    assert client.get("/api/people", headers=ok).status_code == 200
    assert client.get("/healthz").status_code == 200


def test_averages_use_only_months_with_statements(client):
    """Com um único mês importado, a média é aquele mês (não dividida por 3)."""
    acc = client.post("/api/accounts", json={"name": "Conta", "opening_balance": 0}).json()["id"]
    last = add_months(TODAY, -1)
    add_tx(client, acc, last, 9000, "Salario", cat_id(client, "Salário"))
    add_tx(client, acc, last, -600, "Mercado", cat_id(client, "Supermercado"))
    add_tx(client, acc, last, -150, "Loja qualquer")  # sem categoria também é gasto
    m1 = client.get("/api/projection", params={"months": 1}).json()["months"][0]
    assert (m1["receitas"], m1["despesas"], m1["fonte_receitas"]) == (9000, 750, "média")
    sug = {s["name"]: s["amount"] for s in client.get("/api/budget/suggest").json()}
    assert sug == {"Salário": 9000, "Supermercado": 600}
