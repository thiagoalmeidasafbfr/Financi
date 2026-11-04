from datetime import date

import pytest

from app import finance as fin


def test_invoice_month_and_due_date():
    # fechamento dia 25: compra até o dia 25 cai na fatura do mês, depois na do mês seguinte
    assert fin.invoice_month(date(2026, 10, 25), 25) == date(2026, 10, 1)
    assert fin.invoice_month(date(2026, 10, 26), 25) == date(2026, 11, 1)
    assert fin.due_date(date(2026, 10, 1), 25, 5) == date(2026, 11, 5)  # vence no mês seguinte
    assert fin.due_date(date(2026, 10, 1), 3, 10) == date(2026, 10, 10)
    assert fin.invoice_month(date(2026, 2, 28), 31) == date(2026, 2, 1)  # dia 31 em fevereiro


def test_card_invoices_exclude_payments_and_future_installments_count_once():
    txs = [
        fin.CardTx(date(2026, 9, 1), -150, "ML", installment_n=2, installment_total=10),
        fin.CardTx(date(2026, 10, 1), -150, "ML", installment_n=3, installment_total=10),  # mesma compra, extrato seguinte
        fin.CardTx(date(2026, 10, 3), -60, "IFOOD"),
        fin.CardTx(date(2026, 10, 11), 500, "PAGAMENTO", is_payment=True),
        fin.CardTx(date(2026, 10, 12), 20, "ESTORNO"),
    ]
    inv = fin.card_invoices(txs, closing_day=25)
    assert inv[date(2026, 10, 1)] == 150 + 60 - 20
    future = fin.future_installments(txs, closing_day=25)
    assert len(future) == 7 and set(future.values()) == {150}  # parcelas 4 a 10, contadas uma vez
    assert min(future) == date(2026, 11, 1)


def test_loan_status_and_present_value():
    st = fin.loan_status(364.89, 0.0439, date(2026, 10, 10), 11, today=date(2027, 2, 15))
    assert st.paid == 5 and st.remaining == 6
    # valor para quitar hoje (15/02): cada parcela a valor presente pela taxa, pelos dias até o vencimento (10 de mar a ago)
    dues = [date(2027, m, 10) for m in range(3, 9)]
    want = sum(364.89 / 1.0439 ** ((d - date(2027, 2, 15)).days / 30) for d in dues)
    assert st.balance == pytest.approx(want, abs=0.01)
    assert st.balance > fin.present_value(364.89, 0.0439, 6)  # a 1ª parcela vence em 23 dias, não em 30
    assert st.interest_remaining == pytest.approx(364.89 * 6 - st.balance, abs=0.01)
    assert st.end_month == date(2027, 8, 1) and st.next_due == date(2027, 3, 10)
    before = fin.loan_status(100, 0.02, date(2027, 1, 10), 12, today=date(2026, 11, 3))
    assert before.paid == 0 and before.remaining == 12
    done = fin.loan_status(100, 0.02, date(2025, 1, 10), 6, today=date(2026, 11, 3))
    assert done.remaining == 0 and done.balance == 0 and done.next_due is None
    rot = fin.loan_status(0, None, None, None, today=date(2026, 11, 3), informed_balance=4200)
    assert rot.balance == 4200  # rotativo / acordo sem prazo usa o saldo informado


def test_open_term_debt():
    assert fin.open_term_installments(500, None, 1200) == 3
    assert fin.open_term_installments(100, 0.05, 2000) == 0  # parcela não cobre os juros
    n = fin.open_term_installments(300, 0.02, 1000)
    assert n == 4 and fin.present_value(300, 0.02, n) >= 1000 > fin.present_value(300, 0.02, n - 1)
    st = fin.loan_status(500, None, None, None, today=date(2026, 11, 3), informed_balance=1200)
    assert (st.remaining, st.balance, st.end_month) == (3, 1200, date(2027, 2, 1))
    sched = fin.loan_schedule(500, None, None, today=date(2026, 11, 3), balance=1200)
    assert sorted(sched) == [date(2026, 12, 1), date(2027, 1, 1), date(2027, 2, 1)]


def test_payoff_on_a_date():
    """Quitação numa data: parcela que vence no dia conta cheia; as seguintes, descontadas pelos dias corridos."""
    dues = fin.due_dates(date(2027, 1, 31), 3)
    assert dues == [date(2027, 1, 31), date(2027, 2, 28), date(2027, 3, 31)]  # mês curto: último dia
    v = fin.payoff_on(100, 0.03, dues, date(2027, 1, 31))
    assert v == pytest.approx(100 + 100 / 1.03 ** (28 / 30) + 100 / 1.03 ** (59 / 30), abs=0.01)
    assert fin.payoff_on(100, 0.03, dues, date(2027, 2, 1)) == pytest.approx(100 / 1.03 ** (27 / 30) + 100 / 1.03 ** (58 / 30), abs=0.01)
    assert fin.payoff_on(100, None, dues, date(2027, 1, 1)) == 300  # sem juros: soma das parcelas
