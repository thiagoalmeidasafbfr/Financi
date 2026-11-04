"""Saldo acumulado na visão Mês: igual ao do Fluxo nos meses futuros, encadeado, e realizado nos meses passados."""
from datetime import date

from app.finance import add_months, month_start

TODAY = month_start(date.today())  # noqa: DTZ011


def ym(k: int) -> str:
    return add_months(TODAY, k).isoformat()


def test_month_balance_matches_flow(client):
    c = client
    acc = c.post("/api/accounts", json={"name": "Conta", "opening_balance": 1000}).json()["id"]
    c.post("/api/transactions", json={"account_id": acc, "date": add_months(TODAY, -1).isoformat(), "amount": 500, "description": "Pix"})
    c.post("/api/transactions", json={"account_id": acc, "date": TODAY.isoformat(), "amount": -200, "description": "Mercado"})
    c.post("/api/planned", json={"name": "Salário", "kind": "receita", "amount": 8000, "recurrence": "mensal", "start_month": ym(1)})
    c.post("/api/planned", json={"name": "Aluguel", "kind": "despesa", "amount": 2500, "recurrence": "mensal", "start_month": ym(1)})
    table = c.get("/api/projection", params={"months": 6, "detail": True}).json()["table"]
    acc_row = table["totais"]["acumulado"]

    now = c.get("/api/plan", params={"month": ym(0)}).json()["acumulado"]
    assert now["kind"] == "previsto" and now["start"] == 1300 and now["end"] == acc_row["now"]
    prev_end = now["end"]
    for k in range(1, 6):
        a = c.get("/api/plan", params={"month": ym(k)}).json()["acumulado"]
        assert a["end"] == acc_row["values"][k - 1] and a["start"] == prev_end
        prev_end = a["end"]

    past = c.get("/api/plan", params={"month": ym(-1)}).json()["acumulado"]
    assert past == {"kind": "realizado", "start": 1000, "end": 1500}  # sem o mercado deste mês
