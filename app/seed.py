"""Categorias e regras de partida (as regras aprendidas com as correções do usuário têm prioridade)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Category, Rule

# (grupo, tipo, [categorias])
CATEGORIES = [
    ("Moradia", "despesa", ["Aluguel", "Condomínio", "Energia", "Água", "Gás", "Internet e TV", "IPTU", "Manutenção da casa"]),
    ("Alimentação", "despesa", ["Supermercado", "Restaurantes", "Delivery", "Padaria e café"]),
    ("Transporte", "despesa", ["Combustível", "Apps de transporte", "Transporte público", "Estacionamento e pedágio",
                               "Manutenção do carro", "Seguro do carro"]),
    ("Saúde", "despesa", ["Plano de saúde", "Farmácia", "Consultas e exames"]),
    ("Educação", "despesa", ["Escola", "Cursos e livros"]),
    ("Filhos", "despesa", ["Filhos"]),
    ("Lazer", "despesa", ["Lazer e passeios", "Viagens"]),
    ("Compras", "despesa", ["Roupas", "Casa e utilidades", "Eletrônicos", "Compras online"]),
    ("Assinaturas", "despesa", ["Streaming e apps", "Telefone"]),
    ("Cuidados pessoais", "despesa", ["Beleza e cuidados", "Academia"]),
    ("Pets", "despesa", ["Pets"]),
    ("Presentes e doações", "despesa", ["Presentes e doações"]),
    ("Impostos e taxas", "despesa", ["Tarifas bancárias", "Impostos", "Juros e encargos"]),
    ("Dívidas", "despesa", ["Parcela de empréstimo", "Consignado", "Financiamento"]),
    ("Cartões", "despesa", ["Fatura de cartão"]),  # faturas previstas por cartão (fora de Dívidas)
    ("Outros", "despesa", ["Saques", "Outros gastos"]),
    ("Receitas", "receita", ["Salário", "13º e férias", "Bônus e PLR", "Freelance e extras", "Rendimentos",
                             "Reembolsos", "Restituição de IR", "Outras receitas"]),
    ("Transferências", "transferencia", ["Pagamento de fatura", "Transferência entre contas", "Aplicação e resgate"]),
]

# trecho da descrição normalizada (maiúsculas, sem acento) → categoria
KEYWORDS = {
    "Apps de transporte": ["UBER", "99APP", "99 TAXI", "99POP", "CABIFY", "INDRIVE"],
    "Delivery": ["IFOOD", "RAPPI", "ZE DELIVERY", "AIQFOME", "JAMES DELIVERY"],
    "Restaurantes": ["RESTAURANTE", "LANCHONETE", "PIZZARIA", "CHURRASCARIA", "OUTBACK", "MC DONALDS", "MCDONALDS",
                     "BURGER KING", "SUBWAY", "BAR DO", "SPOLETO", "MADERO"],
    "Padaria e café": ["PADARIA", "PANIFICADORA", "CAFETERIA", "STARBUCKS", "CAFE "],
    "Supermercado": ["SUPERMERC", "MERCADO ", "CARREFOUR", "ASSAI", "ATACADAO", "PAO DE ACUCAR", "EXTRA HIPER",
                     "HIPERMERCADO", "SONDA", "DIA BRASIL", "HORTIFRUTI", "OXXO", "BIG BOMPRECO", "SAMS CLUB",
                     "MUFFATO", "ZAFFARI", "SAVEGNAGO", "ATACADISTA"],
    "Combustível": ["POSTO", "SHELL", "IPIRANGA", "PETROBRAS", "BR DISTRIBUIDORA", "AUTO POSTO", "COMBUSTIVE"],
    "Estacionamento e pedágio": ["ESTACIONAMENTO", "ESTAPAR", "SEM PARAR", "CONECTCAR", "VELOE", "PEDAGIO", "TAG "],
    "Transporte público": ["METRO", "BILHETE UNICO", "SPTRANS", "CPTM", "RIOCARD", "BRT "],
    "Farmácia": ["DROGA", "FARMA", "RAIA", "PAGUE MENOS", "PANVEL", "PACHECO", "DROGASIL", "NISSEI"],
    "Plano de saúde": ["UNIMED", "AMIL", "BRADESCO SAUDE", "SULAMERICA", "HAPVIDA", "NOTREDAME", "PORTO SAUDE"],
    "Consultas e exames": ["LABORATORIO", "CLINICA", "HOSPITAL", "FLEURY", "DASA", "LAVOISIER", "ODONTO"],
    "Streaming e apps": ["NETFLIX", "SPOTIFY", "DISNEY", "HBO", "PRIME VIDEO", "AMAZON PRIME", "YOUTUBE",
                         "APPLE COM BILL", "APPLE COM", "GOOGLE PLAY", "GLOBOPLAY", "DEEZER", "PARAMOUNT", "CRUNCHYROLL",
                         "CHATGPT", "OPENAI", "CLAUDE AI", "ANTHROPIC", "MICROSOFT", "DROPBOX", "ICLOUD"],
    "Telefone": ["VIVO", "CLARO", "TIM ", "OI MOVEL", "NEXTEL"],
    "Internet e TV": ["NET SERVICOS", "SKY ", "VIVO FIBRA", "CLARO NET", "OI FIBRA"],
    "Energia": ["ENEL", "CEMIG", "COPEL", "LIGHT ", "CPFL", "ELETROPAULO", "COELBA", "CELESC", "ENERGISA", "EQUATORIAL"],
    "Água": ["SABESP", "CEDAE", "COPASA", "SANEPAR", "EMBASA", "CASAN", "COMPESA", "AGUAS DE"],
    "Gás": ["COMGAS", "ULTRAGAZ", "LIQUIGAS", "SUPERGASBRAS", "NACIONAL GAS"],
    "Academia": ["SMART FIT", "SMARTFIT", "BLUEFIT", "BODYTECH", "TOTALPASS", "GYMPASS", "WELLHUB"],
    "Compras online": ["MERCADOLIVRE", "MERCADO LIVRE", "AMAZON", "SHOPEE", "ALIEXPRESS", "SHEIN", "MAGAZINE LUIZA",
                       "MAGALU", "AMERICANAS", "CASAS BAHIA", "SUBMARINO", "KABUM"],
    "Roupas": ["RENNER", "RIACHUELO", "C&A", "ZARA", "HERING", "CENTAURO", "NETSHOES", "MARISA"],
    "Casa e utilidades": ["LEROY MERLIN", "TOK STOK", "ETNA", "CAMICADO", "TELHANORTE"],
    "Pets": ["PETZ", "COBASI", "PET SHOP", "PETSHOP", "VETERIN"],
    "Viagens": ["LATAM", "GOL LINHAS", "AZUL LINHAS", "BOOKING", "AIRBNB", "DECOLAR", "HOTEL", "123MILHAS", "MAXMILHAS"],
    "Tarifas bancárias": ["TARIFA", "TAR PACOTE", "CESTA DE SERVICOS", "ANUIDADE", "TAXA DE MANUT"],
    "Juros e encargos": ["IOF", "JUROS", "ENCARGOS", "MULTA ATRASO", "MORA"],
    "Impostos": ["DARF", "DAS SIMPLES", "IPVA", "LICENCIAMENTO", "DETRAN", "RECEITA FEDERAL", "GPS INSS"],
    "Saques": ["SAQUE", "SAQ "],
    "Salário": ["SALARIO", "PROVENTOS", "FOLHA DE PAGAMENTO", "PAGTO SALARIO", "REMUNERACAO", "CREDITO DE SALARIO"],
    "Rendimentos": ["RENDIMENTO", "REND PAGO", "JUROS SOBRE CAPITAL", "DIVIDENDOS", "REMUNERACAO APLIC"],
    "Restituição de IR": ["RESTITUICAO", "REST IRPF"],
    "Pagamento de fatura": ["PAGAMENTO DE FATURA", "PAGTO FATURA", "PGTO FATURA", "PAGAMENTO FATURA", "PAG FATURA",
                            "PAGAMENTO RECEBIDO", "PAGAMENTO EFETUADO", "PAGTO CARTAO", "PAG CARTAO CREDITO"],
    "Aplicação e resgate": ["APLICACAO", "RESGATE", "CDB", "TESOURO DIRETO", "POUPANCA", "INVEST FACIL", "RDB"],
    "Consignado": ["CONSIGNADO", "EMPRESTIMO CONSIG"],
    "Parcela de empréstimo": ["EMPRESTIMO", "PARCELA EMPREST", "CREDITO PESSOAL", "CDC "],
    "Financiamento": ["FINANCIAMENTO", "FINANC VEIC", "CAIXA HABITACAO"],
}


def seed(db: Session) -> None:
    """Cria categorias e regras padrão que ainda não existem (idempotente)."""
    existing = {(c.name, c.type): c for c in db.scalars(select(Category))}
    order = 0
    for group, type_, names in CATEGORIES:
        for name in names:
            order += 10
            if (name, type_) not in existing:
                c = Category(name=name, group=group, type=type_, sort_order=order)
                db.add(c)
                existing[(name, type_)] = c
    db.flush()
    by_name = {c.name: c for c in existing.values()}
    have = {(r.pattern, r.match) for r in db.scalars(select(Rule))}
    for cat_name, words in KEYWORDS.items():
        cat = by_name.get(cat_name)
        if not cat:
            continue
        for w in words:
            if (w, "contains") not in have:
                db.add(Rule(pattern=w, match="contains", category_id=cat.id, source="padrao"))
                have.add((w, "contains"))
    db.commit()
