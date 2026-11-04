"""Cálculos financeiros puros (sem banco): meses, faturas de cartão e empréstimos."""
from __future__ import annotations

import calendar
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

# ---------------------------------------------------------------- meses

def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def add_months(d: date, n: int) -> date:
    i = d.year * 12 + d.month - 1 + n
    return date(i // 12, i % 12 + 1, 1)


def months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + b.month - a.month


def day_in_month(m: date, day: int) -> date:
    return date(m.year, m.month, min(day, calendar.monthrange(m.year, m.month)[1]))


# ---------------------------------------------------------------- cartão de crédito

def invoice_month(d: date, closing_day: int) -> date:
    """Mês da fatura em que uma compra cai: até o dia do fechamento entra na fatura do mês, depois na do mês seguinte."""
    m = month_start(d)
    return m if d <= day_in_month(m, closing_day) else add_months(m, 1)


def due_date(invoice: date, closing_day: int, due_day: int) -> date:
    """Vencimento da fatura: no mesmo mês se o dia de vencimento é depois do fechamento, senão no mês seguinte."""
    return day_in_month(invoice if due_day > closing_day else add_months(invoice, 1), due_day)


@dataclass
class CardTx:
    date: date
    amount: float  # compra < 0, estorno/pagamento > 0
    merchant: str
    is_payment: bool = False
    installment_n: int | None = None
    installment_total: int | None = None


def card_invoices(txs: list[CardTx], closing_day: int) -> dict[date, float]:
    """Total de cada fatura (positivo = a pagar), sem os pagamentos da própria fatura."""
    out: dict[date, float] = defaultdict(float)
    for t in txs:
        if not t.is_payment:
            out[invoice_month(t.date, closing_day)] -= t.amount
    return dict(out)


def future_installments(txs: list[CardTx], closing_day: int) -> dict[date, float]:
    """Parcelas que ainda vão cair nas próximas faturas. Cada compra parcelada é contada uma vez, pela
    última parcela já lançada (a mesma compra aparece em vários extratos com parcela 1/10, 2/10...)."""
    latest: dict[tuple, CardTx] = {}
    for t in txs:
        if t.installment_total and t.installment_n and not t.is_payment:
            key = (t.merchant, t.installment_total, round(t.amount, 2))
            if key not in latest or t.installment_n > latest[key].installment_n:
                latest[key] = t
    out: dict[date, float] = defaultdict(float)
    for t in latest.values():
        base = invoice_month(t.date, closing_day)
        for k in range(1, t.installment_total - t.installment_n + 1):
            out[add_months(base, k)] += -t.amount
    return dict(out)


# ---------------------------------------------------------------- empréstimos

def present_value(installment: float, rate: float | None, n: int) -> float:
    if n <= 0:
        return 0.0
    if rate and rate > 0:
        return installment * (1 - (1 + rate) ** -n) / rate
    return installment * n


def payoff_on(installment: float, rate: float | None, dues: list[date], on: date) -> float:
    """Valor para quitar em `on`: cada parcela que vence a partir dessa data trazida a valor presente pela taxa mensal
    do contrato, proporcional aos dias corridos até o vencimento (parcela / (1 + i)^(dias/30))."""
    total = 0.0
    for due in dues:
        if due < on:
            continue
        days = (due - on).days
        total += installment / (1 + rate) ** (days / 30) if rate else installment
    return round(total, 2)


def due_dates(first_due: date, total: int) -> list[date]:
    """Vencimento de cada parcela: o dia da 1ª parcela em cada mês (último dia quando o mês é mais curto)."""
    start = month_start(first_due)
    return [day_in_month(add_months(start, k), first_due.day) for k in range(total)]


@dataclass
class LoanStatus:
    paid: int
    remaining: int
    balance: float  # saldo devedor (valor presente das parcelas restantes)
    interest_remaining: float
    end_month: date | None
    next_due: date | None


def loan_status(installment: float, rate: float | None, first_due: date | None, total: int | None,
                today: date, due_day: int | None = None, informed_balance: float | None = None) -> LoanStatus:
    """Situação de uma dívida parcelada hoje. Sem prazo definido (rotativo, acordo aberto) usa o saldo informado."""
    if not first_due or not total:
        bal = informed_balance or 0.0
        n = open_term_installments(installment, rate, bal)
        if not n:
            return LoanStatus(0, 0, bal, 0.0, None, None)
        start = add_months(month_start(today), 1)
        return LoanStatus(0, n, bal, round(max(0.0, installment * n - bal), 2), add_months(start, n - 1), None)
    day = due_day or first_due.day
    # parcelas já vencidas até hoje
    paid = months_between(first_due, today) + (1 if today >= day_in_month(month_start(today), day) else 0)
    paid = max(0, min(total, paid))
    remaining = total - paid
    if informed_balance is not None and remaining > 0 and not rate:
        balance = informed_balance
    else:  # valor para quitar hoje: parcelas que ainda vão vencer, a valor presente pelos dias até cada vencimento
        balance = payoff_on(installment, rate, [d for d in due_dates(first_due, total) if d > today], today)
    end = add_months(month_start(first_due), total - 1)
    nxt = day_in_month(add_months(month_start(first_due), paid), day) if remaining > 0 else None
    return LoanStatus(paid, remaining, round(balance, 2), round(installment * remaining - balance, 2), end, nxt)


def open_term_installments(installment: float, rate: float | None, balance: float) -> int:
    """Quantas parcelas faltam numa dívida sem prazo (acordo, rotativo) pagando `installment` por mês.

    Retorna 0 quando não há parcela ou quando ela não cobre nem os juros (a dívida não acaba)."""
    if installment <= 0 or balance <= 0:
        return 0
    if not rate:
        return math.ceil(balance / installment - 1e-9)
    if installment <= balance * rate:
        return 0
    return math.ceil(-math.log(1 - rate * balance / installment) / math.log(1 + rate) - 1e-9)


def loan_schedule(installment: float, first_due: date | None, total: int | None, *, today: date | None = None,
                  rate: float | None = None, balance: float | None = None) -> dict[date, float]:
    """Parcela de cada mês (para a projeção de caixa). Sem prazo, estima a partir do mês seguinte a `today`."""
    if not first_due or not total:
        n = open_term_installments(installment, rate, balance or 0.0) if today else 0
        start = add_months(month_start(today), 1) if today else None
        return {add_months(start, k): installment for k in range(n)}
    start = month_start(first_due)
    return {add_months(start, k): installment for k in range(total)}
