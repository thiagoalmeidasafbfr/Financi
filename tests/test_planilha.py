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


def send(client, content, modo="adicionar", secoes=""):
    return client.post("/api/imports/planilha", files={"file": ("plano.xlsx", content)}, data={"modo": modo, "secoes": secoes})


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

    # adicionar de novo o mesmo arquivo não duplica (o que já existe igual é ignorado)
    again = send(client, content).json()
    assert again["ignorados"] == 8 and again["previstos"] == 0 and again["dividas"] == 0
    assert len(client.get("/api/planned").json()) == 6 and len(client.get("/api/debts").json()) == 2
    # substituir apaga as seções que a planilha traz (inclusive o cadastrado no app) e importa de novo
    client.post("/api/debts", json={"name": "Cadastrada à mão", "kind": "outro", "installment": 10})
    sub = send(client, content, modo="substituir").json()
    assert sub["apagados"]["dividas"] == 3 and sub["dividas"] == 2
    assert {d["name"] for d in client.get("/api/debts").json()} == {"PAN 015435447", "Acordo loja"}
    assert len(client.get("/api/planned").json()) == 6


def test_import_by_section(client):
    """Só a seção escolhida entra; numa planilha só com dívidas, substituir não apaga as outras seções."""
    content = filled_template(client)
    r = send(client, content, secoes="receitas").json()
    assert (r["previstos"], r["atrasos"], r["dividas"], r["orcamento"]) == (2, 0, 0, 0) and r["secoes"] == ["receitas"]
    assert {p["kind"] for p in client.get("/api/planned").json()} == {"receita"}
    send(client, content)  # o resto, adicionando
    # planilha só com dívidas, todas as seções marcadas, modo substituir: só Dívidas é trocada
    wb = load_workbook(io.BytesIO(client.get("/api/imports/modelo").content))
    wb["Dívidas"].append(["QI 0365695504", "Consignado", "QI", 199.96, "3,99", "2026-07-05", 48, None, None, None, None])
    buf = io.BytesIO()
    wb.save(buf)
    only = send(client, buf.getvalue(), modo="substituir").json()
    assert only["secoes"] == ["dividas"] and only["apagados"] == {"dividas": 2}
    assert [d["name"] for d in client.get("/api/debts").json()] == ["QI 0365695504"]
    assert len(client.get("/api/planned").json()) == 6  # previstos intactos
    assert send(client, content, modo="qualquer").status_code == 400


def test_import_rejects_other_files(client):
    assert send(client, b"isto nao e xlsx").status_code == 400


def test_month_and_rate_parsing():
    assert parse_month("2026-11") == parse_month("11/2026") == parse_month("nov/26") == parse_month("novembro de 2026") == date(2026, 11, 1)
    assert parse_month(datetime(2026, 11, 20)) == date(2026, 11, 1) and parse_month("") is None  # noqa: DTZ001
    assert parse_rate("4,39") == pytest.approx(0.0439) and parse_rate(0.0249) == pytest.approx(0.0249)
    with pytest.raises(ValueError):
        parse_month("amanhã")


def test_cards_sheet_separate_from_debts(client):
    """Aba Cartões: faturas previstas por cartão, numa seção própria; o cartão cadastrado antes como dívida sai dali em diante."""
    c = client
    cats = {x["name"]: x for x in c.get("/api/categories").json()}
    emp = cats["Parcela de empréstimo"]["id"]
    # como veio da planilha antiga: Carrefour e Picpay como parcela de empréstimo, e um atraso de outubro
    def prev(name, amount, start, end=None, rec="pontual"):
        r = c.post("/api/planned", json={"name": name, "kind": "despesa", "amount": amount, "recurrence": rec, "start_month": f"{start}-01",
                                         "end_month": f"{end}-01" if end else None, "category_id": emp})
        assert r.status_code == 201, r.text
    prev("Carrefour", 1058.34, ym(0))
    prev("Carrefour", 889.05, ym(1), ym(2), "mensal")
    prev("Picpay", 1000, ym(0))
    prev("Carrefour", 700, ym(-1))
    c.post("/api/planned", json={"name": "Aluguel", "kind": "despesa", "amount": 2500, "recurrence": "mensal", "start_month": f"{ym(0)}-01"})

    wb = load_workbook(io.BytesIO(c.get("/api/imports/modelo").content))
    assert "Cartões" in wb.sheetnames
    ws = wb["Cartões"]
    ws.append(["C6", 230, ym(0)[:7], ym(9)[:7], None, None, "parcelamento"])
    ws.append(["Carrefour", "828,34", ym(0)[:7], None, 20, None, "Jim.com 8/10 …"])
    ws.append(["Carrefour", 659.05, ym(1)[:7], ym(2)[:7], 20])
    ws.append(["Carrefour", 217.23, ym(3)[:7], ym(7)[:7], 20])
    ws.append(["PicPay", 1000, ym(0)[:7]])
    ws.append(["PicPay", 1400, ym(1)[:7]])
    buf = io.BytesIO()
    wb.save(buf)
    r = send(c, buf.getvalue(), modo="substituir", secoes="cartoes").json()
    assert r["secoes"] == ["cartoes"] and r["cartoes"] == 6 and r["apagados"]["cartoes_antigos"] == 3
    again = send(c, buf.getvalue(), modo="substituir", secoes="cartoes").json()  # importar de novo não duplica nem apaga o atraso
    assert again["cartoes"] == 6 and again["apagados"]["cartoes"] == 6

    planned = c.get("/api/planned").json()
    card_cat = {x["name"]: x for x in c.get("/api/categories").json()}["Fatura de cartão"]
    assert card_cat["group"] == "Cartões"
    assert not [p for p in planned if p["category_id"] == emp]  # nada mais do Carrefour/Picpay em Dívidas
    late = [(p["name"], p["amount"], p["start_month"]) for p in planned
            if p["category_id"] == card_cat["id"] and p["start_month"] < f"{ym(0)}-01"]
    assert late == [("Carrefour", 700, f"{ym(-1)}-01")]  # o atraso de outubro fica, agora em Cartões
    assert any(p["name"] == "Aluguel" for p in planned)  # o resto não muda

    t = c.get("/api/projection", params={"months": 10, "detail": True}).json()
    sec = {s["key"]: s for s in t["table"]["sections"]}
    rows = {r["label"]: r for g in sec["cartoes"]["groups"] for r in g["rows"]}
    assert set(rows) == {"C6", "Carrefour", "PicPay"} and "dividas" not in {k for k, s in sec.items() if s["groups"]}
    assert rows["Carrefour"]["values"][:8] == [659.05, 659.05, 217.23, 217.23, 217.23, 217.23, 217.23, 0]
    assert rows["PicPay"]["values"][0] == 1400 and rows["C6"]["values"][8] == 230 and rows["C6"]["values"][9] == 0
    m1 = t["months"][0]
    assert m1["parcelas_cartao"] == 659.05 + 230 + 1400 and m1["despesas"] == 2500  # cartões fora das despesas
    plan = c.get("/api/plan", params={"month": f"{ym(1)}-01"}).json()
    assert {x["name"] for x in plan["sections"]["cartoes"]["items"]} == {"C6", "Carrefour", "PicPay"}
    assert plan["sections"]["dividas"]["items"] == [] and plan["saidas"] == 2500 + 659.05 + 230 + 1400
