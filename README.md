# Financi

Plataforma de finanças pessoais da família: recebe os extratos do banco (OFX), categoriza os gastos sozinha,
ajuda a planejar o mês e acompanha as dívidas (cartões, empréstimos, consignados, financiamentos e acordos).

## O que tem

- **Importar extrato**: envie o OFX da conta corrente e da fatura do cartão (vários de uma vez, arrastando).
  A conta é reconhecida pelo número que vem no arquivo e criada na primeira vez. Lançamentos repetidos são
  ignorados, então dá para reenviar períodos que se sobrepõem. Cada importação pode ser desfeita.
- **Categorização automática**, em camadas:
  1. **Regras aprendidas**: quando você corrige a categoria de um lançamento, o app cria uma regra para aquele
     estabelecimento e corrige os parecidos. As suas regras sempre têm prioridade.
  2. **Palavras-chave padrão** (UBER, IFOOD, POSTO, DROGA, NETFLIX, SALARIO, TARIFA…).
  3. **IA (Claude)** para o que sobrar, se `ANTHROPIC_API_KEY` estiver configurada. Respostas muito confiantes
     viram regras; as pouco confiantes ficam na fila **Para revisar**.
- **Lançamentos**: extrato por mês, busca, filtro por conta, fila de revisão, categorização em massa e
  lançamento manual.
- **Planejamento**, em duas visões (no modelo de Monarch, Quicken Simplifi e Copilot):
  - **Mês**: o plano de um mês num modelo só — Entradas − Contas fixas − Dívidas e parcelas − Gastos variáveis =
    **Sobra prevista** (ou o que falta), com barra de para onde vai a renda, previsto × realizado por seção, contas
    em atraso com "Pago", e gastos variáveis por categoria com barra de consumo (toque para mudar o orçamento,
    todo mês ou só naquele mês; sugestão pela média dos extratos).
  - **Fluxo**: linha do saldo projetado e a tabela no formato de planilha (uma linha por previsto, categoria
    orçada, dívida e parcelas de cartão; colunas "Agora" — atrasos e o que ainda vence no mês — e 6, 12 ou 24 meses;
    totais, saldo do mês e saldo acumulado). Tocar num mês abre o plano daquele mês.
  - **Agrupamentos** (ex.: Salário líquido = salário − plano de saúde − consignados) aparecem como linha
    **informativa**, à parte do planejamento, no resumo do mês e no fim da tabela. Não mudam totais nem a projeção.
- **Previstos**: despesas e receitas futuras **todo mês** (a partir de um mês, com fim opcional) ou **uma vez**,
  cadastradas pelas seções do plano do mês. Dá para mover uma ocorrência para outro mês, mudar o valor só de um
  mês, pular um mês ou marcar como pago. O que venceu e não foi pago aparece **em atraso** (no Início e no plano do
  mês); o pagamento é reconhecido pelo extrato quando a previsão tem um "texto no extrato".
- **Planilha de planejamento**: em Importar, **Baixar modelo** gera um .xlsx com as abas Previstos, Atrasos,
  Dívidas e Orçamento (com listas das categorias e pessoas do app). Preencha no Excel ou Google Planilhas e envie:
  tudo é criado de uma vez. Dá para importar **por seção** (Receitas, Despesas previstas, Atrasos, Dívidas,
  Orçamento) em dois modos: **Adicionar** soma ao que existe e ignora o que já existe igual; **Substituir** apaga a
  seção inteira (inclusive o cadastrado no app) e sobe de novo. Só são apagadas as seções que a planilha traz com
  pelo menos uma linha, então um arquivo só com a aba Dívidas troca os consignados sem mexer no resto.
  Meses no formato AAAA-MM; valores positivos.
- **Dívidas**: faturas por cartão (com dia de fechamento e vencimento), limite usado, parcelas futuras; empréstimos
  com parcelas pagas, saldo devedor, valor para quitar hoje e juros restantes; ordem sugerida para quitar
  (maior juro primeiro ou menor saldo primeiro).
- **Casal**: cadastre as pessoas em **Ajustes**. Contas, cartões e dívidas têm titular (ou são conjuntos) e o
  seletor no topo filtra tudo por pessoa.

Pensado para o celular (funciona também no computador). Visual no design system **Azure Finance**
(`public/static/az/`: `tokens.css` e componentes `az-*` em `bundle.css`), seguindo as telas de referência do app:
fundo navy em degradê com cartões de vidro, saldo e cartões desenhados no topo do Início com a folha branca por
baixo, título grande com subtítulo e barra inferior com o botão central elevado (Importar). Tema claro em Ajustes.
Valores com centavos discretos; direção pelo sinal e pela seta (sem verde e vermelho).

**Instalar no celular:** abra o endereço no Safari (iPhone) ou Chrome (Android) → Compartilhar / menu →
**Adicionar à Tela de Início**. O Financi abre em tela cheia, como um app.

## Publicando no Vercel + Neon

1. **Neon**: no painel do projeto, clique em **Connect**, marque **Connection pooling** e copie a connection
   string (começa com `postgresql://` e tem `-pooler` no host). Pode usar como está.
2. **Vercel**: *Add New → Project*, importe este repositório. O Vercel detecta o FastAPI pelo `index.py`.
3. Em *Settings → Environment Variables*:

   | Variável | Valor |
   | --- | --- |
   | `DATABASE_URL` | a connection string do Neon |
   | `FINANCI_PASSWORD` | uma senha forte: o app passa a pedir usuário e senha |
   | `FINANCI_USER` | opcional, padrão `financi` |
   | `ANTHROPIC_API_KEY` | opcional: liga a categorização por IA (crie em console.anthropic.com) |

4. *Deploy* (ou *Redeploy* depois de mudar uma variável). As tabelas são criadas no primeiro acesso.

`vercel.json` coloca a função em São Paulo (`gru1`), na mesma região do Neon (`sa-east-1`); `/healthz`
responde sem senha. O limite de upload no Vercel é de 4 MB por arquivo: para extratos grandes, exporte um
período menor.

> Sem `FINANCI_PASSWORD` o app fica aberto: qualquer pessoa com o link vê seus dados. O app avisa no topo.

### Tabelas antigas

A plataforma usa tabelas com prefixo `fin_` (`fin_accounts`, `fin_transactions`…). As tabelas da versão
anterior (planilha de cenários: `scenarios`, `accounts`, `categories`, `transactions`…) continuam no banco,
sem uso. Se não precisar mais delas, apague-as pelo SQL Editor do Neon. A versão anterior do app está no
histórico do git (commit `a182305`).

## Exportando o OFX

No app ou internet banking, procure **Extrato** (na conta) ou **Fatura** (no cartão) → **Exportar** /
**Salvar como** → formato **OFX** (às vezes aparece como "Money" ou "Quicken"). O app lê OFX 1.x (SGML) e 2.x
(XML), em qualquer codificação usada pelos bancos brasileiros.

Depois de importar o primeiro OFX de um cartão, informe em **Dívidas → Configurar** o dia de fechamento e o
de vencimento: é o que permite separar as compras por fatura.

## Rodando localmente

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
# abra http://localhost:8000  (documentação da API em /docs)
```

Configuração por variáveis de ambiente ou arquivo `.env` (veja `.env.example`):

| Banco | `DATABASE_URL` |
| --- | --- |
| SQLite local (padrão) | `sqlite:///./financi.db` |
| PostgreSQL | `postgresql+psycopg://usuario:senha@host:5432/financi` |
| Neon | a connection string do painel (`postgresql://…`, convertida automaticamente) |

```bash
python -m app.check_db      # mostra o banco (sem a senha) e cria as tabelas
docker compose up --build   # app + PostgreSQL 16 em http://localhost:8000
```

> O banco local (`*.db`), extratos e o `.env` estão no `.gitignore`: são dados pessoais.

## Como os números são calculados

- **Saldo da conta**: o OFX traz o saldo informado pelo banco; o app ajusta o saldo inicial da conta para que
  a soma dos lançamentos bata com ele.
- **Repetidos**: cada lançamento ganha uma chave com data, valor, descrição e ordem no dia. Não usa o FITID,
  porque alguns bancos mudam esse código entre exportações.
- **Parcelas no cartão**: "PARC 03/10" ou um "03/10" no fim da descrição (só em cartão). As parcelas futuras
  entram na fatura do mês em que vão cair.
- **Fatura**: compra até o dia de fechamento entra na fatura do mês; depois dele, na do mês seguinte. O
  vencimento é no mesmo mês se o dia de vencimento for depois do fechamento, senão no mês seguinte.
- **Empréstimo**: com parcela, 1ª parcela e número de parcelas, o app conta as pagas pela data; o saldo
  devedor é o valor presente das parcelas restantes à taxa do contrato (é o valor para quitar hoje). Sem
  prazo (acordo, rotativo), usa o saldo informado e estima quantas parcelas faltam.
- **Previstos**: cada previsão gera uma ocorrência por mês (ou uma só). Séries cadastradas com início no passado
  não geram atraso dos meses anteriores ao cadastro; para registrar algo já vencido, cadastre "uma vez" no mês do
  vencimento. Sem dia de vencimento, vence no fim do mês.
- **Projeção**: começa no saldo das contas menos as faturas abertas. Cada categoria usa o orçamento; as sem
  orçamento usam a média dos últimos meses com extrato (até 3); onde há previsto da categoria naquele mês, vale o
  previsto, e previstos sem categoria somam. O que está em atraso ou ainda vence no mês atual sai no primeiro mês. Transferências e pagamentos de fatura não
  contam como gasto; o grupo Dívidas sai do orçamento porque as parcelas vêm do módulo de dívidas.

## Testes

```bash
pytest                                                   # SQLite temporário
TEST_DATABASE_URL=postgresql+psycopg://… pytest           # contra um PostgreSQL
ruff check .
```

## Estrutura

```
app/
  main.py          FastAPI, senha (Basic auth), /healthz, /api/status
  models.py        tabelas fin_*: pessoas, contas, categorias, lançamentos, regras, orçamentos, dívidas
  ofx.py           leitura de OFX (SGML e XML)
  text.py          normalização de descrições, estabelecimento e parcelas
  importing.py     importação: contas, repetidos, regras e IA
  categorize.py    regras e aprendizado
  ai.py            categorização com Claude (saída estruturada)
  finance.py       cálculos puros: faturas, parcelas, empréstimos
  services.py      orçamento, projeção, cartões e dívidas
  seed.py          categorias e palavras-chave iniciais
  routers/         API: core (cadastros), transactions (lançamentos e importação), planning
  index.html       a página
public/static/     app.js, style.css, design system (az/) e ECharts
tests/             testes e extratos OFX de exemplo
```
