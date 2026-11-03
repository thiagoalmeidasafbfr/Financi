"""Planilha de planejamento: modelo, importação das quatro abas e reimportação sem duplicar."""
import io
from datetime import date, datetime

import pytest
from openpyxl import load_workbook

from app.finance import add_months, month_start
from app.planilha import parse_month, parse_rate

TODAY = month_start(date.today())  # noqa: DTZ011


def ym(k: int) -> str:
    return add_months(TODAY, k).isoformat()[:7]


def filled_template(client) -> bytes:
    r = client.get("/api/imports/modelo")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
    wb = load_workbook(io.BytesIO(r.content))
    assert {"Leia-me", "Previstos", "Atrasos", "Dívidas", "Orçamento"} <= set(wb.sheetnames)
    assert wb["Previstos"].data_validations.dataValidation, "listas de escolha no modelo"
    pv = wb["Previstos"]
    pv.append(["Salário", "Receita", "Salário", 8167, "Todo mês", ym(1), ym(12), 5, "Thiago", "SALARIO"])
    pv.append(["Salário", "Receita", "Salário", "9.600,00", "Todo mês", ym(13), None, 5, "Thiago", None])
    pv.append(["Aluguel", "Despesa", "Aluguel", 1300, "Todo mês", ym(1), None, 10, None, "ALUGUEL"])
    ipva_date = datetime(TODAY.year + 1, 1, 15)  # noqa: DTZ001  (datas do Excel não têm fuso)
    pv.append(["IPVA", "Despesa", "Impostos", 2400, "Uma vez", ipva_date, None, None, None, None])
    pv.append(["Seguros", "Despesa", "Seguros diversos", 585, "Todo mês", ym(1), ym(9), None, None, None])  # categoria nova
    pv.append(["Sem valor", "Despesa", "Outros gastos", None, "Todo mês", ym(1), None, None, None, None])     # aviso
    wb["Atrasos"].append(["Condomínio", "Condomínio", 560, ym(-1), 10, None])
    wb["Dívidas"].append(["PAN 015435447", "Consignado", "PAN", 364.89, "4,39", f"{ym(-1)}-05", None, ym(9), None, None, "PAN"])
    wb["Dívidas"].append(["Acordo loja", "Acordo", "Loja", 200, None, None, None, None, 1200, "Monique", None])
    wb["Orçamento"].append(["Supermercado", 1000, None])
    wb["Orçamento"].append(["Supermercado", 700, ym(1)])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def send(client, content, replace=True):
    return client.post("/api/imports/planilha", files={"file": ("plano.xlsx", content)}, data={"replace": str(replace).lower()})


def test_import_template_end_to_end(client):
    content = filled_template(client)
    r = send(client, content)
    assert r.status_code == 200, r.text
    res = r.json()
    assert (res["previstos"], res["atrasos"], res["dividas"], res["orcamento"]) == (5, 1, 2, 2)
    assert sorted(res["pessoas_criadas"]) == ["Monique", "Thiago"] and res["categorias_criadas"] == ["Seguros diversos"]
    assert any("Previstos, linha 8" in a for a in res["avisos"])  # linha sem valor

    planned = client.get("/api/planned").json()
    sal = sorted((p for p in planned if p["name"] == "Salário"), key=lambda p: p["start_month"])
    assert [p["amount"] for p in sal] == [8167, 9600] and sal[0]["end_month"] == f"{ym(12)}-01" and sal[1]["end_month"] is None
    ipva = next(p for p in planned if p["name"] == "IPVA")
    assert ipva["recurrence"] == "pontual" and ipva["start_month"] == f"{TODAY.year + 1}-01-01"

    flow = client.get("/api/planned/flow", params={"months": 3}).json()
    assert [o["name"] for o in flow["overdue"]] == ["Condomínio"]

    debts = {d["name"]: d for d in client.get("/api/debts").json()}
    pan = debts["PAN 015435447"]
    assert pan["kind"] == "consignado" and pan["total_installments"] == 11 and pan["monthly_rate"] == pytest.approx(0.0439)
    assert debts["Acordo loja"]["balance"] == 1200

    # sem extratos, o comprometimento usa a renda prevista do mês (o salário começa no mês seguinte: ainda sem renda)
    assert client.get("/api/debts/overview").json()["totals"]["comprometimento"] is None

    budgets = {(b["category_id"], b["month"]): b["amount"] for b in client.get("/api/budgets").json()}
    assert sorted(budgets.values()) == [700, 1000]

    # reimportar substitui o que veio da planilha (não duplica)
    again = send(client, content).json()
    assert again["substituidos"] == 8
    assert len(client.get("/api/planned").json()) == 6 and len(client.get("/api/debts").json()) == 2


def test_import_rejects_other_files(client):
    assert send(client, b"isto nao e xlsx").status_code == 400


def test_month_and_rate_parsing():
    assert parse_month("2026-11") == parse_month("11/2026") == parse_month("nov/26") == parse_month("novembro de 2026") == date(2026, 11, 1)
    assert parse_month(datetime(2026, 11, 20)) == date(2026, 11, 1) and parse_month("") is None  # noqa: DTZ001
    assert parse_rate("4,39") == pytest.approx(0.0439) and parse_rate(0.0249) == pytest.approx(0.0249)
    with pytest.raises(ValueError):
        parse_month("amanhã")
