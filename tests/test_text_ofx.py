from app.ofx import parse_amount, parse_ofx
from app.text import merchant_key, parse_installment
from tests.conftest import ofx


def test_parse_bank_statement_sgml_cp1252():
    st = parse_ofx(ofx("conta_corrente.ofx"))
    assert not st.is_card and st.bank_id == "0341" and st.acct_id == "12345-6"
    assert st.balance == 3577.36 and st.balance_date.isoformat() == "2026-10-31"
    assert len(st.transactions) == 8
    pix = st.transactions[1]
    assert pix.amount == -1300.0 and "Imobiliária São João" in pix.description  # vírgula decimal e acentos
    # compras idênticas no mesmo dia não se confundem
    assert st.transactions[2].dedupe_key != st.transactions[3].dedupe_key


def test_parse_card_xml_and_stable_keys():
    a, b = parse_ofx(ofx("cartao.ofx")), parse_ofx(ofx("cartao.ofx"))
    assert a.is_card and a.acct_id == "cartao-9876" and len(a.transactions) == 7
    assert [t.dedupe_key for t in a.transactions] == [t.dedupe_key for t in b.transactions]


def test_amount_formats():
    assert parse_amount("1.234,56") == 1234.56
    assert parse_amount("-1,234.56") == -1234.56
    assert parse_amount("-23,9") == -23.9


def test_merchant_key_and_installments():
    assert merchant_key("COMPRA CARTAO UBER *TRIP SAO PAULO 12/03") == "UBER TRIP SAO PAULO"
    assert merchant_key("PIX ENVIADO JOAO DA SILVA") == "JOAO DA SILVA"
    assert merchant_key("PAG*Padaria Pão Quente") == "PADARIA PAO QUENTE"
    assert merchant_key("MERCADOLIVRE*LOJA - Parcela 3/10") == merchant_key("MERCADOLIVRE*LOJA - Parcela 4/10")
    assert parse_installment("MERCADOLIVRE*LOJA - Parcela 3/10") == (3, 10)
    assert parse_installment("LOJA ELETRO 02/06", is_card=True) == (2, 6)
    assert parse_installment("LOJA ELETRO 02/06", is_card=False) == (None, None)  # na conta pode ser data
    assert parse_installment("UBER 12/03", is_card=True) == (None, None)  # 12 de 3 não é parcela
