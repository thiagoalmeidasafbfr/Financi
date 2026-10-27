from sqlalchemy import delete

from app.db import SessionLocal
from app.models import Category
from app.services import seed_categories


def make_scenario(client, name="Base"):
    return client.post("/api/scenarios", json={"name": name, "start_month": "2026-11-01", "months": 12}).json()


def test_arrear_crud_plan_and_projection(client):
    sc = make_scenario(client)
    a = client.post("/api/arrears", json={"description": "Aluguel", "creditor": "Imobiliária", "amount": 1300,
                                          "due_date": "2026-09-10", "fine_pct": 0.02, "interest_monthly": 0.01}).json()
    r = client.get("/api/arrears", params={"scenario_id": sc["id"], "today": "2026-11-20"}).json()
    item = r["items"][0]
    assert item["months_late"] == 2
    assert round(item["updated_value"], 2) == round(1300 * 1.02 + 1300 * 0.02, 2)
    assert r["totals"]["sem_plano"] == item["updated_value"]

    client.put(f"/api/scenarios/{sc['id']}/arrear-plans",
               json=[{"arrear_id": a["id"], "start_month": "2026-12-01", "installments": 2}])
    p = client.get(f"/api/scenarios/{sc['id']}/projection").json()
    row = next(x for x in p["rows"] if x["kind"] == "atrasos")
    assert row["values"][0] == 0 and row["values"][1] == row["values"][2] > 0
    assert round(sum(row["values"]), 2) == round(1300 * 1.02 + 1300 * 0.03, 2)  # juros até dez/26

    # plano é copiado ao duplicar o cenário
    dup = client.post(f"/api/scenarios/{sc['id']}/duplicate", params={"name": "Cópia"}).json()
    p2 = client.get(f"/api/scenarios/{dup['id']}/projection").json()
    assert p2["kpis"]["total_atrasos_pagos"] == p["kpis"]["total_atrasos_pagos"]

    # pago: sai do fluxo e ganha data de pagamento
    body = {**{k: a[k] for k in ("description", "creditor", "amount", "due_date", "fine_pct", "interest_monthly")},
            "status": "pago"}
    paid = client.put(f"/api/arrears/{a['id']}", json=body).json()
    assert paid["paid_date"]
    p = client.get(f"/api/scenarios/{sc['id']}/projection").json()
    assert p["kpis"]["total_atrasos_pagos"] == 0

    client.put(f"/api/scenarios/{sc['id']}/arrear-plans", json=[{"arrear_id": a["id"], "start_month": None}])
    assert client.delete(f"/api/arrears/{a['id']}").status_code == 204
    assert client.get("/api/arrears").json()["items"] == []


def test_new_line_and_duplicate_name(client):
    sc = make_scenario(client)
    cat = client.post("/api/categories", json={"name": "Babá", "group": "despesa_fixa"}).json()
    client.put(f"/api/scenarios/{sc['id']}/entries", json=[{"category_id": cat["id"], "month": "2026-11-01", "amount": 900}])
    p = client.get(f"/api/scenarios/{sc['id']}/projection").json()
    assert p["series"]["despesas_fixas"][0] == 900
    assert client.post("/api/categories", json={"name": "Babá", "group": "despesa_fixa"}).status_code == 409


def test_seed_adds_new_calculated_lines_to_existing_database(client):
    with SessionLocal() as db:
        db.execute(delete(Category).where(Category.kind == "atrasos"))
        db.commit()
        seed_categories(db)
        assert db.query(Category).filter(Category.kind == "atrasos").count() == 1
        seed_categories(db)
        assert db.query(Category).filter(Category.kind == "atrasos").count() == 1
