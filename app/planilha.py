"""Planilha de importação: modelo (.xlsx com listas) e importação de Previstos, Atrasos, Dívidas e Orçamento.

As colunas são achadas pelo nome do cabeçalho (sem diferença de acento ou maiúsculas), então a ordem pode mudar.
Tudo o que vem da planilha leva a marca IMPORT_TAG nas observações; importar de novo substitui o que veio antes."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import finance as fin
from .models import Budget, Category, Debt, Person, Planned
from .text import strip_accents

IMPORT_TAG = "Importado da planilha"
MESES = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6, "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}
DEBT_KINDS = {"consignado": "consignado", "emprestimo": "emprestimo", "financiamento": "financiamento",
              "cheque especial": "cheque_especial", "acordo": "acordo", "outro": "outro"}

# aba: [(cabeçalho, largura, ajuda)]
SHEETS: dict[str, list[tuple[str, int, str]]] = {
    "Previstos": [
        ("Nome", 28, "Ex.: Aluguel, Salário, Escola"),
        ("Tipo", 11, "Despesa ou Receita"),
        ("Categoria", 24, "Escolha da lista (categorias do app)"),
        ("Valor (R$)", 13, "Valor positivo"),
        ("Frequência", 12, "Todo mês ou Uma vez"),
        ("Início", 11, "Mês: AAAA-MM (ex.: 2026-11)"),
        ("Fim", 11, "Mês final (vazio = sem fim). Só para Todo mês"),
        ("Dia do vencimento", 10, "1 a 31 (vazio = fim do mês)"),
        ("De quem", 14, "Nome da pessoa (vazio = conjunta)"),
        ("Texto no extrato", 18, "Reconhece o pagamento no extrato (ex.: ALUGUEL)"),
    ],
    "Atrasos": [
        ("Nome", 28, "O que está atrasado"),
        ("Categoria", 24, "Escolha da lista"),
        ("Valor (R$)", 13, "Valor em atraso"),
        ("Mês do vencimento", 12, "AAAA-MM do mês em que venceu"),
        ("Dia do vencimento", 10, "1 a 31 (vazio = fim do mês)"),
        ("De quem", 14, "Nome da pessoa (vazio = conjunta)"),
    ],
    "Dívidas": [
        ("Nome", 26, "Ex.: PAN 015435447"),
        ("Tipo", 15, "Consignado, Empréstimo, Financiamento, Cheque especial, Acordo, Outro"),
        ("Credor", 14, "Banco ou loja"),
        ("Parcela (R$)", 12, "Valor da parcela"),
        ("Juros a.m. (%)", 11, "Ex.: 4,39"),
        ("1ª parcela", 12, "Data da 1ª parcela (AAAA-MM-DD ou AAAA-MM)"),
        ("Nº de parcelas", 10, "Total de parcelas (ou preencha a Última parcela)"),
        ("Última parcela", 12, "Mês da última parcela (AAAA-MM), se não souber o nº"),
        ("Saldo devedor (sem prazo)", 14, "Só para rotativo/acordo sem nº de parcelas"),
        ("De quem", 14, "Nome da pessoa (vazio = conjunta)"),
        ("Texto no extrato", 18, "Localiza o último pagamento (ex.: CONSIGNADO)"),
    ],
    "Orçamento": [
        ("Categoria", 26, "Escolha da lista"),
        ("Valor (R$)", 13, "Quanto pretende gastar (ou receber)"),
        ("Mês", 11, "AAAA-MM só para um mês; vazio = vale para todo mês"),
    ],
}


def _norm(s) -> str:
    return re.sub(r"\s+", " ", strip_accents(str(s or "")).lower()).strip()


# ---------------------------------------------------------------- leitura de valores
def parse_money(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return abs(float(v))
    s = str(v).replace("R$", "").replace(" ", "").strip()
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return abs(float(s))
    except ValueError:
        raise ValueError(f"valor inválido: {v!r}") from None


def parse_month(v) -> date | None:
    """Aceita data do Excel, 2026-11, 2026-11-05, 11/2026, 05/11/2026, nov/26 ou novembro de 2026."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return date(v.year, v.month, 1)
    if isinstance(v, date):
        return date(v.year, v.month, 1)
    s = _norm(v)
    if m := re.fullmatch(r"(\d{4})-(\d{1,2})(?:-\d{1,2})?", s):
        return date(int(m[1]), int(m[2]), 1)
    if m := re.fullmatch(r"(?:\d{1,2}/)?(\d{1,2})/(\d{2}|\d{4})", s):
        y = int(m[2]) + (2000 if len(m[2]) == 2 else 0)
        return date(y, int(m[1]), 1)
    if m := re.fullmatch(r"([a-z]{3})[a-z]*\.?(?:\s+de)?[\s/-]+(\d{2}|\d{4})", s):
        if m[1] in MESES:
            y = int(m[2]) + (2000 if len(m[2]) == 2 else 0)
            return date(y, MESES[m[1]], 1)
    raise ValueError(f"mês inválido: {v!r} (use AAAA-MM)")


def parse_date(v) -> date | None:
    """Data completa; se vier só o mês, usa o dia 1."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = _norm(v)
    if m := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s):
        return date(int(m[1]), int(m[2]), int(m[3]))
    if m := re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})", s):
        y = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
        return date(y, int(m[2]), int(m[1]))
    return parse_month(v)


def parse_int(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(str(v).replace(",", ".")))
    except ValueError:
        raise ValueError(f"número inválido: {v!r}") from None


def parse_rate(v) -> float | None:
    """Juros a.m.: 4,39 (por cento) ou 0,0439 (fração) viram 0.0439."""
    x = parse_money(v)
    if x is None:
        return None
    return x / 100 if x >= 0.5 else x


# ---------------------------------------------------------------- modelo
def build_template(categories: list[Category], people: list[Person]) -> bytes:
    wb = Workbook()
    head_fill = PatternFill("solid", fgColor="072061")
    help_fill = PatternFill("solid", fgColor="E6ECFD")
    ws0 = wb.active
    ws0.title = "Leia-me"
    lines = [
        ("Modelo de importação do Financi", True),
        ("", False),
        ("Preencha as abas e envie em Importar → Planilha de planejamento. Pode deixar abas em branco.", False),
        ("Previstos: despesas e receitas futuras. Todo mês (com início e fim opcional) ou Uma vez.", False),
        ("   Valor que muda com o tempo: uma linha por período (ex.: Salário 8.167 de 2027-01 a 2027-12; 9.600 a partir de 2028-01).", False),
        ("Atrasos: contas vencidas e não pagas. Aparecem como 'em atraso' no app.", False),
        ("Dívidas: empréstimos, consignados, financiamentos e acordos. O app calcula parcelas pagas, saldo e juros.", False),
        ("Orçamento: quanto pretende gastar por categoria. Sem mês = vale para todo mês.", False),
        ("", False),
        ("Meses no formato AAAA-MM (ex.: 2026-11). Valores sempre positivos; o Tipo diz se entra ou sai.", False),
        ("Importar de novo substitui os previstos, atrasos e dívidas que vieram da planilha anterior.", False),
        ("A linha 2 de cada aba explica a coluna e pode ficar como está.", False),
    ]
    for i, (t, bold) in enumerate(lines, 1):
        ws0.cell(i, 1, t).font = Font(bold=bold, size=14 if i == 1 else 11)
    ws0.column_dimensions["A"].width = 120

    lists = wb.create_sheet("Listas")
    lists.sheet_state = "hidden"
    cats = [c.name for c in categories if c.active]
    for i, name in enumerate(cats, 1):
        lists.cell(i, 1, name)
    for i, name in enumerate([p.name for p in people], 1):
        lists.cell(i, 2, name)
    cat_ref = f"Listas!$A$1:$A${max(1, len(cats))}"
    ppl_ref = f"Listas!$B$1:$B${max(1, len(people))}"

    for title, cols in SHEETS.items():
        ws = wb.create_sheet(title)
        for j, (name, width, help_) in enumerate(cols, 1):
            h = ws.cell(1, j, name)
            h.font, h.fill = Font(bold=True, color="FFFFFF"), head_fill
            hc = ws.cell(2, j, help_)
            hc.font, hc.fill = Font(italic=True, size=9, color="405FAD"), help_fill
            hc.alignment = Alignment(wrap_text=True, vertical="top")
            ws.column_dimensions[get_column_letter(j)].width = width
        ws.row_dimensions[2].height = 42
        ws.freeze_panes = "A3"
        idx = {n: j for j, (n, _, _) in enumerate(cols, 1)}

        def add_list(col: str, formula: str, ws=ws, idx=idx) -> None:
            dv = DataValidation(type="list", formula1=formula, allow_blank=True)
            ws.add_data_validation(dv)
            letter = get_column_letter(idx[col])
            dv.add(f"{letter}3:{letter}1000")

        if "Categoria" in idx:
            add_list("Categoria", cat_ref)
        if "De quem" in idx and people:
            add_list("De quem", ppl_ref)
        if title == "Previstos":
            add_list("Tipo", '"Despesa,Receita"')
            add_list("Frequência", '"Todo mês,Uma vez"')
        if title == "Dívidas":
            add_list("Tipo", '"Consignado,Empréstimo,Financiamento,Cheque especial,Acordo,Outro"')
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- importação
@dataclass
class Result:
    previstos: int = 0
    atrasos: int = 0
    dividas: int = 0
    orcamento: int = 0
    substituidos: int = 0
    pessoas_criadas: list[str] = field(default_factory=list)
    categorias_criadas: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


class Row(dict):
    """Valores da linha; get() aceita o nome da coluna como está no modelo (acentos e maiúsculas não importam)."""

    def get(self, key, default=None):
        return super().get(_norm(key), default)


def _rows(ws, sheet: str):
    """Linhas da aba como dicionários pelo nome normalizado do cabeçalho (pula a linha de ajuda)."""
    header = [_norm(c.value) for c in next(ws.iter_rows(min_row=1, max_row=1))]
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
        rec = {h: v for h, v in zip(header, row, strict=False) if h}
        if not any(v not in (None, "") for v in rec.values()):
            continue
        # a linha 2 do modelo é a ajuda: texto em todas as colunas e nenhum número
        if i == 2 and not any(isinstance(v, (int, float, date)) for v in rec.values()):
            continue
        yield i, Row(rec)


def import_workbook(db: Session, content: bytes, replace: bool = True) -> Result:
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception as exc:  # noqa: BLE001  (arquivo corrompido ou não é xlsx)
        raise ValueError("Não consegui ler o arquivo. Envie a planilha no formato .xlsx (modelo do Financi).") from exc
    names = {_norm(n): n for n in wb.sheetnames}
    if not any(_norm(s) in names for s in SHEETS):
        raise ValueError("A planilha não tem as abas do modelo (Previstos, Atrasos, Dívidas ou Orçamento).")
    res = Result()

    cats = {(_norm(c.name), c.type): c for c in db.scalars(select(Category))}
    cats_any = {_norm(c.name): c for c in db.scalars(select(Category))}
    people = {_norm(p.name): p for p in db.scalars(select(Person))}

    def category(name, kind: str, where: str) -> int | None:
        if name in (None, ""):
            return None
        key = _norm(name)
        ctype = "receita" if kind == "receita" else "despesa"
        c = cats.get((key, ctype)) or cats_any.get(key)
        if c is None:
            c = Category(name=str(name).strip(), group="Receitas" if ctype == "receita" else "Outros", type=ctype, sort_order=9999)
            db.add(c)
            db.flush()
            cats[(key, ctype)] = cats_any[key] = c
            res.categorias_criadas.append(c.name)
            res.avisos.append(f"{where}: categoria “{c.name}” não existia e foi criada")
        return c.id

    def person(name) -> int | None:
        if name in (None, ""):
            return None
        key = _norm(name)
        if key in ("conjunta", "conjunto", "todos"):
            return None
        p = people.get(key)
        if p is None:
            p = Person(name=str(name).strip())
            db.add(p)
            db.flush()
            people[key] = p
            res.pessoas_criadas.append(p.name)
        return p.id

    if replace:
        for model in (Planned, Debt):
            for obj in db.scalars(select(model).where(model.notes == IMPORT_TAG)):
                db.delete(obj)
                res.substituidos += 1
        db.flush()

    def sheet(title):
        return wb[names[_norm(title)]] if _norm(title) in names else None

    if ws := sheet("Previstos"):
        for i, r in _rows(ws, "Previstos"):
            where = f"Previstos, linha {i}"
            try:
                name = str(r.get("Nome") or "").strip()
                amount = parse_money(r.get("Valor (R$)"))
                start = parse_month(r.get("Início"))
                if not name or not amount or not start:
                    res.avisos.append(f"{where}: faltou nome, valor ou início; linha ignorada")
                    continue
                kind = "receita" if _norm(r.get("Tipo")).startswith("rec") else "despesa"
                once = _norm(r.get("Frequência")).startswith(("uma", "unic", "pont"))
                end = None if once else parse_month(r.get("Fim"))
                if end and end < start:
                    res.avisos.append(f"{where}: fim antes do início; linha ignorada")
                    continue
                db.add(Planned(name=name, kind=kind, amount=amount, recurrence="pontual" if once else "mensal",
                               start_month=start, end_month=end, due_day=_day(r.get("Dia do vencimento")),
                               category_id=category(r.get("Categoria"), kind, where), owner_id=person(r.get("De quem")),
                               match_pattern=(str(r.get("Texto no extrato") or "").strip() or None), notes=IMPORT_TAG))
                res.previstos += 1
            except ValueError as exc:
                res.avisos.append(f"{where}: {exc}; linha ignorada")

    if ws := sheet("Atrasos"):
        for i, r in _rows(ws, "Atrasos"):
            where = f"Atrasos, linha {i}"
            try:
                name = str(r.get("Nome") or "").strip()
                amount = parse_money(r.get("Valor (R$)"))
                month = parse_month(r.get("Mês do vencimento"))
                if not name or not amount or not month:
                    res.avisos.append(f"{where}: faltou nome, valor ou mês do vencimento; linha ignorada")
                    continue
                db.add(Planned(name=name, kind="despesa", amount=amount, recurrence="pontual", start_month=month,
                               due_day=_day(r.get("Dia do vencimento")), category_id=category(r.get("Categoria"), "despesa", where),
                               owner_id=person(r.get("De quem")), notes=IMPORT_TAG))
                res.atrasos += 1
            except ValueError as exc:
                res.avisos.append(f"{where}: {exc}; linha ignorada")

    if ws := sheet("Dívidas"):
        for i, r in _rows(ws, "Dívidas"):
            where = f"Dívidas, linha {i}"
            try:
                name = str(r.get("Nome") or "").strip()
                if not name:
                    res.avisos.append(f"{where}: sem nome; linha ignorada")
                    continue
                first = parse_date(r.get("1ª parcela"))
                total = parse_int(r.get("Nº de parcelas"))
                last = parse_month(r.get("Última parcela"))
                if first and not total and last:
                    total = fin.months_between(fin.month_start(first), last) + 1
                if total is not None and total < 1:
                    res.avisos.append(f"{where}: última parcela antes da primeira; linha ignorada")
                    continue
                kind = DEBT_KINDS.get(_norm(r.get("Tipo")), "emprestimo")
                db.add(Debt(name=name, kind=kind, creditor=(str(r.get("Credor") or "").strip() or None),
                            installment=parse_money(r.get("Parcela (R$)")) or 0, monthly_rate=parse_rate(r.get("Juros a.m. (%)")),
                            first_due=first, total_installments=total, balance=parse_money(r.get("Saldo devedor (sem prazo)")),
                            owner_id=person(r.get("De quem")), match_pattern=(str(r.get("Texto no extrato") or "").strip() or None),
                            notes=IMPORT_TAG))
                res.dividas += 1
            except ValueError as exc:
                res.avisos.append(f"{where}: {exc}; linha ignorada")

    if ws := sheet("Orçamento"):
        for i, r in _rows(ws, "Orçamento"):
            where = f"Orçamento, linha {i}"
            try:
                amount = parse_money(r.get("Valor (R$)"))
                if not r.get("Categoria") or amount is None:
                    res.avisos.append(f"{where}: faltou categoria ou valor; linha ignorada")
                    continue
                cid = category(r.get("Categoria"), "despesa", where)
                month = parse_month(r.get("Mês"))
                cond = Budget.month.is_(None) if month is None else Budget.month == month
                row = db.scalar(select(Budget).where(Budget.category_id == cid, cond))
                if row:
                    row.amount = amount
                else:
                    db.add(Budget(category_id=cid, month=month, amount=amount))
                res.orcamento += 1
            except ValueError as exc:
                res.avisos.append(f"{where}: {exc}; linha ignorada")

    db.commit()
    return res


def _day(v) -> int | None:
    d = parse_int(v)
    if d is None:
        return None
    if not 1 <= d <= 31:
        raise ValueError(f"dia do vencimento inválido: {v!r}")
    return d
