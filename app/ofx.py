"""Leitura de extratos e faturas OFX (1.x SGML e 2.x XML), como os bancos brasileiros exportam."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date

from .text import normalize_description


class OFXError(ValueError):
    pass


@dataclass
class OFXTransaction:
    date: date
    amount: float
    description: str
    fitid: str | None = None
    trntype: str | None = None
    dedupe_key: str = ""


@dataclass
class OFXStatement:
    is_card: bool
    bank_id: str | None
    acct_id: str | None
    acct_type: str | None
    org: str | None
    currency: str | None
    start: date | None
    end: date | None
    balance: float | None
    balance_date: date | None
    transactions: list[OFXTransaction] = field(default_factory=list)


def decode(content: bytes) -> str:
    """OFX 1.x costuma vir em Windows-1252 (CHARSET:1252); 2.x em UTF-8."""
    head = content[:600].decode("ascii", "ignore").upper()
    if "CHARSET:1252" in head or "ENCODING:USASCII" in head and "UTF" not in head:
        try:
            return content.decode("cp1252")
        except UnicodeDecodeError:
            pass
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("cp1252", errors="replace")


def _value(block: str, tag: str) -> str | None:
    """Valor de <TAG>; funciona com e sem tag de fechamento (SGML ou XML)."""
    m = re.search(rf"<{tag}>([^<\r\n]*)", block, re.IGNORECASE)
    if not m:
        return None
    v = m.group(1).strip()
    return v or None


def parse_amount(text: str) -> float:
    t = text.strip().replace(" ", "")
    if "," in t and "." in t:  # o último separador é o decimal
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    return float(t)


def parse_date(text: str | None) -> date | None:
    if not text:
        return None
    m = re.match(r"(\d{4})(\d{2})(\d{2})", text.strip())
    if not m:
        return None
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))


def parse_ofx(content: bytes) -> OFXStatement:
    text = decode(content)
    if "<OFX>" not in text.upper():
        raise OFXError("Arquivo não parece um OFX (sem a tag <OFX>)")
    upper = text.upper()
    is_card = "<CCSTMTRS>" in upper or "<CREDITCARDMSGSRSV1>" in upper
    acct_block = re.search(r"<(BANKACCTFROM|CCACCTFROM)>(.*?)</\1>", text, re.IGNORECASE | re.DOTALL)
    acct = acct_block.group(2) if acct_block else text
    ledger = re.search(r"<LEDGERBAL>(.*?)</LEDGERBAL>", text, re.IGNORECASE | re.DOTALL)
    led = ledger.group(1) if ledger else ""

    st = OFXStatement(
        is_card=is_card,
        bank_id=_value(acct, "BANKID"),
        acct_id=_value(acct, "ACCTID"),
        acct_type=_value(acct, "ACCTTYPE"),
        org=_value(text, "ORG"),
        currency=_value(text, "CURDEF"),
        start=parse_date(_value(text, "DTSTART")),
        end=parse_date(_value(text, "DTEND")),
        balance=parse_amount(_value(led, "BALAMT")) if _value(led, "BALAMT") else None,
        balance_date=parse_date(_value(led, "DTASOF")),
    )

    # cada <STMTTRN> vai até o </STMTTRN> (XML) ou até o próximo <STMTTRN>/fim da lista (SGML)
    blocks = re.findall(r"<STMTTRN>(.*?)(?=</STMTTRN>|<STMTTRN>|</BANKTRANLIST>)", text, re.IGNORECASE | re.DOTALL)
    seen: dict[tuple, int] = {}
    for b in blocks:
        d = parse_date(_value(b, "DTPOSTED"))
        amt = _value(b, "TRNAMT")
        if d is None or amt is None:
            continue
        memo, name = _value(b, "MEMO"), _value(b, "NAME")
        if memo and name and name.upper() not in memo.upper() and memo.upper() not in name.upper():
            desc = f"{name} - {memo}"
        else:
            desc = memo or name or _value(b, "TRNTYPE") or "Lançamento"
        value = round(parse_amount(amt), 2)
        # chave estável entre exportações (alguns bancos mudam o FITID): data + valor + descrição,
        # com contador para compras iguais no mesmo dia
        base = (d.isoformat(), f"{value:.2f}", normalize_description(desc))
        seen[base] = seen.get(base, 0) + 1
        key = hashlib.sha1("|".join((*base, str(seen[base]))).encode()).hexdigest()[:40]
        st.transactions.append(OFXTransaction(date=d, amount=value, description=desc[:255],
                                              fitid=_value(b, "FITID"), trntype=_value(b, "TRNTYPE"), dedupe_key=key))
    return st
