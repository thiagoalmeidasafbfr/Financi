# Financi

Controle financeiro pessoal, planejamento por cenários e fluxo de caixa, com banco de dados.
Nasceu da planilha "Fluxo de Caixa Pessoal" e reproduz a lógica dela (aba "Fluxo Mensal - BR")
de forma que cada cenário fica guardado no banco e pode ser editado, duplicado e comparado.

## O que tem

| Tela | O que faz |
| --- | --- |
| **Painel** | Patrimônio final, KPIs, **Sankey de para onde vai o dinheiro** (período inteiro ou um mês), saldos e receitas × despesas |
| **Fluxo mensal** | Grade editável mês a mês: receitas, despesas fixas, dívidas, variáveis, investimentos e visão consolidada |
| **Premissas** | Parâmetros do cenário, reajustes de salário, inflação, % a investir / saldo mínimo / rentabilidade mês a mês |
| **Consignados** | Quitação de cada contrato por cenário: valor de quitação (VP), **desembolso de caixa**, parcelas evitadas, juros evitados, payback e **comparação de economia entre cenários** |
| **Comparar cenários** | KPIs lado a lado com o melhor destacado, saldos no tempo, totais por grupo e **um Sankey por cenário** |
| **Lançamentos** | Realizado do dia a dia (manual ou importação CSV) |
| **Orçado × realizado** | Planejado do cenário base contra os lançamentos do mês, por categoria |
| **Cadastros** | Importar a planilha .xlsx, categorias e contas |

Visual baseado no design system Glorioso Finance (tokens em `public/static/tokens/`, fonte Urbanist).

## Publicando no Vercel + Neon

1. **Neon**: no painel do projeto, clique em **Connect**, marque **Connection pooling** e copie a connection
   string (começa com `postgresql://` e tem `-pooler` no host). Pode usar como está: o app converte para o driver psycopg.
2. **Vercel**: *Add New → Project*, importe este repositório do GitHub. O Vercel detecta o FastAPI pelo `index.py`
   (não precisa mudar build nem framework).
3. Em *Environment Variables*, antes do primeiro deploy:

   | Variável | Valor |
   | --- | --- |
   | `DATABASE_URL` | a connection string do Neon |
   | `FINANCI_PASSWORD` | uma senha forte: o app passa a pedir usuário e senha |
   | `FINANCI_USER` | opcional, padrão `financi` |

4. *Deploy*. As tabelas são criadas no Neon no primeiro acesso. Abra o endereço do projeto, entre com
   o usuário e a senha e importe a planilha em **Cadastros**.

Detalhes: `vercel.json` coloca a função em São Paulo (`gru1`), na mesma região do Neon (`sa-east-1`);
os arquivos de `public/` são servidos pela CDN; `/healthz` responde sem senha.

> Sem `FINANCI_PASSWORD` o app fica aberto: qualquer pessoa com o link vê seus dados.

## Rodando localmente

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
# abra http://localhost:8000  (documentação da API em /docs)
```

Importe sua planilha pela tela **Cadastros** ou pela linha de comando:

```bash
python -m app.importer Fluxo_de_Caixa_Pessoal.xlsx            # todas as abas "Fluxo Mensal - …"
python -m app.importer Fluxo_de_Caixa_Pessoal.xlsx --only BR "BR > MEI"
```

O importador compara a projeção do app com os totais calculados pela planilha e imprime o resultado
(receitas, despesas, saldo em conta, saldo total e FGTS, mês a mês).

> Planilhas (`*.xlsx`) e o banco local (`*.db`) estão no `.gitignore`: são dados pessoais e não vão para o GitHub.

## Banco de dados

Configurado por `DATABASE_URL` (variável de ambiente ou arquivo `.env`, veja `.env.example`):

| Banco | `DATABASE_URL` |
| --- | --- |
| SQLite local (padrão) | `sqlite:///./financi.db` |
| PostgreSQL | `postgresql+psycopg://usuario:senha@host:5432/financi` |
| Neon / Supabase | a connection string do provedor (`postgresql://…`, convertida automaticamente) |

As tabelas são criadas automaticamente na primeira execução. Para conferir a conexão:

```bash
python -m app.check_db      # mostra o banco (sem a senha), a versão e cria as tabelas
```

### Neon (rodando localmente)

1. No painel do projeto, clique em **Connect**, escolha o branch `production`, o banco `neondb`
   e copie a connection string (aba `.env`). Ela começa com `postgresql://` e termina com
   `?sslmode=require&channel_binding=require`. Pode colar como está: o app converte para o driver psycopg
   e aceita as aspas.
2. Crie o arquivo `.env` na raiz do projeto (ele está no `.gitignore`):
   ```
   DATABASE_URL='postgresql://neondb_owner:SENHA@ep-xxxx.sa-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'
   ```
3. `python -m app.check_db`, depois `python -m app.importer Fluxo_de_Caixa_Pessoal.xlsx` para carregar os cenários
   e `uvicorn app.main:app` para abrir o app.

O plano gratuito do Neon suspende a compute após alguns minutos sem uso. O app testa a conexão antes de
usar (`pool_pre_ping`), então a primeira requisição depois de uma pausa só demora um pouco mais.
Para testar mudanças sem mexer nos dados reais, crie um branch filho no Neon (**Create child branch**)
e aponte o `.env` para ele.

### Docker

```bash
docker compose up --build    # app + PostgreSQL 16 em http://localhost:8000
```

### Modelo de dados

```
Scenario ─┬─ PlanEntry       valor planejado por categoria × mês (ou ajuste de linha automática)
          ├─ SalaryChange    reajustes do salário líquido
          ├─ InflationRate   inflação anual das despesas
          ├─ MonthSetting    % a investir, saldo mínimo, rentabilidade, salário bruto, resgate manual
          └─ LoanPayoff      mês de quitação de cada consignado neste cenário
Category       linhas do fluxo (grupo + tipo: manual ou calculada)
LoanContract   consignados (parcela, taxa, 1º e último desconto)
Account ─ Transaction   realizado
```

## Regras de cálculo (motor em `app/engine.py`)

- **Salário**: último reajuste com início ≤ mês (valor ou % sobre o anterior). **13º** = salário/2 nos meses
  das parcelas, entre o primeiro e o último ano. **1/3 de férias** = salário/3. **Bônus** = nº de salários × salário.
- Linhas calculadas aceitam **ajuste** mês a mês: o valor digitado substitui o cálculo naquele mês.
- **Consignados**: parcela entre o 1º e o último desconto, até o mês da quitação.
  **Quitação** = valor presente das parcelas restantes à taxa do contrato (mesma fórmula da aba Quitações).
- **Saldo**: disponível = saldo anterior + receitas − despesas. Investimento automático = % × (disponível −
  aportes manuais − saldo mínimo). Se faltar caixa, o resgate automático recompõe o saldo mínimo.
  As abas antigas usam "% da sobra do mês", disponível como regra alternativa do cenário.
- **FGTS** (referência, fora do saldo): depósito = alíquota × salário bruto; rendimento mensal = (1 + taxa a.a.)^(1/12) − 1.
- **Inflação** (opcional): fator acumulado aplicado às despesas fixas/variáveis no mês do reajuste.

### Conferência com a planilha

O importador confere cada cenário contra os totais da própria planilha e aponta os meses que divergem.
Foi assim que apareceu uma falha na planilha original: na aba "Fluxo Mensal - BR" a linha de resumo
"(–) Empréstimos e dívidas" está vazia em três meses, então as dívidas desses meses ficam fora do total
de despesas. O app considera esses valores; reproduzindo a falha da planilha, os números batem centavo
a centavo. As demais abas batem sem ajuste.

## Testes

```bash
pytest                                                    # motor + API (SQLite temporário)
TEST_DATABASE_URL=postgresql+psycopg://… pytest           # mesma suíte contra PostgreSQL
FINANCI_XLSX=/caminho/planilha.xlsx pytest tests/test_import_xlsx.py   # confere a importação
```

## Estrutura

```
app/
  engine.py        motor de projeção, quitações e Sankey (puro, sem banco)
  models.py        tabelas (SQLAlchemy 2)
  services.py      banco → motor, categorias padrão, duplicação de cenário
  importer.py      importação da planilha .xlsx
  routers/         API REST (cenários, cadastros, lançamentos, relatórios)
  index.html       interface
public/static/     JS, CSS, tokens do design system e ECharts embutido
index.py           entrada do Vercel
tests/
```

## Próximos passos sugeridos

- Migrações com Alembic, antes de alterar o schema com dados reais em produção.
- Login com contas de usuário (hoje é uma senha única via `FINANCI_PASSWORD`).
- Conciliação automática do realizado (OFX/extrato bancário) e regras de categorização.
