"""Editar um valor da tabela mês a mês: só no mês, ou do mês em diante (dividindo a previsão), sem mexer nas outras."""
from datetime import date

from app.finance import add_months, month_start

TODAY = month_start(date.today())  # noqa: DTZ011


def ym(k: int) -> str:
    return add_months(TODAY, k).isoformat()


def row(client, label, months=10):
    t = client.get("/api/projection", params={"months": months, "detail": True}).json()["table"]
    for s in t["sections"]:
        for g in s["groups"]:
            for r in g["rows"]:
                if r["label"] == label:
                    return r["values"]
    return [0.0] * months


def edit(client, name, k, amount, scope="mes"):
    return client.post("/api/planned/edit-month", json={"name": name, "month": ym(k), "amount": amount, "scope": scope})


def test_edit_one_month_and_from_here(client):
    c = client
    c.post("/api/planned", json={"name": "Salário", "kind": "receita", "amount": 8000, "recurrence": "mensal",
                                 "start_month": ym(1), "end_month": ym(6)})
    c.post("/api/planned", json={"name": "Salário", "kind": "receita", "amount": 9000, "recurrence": "mensal", "start_month": ym(7)})
    assert row(c, "Salário") == [8000] * 6 + [9000] * 4

    assert edit(c, "Salário", 3, 7000).status_code == 200                 # só em ym(3)
    assert row(c, "Salário") == [8000, 8000, 7000, 8000, 8000, 8000] + [9000] * 4
    info = c.get("/api/planned/month-info", params={"name": "salario", "month": ym(4)}).json()
    assert info["series"]["end_month"] == ym(6) and info["can_forward"] and info["occurrence"]["amount"] == 8000

    assert edit(c, "Salário", 4, 8500, "diante").status_code == 200       # de ym(4) até o fim desta previsão
    assert row(c, "Salário") == [8000, 8000, 7000, 8500, 8500, 8500] + [9000] * 4
    assert len([p for p in c.get("/api/planned").json() if p["name"] == "Salário"]) == 3

    edit(c, "Salário", 5, 0)                                              # zerar um mês = pular
    assert row(c, "Salário")[3:6] == [8500, 0, 8500]
    edit(c, "Salário", 6, 0, "diante")                                    # zerar daqui em diante = a previsão termina
    assert row(c, "Salário") == [8000, 8000, 7000, 8500, 0, 0] + [9000] * 4
    edit(c, "Salário", 5, 8600)                                           # mês sem ocorrência: vira previsto pontual
    assert row(c, "Salário")[4] == 8600


def test_empty_cell_and_overlap_guard(client):
    c = client
    c.post("/api/planned", json={"name": "Bônus", "kind": "receita", "amount": 3000, "recurrence": "pontual", "start_month": ym(4)})
    r = edit(c, "Bônus", 2, 1000, "diante")
    assert r.status_code == 400 and "depois" in r.json()["detail"]        # criaria série por cima do bônus de ym(4)
    assert not c.get("/api/planned/month-info", params={"name": "Bônus", "month": ym(2)}).json()["can_forward"]
    assert edit(c, "Bônus", 6, 500, "diante").status_code == 200          # depois do último: série nova todo mês
    assert row(c, "Bônus") == [0, 0, 0, 3000, 0, 500, 500, 500, 500, 500]
    edit(c, "Bônus", 4, 0)                                                # zerar a pontual apaga
    assert row(c, "Bônus")[3] == 0
    assert edit(c, "Não existe", 2, 10).status_code == 404
