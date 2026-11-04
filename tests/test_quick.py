"""Adicionar rápido: categorias mais usadas, palpite pela descrição e regras no lançamento à mão."""
from datetime import date

from tests.conftest import cat_id

TODAY = date.today().isoformat()  # noqa: DTZ011


def test_frequent_categories_and_default_account(client):
    q = client.get("/api/quick").json()
    names = {c["id"]: c["name"] for c in client.get("/api/categories").json()}
    assert [names[i] for i in q["frequent"]["despesa"]][:3] == ["Supermercado", "Restaurantes", "Delivery"]  # sem histórico: padrão
    assert names[q["frequent"]["receita"][0]] == "Salário" and q["account_id"] is None

    card = client.post("/api/accounts", json={"name": "Cartão", "kind": "cartao"}).json()["id"]
    acc = client.post("/api/accounts", json={"name": "Conta", "opening_balance": 0}).json()["id"]
    assert client.get("/api/quick").json()["account_id"] == acc  # conta antes do cartão
    pets = cat_id(client, "Pets")
    for _ in range(3):
        client.post("/api/transactions", json={"account_id": card, "date": TODAY, "amount": -50, "description": "Ração", "category_id": pets})
    q = client.get("/api/quick").json()
    assert q["frequent"]["despesa"][0] == pets and len(q["frequent"]["despesa"]) == 8
    assert q["account_id"] == card  # a do último lançamento à mão


def test_guess_by_rules_and_planned_names(client):
    g = lambda d, k="despesa": client.get("/api/quick/guess", params={"description": d, "kind": k}).json()["category_id"]  # noqa: E731
    assert g("Uber centro") == cat_id(client, "Apps de transporte")
    assert g("ub") is None and g("coisa sem regra") is None
    assert g("Uber centro", "receita") is None  # categoria de despesa não vale para receita
    escola = cat_id(client, "Escola")
    client.post("/api/planned", json={"name": "Mensalidade Ana", "kind": "despesa", "amount": 900, "recurrence": "mensal",
                                      "start_month": TODAY[:8] + "01", "category_id": escola})
    assert g("mensalidade ana") == escola


def test_manual_entry_without_category_uses_rules(client):
    acc = client.post("/api/accounts", json={"name": "Conta", "opening_balance": 0}).json()["id"]
    t = client.post("/api/transactions", json={"account_id": acc, "date": TODAY, "amount": -32.5, "description": "IFOOD *PIZZA"}).json()
    assert t["category_id"] == cat_id(client, "Delivery")
