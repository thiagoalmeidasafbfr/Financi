"""Compromissos: mês cheio por tipo (fixas, parcelas, pontuais, variável), renda, grupos e alívios."""
from datetime import date

import pytest

from app.finance import add_months, month_start
from tests.conftest import cat_id

TODAY = month_start(date.today())  # noqa: DTZ011


def ym(k: int) -> str:
    return add_months(TODAY, k).isoformat()


def test_commitments_by_kind_and_reliefs(client):
    c = client
    plan = lambda **kw: c.post("/api/planned", json={"kind": "despesa", "recurrence": "mensal", **kw})  # noqa: E731
    plan(name="Salário", kind="receita", amount=8000, start_month=ym(0))
    plan(name="Aluguel", amount=2500, start_month=ym(0), category_id=cat_id(c, "Aluguel"))
    plan(name="Seguro", amount=300, start_month=ym(0), end_month=ym(2))                     # termina: alívio em ym(3)
    plan(name="IPVA", amount=1200, recurrence="pontual", start_month=ym(1))
    card = {x["name"]: x for x in c.get("/api/categories").json()}["Fatura de cartão"]["id"]
    plan(name="Carrefour", amount=800, start_month=ym(0), end_month=ym(1), category_id=card)  # cai para 200
    plan(name="Carrefour", amount=200, start_month=ym(2), end_month=ym(4), category_id=card)
    first_due = add_months(TODAY, -9).replace(day=5).isoformat()
    did = c.post("/api/debts", json={"name": "Consignado", "kind": "consignado", "installment": 400, "monthly_rate": 0.03,
                                     "first_due": first_due, "total_installments": 12}).json()["id"]  # última parcela em ym(2)
    c.put("/api/budgets", json=[{"category_id": cat_id(c, "Supermercado"), "month": None, "amount": 900}])

    r = c.get("/api/commitments", params={"months": 6}).json()
    m = r["months"]
    assert [x["month"] for x in m] == [ym(k) for k in range(6)]
    assert (m[0]["fixas"], m[0]["parcelas"], m[0]["pontuais"], m[0]["variavel"]) == (2800, 1200, 0, 900)
    assert m[1]["pontuais"] == 1200 and m[2]["parcelas"] == 600 and m[3]["parcelas"] == 200 and m[3]["fixas"] == 2500
    assert m[0]["committed"] == 4000 and m[0]["income"] == 8000 and m[0]["pct"] == pytest.approx(0.5)
    assert m[0]["margin"] == 8000 - 4000 - 900

    groups = {g["group"]: g for g in r["groups"]}
    assert groups["Cartões"]["values"][:6] == [800, 800, 200, 200, 200, 0] and groups["Cartões"]["kinds"] == ["parcelas"]
    assert {it["ref"] for it in groups["Dívidas e parcelas"]["items"]} == {f"debt:{did}"}

    rel = {(x["label"], x["from_month"]): x for x in r["reliefs"]}
    assert rel[("Carrefour", ym(2))]["amount"] == 600 and not rel[("Carrefour", ym(2))]["ends"]
    assert rel[("Seguro", ym(3))]["ends"] and rel[("Consignado", ym(3))]["detail"] == "última parcela 12/12"
    assert rel[("Carrefour", ym(5))]["ends"]
    assert ("IPVA", ym(2)) not in rel  # pontual não é alívio
    assert [x["from_month"] for x in r["reliefs"]] == sorted(x["from_month"] for x in r["reliefs"])

    # quitação ligada no Cockpit: o consignado termina antes, e o alívio diz "quitação"
    c.put(f"/api/cockpit/payoffs/{did}", json={"active": True, "month": ym(1)})
    r = c.get("/api/commitments", params={"months": 6}).json()
    q = next(x for x in r["reliefs"] if x["label"] == "Consignado")
    assert q["from_month"] == ym(2) and q["detail"].startswith("quitação em")
