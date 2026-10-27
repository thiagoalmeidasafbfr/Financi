from sqlalchemy import delete

from app.db import SessionLocal
from app.models import Category
from app.services import seed_categories


def make_scenario(client, name="Base"):
    return client.post("/api/scenarios", json={"name": name, "start_month": "2026-11-01", "months": 12}).json()


def test_arrear_crud_plan_and_projection(client):
    sc = make_scenario(client)
    base = f"/api/scenarios/{sc['id']}/arrears"
    body = {"description": "Aluguel", "creditor": "Imobiliária", "amount": 1300,
            "due_date": "2026-09-10", "fine_pct": 0.02, "interest_monthly": 0.01}
    a = client.post(base, json=body).json()
    r = client.get(base, params={"today": "2026-11-20"}).json()
    item = r["items"][0]
    assert item["months_late"] == 2
    assert round(item["updated_value"], 2) == round(1300 * 1.02 + 1300 * 0.02, 2)
    assert r["totals"]["sem_plano"] == item["updated_value"]

    client.put(f"{base}/{a['id']}", json={**body, "plan_start": "2026-12-15", "plan_installments": 2})
    p = client.get(f"/api/scenarios/{sc['id']}/projection").json()
    row = next(x for x in p["rows"] if x["kind"] == "atrasos")
    assert row["values"][0] == 0 and row["values"][1] == row["values"][2] > 0
    assert round(sum(row["values"]), 2) == round(1300 * 1.02 + 1300 * 0.03, 2)  # juros até dez/26

    # pago: sai do fluxo e ganha data de pagamento
    paid = client.put(f"{base}/{a['id']}", json={**body, "status": "pago", "plan_start": "2026-12-01"}).json()
    assert paid["paid_date"]
    assert client.get(f"/api/scenarios/{sc['id']}/projection").json()["kpis"]["total_atrasos_pagos"] == 0

    assert client.delete(f"{base}/{a['id']}").status_code == 204
    assert client.get(base).json()["items"] == []


def test_duplicated_scenario_has_independent_arrears(client):
    """Duplicar e excluir um atraso na cópia não pode apagar do original."""
    sc = make_scenario(client)
    base = f"/api/scenarios/{sc['id']}/arrears"
    a = client.post(base, json={"description": "Aluguel", "amount": 1300, "plan_start": "2027-01-01",
                                "plan_installments": 3}).json()
    dup = client.post(f"/api/scenarios/{sc['id']}/duplicate", params={"name": "Cópia"}).json()
    dup_base = f"/api/scenarios/{dup['id']}/arrears"
    copy = client.get(dup_base).json()["items"]
    assert len(copy) == 1 and copy[0]["id"] != a["id"] and copy[0]["plan_installments"] == 3

    assert client.delete(f"{dup_base}/{copy[0]['id']}").status_code == 204
    assert client.get(dup_base).json()["items"] == []
    assert len(client.get(base).json()["items"]) == 1
    p = client.get(f"/api/scenarios/{sc['id']}/projection").json()
    assert round(p["kpis"]["total_atrasos_pagos"], 2) == 1300
    # o id de um cenário não serve no outro
    assert client.delete(f"{dup_base}/{a['id']}").status_code == 404


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
