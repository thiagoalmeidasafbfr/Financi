/* Financi — finanças pessoais (vanilla JS + ECharts, design system Azure Finance). */
"use strict";

// ------------------------------------------------------------------ utilidades
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const BRL2 = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const fmt = (v) => (v == null || isNaN(v) ? "–" : BRL.format(v));
const fmt2 = (v) => (v == null || isNaN(v) ? "–" : BRL2.format(v));
const pct = (v, d = 0) => (v == null || isNaN(v) ? "–" : (v * 100).toFixed(d).replace(".", ",") + "%");
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const MESES_LONGOS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
const mlabel = (iso) => (iso ? `${MESES[+iso.slice(5, 7) - 1]}/${iso.slice(2, 4)}` : "–");
const mlong = (iso) => (iso ? `${MESES_LONGOS[+iso.slice(5, 7) - 1]} de ${iso.slice(0, 4)}` : "–");
const dlabel = (iso) => (iso ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}` : "–");
const short = (v) => {
  const a = Math.abs(v);
  if (a >= 1e6) return (v / 1e6).toFixed(1).replace(".", ",") + "M";
  if (a >= 1e3) return (v / 1e3).toFixed(1).replace(".", ",") + "k";
  return String(Math.round(v));
};
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const parseNum = (s) => {
  s = String(s ?? "").trim();
  if (s === "") return null;
  if (s.includes(",")) s = s.replace(/\./g, "").replace(",", ".");
  const v = Number(s);
  return isNaN(v) ? undefined : v;
};
const thisMonth = () => new Date().toISOString().slice(0, 7) + "-01";
const addMonths = (iso, n) => {
  const [y, m] = iso.split("-").map(Number);
  const i = y * 12 + m - 1 + n;
  return `${Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}-01`;
};
const isMobile = () => window.matchMedia("(max-width: 700px)").matches;
const initials = (s) => (s || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();

// ------------------------------------------------------------------ componentes do Azure Finance
const svg = (d, cls = "") => `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`;
const ICON = {
  tag: svg('<path d="M3 12V4h8l10 10-8 8z"/><circle cx="7.5" cy="8.5" r="1.2"/>'),
  chart: svg('<path d="M7 20V10M12 20V4M17 20v-7"/>'),
  up: svg('<path d="M7 17 17 7M8 7h9v9"/>'),
  down: svg('<path d="M7 7l10 10M17 8v9H8"/>'),
  card: svg('<rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18M7 15h3"/>'),
  clock: svg('<circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/>'),
  debt: svg('<path d="M4 20h16M6 16V9M10 16V9M14 16V9M18 16V9M12 3l8 4H4z"/>'),
  sun: svg('<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>', "i"),
  moon: svg('<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>', "i"),
};
const SPARKLE = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2l2.2 7.8L22 12l-7.8 2.2L12 22l-2.2-7.8L2 12l7.8-2.2z"/></svg>';
const CHEV = `<span class="az-insight__chev">${svg('<path d="M9 6l6 6-6 6"/>')}</span>`;
const well = (content) => `<span class="az-well az-well--sm">${content}</span>`;
const tile = (label, value, sub = "") => `<div class="tile"><div class="tile__label">${label}</div><div class="tile__value">${value}</div>${sub ? `<div class="tile__sub">${sub}</div>` : ""}</div>`;
// linha no padrão InsightRow: poço, título, descrição e (opcional) valor à direita
const listRow = ({ icon, title, desc = "", amount = "", extra = "", cls = "" }) =>
  `<div class="az-insight ${cls}">${well(icon)}<div class="az-insight__text"><div class="az-insight__title">${title}</div>` +
  `${desc ? `<div class="az-insight__desc">${desc}</div>` : ""}</div>${amount ? `<span class="amount">${amount}</span>` : ""}${extra}</div>`;
const signed = (v) => `${v < 0 ? "−" : ""}${fmt2(Math.abs(v))}`;
// valor formatado com sinal (opcional: "+" para entradas), números tabulares
const money = (v, { plus = false } = {}) => {
  const [whole, cents] = fmt2(Math.abs(v)).split(",");
  const sign = v < 0 ? "−" : plus && v > 0 ? "+" : "";
  return `<span class="money">${sign}${whole},${cents}</span>`;
};

function toast(msg, action) {
  const t = $("#toast");
  t.innerHTML = `<span>${esc(msg)}</span>${action ? `<button class="toast-action">${esc(action.label)}</button>` : ""}`;
  t.classList.toggle("has-action", !!action);
  if (action) {
    t.querySelector(".toast-action").onclick = async () => {
      t.classList.remove("show");
      await action.run();
    };
  }
  t.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove("show"), action ? 7000 : 2800);
}

async function api(method, url, body) {
  const opts = { method, headers: {} };
  if (body instanceof FormData) opts.body = body;
  else if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let r;
  try {
    r = await fetch(url, opts);
  } catch (err) {
    toast("Sem conexão. Tente de novo.");
    throw err;
  }
  // sem sessão: mostra a entrada (senha ou Face ID) e repete o pedido; pedidos em paralelo esperam o mesmo login
  if (r.status === 401 && !url.startsWith("/api/auth/")) {
    await requireLogin();
    return api(method, url, body);
  }
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const j = await r.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch (_) { /* sem corpo */ }
    toast(`Erro: ${detail}`);
    throw new Error(detail);
  }
  return r.status === 204 ? null : r.json();
}
const withPerson = (url) => {
  const p = state.person;
  if (!p || p === "all") return url;
  return url + (url.includes("?") ? "&" : "?") + `person=${encodeURIComponent(p)}`;
};

// ------------------------------------------------------------------ gráficos (azuis da marca: aceso Royal Blue / Bright Azure, apagado Cloud Blue)
const charts = {};
const LIT = () => css("--chart-lit");
const DIM = () => css("--chart-dim");
function chart(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  if (charts[id] && charts[id].getDom() === el) return charts[id];
  charts[id] = echarts.init(el, null, { renderer: "svg" });
  return charts[id];
}
window.addEventListener("resize", () => Object.values(charts).forEach((c) => c.resize()));
window.matchMedia("(max-width: 700px)").addEventListener("change", () => refresh());
function baseOption() {
  const ink2 = css("--ink-muted"), axis = css("--line");
  return {
    animationDuration: 480,
    textStyle: { fontFamily: css("--font-sans"), color: ink2 },
    grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
    tooltip: {
      trigger: "axis", backgroundColor: css("--surface-raised"), borderWidth: 0,
      extraCssText: `box-shadow:${css("--shadow-card")};border-radius:12px`,
      textStyle: { color: css("--ink"), fontFamily: css("--font-sans") },
      axisPointer: { type: "line", lineStyle: { color: axis } }, valueFormatter: (v) => fmt(v),
    },
    legend: { top: 0, left: 0, icon: "circle", itemWidth: 8, itemHeight: 8, textStyle: { color: ink2 } },
    xAxis: { type: "category", axisLine: { lineStyle: { color: axis } }, axisTick: { show: false }, axisLabel: { color: css("--ink-faint") } },
    yAxis: { type: "value", splitLine: { lineStyle: { color: css("--chart-grid") } }, axisLabel: { color: css("--ink-faint"), formatter: short } },
  };
}

// ------------------------------------------------------------------ folha inferior
function openSheet(html) {
  $("#sheet-body").innerHTML = html;
  $("#sheet").hidden = false;
  $("#sheet-backdrop").hidden = false;
  requestAnimationFrame(() => $("#sheet").classList.add("open"));
  const first = $("#sheet input, #sheet select");
  if (first && !isMobile()) first.focus();
}
function closeSheet() {
  const s = $("#sheet");
  if (!s || s.hidden) return;
  s.classList.remove("open");
  $("#sheet-backdrop").hidden = true;
  setTimeout(() => (s.hidden = true), 160);
}
$("#sheet-backdrop").addEventListener("click", closeSheet);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeSheet(); });
const sheetVal = (id) => $(`#${id}`)?.value ?? "";

// ------------------------------------------------------------------ estado e dados base
const state = {
  people: [], accounts: [], categories: [], person: "all", tab: "inicio", status: null,
  tx: { month: thisMonth(), account: "", status: "", q: "", selected: new Set(), rows: [] },
  plan: { month: thisMonth(), view: "mes", horizon: 12 },
  ruleSource: "",
};
const KIND_LABEL = { corrente: "Conta corrente", poupanca: "Poupança", cartao: "Cartão de crédito", investimento: "Investimentos", dinheiro: "Dinheiro" };
const DEBT_LABEL = { emprestimo: "Empréstimo", consignado: "Consignado", financiamento: "Financiamento", cheque_especial: "Cheque especial", acordo: "Acordo", outro: "Outro" };
const TYPE_LABEL = { despesa: "Despesas", receita: "Receitas", transferencia: "Transferências (não contam como gasto)" };
const personName = (id) => (id == null ? "Conjunta" : state.people.find((p) => p.id === id)?.name || "–");
const catById = (id) => state.categories.find((c) => c.id === id);
const accById = (id) => state.accounts.find((a) => a.id === id);

async function loadBase() {
  [state.people, state.accounts, state.categories] = await Promise.all([
    api("GET", "/api/people"), api("GET", "/api/accounts?include_inactive=true"), api("GET", "/api/categories"),
  ]);
  const sel = $("#person");
  const opts = [["all", "Todos"], ...state.people.map((p) => [String(p.id), p.name]), ["conjunto", "Conjunto"]];
  if (!opts.some(([v]) => v === state.person)) state.person = "all";
  sel.innerHTML = opts.map(([v, l]) => `<option value="${v}" ${v === state.person ? "selected" : ""}>${esc(l)}</option>`).join("");
  sel.hidden = state.people.length === 0;
}

function categoryOptions(selected, { allowNone = true, types = ["despesa", "receita", "transferencia"] } = {}) {
  let h = allowNone ? `<option value="">Sem categoria</option>` : "";
  for (const t of types) {
    const groups = {};
    state.categories.filter((c) => c.type === t && (c.active || c.id === selected)).forEach((c) => (groups[c.group] ||= []).push(c));
    for (const [g, cs] of Object.entries(groups)) {
      h += `<optgroup label="${esc(t === "despesa" ? g : TYPE_LABEL[t])}">` +
        cs.map((c) => `<option value="${c.id}" ${c.id === selected ? "selected" : ""}>${esc(c.name)}</option>`).join("") + "</optgroup>";
    }
  }
  return h;
}
const accountOptions = (selected, { all = false, label = "Todas as contas" } = {}) =>
  (all ? `<option value="">${label}</option>` : "") +
  state.accounts.filter((a) => a.active || a.id === selected)
    .map((a) => `<option value="${a.id}" ${a.id === selected ? "selected" : ""}>${esc(a.name)}</option>`).join("");
const peopleOptions = (selected, none = "Conjunta") => `<option value="">${none}</option>` +
  state.people.map((p) => `<option value="${p.id}" ${p.id === selected ? "selected" : ""}>${esc(p.name)}</option>`).join("");

async function refresh() {
  await (RENDER[state.tab] || (() => {}))();
}

// ------------------------------------------------------------------ INÍCIO
// olho do saldo: esconde os valores do topo do Início (fica salvo neste aparelho)
let hideValues = false;
try { hideValues = localStorage.getItem("financi-ocultar") === "1"; } catch (_) { /* navegação privada */ }
function applyHidden() {
  $("#tab-inicio").classList.toggle("values-hidden", hideValues);
  $("#h-eye").setAttribute("aria-label", hideValues ? "Mostrar valores" : "Ocultar valores");
}
$("#h-eye").addEventListener("click", () => {
  hideValues = !hideValues;
  try { localStorage.setItem("financi-ocultar", hideValues ? "1" : "0"); } catch (_) { /* navegação privada */ }
  applyHidden();
});
async function renderInicio() {
  const d = await api("GET", withPerson(`/api/dashboard`));
  const empty = !d.has_data;
  $("#home-empty").hidden = !empty;
  $("#home-content").hidden = empty;
  $("#home-crumb").textContent = mlong(d.month);
  if (empty) return;
  if (!state.monthSynced) {
    // na primeira visita com dados, Lançamentos e Planejamento abrem no mesmo mês que o Início mostra
    state.monthSynced = true;
    state.tx.month = d.month;
  }
  if (state.tab === "inicio") screenHead("inicio");
  const T = d.month_totals, DT = d.debts_totals;
  $("#h-saldo").innerHTML = money(d.saldo_contas);
  const net = T.receitas - T.despesas;
  const arrow = svg(net >= 0 ? '<path d="M12 19V5M6 11l6-6 6 6"/>' : '<path d="M12 5v14M6 13l6 6 6-6"/>', "i");
  $("#h-trend").innerHTML = `<b>${arrow}${net >= 0 ? "+" : "−"}${fmt(Math.abs(net))}</b> em ${MESES_LONGOS[+d.month.slice(5, 7) - 1]}`;
  // faixa de saldos: investido, faturas abertas e o que sobra depois de pagar as faturas
  const livre = d.saldo_contas - DT.faturas_abertas;
  $("#h-stats").innerHTML = [["Investido", fmt(d.investido)], ["Faturas abertas", fmt(DT.faturas_abertas)],
    ["Livre após faturas", `${livre < 0 ? "−" : ""}${fmt(Math.abs(livre))}`]]
    .map(([l, v]) => `<div class="hero-stat"><span>${l}</span><b class="money">${v}</b></div>`).join("");

  // big numbers (cada um leva à sua tela)
  const P = d.previstos_mes || { receitas: 0, despesas: 0 };
  const proj = d.projecao || { meses: [] };
  const last = proj.meses[proj.meses.length - 1];
  const big = [
    ["Entradas do mês", fmt(T.receitas), P.receitas || T.receitas_previstas ? `previsto ${fmt(P.receitas || T.receitas_previstas)}` : "sem previsão", "lancamentos"],
    ["Saídas do mês", fmt(T.despesas), T.despesas_orcadas || P.despesas ? `orçado ${fmt(T.despesas_orcadas + P.despesas)}` : "sem orçamento", "orcamento"],
    ["Em atraso", fmt(d.overdue ? d.overdue.total : 0), d.overdue && d.overdue.count ? `${d.overdue.count} ${d.overdue.count === 1 ? "conta" : "contas"}` : "nada vencido", "previstos"],
    ["Dívidas", fmt(DT.saldo_devedor), DT.comprometimento != null ? `${fmt(DT.parcelas_mes)}/mês · ${pct(DT.comprometimento)} da renda` : `${fmt(DT.parcelas_mes)}/mês`, "dividas"],
    ["Faturas abertas", fmt(DT.faturas_abertas), DT.parcelas_cartao_futuras ? `+ ${fmt(DT.parcelas_cartao_futuras)} a cair` : "sem parcelas futuras", "dividas"],
    ["Saldo em 6 meses", last ? `${last.saldo < 0 ? "−" : ""}${fmt(Math.abs(last.saldo))}` : "–", proj.menor ? `menor: ${fmt(proj.menor.saldo)} em ${mlabel(proj.menor.month)}` : "", "projecao"],
  ];
  $("#home-big").innerHTML = big.map(([l, v, sub, go]) => `<button class="tile tile--link" data-big="${go}"><span class="tile__label">${l}</span>
    <span class="tile__value">${v}</span><span class="tile__sub">${sub}</span></button>`).join("");

  // saldo projetado: número grande + minigráfico
  if (last) {
    $("#h-proj-value").innerHTML = money(last.saldo);
    $("#h-proj-sub").textContent = `em ${mlabel(last.month)} · começa em ${fmt(proj.saldo_inicial)} (contas menos faturas)`;
    chart("chart-home-proj").setOption({
      animationDuration: 400, grid: { left: 0, right: 0, top: 8, bottom: 0, containLabel: true },
      tooltip: { ...baseOption().tooltip, trigger: "axis" },
      xAxis: { type: "category", data: proj.meses.map((x) => mlabel(x.month)), axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: "#6b7079", fontSize: 10 } },
      yAxis: { type: "value", show: false, scale: true },
      series: [{ type: "line", data: proj.meses.map((x) => x.saldo), smooth: true, symbol: "circle", symbolSize: 5, color: "#405fad",
        lineStyle: { width: 2 }, areaStyle: { color: "#e6ecfd", opacity: 0.8 },
        markLine: { symbol: "none", silent: true, label: { show: false }, lineStyle: { color: "#7f8a9c", type: "dashed" }, data: [{ yAxis: 0 }] } }],
    }, true);
  }

  // próximos vencimentos (previstos dos próximos 30 dias)
  $("#home-next").innerHTML = (d.proximos || []).map((o) => `<div class="az-insight">${well(esc(initials(o.name)))}
    <div class="az-insight__text"><div class="az-insight__title">${esc(o.name)}</div><div class="az-insight__desc">vence ${dlabel(o.due)}</div></div>
    <div class="tx-right"><span class="amount ${o.kind === "receita" ? "in" : ""}">${money(o.kind === "receita" ? o.amount : -o.amount, { plus: true })}</span></div></div>`).join("")
    || '<p class="hint" style="margin:0">Nada vencendo nos próximos 30 dias. Cadastre contas e receitas em Planejamento → Previstos.</p>';

  // destaques escritos como constatação + o que significa (InsightRow)
  const ins = [];
  if (d.overdue && d.overdue.count) {
    const names = d.overdue.items.map((o) => o.name).slice(0, 2).join(", ");
    ins.push({ icon: "clock", title: `${d.overdue.count} ${d.overdue.count === 1 ? "conta em atraso" : "contas em atraso"}`,
      desc: `${fmt(d.overdue.total)} vencidos · ${names}${d.overdue.count > 2 ? "…" : ""}`, go: "atrasos" });
  }
  if (d.uncategorized) {
    ins.push({ icon: "tag", title: `${d.uncategorized} ${d.uncategorized === 1 ? "lançamento sem categoria" : "lançamentos sem categoria"}`,
      desc: "Categorize para o orçamento ficar certo", go: "review" });
  }
  if (T.despesas_orcadas) {
    const left = T.despesas_orcadas - T.despesas;
    ins.push({ icon: "chart", title: `Gastos em ${pct(T.despesas / T.despesas_orcadas)} do orçamento`,
      desc: left >= 0 ? `Ainda pode gastar ${fmt(left)} este mês` : `${fmt(-left)} acima do orçado`, go: "planejamento" });
  } else {
    ins.push({ icon: "chart", title: `Gastos de ${fmt(T.despesas)} no mês`, desc: "Defina um orçamento para acompanhar", go: "planejamento" });
  }
  const moves = d.groups.filter((g) => g.group !== "Sem categoria").map((g) => {
    const cur = g.values[g.values.length - 1], prev = g.values[g.values.length - 2];
    return { group: g.group, cur, prev, ch: prev > 0 && cur > 0 ? cur / prev - 1 : null };  // só compara meses com gasto nos dois
  }).filter((m) => m.ch != null && Math.abs(m.ch) >= 0.1).sort((a, b) => Math.abs(b.cur - b.prev) - Math.abs(a.cur - a.prev));
  if (moves.length) {
    const m = moves[0];
    ins.push({ icon: m.ch > 0 ? "up" : "down", title: `${m.group} ${m.ch > 0 ? "subiu" : "caiu"}`, badge: `${m.ch > 0 ? "+" : "−"}${pct(Math.abs(m.ch))}`,
      desc: `${fmt(m.cur)} neste mês contra ${fmt(m.prev)} no anterior`, go: "planejamento" });
  }
  if (DT.faturas_abertas || DT.parcelas_cartao_futuras) {
    ins.push({ icon: "card", title: `Faturas abertas somam ${fmt(DT.faturas_abertas)}`,
      desc: DT.parcelas_cartao_futuras ? `Mais ${fmt(DT.parcelas_cartao_futuras)} em parcelas a cair` : "Sem parcelas futuras", go: "dividas" });
  }
  if (DT.saldo_devedor) {
    ins.push({ icon: "debt", title: DT.comprometimento != null ? `Parcelas levam ${pct(DT.comprometimento)} da renda` : `Dívidas somam ${fmt(DT.saldo_devedor)}`,
      desc: `${fmt(DT.parcelas_mes)} por mês · saldo devedor ${fmt(DT.saldo_devedor)}`, go: "dividas" });
  }
  $("#home-insights").innerHTML = ins.map((i) => `<a class="az-insight" href="#" data-go="${i.go}">${well(ICON[i.icon])}
    <div class="az-insight__text"><div class="az-insight__title">${esc(i.title)}${i.badge ? `<span class="az-badge">${i.badge}</span>` : ""}</div>
    <div class="az-insight__desc">${esc(i.desc)}</div></div>${CHEV}</a>`).join("");

  const liquid = d.accounts.filter((a) => a.kind !== "cartao");
  const total = liquid.reduce((sum, a) => sum + Math.max(0, a.balance), 0);
  $("#home-accounts").innerHTML = liquid.map((a) => `<div class="az-insight">${well(esc(initials(a.name)))}
    <div class="az-insight__text"><div class="az-insight__title">${esc(a.name)}</div><div class="az-insight__desc">${KIND_LABEL[a.kind]} · ${esc(personName(a.owner_id))}</div></div>
    <div class="tx-right"><span class="amount">${money(a.balance)}</span><span class="tx-date share">${total > 0 && a.balance > 0 ? pct(a.balance / total) : ""}</span></div></div>`).join("")
    || '<p class="hint" style="margin:0">Nenhuma conta ainda. Envie o extrato OFX da conta em Importações para ver os saldos reais.</p>';

  // cartões desenhados sob o saldo (como o cartão da foto de referência)
  $("#home-cardviz").innerHTML = d.cards.map((c) => {
    const last4 = (c.name.match(/(\d{4})\s*$/) || [, "••••"])[1];
    const label = c.name.replace(/\s*\d{4}\s*$/, "").replace(/^Cartão\s+/i, "");
    return `<button class="cardviz" data-goto="dividas" aria-label="Fatura do ${esc(c.name)}">
      <span class="cardviz__brand">${esc(label)}</span><span class="cardviz__chip"></span>
      <span class="cardviz__num">•••• ${esc(last4)}</span>
      <span class="cardviz__foot"><span><small>${c.configured ? `Fatura ${mlabel(c.invoice.month)}` : "Fatura atual"}</small>${money(c.invoice.amount)}</span>
        <span><small>Vence</small>${c.configured ? dlabel(c.invoice.due) : "–"}</span></span></button>`;
  }).join("");
  $("#home-cardviz").hidden = !d.cards.length;
  applyHidden();

  const recent = await api("GET", withPerson("/api/transactions?limit=5"));
  $("#home-recent").innerHTML = recent.map((t) => txRow(t)).join("") || '<p class="hint">Nenhum lançamento ainda.</p>';

  $("#home-groups").innerHTML = d.groups.length ? d.groups.map((g) => {
    const max = Math.max(...g.values, 1), cur = g.values[g.values.length - 1];
    const withData = g.values.filter((v) => v > 0);
    const avg = withData.length ? withData.reduce((a, b) => a + b, 0) / withData.length : 0;
    const bars = g.values.map((v, i) => `<i class="${i === g.values.length - 1 ? "on" : ""}" style="height:${Math.max(6, (v / max) * 100)}%" title="${mlabel(g.months[i])}: ${fmt(v)}"></i>`).join("");
    return `<div class="az-insight cat-row">${well(esc(initials(g.group)))}<div class="az-insight__text"><div class="az-insight__title">${esc(g.group)}</div>
      <div class="az-insight__desc">média ${fmt(avg)}/mês</div></div><div class="spark">${bars}</div>
      <div class="tx-right"><span class="amount">${money(cur)}</span></div></div>`;
  }).join("") : '<p class="hint">Sem gastos categorizados ainda.</p>';
}
document.addEventListener("click", (e) => {
  const review = e.target.closest("#home-insights [data-go=review]");
  const go = e.target.closest("#home-insights [data-go]");
  const recent = e.target.closest("#home-recent .tx-row");
  if (recent) {
    state.tx.status = "";
    goTab("lancamentos");
    return;
  }
  if (review) {
    e.preventDefault();
    state.tx.status = "revisar";
    goTab("lancamentos");
  } else if (go) {
    e.preventDefault();
    if (go.dataset.go === "atrasos") {
      state.plan.view = "previstos";
      return goTab("planejamento");
    }
    goTab(go.dataset.go);
  }
});

// ------------------------------------------------------------------ LANÇAMENTOS
async function renderLancamentos() {
  const f = state.tx;
  $("#tx-month").value = f.month.slice(0, 7);
  $("#tx-account").innerHTML = accountOptions(f.account ? +f.account : null, { all: true, label: "Todas as contas" });
  if (isMobile()) $("#tx-account").options[0].textContent = "Contas";
  $$("#tx-status button").forEach((b) => b.classList.toggle("active", b.dataset.s === f.status));
  $("#tx-q").value = f.q;
  const pending = f.status !== "";
  $(".filters .month-nav", $("#tab-lancamentos")).classList.toggle("dim", pending);
  $("#tx-status-hint").textContent = pending ? "mostrando todos os meses" : "";
  const params = new URLSearchParams();
  if (!pending) params.set("month", f.month);
  if (f.account) params.set("account_id", f.account);
  if (f.status) params.set("status", f.status);
  if (f.q) params.set("q", f.q);
  f.rows = await api("GET", withPerson(`/api/transactions?${params}`));
  const ins = f.rows.filter((t) => t.amount > 0 && catById(t.category_id)?.type !== "transferencia").reduce((s, t) => s + t.amount, 0);
  const outs = f.rows.filter((t) => t.amount < 0 && catById(t.category_id)?.type !== "transferencia").reduce((s, t) => s - t.amount, 0);
  $("#tx-summary").innerHTML = tile("Entradas", fmt(ins)) + tile("Saídas", fmt(outs)) + tile("Lançamentos", String(f.rows.length));
  renderTxList();
}

function txBadge(t) {
  if (!t.category_id) return '<span class="badge">sem categoria</span>';
  if (t.categorized_by === "ia" && !t.reviewed) return `<span class="badge ai" title="Sugerido pela IA">${SPARKLE}IA ${pct(t.confidence)}</span>`;
  return "";
}

// linha de lançamento: monograma, descrição, categoria · conta, valor e a data embaixo do valor
function txRow(t, { select = false } = {}) {
  const cat = catById(t.category_id), acc = accById(t.account_id);
  const inst = t.installment ? ` · parcela ${t.installment[0]}/${t.installment[1]}` : "";
  return `<div class="az-insight tx-row" data-id="${t.id}">
    ${select ? `<label class="tx-check" title="Selecionar"><input type="checkbox" data-sel="${t.id}" ${state.tx.selected.has(t.id) ? "checked" : ""}></label>` : ""}
    ${well(esc(initials(t.merchant || t.description)))}
    <div class="az-insight__text"><div class="az-insight__title">${esc(t.description)}</div>
      <div class="az-insight__desc">${esc(cat ? cat.name : "Sem categoria")} · ${esc(acc ? acc.name : "")}${inst} ${txBadge(t)}</div></div>
    <div class="tx-right"><span class="amount ${t.amount > 0 ? "in" : ""}">${money(t.amount, { plus: true })}</span>
      <span class="tx-date">${dlabel(t.date)}</span></div></div>`;
}

function renderTxList() {
  const f = state.tx;
  if (!f.rows.length) {
    $("#tx-list").innerHTML = `<p class="hint" style="margin:0">${f.status ? "Nada pendente. Tudo categorizado." : "Nenhum lançamento neste mês. Envie um extrato em Importações."}</p>`;
    updateBulk();
    return;
  }
  $("#tx-list").innerHTML = f.rows.map((t) => txRow(t, { select: true })).join("");
  updateBulk();
}

function updateBulk() {
  const n = state.tx.selected.size;
  $("#bulkbar").hidden = n === 0;
  $("#bulk-count").textContent = `${n} ${n === 1 ? "selecionado" : "selecionados"}`;
  if (n && !$("#bulk-cat").options.length) $("#bulk-cat").innerHTML = categoryOptions(null, { allowNone: false });
}

$("#tx-list").addEventListener("click", (e) => {
  const sel = e.target.closest("[data-sel]");
  if (sel) {
    const id = +sel.dataset.sel;
    sel.checked ? state.tx.selected.add(id) : state.tx.selected.delete(id);
    return updateBulk();
  }
  if (e.target.closest(".tx-check")) return;
  const row = e.target.closest(".tx-row");
  if (row) openTxSheet(state.tx.rows.find((t) => t.id === +row.dataset.id));
});

function openTxSheet(t) {
  const acc = accById(t.account_id);
  const ia = t.categorized_by === "ia" && !t.reviewed;
  openSheet(`<p class="overline">${dlabel(t.date)}/${t.date.slice(0, 4)} · ${esc(acc ? acc.name : "")}</p>
    <h2 style="margin:0 0 4px">${t.amount < 0 ? "−" : ""}${fmt2(Math.abs(t.amount))}</h2>
    <p class="hint">${esc(t.description)}${t.installment ? ` · parcela ${t.installment[0]} de ${t.installment[1]}` : ""}</p>
    ${ia ? `<p class="hint">Sugestão da IA com ${pct(t.confidence)} de confiança. Confirme ou troque.</p>` : ""}
    <label class="field">Categoria<select id="sh-cat">${categoryOptions(t.category_id)}</select></label>
    <label class="check" style="margin-top:12px"><input type="checkbox" id="sh-learn" checked> Lembrar para “${esc(t.merchant)}” e corrigir os parecidos</label>
    <label class="field" style="margin-top:12px">Observação<input id="sh-notes" value="${esc(t.notes || "")}"></label>
    <div class="row" style="margin-top:16px"><button class="primary" id="sh-save">Salvar</button>
      <button class="danger" id="sh-del">Excluir</button></div>`);
  $("#sh-save").onclick = async () => {
    const cid = sheetVal("sh-cat") ? +sheetVal("sh-cat") : null;
    const body = { notes: sheetVal("sh-notes") || null, learn: $("#sh-learn").checked };
    if (cid !== t.category_id || ia) body.category_id = cid;
    if (cid) body.reviewed = true;
    const r = await api("PATCH", `/api/transactions/${t.id}`, body);
    closeSheet();
    toast(r.similar_updated ? `Salvo e ${r.similar_updated} parecido(s) corrigido(s)` : "Salvo");
    await renderLancamentos();
  };
  $("#sh-del").onclick = async () => {
    if (!confirm("Excluir este lançamento?")) return;
    await api("DELETE", `/api/transactions/${t.id}`);
    closeSheet();
    await renderLancamentos();
  };
}

$("#tx-status").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-s]");
  if (!b) return;
  state.tx.status = b.dataset.s;
  state.tx.selected.clear();
  renderLancamentos();
});
$("#tx-month").addEventListener("change", (e) => { if (e.target.value) { state.tx.month = e.target.value + "-01"; state.tx.status = ""; renderLancamentos(); } });
$("#tx-prev").onclick = () => { state.tx.month = addMonths(state.tx.month, -1); state.tx.status = ""; renderLancamentos(); };
$("#tx-next").onclick = () => { state.tx.month = addMonths(state.tx.month, 1); state.tx.status = ""; renderLancamentos(); };
$("#tx-account").addEventListener("change", (e) => { state.tx.account = e.target.value; renderLancamentos(); });
let qTimer;
$("#tx-q").addEventListener("input", (e) => {
  clearTimeout(qTimer);
  qTimer = setTimeout(() => { state.tx.q = e.target.value.trim(); renderLancamentos(); }, 300);
});
$("#bulk-apply").onclick = async () => {
  const ids = [...state.tx.selected];
  const r = await api("POST", "/api/transactions/bulk-category", { ids, category_id: +$("#bulk-cat").value });
  state.tx.selected.clear();
  toast(`${r.updated} categorizado(s)${r.similar_updated ? ` e ${r.similar_updated} parecido(s)` : ""}`);
  await renderLancamentos();
};
$("#bulk-clear").onclick = () => { state.tx.selected.clear(); renderTxList(); };
function openNewTx() {
  if (!state.accounts.length) return toast("Cadastre uma conta em Ajustes ou importe um extrato");
  openSheet(`<p class="overline">Novo lançamento</p><h2>Lançar à mão</h2>
    <div class="form">
      <label class="field">Data<input id="sh-date" type="date" value="${new Date().toISOString().slice(0, 10)}"></label>
      <label class="field">Valor (− saída, + entrada)<input id="sh-amount" inputmode="decimal" placeholder="-50,00"></label>
    </div>
    <label class="field">Descrição<input id="sh-desc"></label>
    <div class="form"><label class="field">Conta<select id="sh-acc">${accountOptions(state.accounts[0].id)}</select></label>
      <label class="field">Categoria<select id="sh-cat">${categoryOptions(null)}</select></label></div>
    <div class="row" style="margin-top:16px"><button class="primary" id="sh-save">Salvar</button></div>`);
  $("#sh-save").onclick = async () => {
    const amount = parseNum(sheetVal("sh-amount"));
    if (amount == null || amount === undefined || !sheetVal("sh-desc")) return toast("Informe valor e descrição");
    await api("POST", "/api/transactions", { account_id: +sheetVal("sh-acc"), date: sheetVal("sh-date"), amount,
      description: sheetVal("sh-desc"), category_id: sheetVal("sh-cat") ? +sheetVal("sh-cat") : null });
    closeSheet();
    toast("Lançamento salvo");
    await renderLancamentos();
  };
}
// ------------------------------------------------------------------ ADICIONAR (rápido): despesa ou receita, já acontecida ou prevista
// Um só formulário: valor primeiro, descrição (a categoria é sugerida pelo texto), categoria em um toque e "quando".
// "Já paguei/recebi" vira lançamento numa conta; "Vou pagar/receber" vira previsto (uma vez ou todo mês).
const QA_LAST_ACC = "financi-qa-conta";
const today = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60e3).toISOString().slice(0, 10);
const shiftDay = (iso, n) => { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };

async function openQuickAdd(preset = {}) {
  const q = await api("GET", "/api/quick");
  const banks = state.accounts.filter((a) => a.active);
  const v = { kind: "despesa", when: banks.length ? "ja" : "vai", rec: "pontual", date: today(), month: thisMonth(), ...preset };
  let catId = null, catTouched = false, more = false;
  const remembered = +store("l", QA_LAST_ACC);
  const accId = banks.some((a) => a.id === remembered) ? remembered : q.account_id ?? banks[0]?.id;
  openSheet(`<div class="qa">
    <div class="segmented qa-kind" id="qa-kind"><button data-k="despesa">Despesa</button><button data-k="receita">Receita</button></div>
    <label class="qa-amount"><span>R$</span><input id="qa-amount" inputmode="decimal" placeholder="0,00" autocomplete="off" aria-label="Valor"></label>
    <input id="qa-desc" class="qa-desc" placeholder="Descrição" autocomplete="off" aria-label="Descrição">
    <p class="overline imp-label">Categoria</p>
    <div class="qa-chips" id="qa-cats"></div>
    <select id="qa-cat-all" aria-label="Outra categoria" hidden></select>
    <p class="overline imp-label">Quando</p>
    <div class="segmented qa-when" id="qa-when"><button data-w="ja"></button><button data-w="vai"></button></div>
    <div id="qa-ja" class="qa-sub">
      <div class="qa-chips" id="qa-days"><button data-d="0">Hoje</button><button data-d="-1">Ontem</button><label class="qa-date"><input type="date" id="qa-date" aria-label="Outra data"></label></div>
      ${banks.length ? `<label class="field">Conta<select id="qa-acc">${banks.map((a) => `<option value="${a.id}" ${a.id === accId ? "selected" : ""}>${esc(a.name)}</option>`).join("")}</select></label>`
        : '<p class="hint">Para lançar o que já aconteceu, cadastre uma conta em Ajustes ou importe um extrato.</p>'}
    </div>
    <div id="qa-vai" class="qa-sub">
      <div class="segmented" id="qa-rec"><button data-r="pontual">Uma vez</button><button data-r="mensal">Todo mês</button></div>
      <div class="form">
        <label class="field"><span id="qa-month-t">Mês</span>${monthInput("qa-month", v.month)}</label>
        <label class="field">Dia (opcional)<input id="qa-day" inputmode="numeric" placeholder="vencimento"></label>
        <label class="field" id="qa-end-l">Até (opcional)${monthInput("qa-end", null)}</label>
      </div>
    </div>
    <div class="qa-actions"><button class="primary" id="qa-save">Salvar</button><button class="secondary" id="qa-again">Salvar e adicionar outra</button></div>
    <button class="link qa-more" id="qa-more" type="button">Mais opções</button>
  </div>`);
  const kindCats = () => state.categories.filter((c) => c.type === v.kind && c.active);
  const paintCats = () => {
    const ids = q.frequent[v.kind] || [];
    const chosenExtra = catId && !ids.includes(catId) ? [catId] : [];
    $("#qa-cats").innerHTML = [...ids, ...chosenExtra].map((id) => catById(id)).filter(Boolean)
      .map((c) => `<button data-c="${c.id}" class="${c.id === catId ? "on" : ""}">${esc(c.name)}</button>`).join("") +
      `<button data-c="more" class="${more ? "on" : ""}">Outras…</button>`;
    $("#qa-cat-all").hidden = !more;
    $("#qa-cat-all").innerHTML = '<option value="">Escolha a categoria</option>' + kindCats().map((c) => `<option value="${c.id}" ${c.id === catId ? "selected" : ""}>${esc(c.name)}</option>`).join("");
  };
  const sync = () => {
    $$("#qa-kind button").forEach((b) => b.classList.toggle("active", b.dataset.k === v.kind));
    $$("#qa-when button").forEach((b) => {
      b.classList.toggle("active", b.dataset.w === v.when);
      b.textContent = b.dataset.w === "ja" ? (v.kind === "despesa" ? "Já paguei" : "Já recebi") : (v.kind === "despesa" ? "Vou pagar" : "Vou receber");
    });
    $$("#qa-rec button").forEach((b) => b.classList.toggle("active", b.dataset.r === v.rec));
    $("#qa-ja").hidden = v.when !== "ja";
    $("#qa-vai").hidden = v.when !== "vai";
    $("#qa-end-l").hidden = v.rec !== "mensal";
    $("#qa-month-t").textContent = v.rec === "mensal" ? "A partir de" : "Mês";
    const d = v.date === today() ? "0" : v.date === shiftDay(today(), -1) ? "-1" : null;
    $$("#qa-days [data-d]").forEach((b) => b.classList.toggle("on", b.dataset.d === d));
    $(".qa-date").classList.toggle("on", d === null);
    $("#qa-date").value = v.date;
    $("#qa-save").textContent = v.when === "ja" ? "Salvar" : "Salvar previsto";
    paintCats();
  };
  sync();
  setTimeout(() => $("#qa-amount").focus(), 30);

  $("#qa-kind").onclick = (e) => { const b = e.target.closest("[data-k]"); if (b && b.dataset.k !== v.kind) { v.kind = b.dataset.k; catId = null; catTouched = false; more = false; sync(); guess(); } };
  $("#qa-when").onclick = (e) => {
    const b = e.target.closest("[data-w]");
    if (!b) return;
    if (b.dataset.w === "ja" && !banks.length) return toast("Cadastre uma conta em Ajustes para lançar o que já aconteceu");
    v.when = b.dataset.w; sync();
  };
  $("#qa-rec").onclick = (e) => { const b = e.target.closest("[data-r]"); if (b) { v.rec = b.dataset.r; sync(); } };
  $("#qa-days").onclick = (e) => { const b = e.target.closest("[data-d]"); if (b) { v.date = shiftDay(today(), +b.dataset.d); sync(); } };
  $("#qa-date").onchange = (e) => { if (e.target.value) { v.date = e.target.value; sync(); } };
  $("#qa-cats").onclick = (e) => {
    const b = e.target.closest("[data-c]");
    if (!b) return;
    if (b.dataset.c === "more") { more = !more; }
    else { catId = catId === +b.dataset.c ? null : +b.dataset.c; catTouched = true; }
    paintCats();
  };
  $("#qa-cat-all").onchange = (e) => { catId = e.target.value ? +e.target.value : null; catTouched = true; more = false; paintCats(); };
  // a categoria vem sozinha pela descrição (regras e previstos com o mesmo nome) enquanto não for escolhida à mão
  let gt;
  const guess = () => {
    clearTimeout(gt);
    gt = setTimeout(async () => {
      const text = $("#qa-desc")?.value.trim();
      if (!text || catTouched) return;
      const r = await api("GET", `/api/quick/guess?kind=${v.kind}&description=${encodeURIComponent(text)}`).catch(() => null);
      if (r && !catTouched && $("#qa-desc")?.value.trim() === text) { catId = r.category_id; paintCats(); }
    }, 350);
  };
  $("#qa-desc").oninput = guess;

  const save = async (again) => {
    const amount = parseNum($("#qa-amount").value);
    const desc = $("#qa-desc").value.trim();
    if (!amount || amount < 0) { $("#qa-amount").focus(); return toast("Informe o valor"); }
    if (!desc) { $("#qa-desc").focus(); return toast("Informe a descrição"); }
    let undo;
    if (v.when === "ja") {
      const acc = +$("#qa-acc").value;
      store("l", QA_LAST_ACC, String(acc));
      const t = await api("POST", "/api/transactions", { account_id: acc, date: v.date, amount: v.kind === "despesa" ? -amount : amount,
        description: desc, category_id: catId });
      undo = () => api("DELETE", `/api/transactions/${t.id}`);
    } else {
      if (!$("#qa-month").value) return toast("Informe o mês");
      const p = await api("POST", "/api/planned", { name: desc, kind: v.kind, amount, recurrence: v.rec, start_month: $("#qa-month").value + "-01",
        end_month: v.rec === "mensal" && $("#qa-end").value ? $("#qa-end").value + "-01" : null,
        due_day: parseInt($("#qa-day").value, 10) || null, category_id: catId, owner_id: null, match_pattern: null });
      undo = () => api("DELETE", `/api/planned/${p.id}`);
    }
    const what = `${v.kind === "despesa" ? "Despesa" : "Receita"} de ${fmt2(amount)} ${v.when === "ja" ? "lançada" : "prevista"}`;
    toast(what, { label: "Desfazer", run: async () => { await undo(); toast("Desfeito"); refresh(); } });
    if (again) {
      $("#qa-amount").value = ""; $("#qa-desc").value = ""; catId = null; catTouched = false; more = false;
      paintCats(); $("#qa-amount").focus();
    } else closeSheet();
    refresh();
  };
  $("#qa-save").onclick = () => save(false);
  $("#qa-again").onclick = () => save(true);
  $("#qa-amount").onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); $("#qa-desc").focus(); } };
  $("#qa-desc").onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); save(false); } };
  // previsto com tudo (de quem, texto no extrato): abre o formulário completo com o que já foi preenchido
  $("#qa-more").onclick = () => {
    const amount = parseNum($("#qa-amount").value);
    if (v.when === "ja") return openNewTx();
    openPlannedSheet(null, { name: $("#qa-desc").value.trim(), kind: v.kind, amount: amount || null, recurrence: v.rec,
      start_month: ($("#qa-month").value || thisMonth().slice(0, 7)) + "-01", category_id: catId, due_day: parseInt($("#qa-day").value, 10) || null });
  };
}
$("#tx-add").onclick = () => openQuickAdd({ when: "ja" });
$("#tx-add-m").onclick = () => openQuickAdd({ when: "ja" });
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-quick]");
  if (b) openQuickAdd(b.dataset.quick === "receita" ? { kind: "receita" } : {});
});

// ------------------------------------------------------------------ IMPORTAR
async function renderImportar() {
  $("#imp-account").innerHTML = `<option value="">Reconhecer pelo arquivo</option>` + accountOptions(null);
  $("#imp-owner").innerHTML = peopleOptions(null);
  const hist = await api("GET", "/api/imports");
  $("#imp-history").innerHTML = hist.length ? `<thead><tr><th>Arquivo</th><th>Conta</th><th>Período</th><th>Novos</th><th>Repetidos</th><th>Regra</th><th>IA</th><th>Sem cat.</th><th></th></tr></thead><tbody>` +
    hist.map((b) => `<tr><td>${esc(b.filename)}</td><td>${esc(b.account || "–")}</td><td>${dlabel(b.period[0])} a ${dlabel(b.period[1])}</td>
      <td>${b.new}</td><td>${b.duplicates}</td><td>${b.by_rule}</td><td>${b.by_ai}</td><td>${b.uncategorized}</td>
      <td><button class="sm" data-undo="${b.id}">Desfazer</button></td></tr>`).join("") + "</tbody>"
    : '<tbody><tr><td class="muted">Nenhuma importação ainda.</td></tr></tbody>';
}

async function importFiles(files) {
  const out = $("#imp-results");
  for (const file of files) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `<p class="hint" style="margin:0">Importando ${esc(file.name)}…</p>`;
    out.prepend(card);
    const fd = new FormData();
    fd.append("file", file);
    if ($("#imp-account").value) fd.append("account_id", $("#imp-account").value);
    if ($("#imp-owner").value) fd.append("owner_id", $("#imp-owner").value);
    try {
      const r = await api("POST", "/api/imports", fd);
      card.innerHTML = `<div class="card-head"><h3>${esc(file.name)}</h3><span class="badge ${r.account.created ? "tint" : ""}">${r.account.created ? "conta criada" : "conta reconhecida"}</span></div>
        <p class="hint" style="margin:0">${esc(r.account.name)} · ${KIND_LABEL[r.account.kind]} · ${dlabel(r.period[0])} a ${dlabel(r.period[1])}</p>
        <div class="tiles">${[["Novos", r.new], ["Repetidos (ignorados)", r.duplicates], ["Por regra", r.by_rule],
          ["Pela IA", r.ai_enabled ? r.by_ai : "desligada"], ["Sem categoria", r.uncategorized]]
          .map(([l, v]) => tile(l, v)).join("")}</div>
        ${r.uncategorized ? `<button class="primary" data-review>Revisar ${r.uncategorized} sem categoria</button>` : ""}
        ${r.account.kind === "cartao" && r.account.created ? `<p class="hint">Cartão novo: informe o dia de fechamento e de vencimento em Ajustes para o app calcular as faturas.</p>` : ""}`;
    } catch (err) {
      card.innerHTML = `<h3>${esc(file.name)}</h3><p class="hint">Não foi possível importar: ${esc(err.message)}</p>`;
    }
  }
  await loadBase();
  await renderImportar();
}
// planilha de planejamento (modelo .xlsx): previstos, atrasos, dívidas e orçamento
// por seção e em dois modos: adicionar (soma) ou substituir (apaga a seção que a planilha traz e sobe de novo)
const SECTION_NAMES = { receitas: "Receitas", despesas: "Despesas previstas", atrasos: "Atrasos", dividas: "Dívidas", orcamento: "Orçamento" };
state.xlsxMode = "adicionar";
function syncXlsxMode() {
  $$("#xlsx-mode button").forEach((b) => b.classList.toggle("active", b.dataset.m === state.xlsxMode));
  $("#xlsx-mode-hint").textContent = state.xlsxMode === "adicionar"
    ? "Soma ao que já existe. O que já existir igual é ignorado."
    : "Apaga tudo das seções marcadas que a planilha trouxer (inclusive o cadastrado no app) e importa de novo. Seções que a planilha não traz ficam como estão.";
}
syncXlsxMode();
$("#xlsx-mode").addEventListener("click", (e) => {
  const b = e.target.closest("[data-m]");
  if (b) { state.xlsxMode = b.dataset.m; syncXlsxMode(); }
});
$("#xlsx-file").addEventListener("click", (e) => {
  const secoes = $$("#xlsx-sections input:checked").map((i) => SECTION_NAMES[i.value]);
  if (!secoes.length) { e.preventDefault(); return toast("Marque pelo menos uma seção"); }
  if (state.xlsxMode === "substituir" && !confirm(`Substituir: o que houver de ${secoes.join(", ")} na planilha vai trocar o que existe hoje nessas seções. Continuar?`)) e.preventDefault();
});
$("#xlsx-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file) return;
  const out = $("#xlsx-result");
  out.innerHTML = `<p class="hint" style="margin:var(--space-3) 0 0">Importando ${esc(file.name)}…</p>`;
  const fd = new FormData();
  fd.append("file", file);
  const secoes = $$("#xlsx-sections input:checked").map((i) => i.value);
  fd.append("secoes", secoes.join(","));
  fd.append("modo", state.xlsxMode);
  try {
    const r = await api("POST", "/api/imports/planilha", fd);
    const apag = Object.entries(r.apagados || {}).map(([k, n]) => `${SECTION_NAMES[k]} (${n})`).join(", ");
    // só as seções que vieram na planilha (importar só dívidas não mostra zeros nas outras)
    const got = new Set(r.secoes || []);
    const tiles = [["Previstos", r.previstos, got.has("receitas") || got.has("despesas")], ["Atrasos", r.atrasos, got.has("atrasos")],
      ["Dívidas", r.dividas, got.has("dividas")], ["Orçamento", r.orcamento, got.has("orcamento")]].filter((x) => x[2]);
    out.innerHTML = `${tiles.length ? `<div class="tiles" style="margin-top:var(--space-4)">${tiles.map(([l, v]) => tile(l, v)).join("")}</div>`
      : `<p class="hint" style="margin-top:var(--space-4)">Nada das seções marcadas veio na planilha.</p>`}
      ${apag ? `<p class="hint">Apagado antes de importar: ${esc(apag)}.</p>` : ""}
      ${r.ignorados ? `<p class="hint">${r.ignorados} já existiam iguais e foram ignorados.</p>` : ""}
      ${r.pessoas_criadas.length ? `<p class="hint">Pessoas criadas: ${esc(r.pessoas_criadas.join(", "))}.</p>` : ""}
      ${r.avisos.length ? `<details class="warnings"><summary>${r.avisos.length} ${r.avisos.length === 1 ? "aviso" : "avisos"}</summary><ul>${r.avisos.map((a) => `<li>${esc(a)}</li>`).join("")}</ul></details>` : ""}
      <div class="row"><button class="secondary" data-goto-plan="previstos">Ver previstos</button><button data-goto="dividas">Ver dívidas</button></div>`;
    await loadBase();
    toast("Planilha importada");
  } catch (err) {
    out.innerHTML = `<p class="hint" style="margin:var(--space-3) 0 0">Não foi possível importar: ${esc(err.message)}</p>`;
  }
});
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-goto-plan], [data-big]");
  if (!b) return;
  const target = b.dataset.gotoPlan || b.dataset.big;
  if (["orcamento", "previstos", "mes", "tabela", "projecao", "fluxo"].includes(target)) {
    state.plan.view = target;
    return goTab("planejamento");
  }
  if (target === "lancamentos") state.tx.status = "";
  goTab(target);
});
$("#ofx-files").addEventListener("change", (e) => { importFiles([...e.target.files]); e.target.value = ""; });
const dz = $("#dropzone");
["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, () => dz.classList.remove("over")));
dz.addEventListener("drop", (e) => { e.preventDefault(); importFiles([...e.dataTransfer.files]); });
$("#imp-results").addEventListener("click", (e) => { if (e.target.closest("[data-review]")) { state.tx.status = "sem_categoria"; goTab("lancamentos"); } });
$("#imp-history").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-undo]");
  if (!b || !confirm("Desfazer esta importação? Os lançamentos que ela trouxe serão apagados.")) return;
  await api("DELETE", `/api/imports/${b.dataset.undo}`);
  toast("Importação desfeita");
  await renderImportar();
});

// ------------------------------------------------------------------ PLANEJAMENTO (Mês | Fluxo)
// Modelo como nos apps de referência (Monarch, Simplifi, Copilot): o plano de um mês é
// Entradas − Contas fixas − Dívidas e parcelas − Gastos variáveis = Sobra prevista.
// O Fluxo mostra os próximos meses: linha do saldo e a tabela no formato de planilha.
const SECTION_INFO = {
  entradas: { title: "Entradas", add: "Nova entrada" },
  fixas: { title: "Contas fixas", add: "Nova conta fixa" },
  dividas: { title: "Dívidas e parcelas", add: "Ver dívidas" },
  variaveis: { title: "Gastos variáveis", add: "Orçar categoria" },
};
async function renderPlanejamento() {
  const view = state.plan.view === "cockpit" ? "cockpit" : ["fluxo", "tabela", "projecao"].includes(state.plan.view) ? "fluxo" : "mes";
  state.plan.view = view;
  $$("#plan-view button").forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  $("#pv-mes").hidden = view !== "mes";
  $("#pv-fluxo").hidden = view !== "fluxo";
  $("#pv-cockpit").hidden = view !== "cockpit";
  return view === "fluxo" ? renderFluxo() : view === "cockpit" ? renderCockpit() : renderMes();
}
$("#plan-view").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-view]");
  if (!b) return;
  state.plan.view = b.dataset.view;
  renderPlanejamento();
});

const STATUS_BADGE = { pago: '<span class="badge tint">pago</span>', atrasado: '<span class="badge strong">em atraso</span>',
  pulado: '<span class="badge">pulado</span>', pendente: "" };
const capFirst = (t) => t.charAt(0).toUpperCase() + t.slice(1);
function occKey(o) { return `${o.planned_id}|${o.original}`; }
function occRow(o, { late = false } = {}) {
  const cat = catById(o.category_id);
  const freq = o.recurrence === "pontual" ? "uma vez" : o.end_month ? `todo mês até ${mlabel(o.end_month)}` : "todo mês";
  const value = o.kind === "receita" ? o.amount : -o.amount;
  const where = late ? `venceu ${dlabel(o.due)}/${o.due.slice(2, 4)}` : `vence ${dlabel(o.due)}`;
  return `<div class="az-insight occ ${o.status}" data-occ="${occKey(o)}">${well(esc(initials(o.name)))}
    <div class="az-insight__text"><div class="az-insight__title">${esc(o.name)} ${STATUS_BADGE[o.status]}</div>
      <div class="az-insight__desc">${esc(cat ? cat.name : o.kind === "receita" ? "Receita" : "Despesa")} · ${freq} · ${where}${o.moved ? ` · movido de ${mlabel(o.original)}` : ""}</div></div>
    <div class="tx-right"><span class="amount ${o.kind === "receita" ? "in" : ""}">${money(value, { plus: true })}</span>
      ${late ? `<button class="sm secondary" data-pay="${occKey(o)}">Pago</button>` : ""}</div></div>`;
}


// ------------------------------------------------------------------ MÊS: plano de um mês
async function renderMes() {
  const month = state.plan.month || thisMonth();
  state.plan.month = month;
  $("#pm-month").textContent = capFirst(mlong(month));
  $("#pm-month").classList.toggle("is-current", month === thisMonth());
  const p = await api("GET", withPerson(`/api/plan?month=${month}`));
  state.planMonth = p;
  state.occ = {};
  const S = p.sections;
  const monthName = MESES_LONGOS[+month.slice(5, 7) - 1];

  // resumo: sobra prevista e para onde vai a renda
  $("#pm-sobra-label").textContent = p.sobra >= 0 ? `Sobra prevista em ${monthName}` : `Faltam em ${monthName}`;
  $("#pm-sobra").innerHTML = money(Math.abs(p.sobra));
  $("#pm-sobra").classList.toggle("short", p.sobra < 0);
  $("#pm-sub").textContent = `Entradas ${fmt(p.entradas)} − saídas previstas ${fmt(p.saidas)}`;
  const base = Math.max(p.entradas, p.saidas, 1);
  const parts = [["fixas", S.fixas.planned], ["dividas", S.dividas.planned], ["variaveis", S.variaveis.planned], ["sobra", Math.max(0, p.sobra)]];
  $("#pm-bar").innerHTML = parts.filter(([, v]) => v > 0).map(([k, v]) => `<i class="seg-${k}" style="width:${(v / base) * 100}%"></i>`).join("");
  const done = (k) => (S[k].actual ? `${fmt(S[k].actual)} ${k === "variaveis" ? "gasto" : "pago"}` : "");
  $("#pm-legend").innerHTML = [["fixas", "Contas fixas"], ["dividas", "Dívidas e parcelas"], ["variaveis", "Gastos variáveis"]]
    .map(([k, l]) => `<div class="pm-leg"><span class="dot seg-${k}"></span><span class="pm-leg__l">${l}</span>
      <span class="pm-leg__a">${done(k)}</span><b>${fmt(S[k].planned)}</b></div>`).join("") +
    `<div class="pm-leg"><span class="dot seg-sobra"></span><span class="pm-leg__l">${p.sobra >= 0 ? "Sobra" : "Falta"}</span><span class="pm-leg__a"></span><b>${fmt(Math.abs(p.sobra))}</b></div>`;
  // agrupamentos: só informativos, numa linha à parte (não entram na conta)
  $("#pm-info").hidden = !p.groupings.length;
  $("#pm-info").innerHTML = p.groupings.map((g) => `<div class="pm-info-row"><span>${esc(g.name)} <span class="tb-tag">informativo</span></span>
    <b>${money(g.value)}</b></div>`).join("");

  // em atraso (meses anteriores; os do próprio mês aparecem nas seções)
  $("#pm-late-card").hidden = !p.atrasos.length;
  $("#pm-late-total").innerHTML = money(-p.atrasos_total);
  $("#pm-late").innerHTML = p.atrasos.map((o) => { state.occ[occKey(o)] = o; return occRow(o, { late: true }); }).join("");

  $("#pm-sections").innerHTML = ["entradas", "fixas", "dividas", "variaveis"].map((k) => planSection(k, S[k], p)).join("");
}

function planSection(k, sec, p) {
  const info = SECTION_INFO[k];
  // seções longas mostram 5 linhas e "Ver todas" (no celular, 14 parcelas ocupam a tela inteira)
  const open = (state.plan.open || {})[k];
  const many = sec.items.length > 6 && !open;
  const rows = (many ? sec.items.slice(0, 5) : sec.items).map((r) => planRow(k, r)).join("") +
    (many ? `<button class="link pm-more" data-plan-more="${k}">Ver todas (${sec.items.length})</button>` : "");
  const sub = {
    entradas: sec.actual ? `${fmt(sec.actual)} recebido` : `${sec.items.length} ${sec.items.length === 1 ? "item" : "itens"}`,
    fixas: sec.actual ? `${fmt(sec.actual)} pago de ${fmt(sec.planned)}` : `${sec.items.length} ${sec.items.length === 1 ? "conta" : "contas"}`,
    dividas: `${sec.items.length} ${sec.items.length === 1 ? "parcela" : "parcelas"}`,
    variaveis: sec.actual ? `${fmt(sec.actual)} gasto de ${fmt(sec.planned)}` : "orçamento por categoria",
  }[k];
  const empty = {
    entradas: "Cadastre salário e outras entradas previstas.",
    fixas: "Aluguel, condomínio, escola, planos… com vencimento.",
    dividas: "Nenhuma parcela neste mês.",
    variaveis: "Defina quanto pretende gastar por categoria (mercado, transporte…).",
  }[k];
  const meter = k === "variaveis" && sec.planned ? `<div class="meter ${sec.actual > sec.planned ? "over" : ""}"><i style="width:${Math.min(100, (sec.actual / sec.planned) * 100)}%"></i></div>` : "";
  return `<div class="card pm-sec pm-sec--${k}">
    <div class="pm-sec__head"><div><h3>${info.title}</h3><p class="pm-sec__sub">${sub}</p></div><b class="pm-sec__total">${fmt(sec.planned)}</b></div>
    ${meter}
    <div class="list">${rows || `<p class="hint pm-empty">${empty}</p>`}</div>
    <div class="pm-sec__foot"><button class="link" data-plan-add="${k}">+ ${info.add}</button>
      ${k === "variaveis" ? '<button class="link" data-plan-suggest>Sugerir pela média</button>' : ""}</div>
  </div>`;
}

function planRow(k, r) {
  if (r.type === "previsto") {
    state.occ[occKey(r)] = r;
    const freq = r.recurrence === "pontual" ? "uma vez" : r.end_month ? `até ${mlabel(r.end_month)}` : "todo mês";
    const value = r.kind === "receita" ? r.amount : -r.amount;
    const status = { pago: r.kind === "receita" ? "recebido" : "pago", atrasado: "em atraso", pulado: "pulado", pendente: "" }[r.status];
    return `<div class="az-insight occ ${r.status}" data-occ="${occKey(r)}">${well(esc(initials(r.name)))}
      <div class="az-insight__text"><div class="az-insight__title">${esc(r.name)}</div>
        <div class="az-insight__desc">${r.kind === "receita" ? "cai" : "vence"} ${dlabel(r.due)} · ${freq}${r.moved ? ` · movido de ${mlabel(r.original)}` : ""}</div></div>
      <div class="tx-right"><span class="amount ${r.kind === "receita" ? "in" : ""}">${money(value, { plus: true })}</span>
        ${status ? `<span class="tx-date st-${r.status}">${status}</span>` : ""}</div></div>`;
  }
  if (r.type === "divida" || r.type === "cartao") {
    const desc = r.type === "divida" ? `${r.installment_n && r.installment_total ? `parcela ${r.installment_n} de ${r.installment_total}` : "parcela"}${r.due ? ` · dia ${r.due.slice(8, 10)}` : ""}` : "parcelas de compras";
    return `<div class="az-insight pm-debt" data-goto="dividas">${well(r.type === "cartao" ? ICON.card : esc(initials(r.name)))}
      <div class="az-insight__text"><div class="az-insight__title">${esc(r.name)}</div><div class="az-insight__desc">${desc}</div></div>
      <div class="tx-right"><span class="amount">${money(-r.amount)}</span></div></div>`;
  }
  // orçamento (gasto variável ou entrada orçada)
  const over = r.amount && r.actual > r.amount;
  const left = r.amount - r.actual;
  const desc = !r.amount ? `sem orçamento · ${fmt(r.actual)} gasto`
    : r.actual ? (over ? `${fmt(r.actual)} de ${fmt(r.amount)} · ${fmt(-left)} acima` : `${fmt(r.actual)} de ${fmt(r.amount)} · restam ${fmt(left)}`)
      : `${r.scope === "mes" ? "só neste mês" : "todo mês"} · nada gasto ainda`;
  return `<div class="az-insight pm-bud" data-bud="${r.category_id ?? ""}">${well(esc(initials(r.name)))}
    <div class="az-insight__text"><div class="az-insight__title">${esc(r.name)}</div><div class="az-insight__desc">${desc}</div>
      ${r.amount ? `<div class="meter ${over ? "over" : ""}"><i style="width:${Math.min(100, (r.actual / r.amount) * 100)}%"></i></div>` : ""}</div>
    <div class="tx-right"><span class="amount">${r.amount ? fmt2(r.amount) : "–"}</span></div></div>`;
}

$("#pm-prev").onclick = () => { state.plan.month = addMonths(state.plan.month || thisMonth(), -1); renderMes(); };
$("#pm-next").onclick = () => { state.plan.month = addMonths(state.plan.month || thisMonth(), 1); renderMes(); };
$("#pm-month").onclick = () => { state.plan.month = thisMonth(); renderMes(); };

$("#pv-mes").addEventListener("click", async (e) => {
  const pay = e.target.closest("[data-pay]");
  if (pay) {
    const o = state.occ[pay.dataset.pay];
    await api("PUT", `/api/planned/${o.planned_id}/occurrence`, { month: o.original, paid: true });
    toast(`${o.name}: marcado como pago`, { label: "Desfazer", run: async () => {
      await api("PUT", `/api/planned/${o.planned_id}/occurrence`, { month: o.original, paid: null });
      await renderMes();
    } });
    return renderMes();
  }
  const add = e.target.closest("[data-plan-add]");
  if (add) {
    const k = add.dataset.planAdd;
    if (k === "dividas") return goTab("dividas");
    if (k === "variaveis") return openAddBudgetSheet();
    return openPlannedSheet(null, { kind: k === "entradas" ? "receita" : "despesa", start_month: state.plan.month });
  }
  if (e.target.closest("[data-plan-suggest]")) return openSuggestSheet();
  const more = e.target.closest("[data-plan-more]");
  if (more) {
    state.plan.open = { ...(state.plan.open || {}), [more.dataset.planMore]: true };
    return renderMes();
  }
  const occ = e.target.closest("[data-occ]");
  if (occ) return openOccSheet(state.occ[occ.dataset.occ]);
  const bud = e.target.closest("[data-bud]");
  if (bud) {
    const row = state.planMonth.sections.variaveis.items.concat(state.planMonth.sections.entradas.items)
      .find((r) => r.type === "orcamento" && String(r.category_id ?? "") === bud.dataset.bud);
    if (row && row.category_id != null) openBudgetSheet(row);
  }
});

// orçamento de uma categoria: quanto pretende gastar (todo mês ou só neste mês)
function openBudgetSheet(row, isNew = false) {
  const m = state.plan.month;
  let scope = row.scope || "padrao";
  openSheet(`<p class="overline">Gastos variáveis · ${capFirst(mlong(m))}</p><h2>${esc(row.name)}</h2>
    <p class="hint">${row.actual ? `Gasto neste mês: ${fmt2(row.actual)}.` : "Nada gasto ainda neste mês."}</p>
    <label class="field">Quanto pretende gastar (R$)<input id="bg-amount" inputmode="decimal" value="${row.amount ? String(row.amount).replace(".", ",") : ""}" placeholder="0,00"></label>
    <div class="row" style="margin-top:var(--space-3)"><div class="segmented" id="bg-scope"><button data-s="padrao">Todo mês</button><button data-s="mes">Só em ${mlabel(m)}</button></div></div>
    <div class="row"><button class="primary" id="bg-save">Salvar</button>${row.amount && !isNew ? '<button class="danger" id="bg-del">Remover</button>' : ""}</div>`);
  const sync = () => $$("#bg-scope button").forEach((b) => b.classList.toggle("active", b.dataset.s === scope));
  sync();
  $("#bg-scope").onclick = (e) => { const b = e.target.closest("[data-s]"); if (b) { scope = b.dataset.s; sync(); } };
  const put = async (amount) => {
    await api("PUT", "/api/budgets", [{ category_id: row.category_id, month: scope === "mes" ? m : null, amount }]);
    closeSheet();
    await renderMes();
  };
  $("#bg-save").onclick = async () => {
    const amount = parseNum(sheetVal("bg-amount"));
    if (amount === undefined) return toast("Valor inválido");
    await put(amount ?? null);
    toast(amount ? `${row.name}: ${fmt(amount)} ${scope === "mes" ? `em ${mlabel(m)}` : "por mês"}` : "Orçamento removido");
  };
  $("#bg-del")?.addEventListener("click", async () => { await put(null); toast("Orçamento removido"); });
}
function openAddBudgetSheet() {
  const used = new Set(state.planMonth.sections.variaveis.items.filter((r) => r.amount).map((r) => r.category_id));
  const opts = state.categories.filter((c) => c.type === "despesa" && c.active && c.group !== "Dívidas" && !used.has(c.id));
  const groups = {};
  opts.forEach((c) => (groups[c.group] ||= []).push(c));
  openSheet(`<p class="overline">Gastos variáveis</p><h2>Orçar categoria</h2>
    <label class="field">Categoria<select id="ab-cat">${Object.entries(groups).map(([g, cs]) => `<optgroup label="${esc(g)}">${cs.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("")}</optgroup>`).join("")}</select></label>
    <div class="row"><button class="primary" id="ab-next">Continuar</button></div>`);
  $("#ab-next").onclick = () => {
    const c = catById(+sheetVal("ab-cat"));
    const row = state.planMonth.sections.variaveis.items.find((r) => r.category_id === c.id);
    openBudgetSheet({ category_id: c.id, name: c.name, amount: 0, actual: row ? row.actual : 0, scope: "padrao" }, true);
  };
}
async function openSuggestSheet() {
  const sug = (await api("GET", withPerson(`/api/budget/suggest?month=${state.plan.month}`))).filter((x) => x.type === "despesa" && catById(x.category_id)?.group !== "Dívidas");
  const have = new Map(state.planMonth.sections.variaveis.items.filter((r) => r.amount).map((r) => [r.category_id, r.amount]));
  openSheet(`<p class="overline">Gastos variáveis</p><h2>Sugestão pela média</h2>
    <p class="hint">Média dos últimos meses com extrato. Marque o que quer usar como orçamento de todo mês.</p>
    <div class="chk-list">${sug.length ? sug.map((x) => `<label class="chk-row"><input type="checkbox" value="${x.category_id}" data-amount="${x.amount}" ${have.has(x.category_id) ? "" : "checked"}>
      <span>${esc(x.name)}</span><b class="chk-val">${fmt(x.amount)}${have.has(x.category_id) ? ` <small>(hoje ${fmt(have.get(x.category_id))})</small>` : ""}</b></label>`).join("")
      : '<p class="hint">Ainda não há extratos suficientes para sugerir. Importe o extrato em Importações.</p>'}</div>
    <div class="row"><button class="primary" id="sg-apply" ${sug.length ? "" : "disabled"}>Aplicar</button></div>`);
  $("#sg-apply").onclick = async () => {
    const items = $$("#sheet .chk-list input:checked").map((i) => ({ category_id: +i.value, month: null, amount: +i.dataset.amount }));
    if (!items.length) return closeSheet();
    await api("PUT", "/api/budgets", items);
    closeSheet();
    toast(`${items.length} ${items.length === 1 ? "categoria orçada" : "categorias orçadas"}`);
    await renderMes();
  };
}

function monthInput(id, iso) {
  return `<div class="month-nav sheet-month"><button class="ghost icon" type="button" data-step="-1" data-for="${id}" aria-label="Mês anterior">‹</button>
    <input type="month" id="${id}" value="${iso ? iso.slice(0, 7) : ""}"><button class="ghost icon" type="button" data-step="1" data-for="${id}" aria-label="Próximo mês">›</button></div>`;
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("#sheet [data-step]");
  if (!b) return;
  const inp = $(`#${b.dataset.for}`);
  const base = inp.value ? inp.value + "-01" : thisMonth();
  inp.value = addMonths(base, +b.dataset.step).slice(0, 7);
  inp.dispatchEvent(new Event("change"));
});

// ocorrência: mudar só este mês (valor, mês), pagar, pular
function openOccSheet(o) {
  const recurring = o.recurrence === "mensal";
  const statusTxt = { pago: "pago", atrasado: "em atraso", pulado: "pulado", pendente: "a vencer" }[o.status];
  openSheet(`<p class="overline">${capFirst(mlong(o.month))} · ${statusTxt}${o.paid_auto ? " (achado no extrato)" : ""}</p>
    <h2 style="margin:0 0 4px">${esc(o.name)}</h2>
    <p class="hint">${recurring ? (o.end_month ? `Todo mês de ${mlabel(o.start_month)} a ${mlabel(o.end_month)}` : `Todo mês desde ${mlabel(o.start_month)}`) : "Uma vez"} · vence ${dlabel(o.due)}</p>
    <div class="form">
      <label class="field">${recurring ? "Valor neste mês" : "Valor"}<input id="oc-amount" inputmode="decimal" value="${String(o.amount).replace(".", ",")}"></label>
      <label class="field">${recurring ? "Mover este mês para" : "Mês"}${monthInput("oc-month", o.month)}</label>
    </div>
    <div class="row occ-actions">
      ${o.status === "pago" ? '<button id="oc-unpay">Desmarcar pago</button>' : '<button class="secondary" id="oc-pay">Marcar como pago</button>'}
      ${recurring ? (o.status === "pulado" ? '<button id="oc-unskip">Voltar a contar</button>' : '<button id="oc-skip">Pular este mês</button>') : ""}
    </div>
    <div class="row occ-links"><button class="link" id="oc-series">Editar previsão</button>
      ${recurring && (o.moved || o.changed || o.status === "pulado") ? '<button class="link" id="oc-reset">Desfazer ajustes deste mês</button>' : ""}</div>
    <div class="row"><button class="primary" id="oc-save">Salvar</button></div>`);
  const put = async (body, msg) => {
    await api("PUT", `/api/planned/${o.planned_id}/occurrence`, { month: o.original, ...body });
    closeSheet();
    if (msg) toast(msg);
    await renderPlanejamento();
  };
  $("#oc-save").onclick = async () => {
    const body = {};
    const amount = parseNum(sheetVal("oc-amount"));
    if (amount && Math.abs(amount - o.amount) > 0.001) body.amount = amount;
    const month = sheetVal("oc-month") ? sheetVal("oc-month") + "-01" : o.month;
    if (month !== o.month) body.moved_to = month;
    if (!Object.keys(body).length) return closeSheet();
    await put(body, body.moved_to ? `Movido para ${mlabel(body.moved_to)}` : "Valor deste mês salvo");
  };
  $("#oc-pay")?.addEventListener("click", () => put({ paid: true }, "Marcado como pago"));
  $("#oc-unpay")?.addEventListener("click", () => put({ paid: false }, "Desmarcado"));
  $("#oc-skip")?.addEventListener("click", () => put({ skipped: true }, "Este mês foi pulado"));
  $("#oc-unskip")?.addEventListener("click", () => put({ skipped: false }));
  $("#oc-reset")?.addEventListener("click", () => put({ reset: true }, "Ajustes deste mês desfeitos"));
  $("#oc-series").onclick = async () => {
    const all = await api("GET", "/api/planned");
    openPlannedSheet(all.find((x) => x.id === o.planned_id));
  };
}

// previsão (série): todo mês de um mês até outro, ou uma vez só
function openPlannedSheet(p, preset = {}) {
  const v = p || { kind: "despesa", recurrence: "mensal", start_month: addMonths(thisMonth(), 1), ...preset };
  openSheet(`<p class="overline">${p ? "Editar previsto" : "Novo previsto"}</p><h2>${p ? esc(p.name) : "Previsto"}</h2>
    <div class="row"><div class="segmented" id="pp-kind"><button data-k="despesa">Despesa</button><button data-k="receita">Receita</button></div></div>
    <div class="row"><div class="segmented" id="pp-rec"><button data-r="mensal">Todo mês</button><button data-r="pontual">Uma vez</button></div></div>
    <div class="form">
      <label class="field wide">Nome<input id="pp-name" value="${esc(v.name || "")}" placeholder="Escola, IPVA, aluguel novo…"></label>
      <label class="field">Valor (R$)<input id="pp-amount" inputmode="decimal" value="${v.amount ? String(v.amount).replace(".", ",") : ""}"></label>
      <label class="field">Dia do vencimento<input id="pp-day" inputmode="numeric" value="${v.due_day || ""}" placeholder="fim do mês"></label>
      <label class="field" id="pp-start-l"><span id="pp-start-t">A partir de</span>${monthInput("pp-start", v.start_month)}</label>
      <label class="field" id="pp-end-l">Até (opcional)${monthInput("pp-end", v.end_month)}</label>
      <label class="field wide">Categoria<select id="pp-cat">${categoryOptions(v.category_id ?? null)}</select></label>
      <label class="field">De quem<select id="pp-owner">${peopleOptions(v.owner_id ?? null)}</select></label>
      <label class="field">Texto no extrato<input id="pp-match" value="${esc(v.match_pattern || "")}" placeholder="ex.: ALUGUEL"></label>
    </div>
    <p class="hint">Com a categoria, a projeção usa este valor no lugar do orçamento dela nesses meses. “Texto no extrato”
      marca como pago quando o lançamento aparecer no extrato; sem ele, marque à mão.</p>
    <div class="row"><button class="primary" id="pp-save">Salvar</button>${p ? '<button class="danger" id="pp-del">Excluir</button>' : ""}</div>`);
  let kind = v.kind, rec = v.recurrence;
  const sync = () => {
    $$("#pp-kind button").forEach((b) => b.classList.toggle("active", b.dataset.k === kind));
    $$("#pp-rec button").forEach((b) => b.classList.toggle("active", b.dataset.r === rec));
    $("#pp-end-l").hidden = rec !== "mensal";
    $("#pp-start-t").textContent = rec === "mensal" ? "A partir de" : "Mês";
  };
  sync();
  $("#pp-kind").onclick = (e) => { const b = e.target.closest("[data-k]"); if (b) { kind = b.dataset.k; sync(); } };
  $("#pp-rec").onclick = (e) => { const b = e.target.closest("[data-r]"); if (b) { rec = b.dataset.r; sync(); } };
  $("#pp-save").onclick = async () => {
    const amount = parseNum(sheetVal("pp-amount"));
    if (!sheetVal("pp-name") || !amount) return toast("Informe nome e valor");
    if (!sheetVal("pp-start")) return toast("Informe o mês");
    const body = {
      name: sheetVal("pp-name"), kind, amount, recurrence: rec, start_month: sheetVal("pp-start") + "-01",
      end_month: rec === "mensal" && sheetVal("pp-end") ? sheetVal("pp-end") + "-01" : null,
      due_day: parseInt(sheetVal("pp-day"), 10) || null, category_id: sheetVal("pp-cat") ? +sheetVal("pp-cat") : null,
      owner_id: sheetVal("pp-owner") ? +sheetVal("pp-owner") : null, match_pattern: sheetVal("pp-match") || null,
    };
    await api(p ? "PUT" : "POST", p ? `/api/planned/${p.id}` : "/api/planned", body);
    closeSheet();
    toast(p ? "Previsto atualizado" : "Previsto criado");
    await renderPlanejamento();
  };
  if (p) $("#pp-del").onclick = async () => {
    if (!confirm(`Excluir "${p.name}" e todos os meses dele?`)) return;
    await api("DELETE", `/api/planned/${p.id}`);
    closeSheet();
    await renderPlanejamento();
  };
}


// ------------------------------------------------------------------ COCKPIT: ações com liga/desliga
// Cada ação ligada muda o fluxo (Fluxo e Mês). Ajustes: linhas que somam entradas/saídas ou substituem um previsto no mês,
// com valor fixo ou fração de outro previsto (ex.: 1/3 do Salário). Quitação: um liga/desliga e um mês por dívida.
const FRACTIONS = [[1, "1"], [1 / 2, "1/2"], [1 / 3, "1/3"], [2 / 3, "2/3"], [1 / 4, "1/4"], [3 / 4, "3/4"], [1 / 6, "1/6"], [1 / 12, "1/12"]];
const fmtFactor = (f) => (f == null ? "" : (FRACTIONS.find(([v]) => Math.abs(v - f) < 1e-6)?.[1] ?? String(+f.toFixed(4)).replace(".", ",")));
function parseFactor(t) {
  t = String(t || "").trim().replace(/\s+/g, "");
  if (!t) return null;
  let m = t.match(/^(\d+(?:[.,]\d+)?)\/(\d+(?:[.,]\d+)?)$/);
  if (m) return parseNum(m[1]) / parseNum(m[2]);
  m = t.match(/^(\d+(?:[.,]\d+)?)%$/);
  if (m) return parseNum(m[1]) / 100;
  const v = parseNum(t);
  return v === undefined ? undefined : v;
}
const switchHtml = (attrs, on, label) => `<label class="switch" title="${esc(label)}"><input type="checkbox" ${attrs} ${on ? "checked" : ""} aria-label="${esc(label)}"><span></span></label>`;
const signedMoney = (v) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${fmt(Math.abs(v))}`;

async function renderCockpit() {
  const h = state.plan.ckHorizon || 18;
  $$("#ck-horizon button").forEach((b) => b.classList.toggle("active", +b.dataset.h === h));
  const ck = await api("GET", `/api/cockpit?months=${h}`);
  state.cockpit = ck;
  const s = ck.summary, last = ck.months[ck.months.length - 1];
  const diff = s.final_with - s.final_base;
  $("#ck-kpis").innerHTML = `
    <div class="ck-kpi"><small>Saldo em ${mlabel(last)}</small><b>${fmt(s.final_with)}</b>
      <em>${s.active ? `${signedMoney(diff)} com ${s.active} ${s.active === 1 ? "ação ligada" : "ações ligadas"}` : "nenhuma ação ligada"}</em></div>
    <div class="ck-kpi"><small>Menor saldo</small><b>${fmt(s.low_with.value)}</b>
      <em>em ${mlabel(s.low_with.month)}${s.active && s.low_with.value !== s.low_base.value ? ` · sem ações ${fmt(s.low_base.value)}` : ""}</em></div>`;
  chart("chart-cockpit").setOption({
    ...baseOption(), grid: { left: 8, right: 16, top: 30, bottom: 8, containLabel: true },
    xAxis: { ...baseOption().xAxis, data: ck.months.map(mlabel) },
    series: [
      { name: "Sem ações", type: "line", data: ck.base, smooth: true, symbol: "none", color: DIM(), lineStyle: { width: 2, type: "dashed" } },
      { name: "Com as ações ligadas", type: "line", data: ck.with, smooth: true, symbol: "circle", symbolSize: 5, color: LIT(), lineStyle: { width: 2.5 },
        markLine: { symbol: "none", silent: true, label: { show: false }, lineStyle: { color: css("--line-strong"), type: "dashed" }, data: [{ yAxis: 0 }] } },
    ],
  }, true);
  chart("chart-cockpit").resize();

  $("#ck-actions").innerHTML = ck.actions.length ? ck.actions.map((a) => {
    const months = a.impact.by_month.slice(0, 3).map((x) => `${signedMoney(x.value)} em ${mlabel(x.month)}`).join(" · ");
    const more = a.impact.by_month.length > 3 ? ` · +${a.impact.by_month.length - 3} meses` : "";
    const problems = a.lines.filter((l) => l.problem).length;
    return `<div class="ck-row ${a.active ? "" : "off"}">
      ${switchHtml(`data-ck-toggle="${a.id}"`, a.active, `Ligar ${a.name}`)}
      <button class="ck-row__main" data-ck-edit="${a.id}"><span class="ck-row__title">${esc(a.name)}</span>
        <span class="ck-row__desc">${problems ? `<span class="ck-warn">${problems} ${problems === 1 ? "linha" : "linhas"} com problema · </span>` : ""}${esc(months + more) || "sem efeito"}</span></button>
      <span class="ck-row__val">${signedMoney(a.impact.total)}</span></div>`;
  }).join("") : '<p class="hint">Crie ações para simular decisões, como antecipar férias, vender dias ou receber um bônus. Ligue e desligue para comparar.</p>';

  $("#ck-payoffs").innerHTML = ck.payoffs.length ? ck.payoffs.map((d) => `<div class="ck-row ${d.active ? "" : "off"}">
      ${switchHtml(`data-ck-pay="${d.debt_id}"`, d.active, `Quitar ${d.name}`)}
      <div class="ck-row__main"><span class="ck-row__title">${esc(d.name)}</span>
        <span class="ck-row__desc">${fmt2(d.installment)}/mês · ${d.installments_left} ${d.installments_left === 1 ? "parcela" : "parcelas"} até ${mlabel(d.end_month)}</span>
        <span class="ck-row__desc">Quitação ${fmt2(d.payoff)}${d.interest_saved > 0.5 ? ` · economiza ${fmt(d.interest_saved)} de juros` : ""}</span>
        <label class="ck-pay__month">Quitar em <input type="month" data-ck-paymonth="${d.debt_id}" value="${d.month.slice(0, 7)}"></label></div>
    </div>`).join("") : '<p class="hint">Nenhuma dívida com parcelas pela frente.</p>';
}
$("#ck-horizon").addEventListener("click", (e) => {
  const b = e.target.closest("[data-h]");
  if (b) { state.plan.ckHorizon = +b.dataset.h; renderCockpit(); }
});
$("#pv-cockpit").addEventListener("change", async (e) => {
  const t = e.target;
  if (t.dataset.ckToggle) {
    await api("PATCH", `/api/cockpit/actions/${t.dataset.ckToggle}`, { active: t.checked });
    toast(t.checked ? "Ação ligada: entra no Fluxo e no Mês" : "Ação desligada");
  } else if (t.dataset.ckPay) {
    const month = $(`[data-ck-paymonth="${t.dataset.ckPay}"]`).value;
    await api("PUT", `/api/cockpit/payoffs/${t.dataset.ckPay}`, { active: t.checked, month: month ? month + "-01" : null });
    toast(t.checked ? `Quitação em ${mlabel(month + "-01")} ligada` : "Quitação desligada");
  } else if (t.dataset.ckPaymonth) {
    if (!t.value) return;
    const on = $(`[data-ck-pay="${t.dataset.ckPaymonth}"]`).checked;
    await api("PUT", `/api/cockpit/payoffs/${t.dataset.ckPaymonth}`, { active: on, month: t.value + "-01" });
  } else return;
  renderCockpit();
});
$("#pv-cockpit").addEventListener("click", (e) => {
  const b = e.target.closest("[data-ck-edit]");
  if (b) openActionSheet(state.cockpit.actions.find((a) => a.id === +b.dataset.ckEdit));
});
$("#ck-add").onclick = () => openActionSheet(null);

// modelo do exemplo de férias: antecipar recebe salário do mês seguinte + 1/3 + 10 dias vendidos + 1ª parcela do 13º seguinte;
// no mês seguinte o salário vira só os 10 dias trabalhados
function feriasTemplate(names) {
  const sal = names.find((n) => /^sal[aá]rio$/i.test(n)) || names.find((n) => /sal[aá]rio/i.test(n)) || "Salário";
  const m0 = thisMonth(), m1 = addMonths(m0, 1);
  const nextName = MESES_LONGOS[+m1.slice(5, 7) - 1];
  const next13 = +m0.slice(0, 4) + 1;
  const frac = (month, label, factor, extra = {}) => ({ month, label, op: "somar", direction: "entrada", factor, base: sal, base_month: m0, ...extra });
  return {
    name: "Antecipação de férias",
    notes: `Valores como fração do ${sal} de ${mlabel(m0)}. Ajuste os meses se o pagamento das férias cair em outro mês.`,
    lines: [
      frac(m0, `Salário de ${nextName} adiantado`, 1),
      frac(m0, "1/3 de férias", 1 / 3),
      frac(m0, "10 dias vendidos (abono)", 1 / 3),
      frac(m0, `1ª parcela do 13º de ${next13} adiantada`, 1 / 2),
      frac(m1, `${capFirst(nextName)}: só os 10 dias trabalhados`, 1 / 3, { op: "substituir", target: sal }),
    ],
  };
}

function openActionSheet(a, preset) {
  const ck = state.cockpit;
  const names = [...new Set(ck.previstos.map((p) => p.name))];
  const v = preset || a || { name: "", notes: "", lines: [] };
  let lines = v.lines.map((l) => ({ ...l }));
  const prevOpts = (sel) => '<option value="">Escolha o previsto</option>' + names.map((n) => `<option ${n === sel ? "selected" : ""}>${esc(n)}</option>`).join("");
  openSheet(`<p class="overline">Cockpit</p><h2>${a ? "Editar ação" : "Nova ação"}</h2>
    ${a ? "" : `<div class="row" style="margin-top:0"><button class="secondary" id="ak-tpl">Usar modelo: antecipação de férias</button></div>`}
    <label class="field">Nome<input id="ak-name" value="${esc(v.name)}" placeholder="Antecipação de férias, venda do carro…"></label>
    <div class="ck-lines" id="ak-lines"></div>
    <div class="row"><button class="secondary" id="ak-add">Adicionar linha</button></div>
    <label class="field">Observação<input id="ak-notes" value="${esc(v.notes || "")}"></label>
    <div class="row"><button class="primary" id="ak-save">Salvar</button>${a ? '<button class="danger" id="ak-del">Excluir</button>' : ""}</div>`);
  const read = () => {
    lines = $$("#ak-lines .ck-line").map((el, i) => {
      const l = lines[i];
      const q = (sel) => el.querySelector(sel);
      return { ...l, month: (q("[data-f=month]").value || thisMonth().slice(0, 7)) + "-01", label: q("[data-f=label]").value,
        amount: l.mode === "valor" ? parseNum(q("[data-f=amount]").value) ?? null : null,
        factor: l.mode === "fracao" ? parseFactor(q("[data-f=factor]").value) ?? null : null,
        base: l.mode === "fracao" ? q("[data-f=base]").value || null : null,
        base_month: l.mode === "fracao" && q("[data-f=base_month]").value ? q("[data-f=base_month]").value + "-01" : null,
        target: l.op === "substituir" ? q("[data-f=target]").value || null : null };
    });
  };
  const paint = () => {
    $("#ak-lines").innerHTML = lines.map((l, i) => {
      l.mode ||= l.factor != null ? "fracao" : "valor";
      const kind = l.op === "substituir" ? "sub" : l.direction;
      const calc = l.value != null && l.mode === "fracao" ? `= ${fmt2(l.value)}` : "";
      return `<div class="ck-line" data-i="${i}">
        <div class="ck-line__top">${monthInput(`ak-m${i}`, l.month).replace('<input type="month"', '<input type="month" data-f="month"')}
          <input data-f="label" value="${esc(l.label || "")}" placeholder="Descrição" aria-label="Descrição"></div>
        <div class="segmented" data-f="kind"><button data-k="entrada" class="${kind === "entrada" ? "active" : ""}">Entrada</button><button data-k="saida" class="${kind === "saida" ? "active" : ""}">Saída</button><button data-k="sub" class="${kind === "sub" ? "active" : ""}">Substituir previsto</button></div>
        ${l.op === "substituir" ? `<div class="ck-line__val">O previsto <select data-f="target">${prevOpts(l.target)}</select> passa a valer:</div>` : ""}
        <div class="ck-line__val"><div class="segmented" data-f="mode"><button data-m="valor" class="${l.mode === "valor" ? "active" : ""}">R$</button><button data-m="fracao" class="${l.mode === "fracao" ? "active" : ""}">Fração de previsto</button></div></div>
        ${l.mode === "valor" ? `<div class="ck-line__val">R$ <input data-f="amount" inputmode="decimal" value="${l.amount != null ? String(l.amount).replace(".", ",") : ""}" placeholder="0,00"></div>`
          : `<div class="ck-line__val"><input data-f="factor" value="${fmtFactor(l.factor)}" placeholder="1/3" aria-label="Fração"> × <select data-f="base">${prevOpts(l.base)}</select></div>
             <div class="ck-line__val">de <input type="month" data-f="base_month" value="${l.base_month ? l.base_month.slice(0, 7) : ""}" aria-label="Mês do previsto de referência"> <span class="ck-line__calc">${calc}${l.problem ? ` ${esc(l.problem)}` : ""}</span></div>`}
        <button class="ghost sm ck-line__rm" data-rm="${i}">Remover linha</button></div>`;
    }).join("") || '<p class="hint">Cada linha muda um mês: soma uma entrada ou saída, ou troca o valor de um previsto (0 zera).</p>';
  };
  paint();
  $("#ak-lines").addEventListener("click", (e) => {
    const line = e.target.closest(".ck-line");
    if (!line) return;
    const i = +line.dataset.i;
    const k = e.target.closest("[data-f=kind] [data-k]"), m = e.target.closest("[data-f=mode] [data-m]"), rm = e.target.closest("[data-rm]");
    if (!k && !m && !rm) return;
    read();
    if (k) Object.assign(lines[i], k.dataset.k === "sub" ? { op: "substituir" } : { op: "somar", direction: k.dataset.k });
    if (m) lines[i].mode = m.dataset.m;
    if (rm) lines.splice(i, 1);
    paint();
  });
  $("#ak-add").onclick = () => {
    read();
    const prev = lines[lines.length - 1];
    lines.push({ month: prev ? prev.month : addMonths(thisMonth(), 1), label: "", op: "somar", direction: "entrada", mode: "valor" });
    paint();
    $$("#ak-lines [data-f=label]").pop()?.focus();
  };
  if (!a) $("#ak-tpl").onclick = () => {
    const t = feriasTemplate(names);
    $("#ak-name").value = t.name;
    $("#ak-notes").value = t.notes;
    lines = t.lines;
    paint();
  };
  $("#ak-save").onclick = async () => {
    read();
    const name = $("#ak-name").value.trim();
    if (!name) return toast("Dê um nome à ação");
    for (const l of lines) {
      if (!l.label.trim()) return toast("Toda linha precisa de descrição");
      if (l.mode === "valor" && (l.amount == null || l.amount < 0)) return toast(`“${l.label}”: informe o valor`);
      if (l.mode === "fracao" && (l.factor == null || !l.base)) return toast(`“${l.label}”: informe a fração e o previsto`);
      if (l.op === "substituir" && !l.target) return toast(`“${l.label}”: escolha o previsto a substituir`);
    }
    const body = { name, notes: $("#ak-notes").value.trim() || null,
      lines: lines.map(({ month, label, op, direction, amount, factor, base, base_month, target }) => ({ month, label: label.trim(), op, direction, amount, factor, base, base_month, target })) };
    await api(a ? "PUT" : "POST", a ? `/api/cockpit/actions/${a.id}` : "/api/cockpit/actions", body);
    closeSheet();
    toast(a ? "Ação atualizada" : "Ação criada. Ligue para ver no fluxo.");
    renderPlanejamento();
  };
  if (a) $("#ak-del").onclick = async () => {
    if (!confirm(`Excluir a ação "${a.name}"?`)) return;
    await api("DELETE", `/api/cockpit/actions/${a.id}`);
    closeSheet();
    renderPlanejamento();
  };
}

// ------------------------------------------------------------------ FLUXO: saldo projetado e tabela mês a mês
const NUM = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
const num = (v) => (Math.round(v) ? NUM.format(Math.round(v)) : "");
const snum = (v) => `${v < 0 ? "−" : ""}${NUM.format(Math.abs(Math.round(v)))}`;
const SECTION_TITLE = { entradas: "Entradas", saidas: "Saídas", dividas: "Dívidas e parcelas" };

async function renderFluxo() {
  const h = state.plan.horizon || 12;
  $$("#tb-horizon button").forEach((b) => b.classList.toggle("active", +b.dataset.h === h));
  const p = await api("GET", withPerson(`/api/projection?months=${h}&detail=true`));
  const t = p.table;
  state.table = t;
  const acc = t.totais.acumulado.values;
  const low = acc.reduce((a, v, i) => (v < a.v ? { v, i } : a), { v: Infinity, i: -1 });
  $("#fx-end").innerHTML = acc.length ? `${money(acc[acc.length - 1])} <small>em ${mlabel(t.months[t.months.length - 1])}</small>` : "";
  $("#tb-hint").innerHTML = `Começa com ${fmt(t.saldo_inicial)} (contas menos faturas)${low.i >= 0 ? ` · menor saldo ${fmt(low.v)} em ${mlabel(t.months[low.i])}` : ""}.`;
  chart("chart-fluxo").setOption({
    ...baseOption(), grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true }, legend: { show: false },
    xAxis: { ...baseOption().xAxis, data: t.months.map(mlabel) },
    series: [{ name: "Saldo acumulado", type: "line", data: acc, smooth: true, symbol: "circle", symbolSize: 6, color: LIT(),
      lineStyle: { width: 2.5 }, areaStyle: { color: DIM(), opacity: 0.45 },
      markLine: { symbol: "none", silent: true, label: { show: false }, lineStyle: { color: css("--line-strong"), type: "dashed" }, data: [{ yAxis: 0 }] } }],
  }, true);
  chart("chart-fluxo").resize();

  const cells = (now, values, cls = "", sources) => `<td class="now ${cls}">${num(now)}</td>` +
    values.map((v, i) => `<td class="${cls} ${sources && sources[i] === "média" ? "avg" : ""}">${num(v)}</td>`).join("");
  const signed = (now, values) => `<td class="now">${snum(now)}</td>` + values.map((v) => `<td>${snum(v)}</td>`).join("");
  let body = "";
  for (const s of t.sections) {
    if (!s.groups.length) continue;
    body += `<tr class="sec"><td class="lbl">${SECTION_TITLE[s.key]}</td>${cells(s.now, s.values)}</tr>`;
    const showGroups = s.groups.length > 1;
    for (const g of s.groups) {
      if (showGroups) body += `<tr class="grp"><td class="lbl">${esc(g.group)}</td>${cells(g.now, g.values)}</tr>`;
      // linhas editáveis: tocar num valor muda aquele mês (ou dali em diante)
      for (const r of g.rows) body += `<tr><td class="lbl ${showGroups ? "sub" : ""}" title="${esc(r.label)}">${esc(r.label)}</td><td class="now">${num(r.now)}</td>` +
        r.values.map((v, i) => `<td class="ed ${r.sources[i] === "média" ? "avg" : ""}" data-ref="${esc(r.ref)}" data-m="${t.months[i]}" data-label="${esc(r.label)}" data-v="${v}" data-src="${r.sources[i]}">${num(v)}</td>`).join("") + "</tr>";
    }
  }
  const T = t.totais;
  body += `<tr class="total first"><td class="lbl">Total de entradas</td>${cells(T.entradas.now, T.entradas.values)}</tr>
    <tr class="total"><td class="lbl">Total de saídas</td>${cells(T.saidas.now, T.saidas.values)}</tr>
    <tr class="total"><td class="lbl">Saldo do mês</td>${signed(T.saldo_mes.now, T.saldo_mes.values)}</tr>
    <tr class="acc"><td class="lbl">Saldo acumulado</td>${signed(T.acumulado.now, T.acumulado.values)}</tr>`;
  // agrupamentos: linhas informativas, à parte da modelagem (não somam em nada)
  if ((t.groupings || []).length) {
    body += `<tr class="info-sep"><td class="lbl">Informativo</td><td colspan="${t.months.length + 1}"></td></tr>` +
      t.groupings.map((g) => `<tr class="info" data-grouping="${g.id}"><td class="lbl" title="${esc(g.name)}">${esc(g.name)}</td>${signed(g.now, g.values)}</tr>`).join("");
  }
  $("#tb-table").innerHTML = `<thead><tr><th class="lbl">R$</th><th class="now" title="Atrasos e o que ainda vence neste mês">Agora</th>
    ${t.months.map((m) => `<th><button class="th-month" data-open-month="${m}">${mlabel(m)}</button></th>`).join("")}</tr></thead><tbody>${body}</tbody>`;
}
$("#tb-table").addEventListener("click", (e) => {
  const mo = e.target.closest("[data-open-month]");
  if (mo) {
    state.plan.month = mo.dataset.openMonth;
    state.plan.view = "mes";
    return renderPlanejamento();
  }
  const td = e.target.closest("td[data-ref]");
  if (td) return openCellSheet({ ref: td.dataset.ref, month: td.dataset.m, label: td.dataset.label, value: +td.dataset.v, source: td.dataset.src });
  const row = e.target.closest("[data-grouping]");
  if (row) openGroupingEditor((state.table.groupings || []).find((g) => g.id === +row.dataset.grouping));
});

// ------------------------------------------------------------------ editar pela tabela: toque num valor
// Previsto: só neste mês ou deste mês em diante (até o fim da previsão). Categoria: orçamento do mês ou de todo mês.
// Dívida: quitar neste mês (vira ação do cockpit). Ação do cockpit: abre a ação.
async function afterCellEdit(ref, month) {
  const wrap = $(".tb-wrap"), x = wrap ? wrap.scrollLeft : 0, y = window.scrollY;
  await renderFluxo();
  if (wrap) wrap.scrollLeft = x;
  window.scrollTo(0, y);
  const cell = $(`#tb-table td[data-ref="${CSS.escape(ref)}"][data-m="${month}"]`);
  if (cell) { cell.classList.add("flash"); setTimeout(() => cell.classList.remove("flash"), 1600); }
}
const cellAmountInput = (v) => `<label class="qa-amount cell-amount"><span>R$</span><input id="ce-amount" inputmode="decimal" value="${v ? String(v.toFixed(2)).replace(".", ",") : ""}" placeholder="0,00" autocomplete="off" aria-label="Valor"></label>`;
function scopeSeg(opts, cur) {
  return `<div class="segmented ce-scope" id="ce-scope">${opts.map(([k, l]) => `<button data-s="${k}" class="${k === cur ? "active" : ""}">${esc(l)}</button>`).join("")}</div>`;
}
function bindScope(get, set) {
  $("#ce-scope")?.addEventListener("click", (e) => {
    const b = e.target.closest("[data-s]");
    if (!b) return;
    set(b.dataset.s);
    $$("#ce-scope button").forEach((x) => x.classList.toggle("active", x.dataset.s === get()));
  });
}

async function openCellSheet(c) {
  const i = c.ref.indexOf(":"), kind = c.ref.slice(0, i), id = c.ref.slice(i + 1);
  if (kind === "plan") return openPlanCell(id, c.month, c.value, c.ref);
  if (kind === "cat") return id === "none" ? openInfoCell(c, "Média dos lançamentos sem categoria. Categorize os lançamentos para orçar cada um.") : openCatCell(+id, c);
  if (kind === "debt") return openDebtCell(+id, c);
  if (kind === "card") return openInfoCell(c, "Parcelas de compras no cartão, calculadas a partir das faturas importadas.");
  if (kind === "acao") {
    state.cockpit = await api("GET", "/api/cockpit");
    const a = state.cockpit.actions.find((x) => x.id === +id);
    return a ? openActionSheet(a) : null;
  }
}
function openInfoCell(c, text) {
  openSheet(`<p class="overline">${capFirst(mlong(c.month))}</p><h2>${esc(c.label)}</h2>
    <p class="hint">${esc(text)}</p><p class="cell-now">${fmt2(c.value)}</p>`);
}

async function openPlanCell(name, month, value, ref) {
  const info = await api("GET", `/api/planned/month-info?name=${encodeURIComponent(name)}&month=${month}`);
  const s = info.series, o = info.occurrence;
  const fwd = s ? (s.end_month ? `De ${mlabel(month)} até ${mlabel(s.end_month)}` : `De ${mlabel(month)} em diante`) : `Todo mês desde ${mlabel(month)}`;
  const now = o ? (o.recurrence === "mensal" ? `Previsto todo mês${s && s.end_month ? ` até ${mlabel(s.end_month)}` : ""}: ${fmt2(s ? s.amount : o.amount)}${o.changed ? ` · neste mês ajustado para ${fmt2(o.amount)}` : ""}${o.status === "pulado" ? " · este mês está pulado" : ""}` : "Previsto só neste mês")
    : "Nada previsto neste mês.";
  let scope = "mes";
  openSheet(`<p class="overline">${capFirst(mlong(month))}</p><h2>${esc(name)}</h2>
    <p class="hint">${esc(now)}</p>
    ${cellAmountInput(value)}
    ${info.can_forward ? scopeSeg([["mes", `Só em ${mlabel(month)}`], ["diante", fwd]], scope) : `<p class="hint">Vale só para ${mlabel(month)}.</p>`}
    <div class="qa-actions"><button class="primary" id="ce-save">Salvar</button><button class="secondary" id="ce-zero">Zerar</button></div>
    <div class="row occ-links">${o ? '<button class="link" id="ce-more">Mover ou marcar como pago</button>' : ""}${s ? '<button class="link" id="ce-series">Editar previsão</button>' : ""}</div>`);
  bindScope(() => scope, (v) => { scope = v; });
  setTimeout(() => $("#ce-amount").select(), 40);
  const send = async (amount) => {
    await api("POST", "/api/planned/edit-month", { name, month, amount, scope });
    closeSheet();
    const when = scope === "mes" ? `em ${mlabel(month)}` : fwd.charAt(0).toLowerCase() + fwd.slice(1);
    toast(amount ? `${name}: ${fmt2(amount)} ${when}` : `${name} zerado ${when}`);
    await afterCellEdit(ref, month);
  };
  $("#ce-save").onclick = () => {
    const v = parseNum($("#ce-amount").value);
    if (v === undefined || v === null || v < 0) return toast("Informe o valor");
    send(v);
  };
  $("#ce-amount").onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); $("#ce-save").click(); } };
  $("#ce-zero").onclick = () => send(0);
  $("#ce-more")?.addEventListener("click", () => openOccSheet(o));
  $("#ce-series")?.addEventListener("click", async () => openPlannedSheet((await api("GET", "/api/planned")).find((p) => p.id === s.id)));
}

async function openCatCell(cid, c) {
  const cat = catById(cid);
  const budgets = await api("GET", "/api/budgets");
  const monthB = budgets.find((b) => b.category_id === cid && b.month === c.month);
  const defB = budgets.find((b) => b.category_id === cid && !b.month);
  let scope = "mes"; // tocou num mês: começa mudando só ele
  const now = monthB ? `Orçamento só de ${mlabel(c.month)}: ${fmt2(monthB.amount)}` : defB ? `Orçamento de todo mês: ${fmt2(defB.amount)}`
    : `Sem orçamento: usa a média dos últimos meses (${fmt2(c.value)})`;
  openSheet(`<p class="overline">${capFirst(mlong(c.month))} · ${cat && cat.type === "receita" ? "receita" : "gastos"}</p><h2>${esc(c.label)}</h2>
    <p class="hint">${esc(now)}</p>
    ${cellAmountInput(c.value)}
    ${scopeSeg([["mes", `Só em ${mlabel(c.month)}`], ["padrao", "Todo mês"]], scope)}
    <div class="qa-actions"><button class="primary" id="ce-save">Salvar</button>
      ${monthB || defB ? `<button class="secondary" id="ce-avg">${monthB ? `Tirar o ajuste de ${mlabel(c.month)}` : "Voltar à média"}</button>` : ""}</div>`);
  bindScope(() => scope, (v) => { scope = v; });
  setTimeout(() => $("#ce-amount").select(), 40);
  const put = async (amount, sc) => {
    await api("PUT", "/api/budgets", [{ category_id: cid, month: sc === "mes" ? c.month : null, amount }]);
    closeSheet();
    await afterCellEdit(c.ref || `cat:${cid}`, c.month);
  };
  $("#ce-save").onclick = async () => {
    const v = parseNum($("#ce-amount").value);
    if (v === undefined || v === null || v < 0) return toast("Informe o valor");
    await put(v, scope);
    toast(`${c.label}: ${fmt2(v)} ${scope === "mes" ? `em ${mlabel(c.month)}` : "todo mês"}`);
  };
  $("#ce-amount").onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); $("#ce-save").click(); } };
  $("#ce-avg")?.addEventListener("click", async () => { await put(null, monthB ? "mes" : "padrao"); toast("Ajuste removido"); });
}

async function openDebtCell(did, c) {
  const info = await api("GET", `/api/cockpit/payoffs/${did}`);
  const here = info.active && info.month === c.month;
  openSheet(`<p class="overline">${capFirst(mlong(c.month))}</p><h2>${esc(info.name)}</h2>
    <p class="hint">${here ? `Quitação neste mês: ${fmt2(c.value)}. Depois disso, as parcelas somem.`
      : `Parcela de ${fmt2(info.installment)}, do contrato (muda em Dívidas).${info.active ? ` A quitação está marcada para ${mlabel(info.month)}.` : ""}`}</p>
    <div class="qa-actions">${here ? '<button class="secondary" id="ce-unpay">Desfazer quitação</button>'
      : `<button class="primary" id="ce-pay">Quitar em ${mlabel(c.month)}</button>`}</div>
    <p class="hint">A quitação paga a parcela do mês e o valor presente das seguintes (juros do contrato). Fica no Cockpit, onde dá para desligar.</p>`);
  const put = async (active) => {
    await api("PUT", `/api/cockpit/payoffs/${did}`, { active, month: c.month });
    closeSheet();
    toast(active ? `${info.name}: quitação em ${mlabel(c.month)}` : "Quitação desfeita");
    await afterCellEdit(`debt:${did}`, c.month);
  };
  $("#ce-pay")?.addEventListener("click", () => put(true));
  $("#ce-unpay")?.addEventListener("click", () => put(false));
}
$("#tb-horizon").addEventListener("click", (e) => {
  const b = e.target.closest("[data-h]");
  if (!b) return;
  state.plan.horizon = +b.dataset.h;
  renderFluxo();
});
$("#tb-groups").onclick = () => openGroupingsSheet();
function openGroupingsSheet() {
  const gs = (state.table && state.table.groupings) || [];
  openSheet(`<p class="overline">Mês a mês</p><h2>Agrupamentos</h2>
    <p class="hint">Uma linha informativa, à parte do planejamento, com o líquido de algumas linhas. Ex.: <b>Salário líquido</b> =
      Salário − Plano de saúde − consignados: o que de fato cai na conta. Não muda totais nem a projeção.</p>
    <div class="list">${gs.map((g) => `<div class="az-insight"><div class="az-insight__text"><div class="az-insight__title">${esc(g.name)}</div>
      <div class="az-insight__desc">${g.refs.length} ${g.refs.length === 1 ? "linha" : "linhas"}</div></div>
      <button class="sm" data-edit-grouping="${g.id}">Editar</button></div>`).join("") || '<p class="hint">Nenhum agrupamento ainda.</p>'}</div>
    <div class="row"><button class="primary" id="gp-new">Novo agrupamento</button></div>`);
  $("#gp-new").onclick = () => openGroupingEditor(null);
  $("#sheet-body").querySelectorAll("[data-edit-grouping]").forEach((b) => {
    b.onclick = () => openGroupingEditor(gs.find((g) => g.id === +b.dataset.editGrouping));
  });
}
function openGroupingEditor(g) {
  const t = state.table;
  const chosen = new Set(g ? g.refs : []);
  const seen = new Set();
  let list = "";
  for (const s of t.sections) {
    const rows = s.groups.flatMap((gr) => gr.rows).filter((r) => (seen.has(r.ref) ? false : seen.add(r.ref)));
    if (!rows.length) continue;
    const sign = s.key === "entradas" ? "+" : "−";
    list += `<p class="overline chk-sec">${SECTION_TITLE[s.key]} <span class="muted">(${sign})</span></p>` +
      rows.map((r) => `<label class="chk-row"><input type="checkbox" value="${esc(r.ref)}" ${chosen.has(r.ref) ? "checked" : ""}>
        <span>${esc(r.label)}</span></label>`).join("");
  }
  openSheet(`<p class="overline">${g ? "Editar agrupamento" : "Novo agrupamento"}</p><h2>${g ? esc(g.name) : "Agrupamento"}</h2>
    <label class="field">Nome<input id="gp-name" value="${esc(g ? g.name : "")}" placeholder="Ex.: Folha"></label>
    <p class="hint" style="margin-top:var(--space-3)">Marque as linhas. Entradas somam, saídas e dívidas subtraem.</p>
    <div class="chk-list">${list || '<p class="hint">A tabela ainda não tem linhas neste período.</p>'}</div>
    <div class="row"><button class="primary" id="gp-save">Salvar</button>${g ? '<button class="danger" id="gp-del">Excluir</button>' : ""}</div>`);
  $("#gp-save").onclick = async () => {
    const name = sheetVal("gp-name").trim();
    if (!name) return toast("Dê um nome ao agrupamento");
    const refs = $$("#sheet .chk-list input:checked").map((i) => i.value);
    await api(g ? "PUT" : "POST", g ? `/api/groupings/${g.id}` : "/api/groupings", { name, refs });
    closeSheet();
    toast(g ? "Agrupamento atualizado" : "Agrupamento criado");
    await renderFluxo();
  };
  if (g) $("#gp-del").onclick = async () => {
    if (!confirm(`Excluir o agrupamento "${g.name}"?`)) return;
    await api("DELETE", `/api/groupings/${g.id}`);
    closeSheet();
    await renderFluxo();
  };
}


// ------------------------------------------------------------------ DÍVIDAS
async function renderDividas() {
  const d = await api("GET", withPerson("/api/debts/overview"));
  const T = d.totals;
  $("#debt-tiles").innerHTML = [
    ["Saldo devedor", fmt(T.saldo_devedor), "empréstimos e acordos"],
    ["Faturas abertas", fmt(T.faturas_abertas), "cartões, fatura atual"],
    ["Parcelas futuras no cartão", fmt(T.parcelas_cartao_futuras), "compras parceladas a cair"],
    ["Parcelas por mês", fmt(T.parcelas_mes), "empréstimos e acordos"],
  ].map(([l, v, sub]) => tile(l, v, sub)).join("");
  // ScoreRing: quanto da renda média vai para parcelas (o número sempre impresso; o anel só reforça)
  const c = T.comprometimento, C = 2 * Math.PI * 58, shown = c == null ? 0 : Math.min(1, c);
  const word = c == null ? "Sem dados" : c <= 0.3 ? "Saudável" : c <= 0.4 ? "Atenção" : "Alto";
  const desc = c == null ? "Importe extratos com receitas para calcular"
    : c <= 0.3 ? "As parcelas cabem bem na renda deste mês" : c <= 0.4 ? "Evite novas parcelas até reduzir as atuais" : "As parcelas pesam na renda; priorize quitar";
  $("#debt-ring").innerHTML = `<div class="health"><div class="health__head"><span>Comprometimento da renda</span></div>
    <div class="az-score"><div class="az-score__ring"><svg viewBox="0 0 128 128"><circle class="az-score__track" cx="64" cy="64" r="58"/>
      <circle class="az-score__value" cx="64" cy="64" r="58" stroke-dasharray="${(C * shown).toFixed(1)} ${C.toFixed(1)}"/></svg>
      <div class="az-score__num">${c == null ? "–" : Math.round(c * 100)}<small>%</small></div></div>
    <div class="az-score__title">${word}</div><div class="az-score__desc">${desc}</div></div></div>`;

  $("#debt-cards").innerHTML = d.cards.length ? d.cards.map((c) => {
    const used = c.limit ? Math.min(1, c.limit_used / c.limit) : null;
    const hist = c.history.map((h) => `<span><b>${fmt(h.amount)}</b> ${mlabel(h.month)}</span>`).join("");
    const fut = c.future_installments.slice(0, 6).map((f) => `<span>${mlabel(f.month)} <b>${fmt(f.amount)}</b></span>`).join("");
    return `<div class="card"><div class="card-head"><h3>${esc(c.name)}</h3><button class="link" data-card="${c.account_id}">${c.configured ? "Editar" : "Configurar"}</button></div>
      ${c.configured ? `<div class="amount-row"><span class="big">${money(c.current_invoice.amount)}</span><span class="muted">fatura de ${mlabel(c.current_invoice.month)} · vence ${dlabel(c.current_invoice.due)}</span></div>`
        : `<p class="hint">Informe o dia de fechamento e de vencimento para calcular as faturas.</p>`}
      ${used != null ? `<div class="meter" title="Limite usado"><i style="width:${used * 100}%"></i></div><p class="hint">${fmt(c.limit_used)} usados de ${fmt(c.limit)} · disponível ${fmt(c.limit_available)}</p>` : ""}
      ${hist ? `<p class="overline">Últimas faturas</p><div class="chips">${hist}</div>` : ""}
      ${fut ? `<p class="overline">Parcelas a cair · total ${fmt(c.future_total)}</p><div class="chips">${fut}</div>` : ""}</div>`;
  }).join("") : '<p class="hint">Nenhum cartão. Importe o OFX da fatura em Importar extrato.</p>';

  $("#debt-list").innerHTML = d.debts.length ? d.debts.map((x) => {
    const prog = x.total_installments ? x.paid / x.total_installments : null;
    return `<div class="card debt"><div class="card-head"><h3>${esc(x.name)}</h3><button class="link" data-debt="${x.id}">Editar</button></div>
      <p class="hint" style="margin:0 0 8px">${DEBT_LABEL[x.kind]}${x.creditor ? ` · ${esc(x.creditor)}` : ""} · ${esc(personName(x.owner_id))}</p>
      <div class="amount-row"><span class="big">${money(x.balance)}</span><span class="muted">saldo devedor${x.total_installments ? " (valor para quitar hoje)" : ""}</span></div>
      ${prog != null ? `<div class="meter"><i style="width:${prog * 100}%"></i></div>
        <p class="hint">${x.paid} de ${x.total_installments} parcelas pagas · ${x.remaining} restantes de ${fmt2(x.installment)} · termina ${mlabel(x.end_month)}</p>`
        : x.remaining ? `<p class="hint">Pagando ${fmt2(x.installment)} por mês, faltam cerca de ${x.remaining} parcelas · termina ${mlabel(x.end_month)}</p>` : ""}
      <div class="kv">${[["Juros a.m.", x.monthly_rate != null ? pct(x.monthly_rate, 2) : "–"], ["Juros que faltam", x.total_installments ? fmt(x.interest_remaining) : "–"],
        ["Próxima parcela", x.next_due ? dlabel(x.next_due) : "–"], ["Último pagamento", x.last_payment ? `${dlabel(x.last_payment.date)} · ${fmt(Math.abs(x.last_payment.amount))}` : "–"]]
        .map(([k, v]) => `<span>${k}</span><b>${v}</b>`).join("")}</div></div>`;
  }).join("") : '<p class="hint">Nenhuma dívida cadastrada. Cadastre empréstimos, consignados, financiamentos e acordos para acompanhar saldo e parcelas.</p>';

  const name = (id) => esc(d.debts.find((x) => x.id === id)?.name || "");
  const list = (ids, why) => ids.length ? `<ol>${ids.map((id) => `<li>${name(id)}</li>`).join("")}</ol><p class="hint">${why}</p>` : '<p class="hint">–</p>';
  $("#debt-strategy-card").hidden = d.debts.filter((x) => x.balance > 0).length < 2;
  $("#debt-strategy").innerHTML = `<div><p class="overline">Maior juro primeiro (avalanche)</p>${list(d.avalanche, "Paga menos juros no total.")}</div>
    <div><p class="overline">Menor saldo primeiro (bola de neve)</p>${list(d.snowball, "Elimina dívidas mais rápido e libera parcelas antes.")}</div>`;
  state.debts = d.debts;
}

$("#debt-cards").addEventListener("click", (e) => { const b = e.target.closest("[data-card]"); if (b) openAccountSheet(accById(+b.dataset.card)); });
$("#debt-list").addEventListener("click", (e) => { const b = e.target.closest("[data-debt]"); if (b) openDebtSheet(state.debts.find((x) => x.id === +b.dataset.debt)); });
$("#debt-add").onclick = () => openDebtSheet(null);

function openDebtSheet(x) {
  const v = x || { kind: "emprestimo" };
  openSheet(`<p class="overline">${x ? "Editar dívida" : "Nova dívida"}</p><h2>${x ? esc(x.name) : "Dívida"}</h2>
    <div class="form">
      <label class="field wide">Nome<input id="dv-name" value="${esc(v.name || "")}" placeholder="Consignado Banco X"></label>
      <label class="field">Tipo<select id="dv-kind">${Object.entries(DEBT_LABEL).map(([k, l]) => `<option value="${k}" ${k === v.kind ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      <label class="field">De quem<select id="dv-owner">${peopleOptions(v.owner_id ?? null)}</select></label>
      <label class="field wide">Credor<input id="dv-creditor" value="${esc(v.creditor || "")}"></label>
      <label class="field">Parcela (R$)<input id="dv-inst" inputmode="decimal" value="${v.installment || ""}"></label>
      <label class="field">Juros ao mês (%)<input id="dv-rate" inputmode="decimal" value="${v.monthly_rate != null ? +(v.monthly_rate * 100).toFixed(4) : ""}"></label>
      <label class="field">1ª parcela<input id="dv-first" type="date" value="${v.first_due || ""}"></label>
      <label class="field">Nº de parcelas<input id="dv-total" inputmode="numeric" value="${v.total_installments || ""}"></label>
      <label class="field wide">Saldo devedor (sem prazo)<input id="dv-balance" inputmode="decimal" value="${v.informed_balance ?? ""}" placeholder="rotativo, acordo"></label>
      <label class="field wide">Texto no extrato<input id="dv-match" value="${esc(v.match_pattern || "")}" placeholder="ex.: CONSIGNADO"></label>
    </div>
    <p class="hint">Com parcela, 1ª parcela e número de parcelas o app calcula quantas foram pagas, o saldo devedor e o valor para quitar
      hoje. “Texto no extrato” localiza o último pagamento nos lançamentos.</p>
    <div class="row"><button class="primary" id="dv-save">Salvar</button>${x ? '<button class="danger" id="dv-del">Excluir</button>' : ""}</div>`);
  $("#dv-save").onclick = async () => {
    const rate = parseNum(sheetVal("dv-rate"));
    const body = {
      name: sheetVal("dv-name"), kind: sheetVal("dv-kind"), creditor: sheetVal("dv-creditor") || null,
      owner_id: sheetVal("dv-owner") ? +sheetVal("dv-owner") : null, installment: parseNum(sheetVal("dv-inst")) || 0,
      monthly_rate: rate == null ? null : rate / 100, first_due: sheetVal("dv-first") || null,
      total_installments: parseInt(sheetVal("dv-total"), 10) || null, balance: parseNum(sheetVal("dv-balance")) ?? null,
      match_pattern: sheetVal("dv-match") || null,
    };
    if (!body.name) return toast("Informe o nome");
    await api(x ? "PUT" : "POST", x ? `/api/debts/${x.id}` : "/api/debts", body);
    closeSheet();
    toast("Dívida salva");
    await renderDividas();
  };
  if (x) $("#dv-del").onclick = async () => {
    if (!confirm("Excluir esta dívida?")) return;
    await api("DELETE", `/api/debts/${x.id}`);
    closeSheet();
    await renderDividas();
  };
}

// ------------------------------------------------------------------ AJUSTES
async function renderAjustes() {
  $("#set-people").innerHTML = state.people.map((p) => listRow({ icon: esc(initials(p.name)), title: esc(p.name),
    extra: `<button class="sm" data-ren-person="${p.id}">Renomear</button><button class="sm ghost" data-del-person="${p.id}">Excluir</button>` })).join("")
    || '<p class="hint">Cadastre quem usa o app (ex.: vocês dois). Cada conta, cartão e dívida pode ter um titular; sem titular fica como conjunta.</p>';
  const st = await api("GET", "/api/status");
  state.status = st;
  renderSecurity();
  $("#set-ai").innerHTML = st.ai
    ? `<div class="az-ai"><span class="az-ai__label">${SPARKLE}IA ligada</span>
         <div class="az-ai__text">Os lançamentos que nenhuma regra reconhece são categorizados pelo Claude. Respostas muito confiantes viram regras.</div>
         <div><button class="sm" id="ai-run" style="background:var(--surface-raised);color:var(--link);border-color:transparent">Categorizar pendentes</button></div></div>`
    : `<div class="az-ai"><span class="az-ai__label">${SPARKLE}IA desligada</span>
         <div class="az-ai__text">Para ligar, crie uma chave em console.anthropic.com e cadastre <code>ANTHROPIC_API_KEY</code> nas variáveis
         de ambiente do Vercel (depois faça Redeploy). O custo é de centavos por mês.</div></div>
       <p class="hint">Sem a chave, o app categoriza só pelas regras, que aprendem com as suas correções.</p>`;
  const accs = state.accounts;
  $("#set-accounts").innerHTML = accs.length ? accs.map((a) => listRow({ cls: a.active ? "" : "inactive",
    icon: a.kind === "cartao" ? ICON.card : esc(initials(a.name)), title: `${esc(a.name)}${a.active ? "" : " (inativa)"}`,
    desc: `${KIND_LABEL[a.kind]} · ${esc(personName(a.owner_id))}${a.kind === "cartao" ? (a.closing_day ? ` · fecha dia ${a.closing_day}, vence dia ${a.due_day}` : " · sem fechamento/vencimento") : ""}`,
    amount: a.kind === "cartao" ? "" : signed(a.balance), extra: `<button class="sm" data-acc="${a.id}">Editar</button>` })).join("")
    : '<p class="hint">As contas são criadas sozinhas ao importar o OFX. Também dá para criar à mão (ex.: dinheiro, investimentos).</p>';
  const groups = {};
  state.categories.forEach((c) => (groups[`${c.type}|${c.group}`] ||= []).push(c));
  $("#set-categories").innerHTML = Object.entries(groups).map(([k, cs]) => {
    const [type, g] = k.split("|");
    return `<div class="cat-group"><p class="overline">${esc(type === "despesa" ? g : TYPE_LABEL[type])}</p><div class="chips">${cs.map((c) =>
      `<button class="chip ${c.active ? "" : "off"}" data-cat="${c.id}">${esc(c.name)}</button>`).join("")}</div></div>`;
  }).join("");
  await renderRules();
}

async function renderRules() {
  const rules = await api("GET", "/api/rules");
  const shown = rules.filter((r) => (state.ruleSource === "padrao" ? r.source === "padrao" : r.source !== "padrao"));
  $$("#rule-filter button").forEach((b) => b.classList.toggle("active", b.dataset.src === state.ruleSource));
  const SRC = { aprendida: "aprendida", manual: "manual", ia: "da IA", padrao: "padrão" };
  $("#set-rules").innerHTML = shown.length ? `<thead><tr><th>Quando a descrição</th><th>Categoria</th><th>Origem</th><th>Usos</th><th></th></tr></thead><tbody>` +
    shown.map((r) => `<tr><td>${r.match === "exact" ? "é" : "contém"} <b>${esc(r.pattern)}</b></td><td>${esc(catById(r.category_id)?.name || "–")}</td>
      <td>${SRC[r.source]}</td><td>${r.hits}</td><td><button class="sm ghost" data-del-rule="${r.id}">Excluir</button></td></tr>`).join("") + "</tbody>"
    : '<tbody><tr><td class="muted">Nenhuma regra sua ainda. Elas aparecem quando você corrige categorias em Lançamentos.</td></tr></tbody>';
}

$("#add-person").onclick = async () => {
  const name = $("#new-person").value.trim();
  if (!name) return;
  await api("POST", "/api/people", { name });
  $("#new-person").value = "";
  await loadBase();
  await renderAjustes();
};
$("#set-people").addEventListener("click", async (e) => {
  const ren = e.target.closest("[data-ren-person]"), del = e.target.closest("[data-del-person]");
  if (ren) {
    const p = state.people.find((x) => x.id === +ren.dataset.renPerson);
    const name = prompt("Novo nome:", p.name);
    if (!name) return;
    await api("PUT", `/api/people/${p.id}`, { name });
  } else if (del) {
    if (!confirm("Excluir esta pessoa? As contas e dívidas dela passam a ser conjuntas.")) return;
    await api("DELETE", `/api/people/${del.dataset.delPerson}`);
  } else return;
  await loadBase();
  await renderAjustes();
});
$("#set-ai").addEventListener("click", async (e) => {
  if (!e.target.closest("#ai-run")) return;
  e.target.disabled = true;
  e.target.textContent = "Categorizando…";
  const r = await api("POST", "/api/transactions/categorize-ai");
  toast(`${r.categorized} de ${r.checked} pendentes categorizados pela IA`);
  await renderAjustes();
});
$("#set-accounts").addEventListener("click", (e) => { const b = e.target.closest("[data-acc]"); if (b) openAccountSheet(accById(+b.dataset.acc)); });
$("#add-account").onclick = () => openAccountSheet(null);

function openAccountSheet(a) {
  const v = a || { kind: "corrente", active: true, opening_balance: 0 };
  openSheet(`<p class="overline">${a ? "Editar conta" : "Nova conta"}</p><h2>${a ? esc(a.name) : "Conta"}</h2>
    <div class="form">
      <label class="field wide">Nome<input id="ac-name" value="${esc(v.name || "")}"></label>
      <label class="field">Tipo<select id="ac-kind">${Object.entries(KIND_LABEL).map(([k, l]) => `<option value="${k}" ${k === v.kind ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      <label class="field">Titular<select id="ac-owner">${peopleOptions(v.owner_id ?? null)}</select></label>
      <label class="field wide">Instituição<input id="ac-inst" value="${esc(v.institution || "")}"></label>
      <label class="field wide">Saldo inicial (R$)<input id="ac-open" inputmode="decimal" value="${v.opening_balance ?? 0}"></label>
      <label class="field">Dia de fechamento (cartão)<input id="ac-close" inputmode="numeric" value="${v.closing_day ?? ""}"></label>
      <label class="field">Dia de vencimento (cartão)<input id="ac-due" inputmode="numeric" value="${v.due_day ?? ""}"></label>
      <label class="field wide">Limite (cartão)<input id="ac-limit" inputmode="decimal" value="${v.credit_limit ?? ""}"></label>
    </div>
    <label class="check" style="margin-top:12px"><input type="checkbox" id="ac-active" ${v.active ? "checked" : ""}> Conta ativa</label>
    <p class="hint">Contas importadas por OFX acertam o saldo sozinhas pelo saldo que o banco informa no arquivo.</p>
    <div class="row"><button class="primary" id="ac-save">Salvar</button>${a ? '<button class="danger" id="ac-del">Excluir conta e lançamentos</button>' : ""}</div>`);
  $("#ac-save").onclick = async () => {
    const body = {
      name: sheetVal("ac-name"), kind: sheetVal("ac-kind"), institution: sheetVal("ac-inst") || null,
      owner_id: sheetVal("ac-owner") ? +sheetVal("ac-owner") : null, opening_balance: parseNum(sheetVal("ac-open")) || 0,
      closing_day: parseInt(sheetVal("ac-close"), 10) || null, due_day: parseInt(sheetVal("ac-due"), 10) || null,
      credit_limit: parseNum(sheetVal("ac-limit")) ?? null, active: $("#ac-active").checked,
    };
    if (!body.name) return toast("Informe o nome");
    await api(a ? "PUT" : "POST", a ? `/api/accounts/${a.id}` : "/api/accounts", body);
    closeSheet();
    toast("Conta salva");
    await loadBase();
    await refresh();
  };
  if (a) $("#ac-del").onclick = async () => {
    if (!confirm(`Excluir "${a.name}" e todos os lançamentos dela?`)) return;
    await api("DELETE", `/api/accounts/${a.id}`);
    closeSheet();
    await loadBase();
    await refresh();
  };
}

$("#set-categories").addEventListener("click", (e) => { const b = e.target.closest("[data-cat]"); if (b) openCategorySheet(catById(+b.dataset.cat)); });
$("#add-category").onclick = () => openCategorySheet(null);
function openCategorySheet(c) {
  const v = c || { type: "despesa", group: "", active: true };
  const groups = [...new Set(state.categories.map((x) => x.group))];
  openSheet(`<p class="overline">${c ? "Editar categoria" : "Nova categoria"}</p><h2>${c ? esc(c.name) : "Categoria"}</h2>
    <div class="form">
      <label class="field wide">Nome<input id="ct-name" value="${esc(v.name || "")}"></label>
      <label class="field">Grupo<input id="ct-group" list="ct-groups" value="${esc(v.group)}"><datalist id="ct-groups">${groups.map((g) => `<option value="${esc(g)}">`).join("")}</datalist></label>
      <label class="field">Tipo<select id="ct-type">${Object.entries({ despesa: "Despesa", receita: "Receita", transferencia: "Transferência" }).map(([k, l]) => `<option value="${k}" ${k === v.type ? "selected" : ""}>${l}</option>`).join("")}</select></label>
    </div>
    <label class="check" style="margin-top:12px"><input type="checkbox" id="ct-active" ${v.active ? "checked" : ""}> Ativa</label>
    <div class="row" style="margin-top:12px"><button class="primary" id="ct-save">Salvar</button>${c ? '<button class="danger" id="ct-del">Excluir</button>' : ""}</div>`);
  $("#ct-save").onclick = async () => {
    const body = { name: sheetVal("ct-name"), group: sheetVal("ct-group") || "Outros", type: sheetVal("ct-type"), active: $("#ct-active").checked, sort_order: c ? c.sort_order : 9999 };
    if (!body.name) return toast("Informe o nome");
    await api(c ? "PUT" : "POST", c ? `/api/categories/${c.id}` : "/api/categories", body);
    closeSheet();
    await loadBase();
    await renderAjustes();
  };
  if (c) $("#ct-del").onclick = async () => {
    if (!confirm("Excluir a categoria? Os lançamentos dela ficam sem categoria.")) return;
    await api("DELETE", `/api/categories/${c.id}`);
    closeSheet();
    await loadBase();
    await renderAjustes();
  };
}

$("#rule-filter").addEventListener("click", (e) => { const b = e.target.closest("button[data-src]"); if (b) { state.ruleSource = b.dataset.src; renderRules(); } });
$("#set-rules").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-del-rule]");
  if (!b) return;
  await api("DELETE", `/api/rules/${b.dataset.delRule}`);
  await renderRules();
});
$("#reapply-rules").onclick = async () => {
  const r = await api("POST", "/api/rules/apply");
  toast(`${r.categorized} de ${r.checked} pendentes categorizados pelas regras`);
};
$("#add-rule").onclick = () => {
  openSheet(`<p class="overline">Nova regra</p><h2>Quando a descrição…</h2>
    <div class="form"><label class="field">Tipo<select id="rl-match"><option value="contains">contém</option><option value="exact">é exatamente</option></select></label>
      <label class="field wide">Texto<input id="rl-pattern" placeholder="ex.: POSTO"></label></div>
    <label class="field">…categorizar como<select id="rl-cat">${categoryOptions(null, { allowNone: false })}</select></label>
    <div class="row" style="margin-top:12px"><button class="primary" id="rl-save">Criar regra</button></div>`);
  $("#rl-save").onclick = async () => {
    if (sheetVal("rl-pattern").trim().length < 2) return toast("Texto muito curto");
    await api("POST", "/api/rules", { pattern: sheetVal("rl-pattern"), match: sheetVal("rl-match"), category_id: +sheetVal("rl-cat") });
    closeSheet();
    state.ruleSource = "";
    await renderRules();
  };
};

// ------------------------------------------------------------------ navegação, tema e início
const RENDER = { inicio: renderInicio, lancamentos: renderLancamentos, importar: renderImportar, planejamento: renderPlanejamento, dividas: renderDividas, ajustes: renderAjustes };

const TITLES = { inicio: "Início", lancamentos: "Lançamentos", importar: "Importações", planejamento: "Planejamento", dividas: "Dívidas", ajustes: "Ajustes" };
const SUBTITLES = {
  inicio: "", lancamentos: "Busque e categorize gastos", importar: "Extratos e faturas em OFX",
  planejamento: "Plano do mês e fluxo futuro", dividas: "Cartões, empréstimos e acordos", ajustes: "Pessoas, contas e preferências",
};
function screenHead(tab) {
  if (tab === "inicio") {
    const who = state.person !== "all" && state.person !== "conjunto" ? personName(+state.person) : "família";
    $("#screen-title").textContent = `Olá, ${who}`;
    $("#screen-sub").textContent = mlong(state.tx.month || thisMonth());
  } else {
    $("#screen-title").textContent = TITLES[tab];
    $("#screen-sub").textContent = SUBTITLES[tab];
  }
}
function showTab(tab) {
  state.tab = tab;
  screenHead(tab);
  $$("#nav button").forEach((x) => x.classList.toggle("active", x.dataset.tab === tab));
  $$("#bottomnav button[data-tab]").forEach((x) => (x.dataset.tab === tab ? x.setAttribute("aria-current", "page") : x.removeAttribute("aria-current")));
  $$("section.tab").forEach((s) => s.classList.toggle("active", s.id === `tab-${tab}`));
  history.replaceState(null, "", `#${tab}`);
}
async function goTab(tab) {
  closeSheet();
  showTab(tab);
  window.scrollTo({ top: 0 });
  await RENDER[tab]();
  Object.values(charts).forEach((c) => c.resize());
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("#nav button[data-tab], #bottomnav button[data-tab], [data-goto]");
  if (b) goTab(b.dataset.tab || b.dataset.goto);
});
window.addEventListener("hashchange", () => {
  const tab = location.hash.slice(1);
  if (RENDER[tab] && tab !== state.tab) goTab(tab);
});
$("#person").addEventListener("change", (e) => { state.person = e.target.value; screenHead(state.tab); refresh(); });

// tema navy (padrão, como as telas de referência) ou claro
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $('meta[name="theme-color"]').setAttribute("content", theme === "navy" ? "#0b2a86" : "#fafafa");
  $$("#theme-seg button").forEach((b) => b.classList.toggle("active", b.dataset.themeSet === theme));
  try { localStorage.setItem("financi-tema", theme); } catch (_) { /* navegação privada */ }
  $("#theme-btn").innerHTML = theme === "navy" ? ICON.sun : ICON.moon;
}
$("#theme-btn").addEventListener("click", async () => {
  applyTheme(document.documentElement.dataset.theme === "navy" ? "light" : "navy");
  await refresh();
});
applyTheme(document.documentElement.dataset.theme === "light" ? "light" : "navy");
$("#theme-seg").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-theme-set]");
  if (!b) return;
  applyTheme(b.dataset.themeSet);
  await refresh();
});

async function checkStatus() {
  const st = await api("GET", "/api/status");
  state.status = st;
  const warn = [];
  if (st.hosted && !st.auth) warn.push("Este endereço está público e sem senha: qualquer pessoa com o link vê seus dados. Defina FINANCI_PASSWORD nas variáveis de ambiente do Vercel e faça um novo deploy.");
  if (st.hosted && st.database === "sqlite") warn.push("DATABASE_URL não está definida: os dados não ficam salvos. Configure a connection string do Neon no Vercel.");
  const el = $("#security-banner");
  el.hidden = !warn.length;
  el.innerHTML = warn.map((w) => `<div><span class="badge strong">atenção</span> ${esc(w)}</div>`).join("");
}

// ------------------------------------------------------------------ acesso: senha uma vez por aparelho, Face ID opcional
const FACEID_KEY = "financi-faceid";      // id da passkey deste aparelho (Face ID ligado aqui)
const UNLOCKED_KEY = "financi-unlocked";  // sessionStorage: já desbloqueado nesta abertura do app
const store = (area, k, v) => {
  try {
    const st = area === "s" ? sessionStorage : localStorage;
    if (v === undefined) return st.getItem(k);
    if (v === null) st.removeItem(k); else st.setItem(k, v);
  } catch (_) { /* navegação privada */ }
  return null;
};
const hasFaceId = () => !!store("l", FACEID_KEY) && !!window.PublicKeyCredential;
const BIO_NAME = /iPhone|iPad/.test(navigator.userAgent) ? "Face ID" : /Mac/.test(navigator.userAgent) ? "Touch ID" : "biometria";
const FACE_SVG = svg('<path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2"/>' +
  '<path d="M9 9.5v1M15 9.5v1M12 9.5v3.5h-1M9.5 15.5c1.4 1.2 3.6 1.2 5 0"/>');
const b64u = {
  enc: (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""),
  dec: (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)), (c) => c.charCodeAt(0)),
};
// credencial do navegador → JSON que o servidor confere (py_webauthn)
function credJSON(c) {
  const r = c.response;
  const out = { id: c.id, rawId: b64u.enc(c.rawId), type: c.type, clientExtensionResults: {}, response: { clientDataJSON: b64u.enc(r.clientDataJSON) } };
  if (c.authenticatorAttachment) out.authenticatorAttachment = c.authenticatorAttachment;
  if (r.attestationObject) {
    out.response.attestationObject = b64u.enc(r.attestationObject);
    out.response.transports = r.getTransports ? r.getTransports() : [];
  } else {
    out.response.authenticatorData = b64u.enc(r.authenticatorData);
    out.response.signature = b64u.enc(r.signature);
    if (r.userHandle) out.response.userHandle = b64u.enc(r.userHandle);
  }
  return out;
}
const postJSON = (url, body) => fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });

let loginWait = null;
function requireLogin() {
  loginWait ||= new Promise((resolve) => showLock(resolve)).finally(() => { loginWait = null; });
  return loginWait;
}
function showLock(done) {
  const el = $("#lock");
  el.hidden = false;
  document.body.classList.add("locked");
  $("#lock-msg").textContent = "";
  const bio = hasFaceId();
  $("#lock-bio").hidden = !bio;
  $("#lock-bio").innerHTML = `${FACE_SVG}<span>Entrar com ${BIO_NAME}</span>`;
  const finish = () => {
    el.hidden = true;
    document.body.classList.remove("locked");
    $("#lock-pw").value = "";
    store("s", UNLOCKED_KEY, "1");
    done();
  };
  $("#lock-form").onsubmit = async (e) => {
    e.preventDefault();
    $("#lock-go").disabled = true;
    // com Face ID ligado a senha também não fica salva: a próxima abertura pede a biometria de novo
    const r = await postJSON("/api/auth/login", { password: $("#lock-pw").value, remember: !hasFaceId() }).catch(() => null);
    $("#lock-go").disabled = false;
    if (r && r.ok) return finish();
    $("#lock-msg").textContent = r && r.status === 401 ? "Senha incorreta" : "Sem conexão. Tente de novo.";
    $("#lock-pw").select();
  };
  $("#lock-bio").onclick = async () => { if (await bioLogin()) finish(); };
  if (bio) bioLogin().then((ok) => ok && finish()); // pede a biometria direto (se o navegador exigir um toque, fica o botão)
  else setTimeout(() => $("#lock-pw").focus(), 60);
}
async function bioLogin() {
  if (bioLogin.busy) return false;
  bioLogin.busy = true;
  try {
    const opts = await (await fetch("/api/auth/passkey/login/options", { method: "POST" })).json();
    const cred = await navigator.credentials.get({ publicKey: { ...opts, challenge: b64u.dec(opts.challenge),
      allowCredentials: (opts.allowCredentials || []).map((c) => ({ ...c, id: b64u.dec(c.id) })) } });
    const r = await postJSON("/api/auth/passkey/login", { credential: credJSON(cred) });
    if (r.ok) return true;
    const j = await r.json().catch(() => ({}));
    $("#lock-msg").textContent = j.detail || "Não foi possível confirmar. Use a senha.";
    return false;
  } catch (e) {
    // cancelado pela pessoa (ou o navegador pediu um toque antes): fica a tela com o botão e a senha
    if (!["NotAllowedError", "AbortError"].includes(e.name)) $("#lock-msg").textContent = `${BIO_NAME} indisponível agora. Use a senha.`;
    return false;
  } finally {
    bioLogin.busy = false;
  }
}

// Face ID ligado: voltar ao app depois de 5 min em segundo plano pede a biometria de novo (a sessão é encerrada)
let hiddenAt = 0;
document.addEventListener("visibilitychange", async () => {
  if (document.hidden) { hiddenAt = Date.now(); return; }
  if (!hasFaceId() || !state.status?.auth || !hiddenAt || Date.now() - hiddenAt < 5 * 60e3) return;
  hiddenAt = 0;
  await fetch("/api/auth/logout", { method: "POST" });
  store("s", UNLOCKED_KEY, null);
  await requireLogin();
  refresh();
});

const deviceLabel = () => {
  const ua = navigator.userAgent;
  return /iPhone/.test(ua) ? "iPhone" : /iPad/.test(ua) ? "iPad" : /Android/.test(ua) ? "Android" : /Mac/.test(ua) ? "Mac" : /Windows/.test(ua) ? "Windows" : "Aparelho";
};
async function renderSecurity() {
  const card = $("#card-security");
  card.hidden = !state.status?.auth;
  if (card.hidden) return;
  const keys = await api("GET", "/api/auth/passkeys");
  const mine = store("l", FACEID_KEY);
  let supported = false;
  try { supported = !!window.PublicKeyCredential && await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable(); } catch (_) { /* sem suporte */ }
  const on = hasFaceId();
  const intro = on
    ? `<p class="hint">Este aparelho abre com ${BIO_NAME}. A senha continua valendo se a biometria falhar.</p>
       <div class="sec-actions"><button class="secondary" id="faceid-off">Desligar ${BIO_NAME} neste aparelho</button></div>`
    : supported
      ? `<p class="hint">A senha fica salva neste aparelho. Para mais privacidade, ligue o ${BIO_NAME}: o app passa a pedir a biometria a cada abertura.</p>
         <div class="sec-actions"><button class="primary" id="faceid-on">Abrir com ${BIO_NAME}</button></div>`
      : '<p class="hint">A senha fica salva neste aparelho. Este navegador não oferece biometria; no iPhone, use o app instalado pelo Safari.</p>';
  const when = (iso) => (iso ? `${dlabel(iso)}/${iso.slice(0, 4)}` : "");
  const list = keys.map((k) => listRow({ icon: FACE_SVG, title: `${esc(k.label)}${String(k.id) === mine ? " · este aparelho" : ""}`,
    desc: `Ligado em ${when(k.created_at)}${k.last_used_at ? ` · último uso ${when(k.last_used_at)}` : ""}`,
    extra: `<button class="sm ghost" data-del-key="${k.id}">Remover</button>` })).join("");
  $("#set-security").innerHTML = `${intro}${list ? `<p class="overline imp-label">Aparelhos com biometria</p><div class="list">${list}</div>` : ""}
    <div class="sec-actions"><button class="ghost" id="logout">Sair deste aparelho</button></div>`;
}
async function enableFaceId() {
  try {
    const opts = await api("POST", "/api/auth/passkey/register/options");
    const cred = await navigator.credentials.create({ publicKey: { ...opts, challenge: b64u.dec(opts.challenge),
      user: { ...opts.user, id: b64u.dec(opts.user.id) },
      excludeCredentials: (opts.excludeCredentials || []).map((c) => ({ ...c, id: b64u.dec(c.id) })) } });
    const r = await api("POST", "/api/auth/passkey/register", { credential: credJSON(cred), label: deviceLabel() });
    store("l", FACEID_KEY, String(r.id));
    store("s", UNLOCKED_KEY, "1");
    toast(`Pronto: o Financi vai abrir com ${BIO_NAME}`);
  } catch (e) {
    if (e.name === "InvalidStateError") { store("l", FACEID_KEY, "1"); toast(`Este aparelho já tem ${BIO_NAME} ligado`); }
    else if (e.name !== "NotAllowedError" && e.name !== "AbortError" && !String(e.message).startsWith("Não")) toast(`Não foi possível ligar: ${e.message}`);
  }
  renderSecurity();
}
document.addEventListener("click", async (e) => {
  if (e.target.closest("#faceid-on")) return enableFaceId();
  if (e.target.closest("#faceid-off")) {
    const id = store("l", FACEID_KEY);
    if (id && /^\d+$/.test(id)) await api("DELETE", `/api/auth/passkeys/${id}`).catch(() => null);
    store("l", FACEID_KEY, null);
    await api("POST", "/api/auth/session", { remember: true }); // volta a ficar salvo neste aparelho
    toast(`${BIO_NAME} desligado. A senha fica salva neste aparelho.`);
    return renderSecurity();
  }
  const del = e.target.closest("[data-del-key]");
  if (del) {
    if (!confirm("Remover a biometria deste aparelho? Ele vai precisar da senha para entrar.")) return;
    await api("DELETE", `/api/auth/passkeys/${del.dataset.delKey}`);
    if (del.dataset.delKey === store("l", FACEID_KEY)) store("l", FACEID_KEY, null);
    return renderSecurity();
  }
  if (e.target.closest("#logout")) {
    if (!confirm("Sair deste aparelho? Para entrar de novo, vai precisar da senha.")) return;
    await fetch("/api/auth/logout", { method: "POST" });
    store("l", FACEID_KEY, null);
    store("s", UNLOCKED_KEY, null);
    location.reload();
  }
});

// a casca do app fica guardada no aparelho (abre sem esperar o servidor); avisa quando há versão nova
if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
  navigator.serviceWorker.register("/sw.js").catch(() => { /* sem service worker: funciona igual, só mais lento */ });
  navigator.serviceWorker.addEventListener("message", (e) => {
    if (e.data && e.data.type === "updated") toast("Nova versão do Financi", { label: "Atualizar", run: () => location.reload() });
  });
}

(async function init() {
  // Face ID ligado: cada abertura do app pede a biometria (recarregar a página na mesma abertura não pede)
  if (hasFaceId() && !store("s", UNLOCKED_KEY)) await fetch("/api/auth/logout", { method: "POST" }).catch(() => null);
  checkStatus().catch(() => null);
  await loadBase();
  const tab = location.hash.slice(1);
  if (RENDER[tab]) showTab(tab);
  await refresh();
})().catch(() => null); // sem rede: a casca abre e o aviso de conexão já apareceu
