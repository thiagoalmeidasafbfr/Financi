"""Banco criado pela versão anterior (consignados e atrasos compartilhados) migra para cópias por cenário."""
from sqlalchemy import inspect, text

from app.db import engine
from app.migrations import init_db


def test_legacy_shared_tables_are_copied_into_each_scenario(client):
    sid = [client.post("/api/scenarios", json={"name": n, "start_month": "2026-11-01", "months": 12}).json()["id"]
           for n in ("A", "B")]
    with engine.begin() as conn:
        conn.execute(text("""create table loan_contracts (id integer primary key, name varchar(120) unique,
            creditor varchar(120), monthly_rate numeric(12,6), installment numeric(14,2), first_month date,
            last_month date, notes text)"""))
        conn.execute(text("""create table loan_payoffs (id integer primary key, scenario_id integer,
            contract_id integer references loan_contracts(id), payoff_month date)"""))
        conn.execute(text("""create table arrears (id integer primary key, description varchar(160),
            creditor varchar(120), owner varchar(80), category_id integer, due_date date, amount numeric(14,2),
            fine_pct numeric(12,6), interest_monthly numeric(12,6), negotiated_amount numeric(14,2),
            status varchar(20), paid_date date, notes text)"""))
        conn.execute(text("""create table arrear_plans (id integer primary key, scenario_id integer,
            arrear_id integer references arrears(id), start_month date, installments integer)"""))
        conn.execute(text("insert into loan_contracts values (1, 'PAN', 'PAN', 0.0439, 364.89, '2026-10-01', "
                          "'2027-08-01', null)"))
        conn.execute(text(f"insert into loan_payoffs values (1, {sid[0]}, 1, '2027-02-01')"))
        conn.execute(text("insert into arrears values (1, 'Aluguel', null, null, null, '2026-10-01', 1300, 0, 0, "
                          "null, 'aberto', null, null)"))
        conn.execute(text(f"insert into arrear_plans values (1, {sid[1]}, 1, '2027-01-01', 3)"))

    done = init_db()
    assert len(done) == 2
    tables = set(inspect(engine).get_table_names())
    assert not {"loan_contracts", "loan_payoffs", "arrears", "arrear_plans"} & tables

    a_loans = client.get(f"/api/scenarios/{sid[0]}/contracts").json()
    b_loans = client.get(f"/api/scenarios/{sid[1]}/contracts").json()
    assert [c["payoff_month"] for c in a_loans] == ["2027-02-01"]
    assert [c["payoff_month"] for c in b_loans] == [None]
    a_arr = client.get(f"/api/scenarios/{sid[0]}/arrears").json()["items"]
    b_arr = client.get(f"/api/scenarios/{sid[1]}/arrears").json()["items"]
    assert (a_arr[0]["plan_start"], b_arr[0]["plan_start"], b_arr[0]["plan_installments"]) == (None, "2027-01-01", 3)
    assert init_db() == []  # idempotente
