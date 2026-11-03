from app.categorize import apply_ai
from app.models import Rule, Transaction
from tests.conftest import cat_id, upload


def test_import_bank_statement_rules_balance_and_duplicates(client):
    r = upload(client, "conta_corrente.ofx").json()
    assert r["account"]["created"] and r["account"]["kind"] == "corrente"
    assert (r["total"], r["new"], r["duplicates"]) == (8, 8, 0)
    assert r["by_rule"] >= 5 and r["by_ai"] == 0
    txs = {t["description"]: t for t in client.get("/api/transactions").json()}
    names = {c["id"]: c["name"] for c in client.get("/api/categories").json()}
    assert names[txs["REMUNERACAO/SALARIO EMPRESA X"]["category_id"]] == "Salário"
    assert names[txs["COMPRA CARTAO UBER *TRIP 07/10"]["category_id"]] == "Apps de transporte"
    assert names[txs["PAGTO FATURA CARTAO"]["category_id"]] == "Pagamento de fatura"
    assert names[txs["TARIFA PACOTE SERVICOS"]["category_id"]] == "Tarifas bancárias"
    assert txs["LOJA DO SEU ZE ME"]["category_id"] is None
    # saldo da conta alinhado ao saldo informado pelo banco
    acc = client.get("/api/accounts").json()[0]
    assert acc["balance"] == 3577.36

    # reimportar o mesmo extrato não duplica e reconhece a conta pelo número
    r2 = upload(client, "conta_corrente.ofx").json()
    assert not r2["account"]["created"] and (r2["new"], r2["duplicates"]) == (0, 8)
    assert len(client.get("/api/transactions").json()) == 8


def test_learning_from_correction(client, db):
    upload(client, "conta_corrente.ofx")
    tx = next(t for t in client.get("/api/transactions").json() if t["description"] == "LOJA DO SEU ZE ME")
    cid = cat_id(client, "Padaria e café")
    r = client.patch(f"/api/transactions/{tx['id']}", json={"category_id": cid}).json()
    assert r["transaction"]["categorized_by"] == "manual" and r["transaction"]["reviewed"]
    assert db.query(Rule).filter(Rule.pattern == tx["merchant"], Rule.source == "aprendida").count() == 1
    # próxima compra no mesmo estabelecimento já entra categorizada pela regra aprendida
    acc = client.get("/api/accounts").json()[0]["id"]
    new = client.post("/api/transactions", json={"account_id": acc, "date": "2026-11-02", "amount": -12.0,
                                                 "description": "LOJA DO SEU ZE ME"}).json()
    assert new["category_id"] is None  # manual sem categoria não passa pelas regras...
    client.post("/api/rules/apply")  # ...até reaplicar
    t = client.get("/api/transactions", params={"q": "SEU ZE"}).json()
    assert {x["category_id"] for x in t} == {cid}


def test_card_import_installments_and_undo(client):
    r = upload(client, "cartao.ofx").json()
    assert r["account"]["kind"] == "cartao" and r["new"] == 7
    acc = r["account"]["id"]
    txs = client.get("/api/transactions", params={"account_id": acc}).json()
    ml = next(t for t in txs if t["description"].startswith("MERCADOLIVRE"))
    assert ml["installment"] == [3, 10]
    names = {c["id"]: c["name"] for c in client.get("/api/categories").json()}
    assert names[next(t for t in txs if t["description"] == "Pagamento recebido")["category_id"]] == "Pagamento de fatura"
    assert names[next(t for t in txs if t["description"] == "NETFLIX.COM")["category_id"]] == "Streaming e apps"
    imports = client.get("/api/imports").json()
    assert imports[0]["new"] == 7
    assert client.delete(f"/api/imports/{imports[0]['id']}").status_code == 204
    assert client.get("/api/transactions", params={"account_id": acc}).json() == []


def test_import_errors(client):
    bad = client.post("/api/imports", files={"file": ("x.ofx", b"isto nao e um ofx", "text/plain")})
    assert bad.status_code == 400


class _Block:
    def __init__(self, text):
        self.type, self.text = "text", text


class _Resp:
    def __init__(self, text, stop="end_turn"):
        self.content, self.stop_reason = [_Block(text)], stop


class FakeClient:
    """Imita client.beta.messages.create guardando os argumentos."""

    def __init__(self, reply):
        self.calls, self._reply = [], reply
        self.beta = self
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        return self._reply(kw) if callable(self._reply) else self._reply


def test_ai_categorizes_leftovers_and_learns_confident_answers(client, db):
    upload(client, "conta_corrente.ofx")
    pending = list(db.query(Transaction).filter(Transaction.category_id.is_(None)))
    assert pending
    import json

    def reply(kw):
        items = json.loads(kw["messages"][0]["content"].split("Lançamentos (JSON):\n")[1].split("\n\n")[0])
        return _Resp(json.dumps({"items": [{"i": it["i"], "category": "Padaria e café", "confidence": 0.95}
                                           for it in items]}))

    fake = FakeClient(reply)
    n = apply_ai(db, pending, client=fake)
    db.commit()
    assert n == len(pending)
    call = fake.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["fallbacks"] == "default"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "Padaria e café" in call["output_config"]["format"]["schema"]["properties"]["items"]["items"]["properties"]["category"]["enum"]
    t = db.get(Transaction, pending[0].id)
    assert t.categorized_by == "ia" and t.confidence == 0.95
    assert db.query(Rule).filter(Rule.source == "ia").count() >= 1  # resposta confiante vira regra


def test_ai_failures_never_break(client, db):
    upload(client, "conta_corrente.ofx")
    pending = list(db.query(Transaction).filter(Transaction.category_id.is_(None)))
    assert apply_ai(db, pending, client=FakeClient(_Resp("", stop="refusal"))) == 0
    assert apply_ai(db, pending, client=FakeClient(_Resp("não é json"))) == 0

    class Boom(FakeClient):
        def create(self, **kw):
            raise RuntimeError("rede caiu")

    assert apply_ai(db, pending, client=Boom(None)) == 0
    # sem chave e sem cliente, nem tenta
    assert apply_ai(db, pending) == 0


def test_review_queue_and_bulk(client):
    upload(client, "conta_corrente.ofx")
    review = client.get("/api/transactions", params={"status": "revisar"}).json()
    assert {t["description"] for t in review} >= {"LOJA DO SEU ZE ME"}
    cid = cat_id(client, "Outros gastos")
    r = client.post("/api/transactions/bulk-category", json={"ids": [t["id"] for t in review], "category_id": cid}).json()
    assert r["updated"] == len(review)
    assert client.get("/api/transactions", params={"status": "sem_categoria"}).json() == []
