"""Valida o importador contra a planilha real.

A planilha tem dados pessoais e não fica no repositório. Para rodar:
    FINANCI_XLSX=/caminho/Fluxo_de_Caixa_Pessoal.xlsx pytest tests/test_import_xlsx.py
"""
import os

import pytest

from app.db import SessionLocal
from app.importer import import_workbook

XLSX = os.environ.get("FINANCI_XLSX")


@pytest.mark.skipif(not XLSX, reason="defina FINANCI_XLSX para validar a importação da planilha")
def test_import_matches_spreadsheet(client):
    with SessionLocal() as db:
        report = import_workbook(db, XLSX)
    print("\n".join(report))
    validations = [line for line in report if "validação" in line]
    assert validations
    ok = [v for v in validations if ": OK" in v]
    assert len(ok) >= len(validations) - 1, report
