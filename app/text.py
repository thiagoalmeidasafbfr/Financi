"""Normalização das descrições dos extratos: chave do estabelecimento e parcelas."""
from __future__ import annotations

import re
import unicodedata

# prefixos que os bancos colocam antes do nome do estabelecimento/pessoa
_PREFIXES = [
    r"COMPRA (?:NO |COM )?(?:CARTAO|CARTÃO|DEBITO|DÉBITO|CREDITO|CRÉDITO)(?: DE)?(?: DEBITO| CREDITO)?",
    r"COMPRA(?: APROVADA)?", r"PAG(?:AMENTO|TO)? (?:DE )?BOLETO", r"PIX (?:ENVIADO|RECEBIDO|TRANSF|QR CODE|QRS)?",
    r"TRANSF(?:ERENCIA)?(?: ENVIADA| RECEBIDA)?(?: PIX)?", r"TED(?: ENVIADA| RECEBIDA)?", r"DOC(?: ENVIADO| RECEBIDO)?",
    r"DEB(?:ITO)? AUT(?:OMATICO)?", r"DEBITO", r"CREDITO", r"SAQUE", r"ELO", r"VISA", r"MASTERCARD",
    r"DEBITO EM CONTA", r"CARTAO", r"INT ", r"SISPAG", r"RSHOP", r"IFD\*?", r"PG ?\*", r"PAG ?\*", r"MP ?\*", r"EC ?\*",
]
_PREFIX_RE = re.compile(r"^(?:(?:" + "|".join(_PREFIXES) + r")[\s\-:*]*)+")
_INSTALLMENT_RE = re.compile(r"\b(?:PARC(?:ELA)?\.?\s*)(\d{1,2})\s*(?:/|DE)\s*(\d{1,2})\b")
_TRAILING_FRACTION_RE = re.compile(r"\(?\b(\d{1,2})/(\d{1,2})\)?\s*$")


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def normalize_description(desc: str) -> str:
    """Maiúsculas, sem acento e com espaços simples (para comparar descrições)."""
    return re.sub(r"\s+", " ", strip_accents(desc or "").upper()).strip()


def parse_installment(desc: str, is_card: bool = False) -> tuple[int | None, int | None]:
    """'LOJA X PARC 03/10' → (3, 10). No cartão aceita também '... 03/10' no fim da descrição."""
    d = normalize_description(desc)
    m = _INSTALLMENT_RE.search(d)
    if not m and is_card:
        m = _TRAILING_FRACTION_RE.search(d)
    if not m:
        return None, None
    n, total = int(m.group(1)), int(m.group(2))
    if 1 <= n <= total and 2 <= total <= 72:
        return n, total
    return None, None


def merchant_key(desc: str) -> str:
    """Chave estável do estabelecimento/pessoa: sem prefixos do banco, números, datas e parcelas.

    'COMPRA CARTAO UBER *TRIP SAO PAULO 12/03' → 'UBER TRIP SAO PAULO'."""
    d = normalize_description(desc)
    d = _INSTALLMENT_RE.sub(" ", d)
    d = _TRAILING_FRACTION_RE.sub(" ", d)
    d = re.sub(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", " ", d)  # datas
    d = re.sub(r"\d+", " ", d)  # códigos, cartões, documentos
    d = _PREFIX_RE.sub("", d.strip())  # prefixos com asterisco (PAG*, MP*...) antes de tirar a pontuação
    d = re.sub(r"[*#@/\\|_.,;:()\[\]{}\-+=\"']", " ", d)
    d = re.sub(r"\s+", " ", d).strip()
    d = _PREFIX_RE.sub("", d).strip()
    d = re.sub(r"\b(LTDA|ME|EPP|SA|S A|EIRELI|CIA)\b", " ", d)
    d = re.sub(r"\s+", " ", d).strip()
    return d[:120] or normalize_description(desc)[:120] or "SEM DESCRICAO"
