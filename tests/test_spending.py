"""Gastos: o que foi marcado como pago e os lançamentos de saída, sem contar duas vezes; e o que falta pagar."""
from datetime import date

from app.finance import add_months, month_start
from tests.conftest import cat_id

TODAY = date.today()  # noqa: DTZ011
CUR = month_start(TODAY)


def test_spending_paid_and_pending(client):
    c = client
    m = CUR.isoformat()
    aluguel = c.post("/api/planned", json={"name": "Aluguel", "kind": "despesa", "amount": 2500, "recurrence": "mensal",
                                           "start_month": m, "due_day": 28, "category_id": cat_id(c, "Aluguel")}).json()
    escola = c.post("/api/planned", json={"name": "Escola", "kind": "despesa", "amount": 900, "recurrence": "mensal",
                                          "start_month": m, "due_day": 28, "category_id": cat_id(c, "Escola")}).json()
    c.post("/api/planned", json={"name": "Salário", "kind": "receita", "amount": 8000, "recurrence": "mensal", "start_month": m})
    s = c.get("/api/spending").json()
    assert s["spent"] == 0 and s["to_pay"] == 3400 and {o["name"] for o in s["pending"]} == {"Aluguel", "Escola"}

    # marcar como pago: vai para os gastos e sai do "falta pagar"
    c.put(f"/api/planned/{aluguel['id']}/occurrence", json={"month": m, "paid": True})
    acc = c.post("/api/accounts", json={"name": "Conta", "opening_balance": 0}).json()["id"]
    c.post("/api/transactions", json={"account_id": acc, "date": TODAY.isoformat(), "amount": -80, "description": "Farmácia",
                                      "category_id": cat_id(c, "Farmácia")})
    c.post("/api/transactions", json={"account_id": acc, "date": TODAY.isoformat(), "amount": -1000, "description": "Fatura",
                                      "category_id": cat_id(c, "Pagamento de fatura")})  # transferência: não é gasto
    c.post("/api/transactions", json={"account_id": acc, "date": TODAY.isoformat(), "amount": 500, "description": "Pix recebido"})
    s = c.get("/api/spending").json()
    assert s["spent"] == 2580 and s["to_pay"] == 900
    assert {(it["name"], it["source"]) for it in s["items"]} == {("Aluguel", "previsto pago"), ("Farmácia", "lançado")}
    assert {g["group"]: g["amount"] for g in s["by_group"]} == {"Moradia": 2500, "Saúde": 80}
    assert s["planned"] == 3400 and len(s["history"]) == 6 and s["history"][-1] == {"month": m, "spent": 2580, "planned": 3400}

    # previsto pago pelo extrato não conta duas vezes (o lançamento já é o gasto)
    c.put(f"/api/planned/{escola['id']}", json={"name": "Escola", "kind": "despesa", "amount": 900, "recurrence": "mensal",
                                                "start_month": m, "due_day": 28, "category_id": cat_id(c, "Escola"), "match_pattern": "COLEGIO"})
    c.post("/api/transactions", json={"account_id": acc, "date": TODAY.isoformat(), "amount": -900, "description": "COLEGIO ABC"})
    s = c.get("/api/spending").json()
    assert s["spent"] == 2580 + 900 and s["to_pay"] == 0
    assert [it["source"] for it in s["items"] if "COLEGIO" in it["name"]] == ["lançado"]
    # outro mês: nada
    assert c.get("/api/spending", params={"month": add_months(CUR, -3).isoformat()}).json()["spent"] == 0


def test_overdue_from_previous_months_is_still_to_pay(client):
    c = client
    prev = add_months(CUR, -1).isoformat()
    c.post("/api/planned", json={"name": "Condomínio atrasado", "kind": "despesa", "amount": 560, "recurrence": "pontual", "start_month": prev})
    s = c.get("/api/spending").json()
    assert [o["name"] for o in s["pending"]] == ["Condomínio atrasado"] and s["pending"][0]["status"] == "atrasado" and s["to_pay"] == 560
    assert c.get("/api/spending", params={"month": prev}).json()["to_pay"] == 560  # no próprio mês também
    assert c.get("/api/spending", params={"month": add_months(CUR, 1).isoformat()}).json()["to_pay"] == 0


def test_paid_counts_in_the_month_it_was_paid(client):
    """Atraso de mês anterior pago agora: é gasto deste mês (data do pagamento), não do mês da conta."""
    c = client
    prev = add_months(CUR, -1).isoformat()
    p = c.post("/api/planned", json={"name": "Condomínio", "kind": "despesa", "amount": 560, "recurrence": "pontual",
                                     "start_month": prev}).json()
    c.put(f"/api/planned/{p['id']}/occurrence", json={"month": prev, "paid": True})
    s = c.get("/api/spending").json()
    assert s["spent"] == 560 and s["items"][0]["date"] == TODAY.isoformat() and s["items"][0]["source"].startswith("previsto de")
    assert c.get("/api/spending", params={"month": prev}).json()["spent"] == 0
    c.put(f"/api/planned/{p['id']}/occurrence", json={"month": prev, "paid": False})  # desmarcar: volta a faltar pagar
    s = c.get("/api/spending").json()
    assert s["spent"] == 0 and s["to_pay"] == 560
