"""Criação das tabelas e migrações de versões anteriores (sem Alembic: cada passo é idempotente)."""
from sqlalchemy import MetaData, Table, inspect, insert, select, text

from .db import Base, SessionLocal, engine
from .models import Arrear, LoanContract
from .services import seed_categories


def init_db() -> list[str]:
    """Cria o que faltar, migra dados antigos e garante as categorias padrão. Devolve o que foi migrado."""
    Base.metadata.create_all(engine)
    done = migrate_shared_loans_and_arrears()
    with SessionLocal() as db:
        seed_categories(db)
    return done


def migrate_shared_loans_and_arrears() -> list[str]:
    """Até a versão anterior, consignados (loan_contracts + loan_payoffs) e atrasos (arrears + arrear_plans)
    eram compartilhados entre cenários. Agora cada cenário tem a sua cópia: copia cada registro para
    todos os cenários, com o mês de quitação / plano que aquele cenário tinha, e remove as tabelas antigas."""
    if not {"loan_contracts", "arrears"} & set(inspect(engine).get_table_names()):
        return []
    done = []
    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":  # duas instâncias subindo juntas não migram em dobro
            conn.execute(text("select pg_advisory_xact_lock(724001)"))
        tables = set(inspect(conn).get_table_names())
        md = MetaData()
        scenario_ids = [r[0] for r in conn.execute(text("select id from scenarios"))]

        if "loan_contracts" in tables:
            old = Table("loan_contracts", md, autoload_with=conn)
            payoffs = {}
            if "loan_payoffs" in tables:
                lp = Table("loan_payoffs", md, autoload_with=conn)
                payoffs = {(r.scenario_id, r.contract_id): r.payoff_month for r in conn.execute(select(lp))}
            contracts = conn.execute(select(old)).all()
            rows = [{"scenario_id": s, "name": c.name, "creditor": c.creditor, "monthly_rate": c.monthly_rate,
                     "installment": c.installment, "first_month": c.first_month, "last_month": c.last_month,
                     "notes": c.notes, "payoff_month": payoffs.get((s, c.id))}
                    for s in scenario_ids for c in contracts]
            if rows:
                conn.execute(insert(LoanContract.__table__), rows)
            if "loan_payoffs" in tables:
                lp.drop(conn)
            old.drop(conn)
            done.append(f"{len(contracts)} consignados copiados para {len(scenario_ids)} cenários")

        if "arrears" in tables:
            old = Table("arrears", md, autoload_with=conn)
            plans = {}
            if "arrear_plans" in tables:
                ap = Table("arrear_plans", md, autoload_with=conn)
                plans = {(r.scenario_id, r.arrear_id): r for r in conn.execute(select(ap))}
            arrears = conn.execute(select(old)).all()
            rows = []
            for s in scenario_ids:
                for a in arrears:
                    p = plans.get((s, a.id))
                    rows.append({"scenario_id": s, "description": a.description, "creditor": a.creditor,
                                 "owner": a.owner, "category_id": a.category_id, "due_date": a.due_date,
                                 "amount": a.amount, "fine_pct": a.fine_pct, "interest_monthly": a.interest_monthly,
                                 "negotiated_amount": a.negotiated_amount, "status": a.status,
                                 "paid_date": a.paid_date, "notes": a.notes,
                                 "plan_start": p.start_month if p else None,
                                 "plan_installments": p.installments if p else 1})
            if rows:
                conn.execute(insert(Arrear.__table__), rows)
            if "arrear_plans" in tables:
                ap.drop(conn)
            old.drop(conn)
            done.append(f"{len(arrears)} atrasos copiados para {len(scenario_ids)} cenários")
    return done
