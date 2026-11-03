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
  const r = await fetch(url, opts);
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
  plan: { month: thisMonth(), scope: "padrao", suggestions: null },
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
async function renderInicio() {
  const d = await api("GET", withPerson(`/api/dashboard`));
  const empty = state.accounts.length === 0;
  $("#home-empty").hidden = !empty;
  $("#home-content").hidden = empty;
  $("#home-crumb").textContent = mlong(d.month);
  if (empty) return;
  if (!state.monthSynced) {
    // na primeira visita com dados, Lançamentos e Planejamento abrem no mesmo mês que o Início mostra
    state.monthSynced = true;
    state.tx.month = state.plan.month = d.month;
  }
  const T = d.month_totals, DT = d.debts_totals;
  $("#h-saldo").textContent = fmt2(d.saldo_contas);
  const net = T.receitas - T.despesas;
  const arrow = svg(net >= 0 ? '<path d="M12 19V5M6 11l6-6 6 6"/>' : '<path d="M12 5v14M6 13l6 6 6-6"/>', "i");
  $("#h-trend").innerHTML = `<b>${arrow}${net >= 0 ? "+" : "−"}${fmt(Math.abs(net))}</b> em ${MESES_LONGOS[+d.month.slice(5, 7) - 1]}`;
  $("#h-detail").textContent = `Receitas ${fmt(T.receitas)} · Despesas ${fmt(T.despesas)}${d.investido ? ` · Investido ${fmt(d.investido)}` : ""}`;
  $("#qa-review").textContent = d.uncategorized ? `${d.uncategorized} pendentes` : "Nada pendente";

  // destaques escritos como constatação + o que significa (InsightRow)
  const ins = [];
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

  const accRows = d.accounts.filter((a) => a.kind !== "cartao").map((a) => listRow({ icon: esc(initials(a.name)), title: esc(a.name),
    desc: `${KIND_LABEL[a.kind]} · ${esc(personName(a.owner_id))}`, amount: signed(a.balance) }));
  const cardRows = d.cards.map((c) => listRow({ icon: ICON.card, title: esc(c.name),
    desc: c.configured ? `Fatura de ${mlabel(c.invoice.month)} · vence ${dlabel(c.invoice.due)}` : "Configure fechamento e vencimento",
    amount: fmt2(c.invoice.amount) }));
  $("#home-accounts").innerHTML = [...accRows, ...cardRows].join("") || '<p class="hint">Nenhuma conta.</p>';

  $("#home-groups").innerHTML = d.groups.length ? d.groups.map((g) => {
    const max = Math.max(...g.values, 1), cur = g.values[g.values.length - 1];
    const withData = g.values.filter((v) => v > 0);
    const avg = withData.length ? withData.reduce((a, b) => a + b, 0) / withData.length : 0;
    const bars = g.values.map((v, i) => `<i class="${i === g.values.length - 1 ? "on" : ""}" style="height:${Math.max(6, (v / max) * 100)}%" title="${mlabel(g.months[i])}: ${fmt(v)}"></i>`).join("");
    return `<div class="cat-card">${well(esc(initials(g.group)))}<div class="cat-card__text"><div class="cat-card__label">${esc(g.group)}</div>
      <div class="cat-card__meta">média ${fmt(avg)} por mês</div></div><div class="cat-card__right"><div class="cat-card__amount">${fmt2(cur)}</div>
      <div class="spark">${bars}</div></div></div>`;
  }).join("") : '<p class="hint">Sem gastos categorizados ainda.</p>';
}
document.addEventListener("click", (e) => {
  const review = e.target.closest(".home-actions [data-review], #home-insights [data-go=review]");
  const go = e.target.closest("#home-insights [data-go]");
  if (review) {
    e.preventDefault();
    state.tx.status = "revisar";
    goTab("lancamentos");
  } else if (go) {
    e.preventDefault();
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

function renderTxList() {
  const f = state.tx;
  if (!f.rows.length) {
    $("#tx-list").innerHTML = `<p class="hint" style="margin:0">${f.status ? "Nada pendente. Tudo categorizado." : "Nenhum lançamento neste mês. Importe um extrato em Importar extrato."}</p>`;
    updateBulk();
    return;
  }
  let h = "", last = null;
  for (const t of f.rows) {
    if (t.date !== last) {
      h += `<div class="day-head">${dlabel(t.date)}</div>`;
      last = t.date;
    }
    const cat = catById(t.category_id), acc = accById(t.account_id);
    const inst = t.installment ? ` · parcela ${t.installment[0]}/${t.installment[1]}` : "";
    h += `<div class="az-insight tx-row" data-id="${t.id}">
      <label class="tx-check" title="Selecionar"><input type="checkbox" data-sel="${t.id}" ${f.selected.has(t.id) ? "checked" : ""}></label>
      ${well(esc(initials(cat ? cat.group : "?")))}
      <div class="az-insight__text"><div class="az-insight__title">${esc(t.description)}</div>
        <div class="az-insight__desc">${esc(cat ? cat.name : "Sem categoria")} · ${esc(acc ? acc.name : "")}${inst} ${txBadge(t)}</div></div>
      <span class="amount">${signed(t.amount)}</span></div>`;
  }
  $("#tx-list").innerHTML = h;
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
$("#tx-add").onclick = openNewTx;
$("#tx-fab").onclick = openNewTx;

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

// ------------------------------------------------------------------ PLANEJAMENTO
const srcTag = (src) => (src === "orçamento" ? "" : ` <span class="muted">(${src})</span>`);
async function renderPlanejamento() {
  const p = state.plan;
  $("#bud-month").value = p.month.slice(0, 7);
  $$("#bud-scope button").forEach((b) => b.classList.toggle("active", b.dataset.scope === p.scope));
  const [v, proj] = await Promise.all([api("GET", withPerson(`/api/budget?month=${p.month}`)), api("GET", withPerson(`/api/projection?months=6`))]);
  const T = v.totals;
  $("#bud-tiles").innerHTML = [
    ["Receitas", fmt(T.receitas), T.receitas_previstas ? `previstas ${fmt(T.receitas_previstas)}` : "sem previsão"],
    ["Despesas", fmt(T.despesas), T.despesas_orcadas ? `orçadas ${fmt(T.despesas_orcadas)}` : "sem orçamento"],
    ["Sobra do mês", `${T.receitas < T.despesas ? "−" : ""}${fmt(Math.abs(T.receitas - T.despesas))}`, T.receitas_previstas ? `prevista ${fmt(T.receitas_previstas - T.despesas_orcadas)}` : ""],
    ["Sem categoria", fmt(T.sem_categoria), T.sem_categoria ? "categorize em Lançamentos" : "tudo categorizado"],
  ].map(([l, val, sub]) => tile(l, val, sub)).join("");

  const byCat = Object.fromEntries(v.rows.map((r) => [r.category_id, r]));
  const sug = p.suggestions ? Object.fromEntries(p.suggestions.map((s) => [s.category_id, s.amount])) : {};
  let h = `<thead><tr><th>Categoria</th><th>Orçado</th><th>Realizado</th><th>Restante</th><th class="bar-col"></th></tr></thead><tbody>`;
  for (const type of ["despesa", "receita"]) {
    const groups = {};
    state.categories.filter((c) => c.type === type && c.active).forEach((c) => (groups[c.group] ||= []).push(c));
    h += `<tr class="group"><td colspan="5">${TYPE_LABEL[type]}</td></tr>`;
    for (const [g, cs] of Object.entries(groups)) {
      const sumP = cs.reduce((s, c) => s + (byCat[c.id]?.planned || 0), 0), sumA = cs.reduce((s, c) => s + (byCat[c.id]?.actual || 0), 0);
      if (type === "despesa") h += `<tr class="subgroup"><td>${esc(g)}</td><td>${fmt(sumP)}</td><td>${fmt(sumA)}</td><td>${sumP ? fmt(sumP - sumA) : ""}</td><td></td></tr>`;
      for (const c of cs) {
        const r = byCat[c.id] || { planned: 0, actual: 0 };
        const value = c.id in sug ? sug[c.id] : r.planned || "";
        const ratio = r.planned ? r.actual / r.planned : 0;
        const over = r.planned && r.actual > r.planned;
        h += `<tr><td class="cat-name">${esc(c.name)}</td>
          <td><input class="bud-in ${c.id in sug ? "suggested" : ""}" data-cat="${c.id}" inputmode="decimal" value="${value}" placeholder="–"></td>
          <td>${r.actual ? fmt2(r.actual) : ""}</td><td>${r.planned ? `${over ? "−" : ""}${fmt(Math.abs(r.planned - r.actual))}${over ? " acima" : ""}` : ""}</td>
          <td class="bar-col">${r.planned ? `<div class="meter ${over ? "over" : ""}"><i style="width:${Math.min(100, ratio * 100)}%"></i></div>` : ""}</td></tr>`;
      }
    }
  }
  const unc = byCat["null"] || v.rows.find((r) => r.category_id === null);
  if (unc) h += `<tr><td class="cat-name muted">Sem categoria</td><td></td><td>${fmt2(unc.actual)}</td><td></td><td></td></tr>`;
  const mobile = isMobile();
  $("#bud-table").innerHTML = mobile ? "" : h + "</tbody>";
  $("#bud-list").innerHTML = mobile ? budgetList(byCat, sug, unc) : "";
  $("#bud-savebar").hidden = true;

  // projeção
  $("#proj-hint").innerHTML = `Começa no próximo mês com <b>${fmt(proj.saldo_inicial)}</b> (saldo em contas ${fmt(proj.saldo_atual)}
    menos faturas abertas ${fmt(proj.faturas_abertas)}). Cada categoria usa o orçamento; as que não têm orçamento usam a média dos últimos meses (até 3).
    Somam-se as parcelas das dívidas e as parcelas de cartão já compradas.`;
  const ms = proj.months;
  chart("chart-proj").setOption({
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: ms.map((m) => mlabel(m.month)) },
    series: [
      { name: "Saldo projetado", type: "line", data: ms.map((m) => m.saldo), color: LIT(), symbol: "circle", symbolSize: 7, lineStyle: { width: 2.5 },
        areaStyle: { color: DIM(), opacity: 0.5 },
        markLine: { symbol: "none", silent: true, label: { show: false }, lineStyle: { color: css("--line-strong"), type: "dashed" }, data: [{ yAxis: 0 }] } },
      { name: "Dívidas + parcelas de cartão", type: "bar", data: ms.map((m) => m.dividas + m.parcelas_cartao), color: css("--chart-mid"), barMaxWidth: 22, itemStyle: { borderRadius: [4, 4, 0, 0] } },
    ],
  }, true);
  if (isMobile()) {
    // celular: só o que cabe (saídas = despesas + dívidas + parcelas de cartão)
    $("#proj-table").innerHTML = `<thead><tr><th>Mês</th><th>Entradas</th><th>Saídas</th><th>Saldo</th></tr></thead><tbody>` +
      ms.map((m) => `<tr><td>${mlabel(m.month)}</td><td>${short(m.receitas)}</td><td>${short(m.despesas + m.dividas + m.parcelas_cartao)}</td>
        <td><b>${m.saldo < 0 ? "−" : ""}${fmt(Math.abs(m.saldo))}</b></td></tr>`).join("") + "</tbody>";
    return;
  }
  $("#proj-table").innerHTML = `<thead><tr><th>Mês</th><th>Receitas</th><th>Despesas</th><th>Dívidas</th><th>Parcelas cartão</th><th>Saldo</th></tr></thead><tbody>` +
    ms.map((m) => `<tr><td>${mlabel(m.month)}</td><td>${fmt(m.receitas)}${srcTag(m.fonte_receitas)}</td>
      <td>${fmt(m.despesas)}${srcTag(m.fonte_despesas)}</td><td>${fmt(m.dividas)}</td><td>${fmt(m.parcelas_cartao)}</td>
      <td class="${m.saldo < 0 ? "neg" : ""}"><b>${m.saldo < 0 ? "−" : ""}${fmt(Math.abs(m.saldo))}</b></td></tr>`).join("") + "</tbody>";
}

// orçamento no celular: uma linha por categoria com o valor editável e a barra de consumo
function budgetList(byCat, sug, unc) {
  let h = "";
  for (const type of ["despesa", "receita"]) {
    const groups = {};
    state.categories.filter((c) => c.type === type && c.active).forEach((c) => (groups[c.group] ||= []).push(c));
    h += `<p class="overline bl-type">${type === "despesa" ? "Despesas" : "Receitas"}</p>`;
    for (const [g, cs] of Object.entries(groups)) {
      const sumP = cs.reduce((s, c) => s + (byCat[c.id]?.planned || 0), 0), sumA = cs.reduce((s, c) => s + (byCat[c.id]?.actual || 0), 0);
      h += `<div class="bl-group"><div class="bl-group__head"><b>${esc(type === "despesa" ? g : "Receitas")}</b>
        <span>${sumP ? `${fmt(sumA)} de ${fmt(sumP)}` : sumA ? fmt(sumA) : ""}</span></div>`;
      for (const c of cs) {
        const r = byCat[c.id] || { planned: 0, actual: 0 };
        const value = c.id in sug ? sug[c.id] : r.planned || "";
        const over = r.planned && r.actual > r.planned;
        const left = r.planned - r.actual;
        const info = r.planned ? (over ? `${fmt(-left)} acima` : `restam ${fmt(left)}`) : r.actual ? "sem orçamento" : "";
        h += `<div class="bl-row"><div class="bl-row__text"><div class="bl-row__name">${esc(c.name)}</div>
            <div class="bl-row__meta">${r.actual ? `${fmt2(r.actual)} realizado` : "nada realizado"}${info ? ` · ${info}` : ""}</div>
            ${r.planned ? `<div class="meter ${over ? "over" : ""}"><i style="width:${Math.min(100, (r.actual / r.planned) * 100)}%"></i></div>` : ""}</div>
          <input class="bud-in ${c.id in sug ? "suggested" : ""}" data-cat="${c.id}" inputmode="decimal" value="${value}" placeholder="R$" aria-label="Orçado para ${esc(c.name)}"></div>`;
      }
      h += "</div>";
    }
  }
  if (unc) h += `<div class="bl-group"><div class="bl-group__head"><b>Sem categoria</b><span>${fmt2(unc.actual)}</span></div></div>`;
  return h;
}
$("#bud-card").addEventListener("input", (e) => { if (e.target.matches(".bud-in") && isMobile()) $("#bud-savebar").hidden = false; });

$("#bud-month").addEventListener("change", (e) => { if (e.target.value) { state.plan.month = e.target.value + "-01"; state.plan.suggestions = null; renderPlanejamento(); } });
$("#bud-prev").onclick = () => { state.plan.month = addMonths(state.plan.month, -1); state.plan.suggestions = null; renderPlanejamento(); };
$("#bud-next").onclick = () => { state.plan.month = addMonths(state.plan.month, 1); state.plan.suggestions = null; renderPlanejamento(); };
$("#bud-scope").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-scope]");
  if (!b) return;
  state.plan.scope = b.dataset.scope;
  $$("#bud-scope button").forEach((x) => x.classList.toggle("active", x === b));
});
$("#bud-suggest").onclick = async () => {
  state.plan.suggestions = await api("GET", withPerson(`/api/budget/suggest?month=${state.plan.month}`));
  await renderPlanejamento();
  toast(state.plan.suggestions.length ? "Sugestões preenchidas (em destaque). Ajuste e salve." : "Sem histórico suficiente para sugerir");
};
async function saveBudget() {
  const month = state.plan.scope === "mes" ? state.plan.month : null;
  const items = $$("#bud-card .bud-in").map((i) => ({ category_id: +i.dataset.cat, month, amount: parseNum(i.value) ?? null }))
    .filter((it) => it.amount !== undefined);
  await api("PUT", "/api/budgets", items);
  state.plan.suggestions = null;
  toast(month ? `Orçamento de ${mlabel(month)} salvo` : "Orçamento padrão salvo (vale para todo mês)");
  await renderPlanejamento();
}
$("#bud-save").onclick = saveBudget;
$("#bud-save-m").onclick = saveBudget;

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
  $("#debt-ring").innerHTML = `<div class="az-score"><div class="az-score__ring"><svg viewBox="0 0 128 128"><circle class="az-score__track" cx="64" cy="64" r="58"/>
      <circle class="az-score__value" cx="64" cy="64" r="58" stroke-dasharray="${(C * shown).toFixed(1)} ${C.toFixed(1)}"/></svg>
      <div class="az-score__num">${c == null ? "–" : Math.round(c * 100)}<small>% da renda</small></div></div>
    <div class="az-score__title">Comprometimento</div><div class="az-score__desc">${c == null ? "Importe extratos com receitas para calcular" : "Parcelas por mês sobre a renda média"}</div></div>`;

  $("#debt-cards").innerHTML = d.cards.length ? d.cards.map((c) => {
    const used = c.limit ? Math.min(1, c.limit_used / c.limit) : null;
    const hist = c.history.map((h) => `<span><b>${fmt(h.amount)}</b> ${mlabel(h.month)}</span>`).join("");
    const fut = c.future_installments.slice(0, 6).map((f) => `<span>${mlabel(f.month)} <b>${fmt(f.amount)}</b></span>`).join("");
    return `<div class="card"><div class="card-head"><h3>${esc(c.name)}</h3><button class="link" data-card="${c.account_id}">${c.configured ? "Editar" : "Configurar"}</button></div>
      ${c.configured ? `<div class="amount-row"><span class="big">${fmt2(c.current_invoice.amount)}</span><span class="muted">fatura de ${mlabel(c.current_invoice.month)} · vence ${dlabel(c.current_invoice.due)}</span></div>`
        : `<p class="hint">Informe o dia de fechamento e de vencimento para calcular as faturas.</p>`}
      ${used != null ? `<div class="meter" title="Limite usado"><i style="width:${used * 100}%"></i></div><p class="hint">${fmt(c.limit_used)} usados de ${fmt(c.limit)} · disponível ${fmt(c.limit_available)}</p>` : ""}
      ${hist ? `<p class="overline">Últimas faturas</p><div class="chips">${hist}</div>` : ""}
      ${fut ? `<p class="overline">Parcelas a cair · total ${fmt(c.future_total)}</p><div class="chips">${fut}</div>` : ""}</div>`;
  }).join("") : '<p class="hint">Nenhum cartão. Importe o OFX da fatura em Importar extrato.</p>';

  $("#debt-list").innerHTML = d.debts.length ? d.debts.map((x) => {
    const prog = x.total_installments ? x.paid / x.total_installments : null;
    return `<div class="card debt"><div class="card-head"><h3>${esc(x.name)}</h3><button class="link" data-debt="${x.id}">Editar</button></div>
      <p class="hint" style="margin:0 0 8px">${DEBT_LABEL[x.kind]}${x.creditor ? ` · ${esc(x.creditor)}` : ""} · ${esc(personName(x.owner_id))}</p>
      <div class="amount-row"><span class="big">${fmt2(x.balance)}</span><span class="muted">saldo devedor${x.total_installments ? " (valor para quitar hoje)" : ""}</span></div>
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

const TITLES = { inicio: "Início", lancamentos: "Lançamentos", importar: "Importar extrato", planejamento: "Planejamento", dividas: "Dívidas", ajustes: "Ajustes" };
function showTab(tab) {
  state.tab = tab;
  $("#screen-title").textContent = TITLES[tab];
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
$("#person").addEventListener("change", (e) => { state.person = e.target.value; refresh(); });

// tema claro (páginas brancas) ou navy; o cabeçalho do Início é sempre navy
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $('meta[name="theme-color"]').setAttribute("content", theme === "navy" ? "#072061" : "#fafafa");
  $$("#theme-seg button").forEach((b) => b.classList.toggle("active", b.dataset.themeSet === theme));
  try { localStorage.setItem("financi-theme", theme); } catch (_) { /* navegação privada */ }
  $("#theme-btn").innerHTML = theme === "navy" ? ICON.sun : ICON.moon;
}
$("#theme-btn").addEventListener("click", async () => {
  applyTheme(document.documentElement.dataset.theme === "navy" ? "light" : "navy");
  await refresh();
});
applyTheme(document.documentElement.dataset.theme === "navy" ? "navy" : "light");
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

(async function init() {
  checkStatus();
  await loadBase();
  const tab = location.hash.slice(1);
  if (RENDER[tab]) showTab(tab);
  await refresh();
})();
