"""Cockpit: ações ligadas mudam o fluxo (ajustes com frações de previstos, substituições e quitação de dívidas)."""
from datetime import date

import pytest

from app import cockpit
from app.finance import add_months, month_start
from app.models import Debt

TODAY = month_start(date.today())  # noqa: DTZ011


def ym(k: int) -> str:
    return add_months(TODAY, k).isoformat()


def saldo(client, months=12, detail=False):
    return client.get("/api/projection", params={"months": months, "detail": detail}).json()


@pytest.fixture()
def salary(client):
    client.post("/api/planned", json={"name": "Salário", "kind": "receita", "amount": 8000, "recurrence": "mensal",
                                      "start_month": ym(0), "due_day": 5})
    return client


FERIAS = {"name": "Antecipação de férias", "lines": [
    {"month": ym(1), "label": "Salário adiantado", "op": "somar", "direction": "entrada", "factor": 1, "base": "Salário"},
    {"month": ym(1), "label": "1/3 de férias", "op": "somar", "direction": "entrada", "factor": 1 / 3, "base": "Salário"},
    {"month": ym(2), "label": "Só os 10 dias trabalhados", "op": "substituir", "target": "Salário", "factor": 1 / 3,
     "base": "Salário", "base_month": ym(1)},
    {"month": ym(3), "label": "Viagem", "op": "somar", "direction": "saida", "amount": 1500},
]}


def test_adjustment_only_counts_when_on(salary):
    c = salary
    base = saldo(c)["months"]
    aid = c.post("/api/cockpit/actions", json=FERIAS).json()["id"]
    assert saldo(c)["months"] == base  # desligada: nada muda
    ov = c.get("/api/cockpit").json()
    act = ov["actions"][0]
    assert [ln["value"] for ln in act["lines"]] == [8000, 2666.67, 2666.67, 1500]
    assert act["impact"]["total"] == pytest.approx(8000 + 2666.67 - 5333.33 - 1500)
    assert ov["summary"]["final_with"] == ov["summary"]["final_base"]

    c.patch(f"/api/cockpit/actions/{aid}", json={"active": True})
    p = saldo(c, detail=True)
    deltas = [round(a["saldo"] - b["saldo"], 2) for a, b in zip(p["months"], base, strict=True)]
    assert deltas[:4] == [10666.67, 5333.34, 3833.34, 3833.34]
    # na tabela: linhas do cockpit e o salário substituído no mês
    rows = {r["label"]: r for s in p["table"]["sections"] for g in s["groups"] for r in g["rows"]}
    assert rows["1/3 de férias"]["values"][0] == 2666.67 and rows["Salário"]["values"][1] == 2666.67
    groups = {g["group"] for s in p["table"]["sections"] for g in s["groups"]}
    assert "Cockpit · Antecipação de férias" in groups
    # plano do mês também
    m2 = c.get("/api/plan", params={"month": ym(2)}).json()
    assert [r["amount"] for r in m2["sections"]["entradas"]["items"] if r["name"] == "Salário"] == [2666.67]
    m1 = c.get("/api/plan", params={"month": ym(1)}).json()
    assert {r["name"] for r in m1["sections"]["entradas"]["items"] if r["type"] == "acao"} == {"Salário adiantado", "1/3 de férias"}
    ov = c.get("/api/cockpit").json()
    assert ov["summary"]["final_with"] - ov["summary"]["final_base"] == pytest.approx(3833.34, abs=0.01)

    # referência que não existe aparece como problema e não entra
    bad = {**FERIAS, "name": "Errada", "lines": [{"month": ym(1), "label": "x", "op": "substituir", "target": "Bônus", "amount": 0}]}
    bid = c.post("/api/cockpit/actions", json=bad).json()["id"]
    errada = next(a for a in c.get("/api/cockpit").json()["actions"] if a["id"] == bid)
    assert "não existe" in errada["lines"][0]["problem"] and errada["impact"]["total"] == 0
    assert c.post("/api/cockpit/actions", json={"name": "Sem valor", "lines": [{"month": ym(1), "label": "y"}]}).status_code == 400
    assert c.delete(f"/api/cockpit/actions/{aid}").status_code == 204
    assert saldo(c)["months"] == base


def test_payoff_per_debt(salary):
    c = salary
    first_due = add_months(TODAY, -2).replace(day=5).isoformat()
    did = c.post("/api/debts", json={"name": "PARATI 1", "kind": "consignado", "installment": 300, "monthly_rate": 0.02,
                                     "first_due": first_due, "total_installments": 12}).json()["id"]
    base = saldo(c)["months"]
    ov = c.get("/api/cockpit").json()
    po = ov["payoffs"][0]
    assert po["debt_id"] == did and po["active"] is False and po["date"] > date.today().isoformat()  # noqa: DTZ011  (próximo vencimento)

    def pv(on: date, months: range) -> float:  # cada parcela a valor presente pelos dias corridos até o vencimento
        return sum(300 / 1.02 ** ((date.fromisoformat(ym(k)).replace(day=5) - on).days / 30) for k in months)

    # quitar no vencimento da parcela de ym(3): ela entra cheia, as seguintes descontadas
    due3 = date.fromisoformat(ym(3)).replace(day=5)
    r = c.put(f"/api/cockpit/payoffs/{did}", json={"active": True, "month": ym(3)})
    assert r.json()["date"] == due3.isoformat()
    po = c.get("/api/cockpit").json()["payoffs"][0]
    value = pv(due3, range(3, 10))
    assert po["payoff"] == pytest.approx(value, abs=0.01) and po["avoided"] == 2100 and po["installments_left"] == 7
    assert po["interest_saved"] == pytest.approx(2100 - value, abs=0.01)
    p = saldo(c)["months"]
    debts = [r["dividas"] for r in p]
    assert debts[2] == pytest.approx(value, abs=0.01) and debts[3:] == [0] * 9 and debts[:2] == [300, 300]
    assert p[-1]["saldo"] - base[-1]["saldo"] == pytest.approx(2100 - value, abs=0.01)

    # quitar no dia 20: a parcela do dia 5 desse mês é paga normalmente; quita as 6 seguintes, descontadas desde o dia 20
    day20 = due3.replace(day=20)
    c.put(f"/api/cockpit/payoffs/{did}", json={"active": True, "date": day20.isoformat()})
    v20 = pv(day20, range(4, 10))
    info = c.get(f"/api/cockpit/payoffs/{did}").json()
    assert info["set_date"] == day20.isoformat() and info["payoff"] == pytest.approx(v20, abs=0.01) and info["installments_left"] == 6
    debts = [r["dividas"] for r in saldo(c)["months"]]
    assert debts[2] == pytest.approx(300 + v20, abs=0.01) and debts[3:] == [0] * 9
    # simular outra data sem mudar a marcada
    prev = c.get(f"/api/cockpit/payoffs/{did}", params={"on": due3.replace(day=10).isoformat()}).json()
    assert prev["payoff"] == pytest.approx(pv(due3.replace(day=10), range(4, 10)), abs=0.01) and prev["set_date"] == day20.isoformat()
    # dívidas: valor da quitação na data marcada
    ov_d = next(x for x in c.get("/api/debts/overview").json()["debts"] if x["id"] == did)
    assert ov_d["payoff_date"] == day20.isoformat() and ov_d["payoff_at_date"] == pytest.approx(v20, abs=0.01)
    c.put(f"/api/cockpit/payoffs/{did}", json={"active": True, "month": ym(3)})
    # plano do mês mostra a quitação
    m3 = c.get("/api/plan", params={"month": ym(3)}).json()
    assert [r["name"] for r in m3["sections"]["dividas"]["items"]] == ["PARATI 1 · quitação"]
    assert c.get("/api/plan", params={"month": ym(4)}).json()["sections"]["dividas"]["items"] == []
    c.put(f"/api/cockpit/payoffs/{did}", json={"active": False})
    assert saldo(c)["months"] == base
    assert c.put("/api/cockpit/payoffs/999", json={"active": True}).status_code == 404


def test_payoff_value_before_and_after_due_day():
    d = Debt(id=1, name="x", installment=100, monthly_rate=0.0, first_due=date(2026, 1, 5), total_installments=10)
    assert cockpit.payoff_value(d, date(2026, 3, 1), date(2026, 3, 2)) == 800   # parcela de março ainda não saiu
    assert cockpit.payoff_value(d, date(2026, 3, 1), date(2026, 3, 10)) == 700  # já saiu: só as seguintes
    assert cockpit.payoff_value(d, date(2027, 1, 1), date(2026, 3, 10)) == 0    # depois do fim


def test_grouping_with_cockpit_row(salary):
    """Agrupamento pode incluir a linha de uma ação do cockpit (antes dava "Linha inválida: acao:1")."""
    c = salary
    aid = c.post("/api/cockpit/actions", json={**FERIAS, "active": True}).json()["id"]
    r = c.post("/api/groupings", json={"name": "Folha", "refs": ["plan:Salário", f"acao:{aid}"]})
    assert r.status_code in (200, 201), r.text
    g = c.get("/api/projection", params={"months": 4, "detail": True}).json()["table"]["groupings"][0]
    assert g["values"][0] == pytest.approx(8000 + 8000 + 2666.67)  # salário + as duas entradas da ação em ym(1)


def test_payoff_concurrent_create(salary, monkeypatch):
    """Dois pedidos que criam a mesma quitação ao mesmo tempo: o segundo atualiza a criada (antes: erro 500)."""
    from sqlalchemy.orm import Session

    from app.models import Action

    c = salary
    first_due = add_months(TODAY, -2).replace(day=5).isoformat()
    did = c.post("/api/debts", json={"name": "D", "kind": "consignado", "installment": 100, "monthly_rate": 0.02,
                                     "first_due": first_due, "total_installments": 12}).json()["id"]
    real = Session.scalar
    calls = {"n": 0}

    def racing(self, stmt, *a, **kw):  # 1ª busca não acha nada, como se o outro pedido ainda não tivesse gravado
        if "fin_actions" in str(stmt) and calls["n"] == 0:
            calls["n"] += 1
            self.add(Action(name="outro pedido", kind="quitacao", debt_id=did, active=False, month=date.fromisoformat(ym(1))))
            self.flush()
            self.commit()
            return None
        return real(self, stmt, *a, **kw)

    monkeypatch.setattr(Session, "scalar", racing)
    r = c.put(f"/api/cockpit/payoffs/{did}", json={"active": True, "month": ym(3)})
    monkeypatch.setattr(Session, "scalar", real)
    assert r.status_code == 200 and r.json()["active"] is True and r.json()["month"] == ym(3)
