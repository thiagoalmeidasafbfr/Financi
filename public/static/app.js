/* Financi — interface (vanilla JS + ECharts). */
"use strict";

// ------------------------------------------------------------------ utilidades
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const BRL2 = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const NUM = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmt = (v) => (v == null || isNaN(v) ? "–" : BRL.format(v));
const fmt2 = (v) => (v == null || isNaN(v) ? "–" : BRL2.format(v));
const num = (v) => (!v ? "" : NUM.format(v));
const pct = (v, d = 1) => (v == null || isNaN(v) ? "–" : (v * 100).toFixed(d).replace(".", ",") + "%");
const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const mlabel = (iso) => (iso ? `${MESES[+iso.slice(5, 7) - 1]}/${iso.slice(2, 4)}` : "–");
const short = (v) => {
  const a = Math.abs(v);
  if (a >= 1e6) return (v / 1e6).toFixed(1).replace(".", ",") + "M";
  if (a >= 1e3) return (v / 1e3).toFixed(1).replace(".", ",") + "k";
  return String(Math.round(v));
};
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const parseNum = (s) => {
  s = String(s).trim();
  if (s === "") return null;
  if (s.includes(",")) s = s.replace(/\./g, "").replace(",", ".");
  const v = Number(s);
  return isNaN(v) ? undefined : v;
};
const toMonthInput = (iso) => (iso ? iso.slice(0, 7) : "");
const fromMonthInput = (v) => (v ? `${v}-01` : null);

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove("show"), 2600);
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
    try { detail = JSON.stringify((await r.json()).detail); } catch (_) { /* sem corpo */ }
    toast(`Erro: ${detail}`);
    throw new Error(detail);
  }
  return r.status === 204 ? null : r.json();
}

// ------------------------------------------------------------------ gráficos
const SERIES = () => ["--series-1", "--series-2", "--series-3", "--series-4", "--series-5"].map(css);
const charts = {};

function chart(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  if (charts[id] && charts[id].getDom() === el) return charts[id];
  charts[id] = echarts.init(el, null, { renderer: "svg" });
  return charts[id];
}
window.addEventListener("resize", () => Object.values(charts).forEach((c) => c.resize()));

function baseOption() {
  const ink2 = css("--text-secondary"), grid = css("--chart-grid"), axis = css("--border-default");
  return {
    animationDuration: 520,
    textStyle: { fontFamily: css("--font-core"), color: ink2 },
    grid: { left: 8, right: 16, top: 36, bottom: 8, containLabel: true },
    tooltip: {
      trigger: "axis", backgroundColor: css("--surface-card"), borderWidth: 0,
      extraCssText: `box-shadow:${css("--shadow-pop")};border-radius:10px`,
      textStyle: { color: css("--text-primary"), fontFamily: css("--font-core") },
      axisPointer: { type: "line", lineStyle: { color: axis } },
      valueFormatter: (v) => fmt(v),
    },
    legend: { top: 0, left: 0, icon: "circle", itemWidth: 8, itemHeight: 8, textStyle: { color: ink2 } },
    xAxis: { type: "category", axisLine: { lineStyle: { color: axis } }, axisTick: { show: false }, axisLabel: { color: css("--text-muted") } },
    yAxis: {
      type: "value", splitLine: { lineStyle: { color: grid } }, axisLabel: { color: css("--text-muted"), formatter: short },
    },
  };
}

// cor fixa por cenário (segue a entidade, não a posição na seleção)
function scenarioColor(id) {
  const idx = state.scenarios.findIndex((s) => s.id === id);
  const pal = SERIES();
  return idx >= 0 && idx < pal.length ? pal[idx] : css("--series-other");
}

const SANKEY_COLORS = () => ({
  receita: css("--series-1"),
  despesa_fixa: css("--series-2"),
  divida: css("--series-4"),
  despesa_variavel: css("--series-5"),
  investimento: css("--series-3"),
  sobra: css("--ink-900"),
  outros: css("--gray-500"),
});

function renderSankey(id, data, compact = false) {
  const c = chart(id);
  if (!c) return;
  const colors = SANKEY_COLORS();
  c.setOption({
    textStyle: { fontFamily: css("--font-core") },
    tooltip: {
      trigger: "item", backgroundColor: css("--surface-card"), borderWidth: 0,
      extraCssText: `box-shadow:${css("--shadow-pop")};border-radius:10px`,
      textStyle: { color: css("--text-primary") },
      formatter: (p) => {
        if (p.dataType === "edge") return `${esc(p.data.source)} → ${esc(p.data.target)}<br><b>${fmt(p.data.value)}</b>`;
        let html = `${esc(p.name)}<br><b>${fmt(p.value)}</b>`;
        const src = data.sources;
        if (p.name === data.hub && src && (src.resgates > 0.005 || src.saldo_anterior > 0.005)) {
          html += `<br><span style="color:${css("--text-secondary")}">receitas ${fmt(src.receitas)}` +
            (src.resgates > 0.005 ? ` · resgates ${fmt(src.resgates)}` : "") +
            (src.saldo_anterior > 0.005 ? ` · saldo anterior ${fmt(src.saldo_anterior)}` : "") + "</span>";
        }
        return html;
      },
    },
    series: [{
      type: "sankey", left: 8, right: compact ? 110 : 190, top: 8, bottom: 8,
      nodeGap: compact ? 6 : 9, nodeWidth: 10, draggable: false,
      emphasis: { focus: "adjacency" },
      data: data.nodes.map((n) => ({
        name: n.name, depth: n.depth, itemStyle: { color: colors[n.group] || colors.outros, borderWidth: 0 },
        // rótulos das colunas do meio ganham fundo para não se perderem sobre os fluxos
        label: n.depth === 1 || n.depth === 2
          ? { backgroundColor: css("--surface-card"), borderRadius: 4, padding: [2, 5], opacity: 0.94 }
          : { overflow: "truncate", width: compact ? 105 : 180 },
      })),
      links: data.links,
      lineStyle: { color: "gradient", opacity: 0.28, curveness: 0.5 },
      label: {
        color: css("--text-primary"), fontSize: compact ? 10 : 12,
        formatter: (p) => `${p.name}  {v|${short(p.value)}}`,
        rich: { v: { color: css("--text-muted"), fontSize: compact ? 9 : 11 } },
      },
    }],
  }, true);
}

// ------------------------------------------------------------------ estado
const state = {
  scenarios: [], categories: [], accounts: [], loans: [],
  current: null, projection: null, view: null, period: { start: null, end: null }, tab: "painel", arrears: [], newLines: new Set(), sug: { month: null, result: null },
  sankeyMonth: null, compareIds: null,
};
const GROUPS = {
  receita: "Receitas", despesa_fixa: "Despesas fixas", divida: "Empréstimos e dívidas",
  despesa_variavel: "Despesas variáveis", investimento: "Investimentos e reserva",
};
const KINDS = {
  manual: "Manual", salario: "Salário (reajustes)", decimo_terceiro: "13º salário", ferias: "1/3 de férias",
  restituicao_ir: "Restituição IR", bonus: "Bônus", consignados: "Consignados", quitacao: "Quitação de consignados",
  atrasos: "Pagamento de atrasos",
};

async function loadBase() {
  [state.scenarios, state.categories, state.accounts] = await Promise.all([
    api("GET", "/api/scenarios"), api("GET", "/api/categories"), api("GET", "/api/accounts"),
  ]);
  const sel = $("#scenario");
  if (!state.scenarios.find((s) => s.id === state.current)) {
    const base = state.scenarios.find((s) => s.is_baseline) || state.scenarios[0];
    state.current = base ? base.id : null;
  }
  sel.innerHTML = state.scenarios.map((s) => `<option value="${s.id}">${esc(s.name)}${s.is_baseline ? " (base)" : ""}</option>`).join("");
  if (state.current) sel.value = state.current;
}

const currentScenario = () => state.scenarios.find((s) => s.id === state.current);

async function loadProjection() {
  if (!state.current) {
    state.projection = state.view = null;
    return;
  }
  state.projection = await api("GET", `/api/scenarios/${state.current}/projection`);
  const months = state.projection.months;
  let { start, end } = state.period;
  if (start && !months.includes(start)) start = null;
  if (end && !months.includes(end)) end = null;
  if (start && end && start > end) [start, end] = [end, start];
  state.period = { start, end };
  // Painel e Fluxo usam o recorte do período; as demais telas usam o horizonte inteiro
  state.view = start || end
    ? await api("GET", `/api/scenarios/${state.current}/projection?${periodQuery()}`)
    : state.projection;
}

function periodQuery() {
  const q = new URLSearchParams();
  if (state.period.start) q.set("start", state.period.start);
  if (state.period.end) q.set("end", state.period.end);
  return q.toString();
}

function periodPresets(months) {
  const presets = [["Horizonte todo", null, null]];
  const today = new Date().toISOString().slice(0, 7) + "-01";
  const from = months.find((m) => m >= today);
  if (from) {
    const i = months.indexOf(from);
    presets.push(["Próximos 12 meses", from, months[Math.min(i + 11, months.length - 1)]]);
  }
  for (const y of [...new Set(months.map((m) => m.slice(0, 4)))]) {
    const ms = months.filter((m) => m.startsWith(y));
    presets.push([y, ms[0], ms[ms.length - 1]]);
  }
  return presets;
}

function renderPeriodBars() {
  const months = state.projection?.months || [];
  const { start, end } = state.period;
  const s = start || months[0], e = end || months[months.length - 1];
  const opts = (sel) => months.map((m) => `<option value="${m}" ${m === sel ? "selected" : ""}>${mlabel(m)}</option>`).join("");
  const presets = periodPresets(months);
  $$(".period-bar").forEach((bar) => {
    bar.innerHTML = `<span class="eyebrow" style="margin:0">Período</span>
      <select data-p="start" aria-label="Início do período">${opts(s)}</select><span class="muted">a</span>
      <select data-p="end" aria-label="Fim do período">${opts(e)}</select>
      <div class="segmented">${presets.map(([label, a, b]) =>
        `<button data-a="${a || ""}" data-b="${b || ""}" class="${(a || null) === start && (b || null) === end ? "active" : ""}">${label}</button>`).join("")}</div>
      <span class="muted">${state.view ? `${state.view.months.length} meses` : ""}</span>`;
  });
}

async function setPeriod(start, end) {
  const months = state.projection?.months || [];
  // período igual ao horizonte inteiro = sem recorte
  state.period = {
    start: start && start !== months[0] ? start : null,
    end: end && end !== months[months.length - 1] ? end : null,
  };
  await refresh();
}

document.addEventListener("change", (e) => {
  const bar = e.target.closest(".period-bar");
  if (!bar || !e.target.dataset.p) return;
  setPeriod(bar.querySelector('[data-p="start"]').value, bar.querySelector('[data-p="end"]').value);
});
document.addEventListener("click", (e) => {
  const b = e.target.closest(".period-bar .segmented button");
  if (b) setPeriod(b.dataset.a || null, b.dataset.b || null);
});

async function refresh() {
  $$("[data-scn]").forEach((el) => (el.textContent = currentScenario()?.name || "sem cenário"));
  const empty = !state.scenarios.length;
  $("#empty-state").hidden = !empty;
  $("#painel-content").hidden = empty;
  await loadProjection();
  renderPeriodBars();
  await (RENDER[state.tab] || (() => {}))();
}

// ------------------------------------------------------------------ PAINEL
const KPI_LABELS = [
  ["PERÍODO", null],
  ["mes_inicial", "Mês inicial", "m"], ["mes_final", "Mês final", "m"], ["n_meses", "Nº de meses", "n"],
  ["PATRIMÔNIO", null],
  ["saldo_inicial_conta", "Saldo inicial em conta"], ["saldo_final_conta", "Saldo final em conta"],
  ["saldo_final_investido", "Saldo final investido"], ["saldo_inicial_fgts", "Saldo inicial FGTS"],
  ["saldo_final_fgts", "Saldo final FGTS"], ["patrimonio_final", "Conta + investimentos + FGTS"],
  ["menor_saldo_conta", "Menor saldo em conta"], ["mes_menor_saldo", "Mês do menor saldo", "m"],
  ["meses_saldo_negativo", "Meses com saldo negativo", "n"], ["rendimento_acumulado", "Rendimento acumulado dos investimentos"],
  ["MÉDIAS MENSAIS", null],
  ["receita_media", "Receita média"], ["despesa_media", "Despesa média (total)"],
  ["custo_moradia_medio", "Custo médio com moradia"], ["pct_renda_moradia", "% da renda com moradia", "p"],
  ["custo_saude_medio", "Custo médio com saúde"], ["despesa_variavel_media", "Despesas variáveis – média"],
  ["saldo_livre_medio", "Saldo livre médio"], ["taxa_poupanca", "Taxa de poupança", "p"],
  ["DÍVIDAS", null],
  ["total_parcelas", "Total pago em parcelas"], ["total_quitacoes", "Total em quitações antecipadas"],
  ["total_atrasos_pagos", "Total pago em atrasos"],
  ["total_dividas", "Total de dívidas pagas"], ["pct_renda_dividas", "% da renda com dívidas", "p"],
  ["ultimo_mes_com_parcela", "Último mês com parcela", "m"], ["meses_acima_limite_dividas", "Meses acima do limite", "n"],
  ["INVESTIMENTOS", null],
  ["total_investido", "Total investido / reserva"],
];
const kfmt = (v, t) => (t === "m" ? mlabel(v) : t === "n" ? String(v ?? "–") : t === "p" ? pct(v) : fmt(v));

async function renderPainel() {
  const p = state.view;
  if (!p) return;
  const k = p.kpis, s = p.series, months = p.months;
  const whole = !state.period.start && !state.period.end;
  $("#hero-eyebrow").textContent = `Patrimônio ao fim ${whole ? "do horizonte" : `de ${mlabel(k.mes_final)}`} · conta + investimentos + FGTS`;
  $("#hero-value").textContent = fmt(k.patrimonio_final);
  $("#hero-caption").textContent = `${mlabel(k.mes_inicial)} a ${mlabel(k.mes_final)} · ${k.n_meses} meses`;
  const neg = k.meses_saldo_negativo;
  $("#hero-insight").innerHTML = neg
    ? `<div class="insight"><span class="badge negative">${neg} ${neg > 1 ? "meses" : "mês"}</span><span>com saldo negativo em conta; o pior é <b>${mlabel(k.mes_menor_saldo)}</b> (${fmt(k.menor_saldo_conta)})</span></div>`
    : `<div class="insight"><span class="badge accent">ok</span><span>saldo em conta nunca fica negativo no período</span></div>`;

  const tiles = [
    ["Saldo final em conta", fmt(k.saldo_final_conta), `menor: ${fmt(k.menor_saldo_conta)} em ${mlabel(k.mes_menor_saldo)}`],
    ["Saldo final investido", fmt(k.saldo_final_investido), `rendimento acumulado ${fmt(k.rendimento_acumulado)}`],
    ["FGTS ao fim", fmt(k.saldo_final_fgts), "referência, fora do saldo em conta"],
    ["Saldo livre médio", fmt(k.saldo_livre_medio), `taxa de poupança ${pct(k.taxa_poupanca)}`],
    ["Renda com dívidas", pct(k.pct_renda_dividas), `${k.meses_acima_limite_dividas} meses acima do limite`],
    ["Última parcela", mlabel(k.ultimo_mes_com_parcela), `quitações: ${fmt(k.total_quitacoes)}`, true],
  ];
  $("#kpi-tiles").innerHTML = tiles.map(([l, v, sub, inv]) =>
    `<div class="tile${inv ? " inverse" : ""}"><div class="label">${l}</div><div class="value">${v}</div><div class="sub">${sub}</div></div>`).join("");

  // Sankey
  const mSel = $("#sankey-month");
  mSel.innerHTML = months.map((m) => `<option value="${m}">${mlabel(m)}</option>`).join("");
  if (state.sankeyMonth && months.includes(state.sankeyMonth)) mSel.value = state.sankeyMonth;
  await drawPainelSankey();

  renderWaterfall(p.waterfall, k);
  const pal = SERIES();
  const line = (name, data, color, extra = {}) => ({ name, type: "line", data, color, symbol: "none", lineStyle: { width: 2 }, ...extra });
  chart("chart-lines").setOption({
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: months.map(mlabel) },
    series: [
      line("Receitas", s.receitas, pal[0]),
      line("Despesas", s.total_despesas, pal[1]),
      line("Saldo conta + investido", s.saldo_total, css("--ink-900"), { lineStyle: { width: 2.5 },
        markLine: { symbol: "none", silent: true, label: { show: false }, lineStyle: { color: css("--border-strong"), type: "dashed" }, data: [{ yAxis: 0 }] } }),
      line("FGTS", s.fgts_saldo, pal[2], { lineStyle: { width: 2, type: "dashed" } }),
    ],
  }, true);

  // tabela de KPIs
  let html = "<table>";
  for (const [key, label, t] of KPI_LABELS) {
    if (label === null) html += `<tr class="group"><td colspan="2">${key}</td></tr>`;
    else html += `<tr><td>${label}</td><td>${kfmt(k[key], t)}</td></tr>`;
  }
  $("#kpi-table").innerHTML = html + "</table>";
}

function renderWaterfall(w, k) {
  const cats = ["Saldo inicial", ...w.steps.map((x) => x.label), "Saldo final"];
  const items = [];
  let run = w.start;
  items.push({ y0: 0, y1: w.start, v: w.start, kind: "total" });
  for (const st of w.steps) {
    items.push({ y0: run, y1: run + st.value, v: st.value, kind: st.value >= 0 ? "up" : "down" });
    run += st.value;
  }
  items.push({ y0: 0, y1: w.end, v: w.end, kind: "total" });
  const color = { total: css("--ink-900"), up: css("--series-2"), down: css("--red-500") };
  const signed = (v, kind) => (kind === "total" ? fmt(v) : `${v >= 0 ? "+" : "−"}${fmt(Math.abs(v))}`);
  chart("chart-waterfall").setOption({
    ...baseOption(),
    legend: { show: false },
    grid: { left: 8, right: 16, top: 30, bottom: 8, containLabel: true },
    tooltip: { ...baseOption().tooltip, trigger: "item", formatter: (p) => {
      const it = items[p.dataIndex];
      return `${cats[p.dataIndex]}<br><b>${signed(it.v, it.kind)}</b>` +
        (p.dataIndex === 0 ? `<br><span style="color:${css("--text-muted")}">fim de ${mlabel(prevMonth(k.mes_inicial))}</span>` : "") +
        (p.dataIndex === items.length - 1 ? `<br><span style="color:${css("--text-muted")}">fim de ${mlabel(k.mes_final)}</span>` : "");
    } },
    xAxis: { ...baseOption().xAxis, data: cats, axisLabel: { color: css("--text-secondary"), interval: 0, width: 80, overflow: "break", fontSize: 11 } },
    series: [{
      type: "custom",
      data: items.map((it, i) => [i, it.y0, it.y1]),
      renderItem: (params, api) => {
        const i = api.value(0), a = api.coord([i, api.value(1)]), b = api.coord([i, api.value(2)]);
        const w2 = api.size([1, 0])[0] * 0.56;
        const it = items[i];
        return {
          type: "group",
          children: [
            { type: "rect", shape: { x: a[0] - w2 / 2, y: Math.min(a[1], b[1]), width: w2, height: Math.max(1, Math.abs(a[1] - b[1])), r: 3 },
              style: { fill: color[it.kind] } },
            { type: "text", style: { text: short(it.v), x: a[0], y: Math.min(a[1], b[1]) - 6, align: "center", verticalAlign: "bottom",
              fill: css("--text-secondary"), font: `11px ${css("--font-core")}` } },
          ],
        };
      },
      encode: { x: 0, y: [1, 2] },
    }],
  }, true);
}

const prevMonth = (iso) => { const [y, m] = iso.split("-").map(Number); return m === 1 ? `${y - 1}-12-01` : `${y}-${String(m - 1).padStart(2, "0")}-01`; };

async function drawPainelSankey() {
  const mode = $("#sankey-mode .active").dataset.mode;
  const sel = $("#sankey-month");
  sel.hidden = mode !== "month";
  let url = `/api/scenarios/${state.current}/sankey?${periodQuery()}`;
  if (mode === "month") {
    state.sankeyMonth = sel.value;
    url = `/api/scenarios/${state.current}/sankey?month=${sel.value}`;
  }
  renderSankey("chart-sankey", await api("GET", url));
}

// ------------------------------------------------------------------ FLUXO
const SUMMARY_ROWS = [
  ["receitas", "Receitas totais"], ["total_despesas", "Total de despesas"], ["saldo_operacional", "Saldo operacional"],
  ["saldo_disponivel", "Saldo disponível em conta (antes de investir)"], ["investimentos", "(−) Investimentos e reserva"],
  ["inv_resgate_automatico", "(+) Resgate automático"], ["saldo_livre", "Saldo livre do mês"],
  ["saldo_conta", "Saldo acumulado em conta", "highlight"], ["inv_rendimento", "(+) Rendimento dos investimentos"],
  ["inv_saldo_fim", "Saldo investido"],
  ["saldo_total", "Saldo total (conta + investimentos)", "highlight"], ["fgts_saldo", "Saldo FGTS (referência)"],
];

function seriesRow(label, vals, { cls = "", tip = "", last = false, fmtv = num } = {}) {
  const sum = vals.reduce((a, b) => a + b, 0);
  return `<tr class="${cls}" title="${tip}"><td>${label}</td>${vals.map((v) => `<td class="auto">${fmtv(v)}</td>`).join("")}
    <td>${last ? fmtv(vals[vals.length - 1]) : fmtv(sum)}</td><td>${last ? "" : fmtv(sum / vals.length)}</td></tr>`;
}

function investAutoRow(p) {
  const s = p.series;
  if (!s.inv_automatico.some((v) => v)) return "";
  return seriesRow('Investimento automático <span class="badge">auto</span>', s.inv_automatico,
    { tip: "Calculado pelo % a investir e pelo saldo mínimo (Premissas → parâmetros mês a mês)" });
}

function investYieldRows(p) {
  const s = p.series;
  if (!s.inv_saldo_fim.some((v) => v) && !s.inv_rendimento.some((v) => v)) return "";
  const pctv = (v) => (v ? pct(v, 2) : "");
  return seriesRow("Rendimento do mês", s.inv_rendimento, { cls: "info", tip: "Saldo investido no início do mês × rentabilidade" }) +
    seriesRow("Rendimento acumulado", s.inv_rendimento_acumulado, { cls: "info", last: true }) +
    seriesRow("Rentabilidade (% a.m.)", s.inv_rentabilidade, { cls: "info", last: true, fmtv: pctv }) +
    seriesRow("Saldo investido no fim do mês", s.inv_saldo_fim, { cls: "info", last: true });
}

function renderFluxo() {
  const p = state.view;
  if (!p) return;
  const months = p.months;
  let h = `<thead><tr><th>R$</th>${months.map((m) => `<th>${mlabel(m)}</th>`).join("")}<th>Total</th><th>Média</th></tr></thead><tbody>`;
  for (const [g, label] of Object.entries(GROUPS)) {
    const showEmpty = $("#flow-empty").checked;
    const rows = p.rows.filter((r) => r.group === g &&
      (showEmpty || r.kind !== "manual" || state.newLines.has(r.category_id) || r.values.some((v) => v)));
    h += `<tr class="group"><td>${label} <button class="ghost sm newline" data-newline="${g}">+ Nova linha</button></td>${months.map(() => "<td></td>").join("")}<td></td><td></td></tr>`;
    if (g === "investimento") h += investAutoRow(p);
    for (const r of rows) {
      const auto = r.kind !== "manual";
      h += `<tr data-cat="${r.category_id}"><td>${esc(r.name)}${auto ? ' <span class="badge">auto</span>' : ""}
        <span class="rowtools"><button class="ghost sm" data-fill="${r.category_id}" title="Repetir um valor em vários meses">Repetir</button>${auto ? "" : `<button class="ghost sm" data-rename="${r.category_id}" title="Renomear a linha (vale para todos os cenários)">Renomear</button><button class="ghost sm danger" data-clear="${r.category_id}" title="Apagar os valores desta linha neste cenário">Remover</button>`}</span></td>`;
      r.values.forEach((v, i) => {
        const cls = ["cell", auto ? "auto" : "", r.overridden[i] ? "override" : ""].join(" ");
        h += `<td class="${cls}" data-i="${i}">${num(v)}</td>`;
      });
      h += `<td>${num(r.total)}</td><td>${num(r.average)}</td></tr>`;
    }
    // investimentos: o total inclui o investimento automático (que não é uma linha digitada)
    const tot = g === "investimento" ? p.series.investimentos
      : months.map((_, i) => rows.reduce((a, r) => a + r.values[i], 0));
    const sum = tot.reduce((a, b) => a + b, 0);
    h += `<tr class="total"><td>Total ${label.toLowerCase()}</td>${tot.map((v) => `<td>${num(v)}</td>`).join("")}<td>${num(sum)}</td><td>${num(sum / months.length)}</td></tr>`;
    if (g === "investimento") h += investYieldRows(p);
  }
  h += `<tr class="group"><td>Visão consolidada</td>${months.map(() => "<td></td>").join("")}<td></td><td></td></tr>`;
  for (const [key, label, cls] of SUMMARY_ROWS) {
    const vals = p.series[key];
    const cum = ["saldo_conta", "inv_saldo_fim", "saldo_total", "fgts_saldo", "saldo_disponivel"].includes(key);
    const sum = vals.reduce((a, b) => a + b, 0);
    h += `<tr class="${cls || ""}"><td>${label}</td>${vals.map((v) => `<td class="${v < -0.005 ? "neg" : ""}">${num(v)}</td>`).join("")}
      <td>${cum ? num(vals[vals.length - 1]) : num(sum)}</td><td>${cum ? "" : num(sum / vals.length)}</td></tr>`;
  }
  h += `<tr><td>% da renda com dívidas</td>${p.series.pct_dividas.map((v, i) =>
    `<td class="${p.series.alerta_dividas[i] ? "alert" : ""}">${pct(v)}</td>`).join("")}<td></td><td></td></tr>`;
  h += "</tbody>";
  $("#flow-table").innerHTML = h;
}

$("#flow-empty").addEventListener("change", renderFluxo);
$("#flow-table").addEventListener("click", async (ev) => {
  const fillBtn = ev.target.closest("[data-fill]");
  if (fillBtn) return fillRow(+fillBtn.dataset.fill);
  const t = ev.target.closest("[data-newline],[data-rename],[data-clear]");
  if (t?.dataset.newline) return newLine(t.dataset.newline);
  if (t?.dataset.rename) return renameLine(+t.dataset.rename);
  if (t?.dataset.clear) return clearLine(+t.dataset.clear);
  const td = ev.target.closest("td.cell");
  if (!td || td.querySelector("input")) return;
  const catId = +td.parentElement.dataset.cat, i = +td.dataset.i;
  const row = state.view.rows.find((r) => r.category_id === catId);
  const month = state.view.months[i];
  const editable = row.kind === "manual" ? row.values[i] : row.overridden[i] ? row.values[i] : "";
  td.innerHTML = `<input class="edit" value="${editable ? String(editable).replace(".", ",") : ""}">`;
  const input = td.querySelector("input");
  input.focus();
  input.select();
  let done = false;
  const commit = async (save) => {
    if (done) return;
    done = true;
    if (!save) return renderFluxo();
    const v = parseNum(input.value);
    if (v === undefined) { toast("Valor inválido"); return renderFluxo(); }
    await api("PUT", `/api/scenarios/${state.current}/entries`, [{ category_id: catId, month, amount: v }]);
    await refresh();
  };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") commit(true);
    if (e.key === "Escape") commit(false);
  });
  input.addEventListener("blur", () => commit(true));
});

async function newLine(group) {
  const name = (prompt(`Nome da nova linha em "${GROUPS[group]}":`) || "").trim();
  if (!name) return;
  // linha que já existe (oculta por estar vazia neste cenário ou desativada) é reaproveitada
  let cat = state.categories.find((c) => c.group === group && c.name.toLowerCase() === name.toLowerCase());
  if (cat && !cat.active) await api("PUT", `/api/categories/${cat.id}`, { ...cat, active: true });
  if (!cat) {
    const order = Math.max(0, ...state.categories.filter((c) => c.group === group).map((c) => c.sort_order)) + 10;
    cat = await api("POST", "/api/categories", { name, group, kind: "manual", sort_order: order });
  }
  state.newLines.add(cat.id);
  await loadBase();
  await refresh();
  toast(`Linha “${name}” criada: clique nas células para lançar valores`);
}

async function renameLine(catId) {
  const cat = state.categories.find((c) => c.id === catId);
  const name = (prompt("Novo nome (vale para todos os cenários):", cat.name) || "").trim();
  if (!name || name === cat.name) return;
  await api("PUT", `/api/categories/${catId}`, { ...cat, name });
  await loadBase();
  await refresh();
}

async function clearLine(catId) {
  const row = state.projection.rows.find((r) => r.category_id === catId);
  if (!confirm(`Apagar todos os valores de "${row.name}" neste cenário? A linha some do fluxo (continua disponível nos outros cenários).`)) return;
  const m = state.projection.months;
  await api("POST", `/api/scenarios/${state.current}/entries/fill`,
    { category_id: catId, from_month: m[0], to_month: m[m.length - 1], amount: null });
  state.newLines.delete(catId);
  await refresh();
}

async function fillRow(catId) {
  const row = state.view.rows.find((r) => r.category_id === catId);
  const months = state.view.months;
  const value = prompt(`Valor para "${row.name}" (vazio = limpar):`, "");
  if (value === null) return;
  const v = parseNum(value);
  if (v === undefined) return toast("Valor inválido");
  const from = prompt("A partir de (mm/aaaa):", mlabel(months[0]).replace(/^(\w+)\/(\d+)$/, (_, m, y) => `${String(MESES.indexOf(m) + 1).padStart(2, "0")}/20${y}`));
  if (!from) return;
  const to = prompt("Até (mm/aaaa):", `${months[months.length - 1].slice(5, 7)}/${months[months.length - 1].slice(0, 4)}`);
  if (!to) return;
  const iso = (s) => { const [m, y] = s.split("/"); return `${y}-${m.padStart(2, "0")}-01`; };
  await api("POST", `/api/scenarios/${state.current}/entries/fill`, { category_id: catId, from_month: iso(from), to_month: iso(to), amount: v });
  toast("Valores lançados");
  await refresh();
}

// ------------------------------------------------------------------ PREMISSAS
const SCN_FIELDS = [
  ["name", "Nome", "text"], ["description", "Descrição", "text"], ["start_month", "Mês inicial", "month"],
  ["months", "Horizonte (meses)", "int"], ["initial_balance", "Saldo inicial em conta (R$)", "money"],
  ["debt_limit_pct", "Limite de dívidas (% da renda)", "pct"], ["is_baseline", "Cenário base (orçado × realizado)", "bool"],
  ["fgts_initial", "Saldo inicial FGTS (R$)", "money"], ["fgts_rate_yearly", "Rendimento FGTS (% a.a.)", "pct"],
  ["fgts_aliquot", "Alíquota FGTS (% do bruto)", "pct"], ["gross_salary", "Salário bruto (R$)", "money"],
  ["bonus_salaries", "Bônus anual (nº de salários)", "float"], ["bonus_month", "Mês do bônus (1–12)", "int"],
  ["ir_amount", "Restituição IR (R$)", "money"], ["ir_month", "Mês da restituição (1–12)", "int"],
  ["vacation_month", "Mês do 1/3 de férias (1–12)", "int"],
  ["thirteenth_first_year", "13º – primeiro ano", "int"], ["thirteenth_last_year", "13º – último ano", "int"],
  ["thirteenth_month_1", "13º – mês da 1ª parcela", "int"], ["thirteenth_month_2", "13º – mês da 2ª parcela", "int"],
  ["apply_inflation", "Aplicar inflação nas despesas", "bool"], ["inflation_month", "Mês do reajuste (1–12)", "int"],
  ["invest_mode", "Regra do investimento automático", "mode"], ["invest_pct", "% a investir (padrão)", "pct"],
  ["min_balance", "Saldo mínimo em conta (R$)", "money"], ["invest_return_monthly", "Rentabilidade (% a.m.)", "pct"],
  ["initial_invested", "Saldo inicial investido (R$)", "money"],
];

// [exemplo no campo, explicação ao passar o mouse]
const FIELD_HELP = {
  months: ["26", "Quantos meses o cenário projeta a partir do mês inicial"],
  gross_salary: ["12000", "Usado só para o depósito de FGTS (alíquota × salário bruto); o fluxo usa o salário líquido dos reajustes"],
  bonus_salaries: ["1,5", "Bônus = este número × salário líquido do mês do bônus. Vazio ou 0 = sem bônus"],
  bonus_month: ["3", "Mês do ano em que o bônus cai (1 = janeiro … 12 = dezembro)"],
  ir_month: ["5", "Mês do ano em que a restituição cai (1–12). Vazio = sem restituição"],
  vacation_month: ["9", "Mês do ano em que entra o 1/3 de férias (salário líquido ÷ 3). Vazio = sem 1/3"],
  thirteenth_first_year: ["2026", "Primeiro ano em que você recebe 13º neste cenário. 13º = metade do salário líquido em cada mês de parcela. Vazio = sem 13º (ex.: MEI/PJ)"],
  thirteenth_last_year: ["2028", "Último ano em que você recebe 13º (normalmente o último ano do horizonte). Vazio = sem 13º"],
  thirteenth_month_1: ["11", "Mês da 1ª parcela do 13º (normalmente 11 = novembro)"],
  thirteenth_month_2: ["12", "Mês da 2ª parcela do 13º (normalmente 12 = dezembro)"],
  inflation_month: ["6", "Mês do ano em que a inflação das despesas é aplicada"],
  invest_pct: ["90", "Quanto do saldo vai para investimentos todo mês (pode variar mês a mês em Parâmetros mês a mês)"],
  min_balance: ["1000", "Valor que sempre fica em conta; abaixo disso o app resgata dos investimentos"],
  invest_return_monthly: ["1,1", "Rentabilidade mensal dos investimentos, em % ao mês"],
};

function scenarioFormHTML(sc) {
  return SCN_FIELDS.map(([k, label, t]) => {
    const v = sc[k];
    const [ph, tip] = FIELD_HELP[k] || ["", ""];
    if (t === "bool") return `<label class="field check"><input type="checkbox" name="${k}" ${v ? "checked" : ""}>${label}</label>`;
    if (t === "mode") return `<label class="field" title="% do saldo acima do mínimo: investe parte de tudo que está em conta acima do saldo mínimo. % da sobra do mês: investe parte só do que sobrou no mês (regra das abas antigas)"><span>${label} <span class="help">?</span></span><select name="${k}">
      <option value="excedente" ${v === "excedente" ? "selected" : ""}>% do saldo acima do mínimo</option>
      <option value="saldo_mes" ${v === "saldo_mes" ? "selected" : ""}>% da sobra do mês</option></select></label>`;
    let val = v ?? "";
    if (t === "month") val = toMonthInput(v);
    if (t === "pct" && v != null) val = +(v * 100).toFixed(4);
    const type = t === "month" ? "month" : t === "text" ? "text" : "number";
    const step = t === "int" ? "1" : "any";
    return `<label class="field" ${tip ? `title="${esc(tip)}"` : ""}><span>${label}${tip ? ' <span class="help">?</span>' : ""}</span>
      <input name="${k}" type="${type}" step="${step}" value="${esc(val)}" ${ph ? `placeholder="ex.: ${esc(ph)}"` : ""}></label>`;
  }).join("");
}

function readScenarioForm() {
  const f = $("#scenario-form"), out = {};
  for (const [k, , t] of SCN_FIELDS) {
    const el = f.elements[k];
    if (t === "bool") out[k] = el.checked;
    else if (t === "text" || t === "mode") out[k] = el.value || (k === "description" ? null : el.value);
    else if (t === "month") out[k] = fromMonthInput(el.value);
    else if (el.value === "") out[k] = ["bonus_month", "ir_month", "vacation_month", "thirteenth_first_year", "thirteenth_last_year"].includes(k) ? null : 0;
    else out[k] = t === "pct" ? Number(el.value) / 100 : t === "int" ? parseInt(el.value, 10) : Number(el.value);
  }
  return out;
}

async function renderPremissas() {
  const sc = currentScenario();
  if (!sc) {
    $("#scenario-form").innerHTML = '<p class="hint">Nenhum cenário. Clique em “Novo cenário”.</p>';
    return;
  }
  $("#scenario-form").innerHTML = scenarioFormHTML(sc);
  const [sal, infl, ms] = await Promise.all([
    api("GET", `/api/scenarios/${sc.id}/salary-changes`), api("GET", `/api/scenarios/${sc.id}/inflation`),
    api("GET", `/api/scenarios/${sc.id}/month-settings`),
  ]);
  renderSalary(sal);
  renderInflation(infl);
  const byMonth = Object.fromEntries(ms.map((m) => [m.month, m]));
  const months = state.projection.months;
  let h = `<thead><tr><th>Mês</th><th>% a investir</th><th>Saldo mínimo</th><th>Rentab. % a.m.</th><th>Salário bruto</th><th>Resgate manual</th>
    <th>Efetivo: % · mín · rentab.</th></tr></thead><tbody>`;
  months.forEach((m, i) => {
    const r = byMonth[m] || {};
    const s = state.projection.series;
    const inp = (k, scale = 1) => `<input data-k="${k}" type="number" step="any" style="width:110px" value="${r[k] != null ? +(r[k] * scale).toFixed(4) : ""}">`;
    h += `<tr data-month="${m}"><td>${mlabel(m)}</td><td>${inp("invest_pct", 100)}</td><td>${inp("min_balance")}</td>
      <td>${inp("invest_return", 100)}</td><td>${inp("gross_salary")}</td><td>${inp("manual_redemption")}</td>
      <td class="muted">${pct(s.pct_investir[i], 0)} · ${fmt(s.saldo_minimo[i])} · ${pct(s.inv_rentabilidade[i], 2)}</td></tr>`;
  });
  $("#month-table").innerHTML = h + "</tbody>";
}

function renderSalary(items) {
  $("#salary-table").innerHTML = `<thead><tr><th>A partir de</th><th>Novo salário (R$)</th><th>ou reajuste (%)</th><th></th></tr></thead><tbody>` +
    items.map((s) => `<tr><td><input type="month" data-k="start_month" value="${toMonthInput(s.start_month)}"></td>
      <td><input type="number" step="any" data-k="amount" value="${s.amount ?? ""}"></td>
      <td><input type="number" step="any" data-k="pct" value="${s.pct != null ? +(s.pct * 100).toFixed(4) : ""}"></td>
      <td><button class="ghost sm danger" data-del>Remover</button></td></tr>`).join("") + "</tbody>";
}

function renderInflation(items) {
  $("#inflation-table").innerHTML = `<thead><tr><th>Ano</th><th>Fixas (% a.a.)</th><th>Variáveis (% a.a.)</th><th></th></tr></thead><tbody>` +
    items.map((r) => `<tr><td><input type="number" data-k="year" value="${r.year}"></td>
      <td><input type="number" step="any" data-k="fixed_pct" value="${+(r.fixed_pct * 100).toFixed(4)}"></td>
      <td><input type="number" step="any" data-k="variable_pct" value="${+(r.variable_pct * 100).toFixed(4)}"></td>
      <td><button class="ghost sm danger" data-del>Remover</button></td></tr>`).join("") + "</tbody>";
}

["#salary-table", "#inflation-table"].forEach((sel) => $(sel).addEventListener("click", (e) => {
  if (e.target.matches("[data-del]")) e.target.closest("tr").remove();
}));
$("#btn-add-salary").onclick = () =>
  renderSalary([...readSalary(), { start_month: state.projection?.months[0], amount: null, pct: null }]);
$("#btn-add-infl").onclick = () => renderInflation([...readInflation(), { year: new Date().getFullYear() + 1, fixed_pct: 0.045, variable_pct: 0.045 }]);

const rowVal = (tr, k) => tr.querySelector(`[data-k="${k}"]`).value;
function readSalary() {
  return $$("#salary-table tbody tr").map((tr) => ({
    start_month: fromMonthInput(rowVal(tr, "start_month")),
    amount: rowVal(tr, "amount") === "" ? null : Number(rowVal(tr, "amount")),
    pct: rowVal(tr, "pct") === "" ? null : Number(rowVal(tr, "pct")) / 100,
  })).filter((r) => r.start_month);
}
function readInflation() {
  return $$("#inflation-table tbody tr").map((tr) => ({
    year: parseInt(rowVal(tr, "year"), 10),
    fixed_pct: Number(rowVal(tr, "fixed_pct") || 0) / 100,
    variable_pct: Number(rowVal(tr, "variable_pct") || 0) / 100,
  })).filter((r) => r.year);
}

$("#btn-save-salary").onclick = async () => {
  await api("PUT", `/api/scenarios/${state.current}/salary-changes`, readSalary());
  toast("Reajustes salvos");
  await refresh();
};
$("#btn-save-infl").onclick = async () => {
  await api("PUT", `/api/scenarios/${state.current}/inflation`, readInflation());
  toast("Inflação salva");
  await refresh();
};
$("#btn-save-months").onclick = async () => {
  const items = $$("#month-table tbody tr").map((tr) => {
    const g = (k, scale = 1) => { const v = rowVal(tr, k); return v === "" ? null : Number(v) / scale; };
    return { month: tr.dataset.month, invest_pct: g("invest_pct", 100), min_balance: g("min_balance"),
      invest_return: g("invest_return", 100), gross_salary: g("gross_salary"), manual_redemption: g("manual_redemption") };
  });
  await api("PUT", `/api/scenarios/${state.current}/month-settings`, items);
  toast("Parâmetros mensais salvos");
  await refresh();
};
$("#btn-save-scenario").onclick = async (e) => {
  e.preventDefault();
  await api("PUT", `/api/scenarios/${state.current}`, readScenarioForm());
  toast("Premissas salvas");
  await loadBase();
  await refresh();
};
$("#btn-new-scenario").onclick = async () => {
  const name = prompt("Nome do novo cenário:");
  if (!name) return;
  const d = new Date();
  const sc = await api("POST", "/api/scenarios", { name, start_month: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`, months: 24 });
  state.current = sc.id;
  await loadBase();
  await refresh();
};
$("#btn-dup-scenario").onclick = async () => {
  const name = prompt("Nome da cópia:", `${currentScenario().name} (cópia)`);
  if (!name) return;
  const sc = await api("POST", `/api/scenarios/${state.current}/duplicate?name=${encodeURIComponent(name)}`);
  state.current = sc.id;
  toast("Cenário duplicado");
  await loadBase();
  await refresh();
};
$("#btn-del-scenario").onclick = async () => {
  if (!confirm(`Excluir o cenário "${currentScenario().name}"? Isso apaga todos os valores planejados dele.`)) return;
  await api("DELETE", `/api/scenarios/${state.current}`);
  state.current = null;
  await loadBase();
  await refresh();
};

// ------------------------------------------------------------------ CONSIGNADOS
const PLANNER_ROWS = [
  ["receitas", "Receitas"], ["despesas_sem_quitacoes", "Despesas (sem quitações)"],
  ["parcelas_consignados", "  dos quais: parcelas de consignados"], ["quitacoes", "Quitações agendadas"],
  ["investimentos", "(−) Investido no mês"], ["resgates", "(+) Resgates"],
  ["saldo_conta", "Saldo em conta"], ["saldo_investido", "Saldo investido"],
  ["saldo_total", "Saldo total disponível (conta + investimentos)", "highlight"],
];
const NUM0 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });

function renderPlanner(pl) {
  const months = pl.months;
  const cb = '<td class="cb"></td><td class="cb"></td><td class="cb last"></td>';
  let h = `<thead><tr><th>R$</th><th class="cb" title="Parcela descontada por mês">Parcela</th>
    <th class="cb" title="Parcela liberada por mês para cada R$ 1.000 usados na quitação (no mês agendado ou, sem agendamento, no primeiro mês)">Libera por R$ 1 mil</th>
    <th class="cb last" title="Economia total (parcelas evitadas − valor da quitação) ÷ valor investido">Ganho total</th>
    ${months.map((m) => `<th>${mlabel(m)}</th>`).join("")}</tr></thead><tbody>`;
  for (const [k, label, cls] of PLANNER_ROWS) {
    const sub = label.startsWith("  ");
    h += `<tr class="${cls || ""}"><td class="${sub ? "muted" : ""}" style="${sub ? "padding-left:22px" : ""}">${label.trim()}</td>${cb}${pl.account[k].map((v) =>
      `<td class="${v < -0.5 ? "neg" : ""} ${sub ? "muted" : ""}">${Math.abs(v) < 0.5 ? "" : NUM0.format(v)}</td>`).join("")}</tr>`;
  }
  h += `<tr class="group"><td>Valor para quitar em cada mês · clique para agendar</td><td class="cb" colspan="3">custo-benefício</td>${months.map(() => "<td></td>").join("")}</tr>`;
  const refs = pl.contracts.map((c) => c.ref?.monthly_return || 0);
  const best = [...refs].sort((a, b) => b - a).slice(0, 3);
  for (const c of pl.contracts) {
    const r = c.ref;
    const refTip = r ? `Referência: quitar em ${mlabel(r.month)} por ${fmt2(r.value)}` : "";
    h += `<tr><td title="Taxa ${c.monthly_rate != null ? pct(c.monthly_rate, 2) : "–"} a.m. · último desconto ${mlabel(c.last_month)}">${esc(c.name)}</td>
      <td class="cb">${fmt(c.installment)}</td>
      <td class="cb ${r && best.includes(r.monthly_return) ? "best-cb" : ""}" title="${refTip}: cada R$ 1.000 liberam ${r ? fmt2(r.monthly_return * 1000) : "–"} de parcela por mês">${r ? `${fmt(r.monthly_return * 1000)}<span class="muted">/mês</span>` : "–"}</td>
      ${c.monthly_rate == null
        ? '<td class="cb last muted" title="Informe a taxa do contrato (em Contratos) para calcular o valor presente e a economia">sem taxa</td>'
        : `<td class="cb last" title="${refTip}: economia de ${r ? fmt2(r.total_gain * r.value) : "–"} sobre o valor investido">${r ? pct(r.total_gain) : "–"}</td>`}`;
    const paidAt = c.cells.findIndex((x) => x && x.scheduled);
    c.cells.forEach((cell, i) => {
      if (!cell) return (h += "<td></td>");
      if (paidAt >= 0 && i > paidAt) {
        // contrato já quitado: os meses seguintes ficam zerados, mas clicar move a quitação para cá
        return (h += `<td class="pcell after" data-contract="${c.id}" data-month="${months[i]}"
          title="Já quitado em ${mlabel(months[paidAt])} · clique para mudar a quitação para ${mlabel(months[i])} (${fmt2(cell.value)})"></td>`);
      }
      const cls = cell.scheduled ? "scheduled" : cell.fits ? "fits" : "nofit";
      const tip = `Quitar em ${mlabel(months[i])}: ${fmt2(cell.value)} · ${cell.remaining} parcelas restantes · juros evitados ${fmt2(cell.interest_saved)}` +
        ` · cada R$ 1.000 liberam ${fmt2((c.installment / cell.value) * 1000)}/mês · ganho total ${pct(cell.interest_saved / cell.value)}` +
        (cell.scheduled ? " · clique para desmarcar" : " · clique para agendar");
      h += `<td class="pcell ${cls}" data-contract="${c.id}" data-month="${months[i]}" data-scheduled="${cell.scheduled ? 1 : ""}" title="${tip}">${NUM0.format(cell.value)}</td>`;
    });
    h += "</tr>";
  }
  $("#payoff-planner").innerHTML = h + "</tbody>";

  const pal = SERIES();
  chart("chart-planner").setOption({
    ...baseOption(),
    grid: { left: 8, right: 16, top: 30, bottom: 4, containLabel: true },
    xAxis: { ...baseOption().xAxis, data: months.map(mlabel) },
    series: [
      { name: "Saldo total (conta + investimentos)", type: "line", data: pl.account.saldo_total, color: css("--ink-900"), symbol: "none", lineStyle: { width: 2 },
        markLine: { symbol: "none", silent: true, label: { show: false }, lineStyle: { color: css("--border-strong"), type: "dashed" }, data: [{ yAxis: 0 }] } },
      { name: "Quitações agendadas", type: "bar", data: pl.account.quitacoes, color: pal[0], barMaxWidth: 18, itemStyle: { borderRadius: [4, 4, 0, 0] } },
    ],
  }, true);
}

$("#payoff-planner").addEventListener("click", async (e) => {
  const td = e.target.closest("td.pcell");
  if (!td) return;
  const month = td.dataset.scheduled ? null : td.dataset.month;
  await api("PUT", `/api/scenarios/${state.current}/payoffs`, [{ contract_id: +td.dataset.contract, payoff_month: month }]);
  toast(month ? `Quitação agendada para ${mlabel(month)}` : "Quitação desmarcada");
  await refresh();
});

async function renderSuggestion() {
  const months = state.projection?.months || [];
  const sel = $("#sug-month");
  if (!months.includes(state.sug.month)) state.sug.month = months[0];
  sel.innerHTML = months.map((m) => `<option value="${m}" ${m === state.sug.month ? "selected" : ""}>${mlabel(m)}</option>`).join("");
  const params = new URLSearchParams({ month: state.sug.month, min_remaining: $("#sug-min").value || "0" });
  const budget = $("#sug-budget").value;
  if (budget !== "") params.set("budget", budget);
  const r = await api("GET", `/api/scenarios/${state.current}/payoff-suggestion?${params}`);
  state.sug.result = r;
  $("#sug-budget").placeholder = r.available != null ? `saldo do mês: ${NUM0.format(r.available)}` : "";
  const T = r.totals;
  $("#sug-tiles").innerHTML = [
    ["Parcela liberada por mês", fmt(T.parcela_liberada), r.selected.length ? `a partir de ${mlabel(r.month)}` : "nenhuma quitação cabe no valor", true],
    ["Valor das quitações", fmt(T.valor_quitacao), `de ${fmt(r.budget)} disponíveis`],
    ["Sobra do valor", fmt(T.sobra), "fica em conta"],
    ["Libera por R$ 1 mil", T.valor_quitacao ? `${fmt(T.por_mil)}/mês` : "–", "parcela liberada ÷ valor pago"],
    ["Juros evitados", fmt(T.juros_evitados), "até o fim dos contratos"],
  ].map(([l, v, s, inv]) => `<div class="tile${inv ? " inverse" : ""}"><div class="label">${l}</div><div class="value">${v}</div><div class="sub">${s}</div></div>`).join("");
  const rows = [...r.candidates, ...r.skipped];
  $("#sug-table").innerHTML = `<thead><tr><th>Contrato</th><th>Parcela liberada</th><th>Valor para quitar</th><th>Libera por R$ 1 mil</th>
    <th>Parcelas restantes</th><th>Juros evitados</th><th>Agendado hoje</th><th>Sugestão</th></tr></thead><tbody>` +
    rows.map((c) => {
      const skipped = r.skipped.includes(c);
      return `<tr class="${c.selected ? "highlight" : ""} ${skipped ? "muted" : ""}"><td>${esc(c.name)}</td><td>${fmt2(c.installment)}</td><td>${fmt2(c.value)}</td>
        <td>${fmt(c.per_thousand)}/mês</td><td>${c.remaining}</td><td>${c.monthly_rate == null ? '<span class="muted">sem taxa</span>' : fmt2(c.interest_saved)}</td>
        <td>${c.scheduled_month ? mlabel(c.scheduled_month) : "–"}</td>
        <td>${c.selected ? '<span class="badge inverse">quitar</span>' : skipped ? `<span class="muted">termina em ${c.remaining} ${c.remaining === 1 ? "mês" : "meses"}</span>` : ""}</td></tr>`;
    }).join("") + "</tbody>";
  const btn = $("#btn-sug-apply");
  btn.hidden = !r.selected.length;
  btn.textContent = `Agendar ${r.selected.length === 1 ? "esta quitação" : `estas ${r.selected.length} quitações`} em ${mlabel(r.month)}`;
  const moved = r.selected.filter((c) => c.scheduled_month && c.scheduled_month !== r.month);
  $("#sug-note").textContent = moved.length ? `Muda o agendamento de: ${moved.map((c) => `${c.name} (hoje em ${mlabel(c.scheduled_month)})`).join(", ")}.` : "";
}

$("#sug-month").addEventListener("change", (e) => { state.sug.month = e.target.value; $("#sug-budget").value = ""; renderSuggestion(); });
$("#sug-budget").addEventListener("change", renderSuggestion);
$("#sug-min").addEventListener("change", renderSuggestion);
$("#btn-sug-apply").onclick = async () => {
  const r = state.sug.result;
  await api("PUT", `/api/scenarios/${state.current}/payoffs`, r.selected.map((c) => ({ contract_id: c.id, payoff_month: r.month })));
  toast(`${r.selected.length} quitação(ões) agendada(s) em ${mlabel(r.month)}: libera ${fmt(r.totals.parcela_liberada)}/mês`);
  $("#sug-budget").value = "";
  await refresh();
};

async function renderConsignados() {
  if (!state.current) return;
  const [t, cmp, pl, contracts] = await Promise.all([
    api("GET", `/api/scenarios/${state.current}/loans`), api("GET", "/api/reports/loans-compare"),
    api("GET", `/api/scenarios/${state.current}/payoff-planner`),
    api("GET", `/api/scenarios/${state.current}/contracts`), renderSuggestion(),
  ]);
  state.loans = contracts;
  // planejador ordenado pelo que mais libera parcela por real investido
  pl.contracts.sort((a, b) => (b.ref?.monthly_return || 0) - (a.ref?.monthly_return || 0));
  renderPlanner(pl);
  const T = t.totals || {};
  $("#loan-tiles").innerHTML = [
    ["Desembolso com quitações", fmt(T.desembolso_quitacoes), "saída de caixa nos meses de quitação"],
    ["Parcelas evitadas", fmt(T.parcelas_evitadas), "soma das parcelas que deixam de ser descontadas"],
    ["Economia líquida", fmt(T.economia_liquida), "parcelas evitadas − desembolso", true],
    ["Parcela mensal liberada", fmt(T.parcela_mensal_liberada), "folga no orçamento após quitar"],
    ["Payback", T.mes_payback ? mlabel(T.mes_payback) : "–", "mês em que a economia cobre o desembolso"],
  ].map(([l, v, s, inv]) => `<div class="tile${inv ? " inverse" : ""}"><div class="label">${l}</div><div class="value">${v}</div><div class="sub">${s}</div></div>`).join("");

  let h = `<thead><tr><th>Contrato</th><th>Parcela</th><th>Taxa a.m.</th><th>1º desconto</th><th>Último</th><th>Mês de quitação</th>
    <th>Parcelas quitadas</th><th>Valor da quitação</th><th>Parcelas evitadas</th><th>Juros evitados</th><th>Quitação ÷ parcela</th><th>Retorno mensal</th></tr></thead><tbody>`;
  for (const c of t.contracts) {
    h += `<tr data-id="${c.id}"><td>${esc(c.name)}</td><td>${fmt2(c.installment)}</td><td>${c.monthly_rate != null ? pct(c.monthly_rate, 2) : "–"}</td>
      <td>${mlabel(c.first_month)}</td><td>${mlabel(c.last_month)}</td>
      <td><input type="month" data-payoff value="${toMonthInput(c.payoff_month)}"></td>
      <td>${c.payoff_month ? c.remaining : "–"}</td><td>${c.payoff_month ? fmt2(c.payoff_value) : "–"}</td>
      <td>${c.payoff_month ? fmt2(c.installments_avoided) : "–"}</td>
      <td class="${c.interest_saved > 0 ? "pos" : ""}">${c.payoff_month ? fmt2(c.interest_saved) : "–"}</td>
      <td>${c.months_equivalent ? c.months_equivalent.toFixed(1).replace(".", ",") + " meses" : "–"}</td>
      <td>${c.monthly_return ? pct(c.monthly_return) : "–"}</td></tr>`;
  }
  const sum = (k) => t.contracts.filter((c) => c.payoff_month).reduce((a, c) => a + c[k], 0);
  h += `<tr class="total"><td>Total</td><td>${fmt2(t.contracts.reduce((a, c) => a + c.installment, 0))}</td><td></td><td></td><td></td><td></td><td></td>
    <td>${fmt2(sum("payoff_value"))}</td><td>${fmt2(sum("installments_avoided"))}</td><td>${fmt2(sum("interest_saved"))}</td><td></td><td></td></tr></tbody>`;
  $("#loan-table").innerHTML = h;

  const pal = SERIES();
  const months = t.months.map(mlabel);
  chart("chart-loan-cash").setOption({
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: months },
    series: [
      { name: "Parcelas (com quitação)", type: "bar", stack: "c", data: t.installments_with_payoff, color: css("--ink-900"), barMaxWidth: 18 },
      { name: "Desembolso de quitação", type: "bar", stack: "c", data: t.payoff_disbursement, color: pal[0], barMaxWidth: 18, itemStyle: { borderRadius: [4, 4, 0, 0] } },
      { name: "Parcelas sem quitar", type: "line", data: t.installments_without_payoff, color: pal[1], symbol: "none", lineStyle: { width: 2, type: "dashed" } },
    ],
  }, true);
  chart("chart-loan-cum").setOption({
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: months },
    series: [{
      name: "Economia acumulada", type: "line", data: t.cumulative_net_saving, color: pal[0], symbol: "none",
      lineStyle: { width: 2 }, areaStyle: { opacity: 0.12 },
      markLine: {
        symbol: "none", silent: true, label: { color: css("--text-secondary"), formatter: (p) => p.name },
        lineStyle: { color: css("--border-strong"), type: "dashed" },
        data: [{ yAxis: 0, name: "" }, ...(T.mes_payback ? [{ xAxis: mlabel(T.mes_payback), name: `payback ${mlabel(T.mes_payback)}` }] : [])],
      },
    }],
  }, true);

  // comparação entre cenários
  const scs = cmp.scenarios;
  let ct = `<table><thead><tr><th>Cenário</th><th>Contratos quitados</th><th>Desembolso</th><th>Parcelas evitadas</th><th>Economia líquida</th>
    <th>Parcela liberada/mês</th><th>Payback</th></tr></thead><tbody>`;
  const bestEco = Math.max(...scs.map((s) => s.totals.economia_liquida || 0));
  for (const s of scs) {
    const n = s.contracts.filter((c) => c.payoff_month).length;
    ct += `<tr><td><span class="dot" style="background:${scenarioColor(s.id)}"></span> ${esc(s.name)}</td><td>${n}</td>
      <td>${fmt(s.totals.desembolso_quitacoes)}</td><td>${fmt(s.totals.parcelas_evitadas)}</td>
      <td class="${s.totals.economia_liquida === bestEco && bestEco > 0 ? "best" : ""}">${fmt(s.totals.economia_liquida)}</td>
      <td>${fmt(s.totals.parcela_mensal_liberada)}</td><td>${s.totals.mes_payback ? mlabel(s.totals.mes_payback) : "–"}</td></tr>`;
  }
  // detalhe por contrato × cenário
  ct += `</tbody></table><p class="eyebrow" style="margin-top:20px">Mês e valor de quitação por contrato</p><table><thead><tr><th>Contrato</th>${scs.map((s) => `<th>${esc(s.name)}</th>`).join("")}</tr></thead><tbody>`;
  // cada cenário tem os próprios contratos: casa pelo nome
  const names = [...new Set(scs.flatMap((s) => s.contracts.map((c) => c.name)))];
  names.forEach((name) => {
    ct += `<tr><td>${esc(name)}</td>${scs.map((s) => {
      const c = s.contracts.find((x) => x.name === name);
      if (!c) return '<td><span class="muted">sem contrato</span></td>';
      return `<td>${c.payoff_month ? `${mlabel(c.payoff_month)} · ${fmt(c.payoff_value)} <span class="muted">(economia ${fmt(c.interest_saved)})</span>` : '<span class="muted">não quita</span>'}</td>`;
    }).join("")}</tr>`;
  });
  $("#loan-compare-table").innerHTML = ct + "</tbody></table>";

  const allMonths = [...new Set(scs.flatMap((s) => s.months))].sort();
  chart("chart-loan-compare").setOption({
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: allMonths.map(mlabel) },
    series: scs.map((s) => {
      const idx = Object.fromEntries(s.months.map((m, i) => [m, i]));
      return { name: s.name, type: "line", symbol: "none", lineStyle: { width: 2 }, color: scenarioColor(s.id),
        data: allMonths.map((m) => (m in idx ? s.cumulative_net_saving[idx[m]] : null)) };
    }),
  }, true);
  chart("chart-loan-bars").setOption({
    ...baseOption(),
    tooltip: { ...baseOption().tooltip, axisPointer: { type: "shadow" } },
    xAxis: { ...baseOption().xAxis, data: scs.map((s) => s.name) },
    series: [
      { name: "Desembolso", type: "bar", data: scs.map((s) => s.totals.desembolso_quitacoes), color: css("--ink-900"), itemStyle: { borderRadius: [4, 4, 0, 0] } },
      { name: "Parcelas evitadas", type: "bar", data: scs.map((s) => s.totals.parcelas_evitadas), color: pal[1], itemStyle: { borderRadius: [4, 4, 0, 0] } },
      { name: "Economia líquida", type: "bar", data: scs.map((s) => s.totals.economia_liquida), color: pal[0], itemStyle: { borderRadius: [4, 4, 0, 0] } },
    ],
  }, true);

  renderContracts();
}

$("#loan-table").addEventListener("change", async (e) => {
  if (!e.target.matches("[data-payoff]")) return;
  const id = +e.target.closest("tr").dataset.id;
  await api("PUT", `/api/scenarios/${state.current}/payoffs`, [{ contract_id: id, payoff_month: fromMonthInput(e.target.value) }]);
  toast("Quitação atualizada");
  await refresh();
});

function renderContracts() {
  $("#contracts-table").innerHTML = `<thead><tr><th>Contrato</th><th>Credor</th><th>Taxa % a.m.</th><th>Parcela</th><th>1º desconto</th><th>Último desconto</th><th></th></tr></thead><tbody>` +
    state.loans.map((l) => `<tr data-id="${l.id}"><td><input data-k="name" value="${esc(l.name)}"></td><td><input data-k="creditor" value="${esc(l.creditor || "")}"></td>
      <td><input data-k="monthly_rate" type="number" step="any" style="width:90px" value="${l.monthly_rate != null ? +(l.monthly_rate * 100).toFixed(4) : ""}"></td>
      <td><input data-k="installment" type="number" step="0.01" style="width:110px" value="${l.installment}"></td>
      <td><input data-k="first_month" type="month" value="${toMonthInput(l.first_month)}"></td>
      <td><input data-k="last_month" type="month" value="${toMonthInput(l.last_month)}"></td>
      <td><button class="sm" data-save>Salvar</button> <button class="ghost sm danger" data-del>Excluir</button></td></tr>`).join("") + "</tbody>";
}

$("#contracts-table").addEventListener("click", async (e) => {
  const tr = e.target.closest("tr");
  if (!tr) return;
  const id = tr.dataset.id;
  if (e.target.matches("[data-del]")) {
    if (!confirm("Excluir este contrato só deste cenário?")) return;
    await api("DELETE", `/api/scenarios/${state.current}/contracts/${id}`);
  } else if (e.target.matches("[data-save]")) {
    const rate = rowVal(tr, "monthly_rate");
    const body = { name: rowVal(tr, "name"), creditor: rowVal(tr, "creditor") || null,
      monthly_rate: rate === "" ? null : Number(rate) / 100, installment: Number(rowVal(tr, "installment")),
      first_month: fromMonthInput(rowVal(tr, "first_month")), last_month: fromMonthInput(rowVal(tr, "last_month")),
      payoff_month: state.loans.find((l) => String(l.id) === id)?.payoff_month || null };
    if (!body.name || !body.first_month || !body.last_month) return toast("Informe nome, 1º e último desconto");
    const base = `/api/scenarios/${state.current}/contracts`;
    await api(id ? "PUT" : "POST", id ? `${base}/${id}` : base, body);
    toast("Contrato salvo neste cenário");
  } else return;
  await refresh();
});
$("#btn-add-contract").onclick = () => {
  state.loans.push({ id: "", name: "", creditor: "", monthly_rate: null, installment: 0, first_month: null, last_month: null });
  renderContracts();
};

// ------------------------------------------------------------------ EM ATRASO
const ARREAR_STATUS = { aberto: "Em aberto", negociado: "Negociado", pago: "Pago" };

async function renderAtrasos() {
  if (!state.current) return;
  const data = await api("GET", `/api/scenarios/${state.current}/arrears`);
  state.arrears = data.items;
  const T = data.totals;
  $("#arrear-tiles").innerHTML = [
    ["Em aberto", String(T.em_aberto), `mais antigo: ${T.mais_antigo_meses} ${T.mais_antigo_meses === 1 ? "mês" : "meses"}`],
    ["Valor original", fmt(T.valor_original), "soma dos valores vencidos"],
    ["Valor atualizado hoje", fmt(T.valor_atualizado), `encargos: ${fmt(T.valor_atualizado - T.valor_original)}`, true],
    ["Planejado no cenário", fmt(T.planejado), "entra no fluxo como Pagamento de atrasos"],
    ["Sem plano de pagamento", fmt(T.sem_plano), T.sem_plano > 0 ? "defina início e parcelas abaixo" : "tudo planejado"],
  ].map(([l, v, s, inv]) => `<div class="tile${inv ? " inverse" : ""}"><div class="label">${l}</div><div class="value">${v}</div><div class="sub">${s}</div></div>`).join("");
  renderArrearTable();

  const open = data.items.filter((a) => a.status !== "pago").sort((a, b) => b.updated_value - a.updated_value);
  const label = (a) => a.creditor && a.creditor !== a.description ? `${a.description} · ${a.creditor}` : a.description;
  const pal = SERIES();
  chart("chart-arrear-items").setOption({
    ...baseOption(),
    grid: { left: 8, right: 24, top: 36, bottom: 8, containLabel: true },
    tooltip: { ...baseOption().tooltip, axisPointer: { type: "shadow" } },
    xAxis: { type: "value", splitLine: { lineStyle: { color: css("--chart-grid") } }, axisLabel: { color: css("--text-muted"), formatter: short } },
    yAxis: { type: "category", inverse: true, data: open.map(label), axisTick: { show: false },
      axisLine: { lineStyle: { color: css("--border-default") } }, axisLabel: { color: css("--text-secondary"), width: 170, overflow: "truncate" } },
    series: [
      { name: "Original / acordo", type: "bar", stack: "a", color: css("--ink-900"), barMaxWidth: 18,
        data: open.map((a) => (a.negotiated_amount != null ? a.updated_value : a.amount)) },
      { name: "Multa e juros", type: "bar", stack: "a", color: pal[0], barMaxWidth: 18, itemStyle: { borderRadius: [0, 4, 4, 0] },
        data: open.map((a) => a.charges) },
    ],
  }, true);

  const p = state.projection;
  const row = p?.rows.find((r) => r.kind === "atrasos");
  chart("chart-arrear-plan").setOption({
    ...baseOption(),
    xAxis: { ...baseOption().xAxis, data: (p?.months || []).map(mlabel) },
    series: [{ name: "Pagamento de atrasos", type: "bar", color: pal[0], itemStyle: { borderRadius: [4, 4, 0, 0] }, data: row ? row.values : [] }],
  }, true);
}

function renderArrearTable() {
  const cats = '<option value="">–</option>' + state.categories.filter((c) => c.kind === "manual").map((c) =>
    `<option value="${c.id}">${esc(c.name)}</option>`).join("");
  const h = `<thead><tr><th>Descrição</th><th>Credor</th><th>Responsável</th><th>Categoria</th><th>Vencimento</th><th>Valor original</th>
    <th>Multa %</th><th>Juros % a.m.</th><th>Acordo (R$)</th><th>Situação</th><th>Atraso</th><th>Valor atualizado</th>
    <th>Pagar a partir de</th><th>Parcelas</th><th>Parcela</th><th></th></tr></thead><tbody>` +
    state.arrears.map((a) => `<tr data-id="${a.id}" class="${a.status === "pago" ? "muted" : ""}">
      <td><input data-k="description" value="${esc(a.description)}" style="width:190px"></td>
      <td><input data-k="creditor" value="${esc(a.creditor || "")}" style="width:120px"></td>
      <td><input data-k="owner" value="${esc(a.owner || "")}" style="width:100px"></td>
      <td><select data-k="category_id" style="width:140px">${cats.replace(`value="${a.category_id}"`, `value="${a.category_id}" selected`)}</select></td>
      <td><input data-k="due_date" type="date" value="${a.due_date || ""}"></td>
      <td><input data-k="amount" type="number" step="0.01" style="width:100px" value="${a.amount ?? ""}"></td>
      <td><input data-k="fine_pct" type="number" step="any" style="width:64px" value="${a.fine_pct ? +(a.fine_pct * 100).toFixed(4) : ""}"></td>
      <td><input data-k="interest_monthly" type="number" step="any" style="width:64px" value="${a.interest_monthly ? +(a.interest_monthly * 100).toFixed(4) : ""}"></td>
      <td><input data-k="negotiated_amount" type="number" step="0.01" style="width:100px" value="${a.negotiated_amount ?? ""}"></td>
      <td><select data-k="status">${Object.entries(ARREAR_STATUS).map(([k, l]) => `<option value="${k}" ${k === a.status ? "selected" : ""}>${l}</option>`).join("")}</select></td>
      <td>${a.id ? (a.due_date ? `${a.months_late} ${a.months_late === 1 ? "mês" : "meses"}` : "–") : ""}</td>
      <td>${a.id ? fmt2(a.updated_value) : ""}</td>
      <td><input data-k="plan_start" type="month" value="${toMonthInput(a.plan_start)}" ${a.status === "pago" ? "disabled" : ""}></td>
      <td><input data-k="plan_installments" type="number" min="1" step="1" style="width:60px" value="${a.plan_installments ?? 1}" ${a.status === "pago" ? "disabled" : ""}></td>
      <td>${a.plan_installment ? fmt2(a.plan_installment) : "–"}</td>
      <td><button class="sm" data-save>Salvar</button> <button class="ghost sm danger" data-del>Excluir</button></td></tr>`).join("") +
    `<tr class="total"><td colspan="5">Total em aberto</td><td>${fmt2(state.arrears.filter((a) => a.status !== "pago").reduce((s, a) => s + (a.amount || 0), 0))}</td>
      <td colspan="5"></td><td>${fmt2(state.arrears.filter((a) => a.status !== "pago").reduce((s, a) => s + (a.updated_value || 0), 0))}</td><td colspan="4"></td></tr></tbody>`;
  $("#arrear-table").innerHTML = h;
}

$("#arrear-table").addEventListener("click", async (e) => {
  const tr = e.target.closest("tr[data-id]");
  if (!tr) return;
  const id = tr.dataset.id;
  if (e.target.matches("[data-del]")) {
    if (!id) {
      state.arrears = state.arrears.filter((a) => a.id !== "");
      return renderArrearTable();
    }
    if (!confirm("Excluir este atraso só deste cenário?")) return;
    await api("DELETE", `/api/scenarios/${state.current}/arrears/${id}`);
  } else if (e.target.matches("[data-save]")) {
    const v = (k) => rowVal(tr, k);
    const numOrNull = (k, scale = 1) => (v(k) === "" ? null : Number(v(k)) / scale);
    if (!v("description") || v("amount") === "") return toast("Informe descrição e valor original");
    const body = {
      description: v("description"), creditor: v("creditor") || null, owner: v("owner") || null,
      category_id: v("category_id") ? +v("category_id") : null, due_date: v("due_date") || null,
      amount: Number(v("amount")), fine_pct: numOrNull("fine_pct", 100) || 0, interest_monthly: numOrNull("interest_monthly", 100) || 0,
      negotiated_amount: numOrNull("negotiated_amount"), status: v("status"),
      plan_start: v("status") === "pago" ? null : fromMonthInput(v("plan_start")),
      plan_installments: Math.max(1, parseInt(v("plan_installments") || "1", 10)),
    };
    const base = `/api/scenarios/${state.current}/arrears`;
    await api(id ? "PUT" : "POST", id ? `${base}/${id}` : base, body);
    toast("Atraso salvo neste cenário");
  } else return;
  await refresh();
});

$("#btn-add-arrear").onclick = () => {
  state.arrears.unshift({ id: "", description: "", creditor: "", owner: "", category_id: null, due_date: null, amount: null,
    fine_pct: 0.02, interest_monthly: 0.01, negotiated_amount: null, status: "aberto", plan_start: null, plan_installments: 1 });
  renderArrearTable();
  $("#arrear-table tbody input").focus();
};

// ------------------------------------------------------------------ COMPARAR
async function renderComparar() {
  if (state.compareIds === null) state.compareIds = state.scenarios.map((s) => s.id);
  $("#compare-picks").innerHTML = '<span class="muted">Cenários:</span>' + state.scenarios.map((s) =>
    `<label class="pick"><input type="checkbox" value="${s.id}" ${state.compareIds.includes(s.id) ? "checked" : ""}>
      <span class="dot" style="background:${scenarioColor(s.id)}"></span>${esc(s.name)}</label>`).join("");
  if (!state.compareIds.length) return;
  const data = await api("GET", `/api/reports/compare?ids=${state.compareIds.join(",")}`);
  const scs = data.scenarios;

  // maior/menor é melhor
  const rows = [
    ["patrimonio_final", "Conta + investimentos + FGTS", "max"], ["saldo_final_conta", "Saldo final em conta", "max"],
    ["saldo_final_investido", "Saldo final investido", "max"], ["saldo_final_fgts", "Saldo final FGTS", "max"],
    ["menor_saldo_conta", "Menor saldo em conta", "max"], ["mes_menor_saldo", "Mês do menor saldo", null, "m"],
    ["meses_saldo_negativo", "Meses com saldo negativo", "min", "n"], ["receita_media", "Receita média", "max"],
    ["despesa_media", "Despesa média", "min"], ["custo_moradia_medio", "Custo médio com moradia", "min"],
    ["saldo_livre_medio", "Saldo livre médio", "max"], ["taxa_poupanca", "Taxa de poupança", "max", "p"],
    ["total_dividas", "Total de dívidas pagas", "min"], ["total_quitacoes", "Total em quitações", null],
    ["pct_renda_dividas", "% da renda com dívidas", "min", "p"], ["ultimo_mes_com_parcela", "Último mês com parcela", null, "m"],
    ["total_investido", "Total investido", "max"],
  ];
  let h = `<table><thead><tr><th>Indicador</th>${scs.map((s) => `<th><span class="dot" style="background:${scenarioColor(s.id)}"></span> ${esc(s.name)}</th>`).join("")}</tr></thead><tbody>`;
  for (const [k, label, dir, t] of rows) {
    const vals = scs.map((s) => s.kpis[k]);
    const best = dir && scs.length > 1 ? (dir === "max" ? Math.max(...vals) : Math.min(...vals)) : null;
    h += `<tr><td>${label}</td>${vals.map((v) => `<td class="${best !== null && v === best ? "best" : ""} ${typeof v === "number" && v < 0 && !t ? "neg" : ""}">${kfmt(v, t)}</td>`).join("")}</tr>`;
  }
  $("#compare-table").innerHTML = h + '</tbody></table><p class="hint" style="margin-top:8px">● marca o melhor valor do indicador entre os cenários.</p>';

  const months = data.months.map(mlabel);
  for (const [id, key] of [["chart-cmp-total", "saldo_total"], ["chart-cmp-conta", "saldo_conta"]]) {
    chart(id).setOption({
      ...baseOption(),
      xAxis: { ...baseOption().xAxis, data: months },
      series: scs.map((s) => ({ name: s.name, type: "line", symbol: "none", lineStyle: { width: 2 }, color: scenarioColor(s.id), data: s.aligned[key] })),
    }, true);
  }
  const groupCols = [
    ["Despesas fixas", (s) => s.groups.despesa_fixa], ["Empréstimos e dívidas", (s) => s.groups.divida],
    ["Despesas variáveis", (s) => s.groups.despesa_variavel], ["Aportes manuais", (s) => s.groups.investimento],
    ["Investimento automático", (s) => s.auto_investment],
  ].filter((g) => scs.some((s) => g[1](s) > 0));
  chart("chart-cmp-groups").setOption({
    ...baseOption(),
    tooltip: { ...baseOption().tooltip, axisPointer: { type: "shadow" } },
    xAxis: { ...baseOption().xAxis, data: groupCols.map((g) => g[0]) },
    series: scs.map((s) => ({
      name: s.name, type: "bar", color: scenarioColor(s.id), itemStyle: { borderRadius: [4, 4, 0, 0] },
      data: groupCols.map((g) => g[1](s)),
    })),
  }, true);

  const box = $("#compare-sankeys");
  box.innerHTML = scs.map((s) => `<div class="card"><p class="eyebrow"><span class="dot" style="background:${scenarioColor(s.id)}"></span> ${esc(s.name)}</p><div id="sk-${s.id}" class="chart mid"></div></div>`).join("");
  await Promise.all(scs.map(async (s) => renderSankey(`sk-${s.id}`, await api("GET", `/api/scenarios/${s.id}/sankey`), true)));
}

$("#compare-picks").addEventListener("change", () => {
  state.compareIds = $$("#compare-picks input:checked").map((i) => +i.value);
  renderComparar();
});

// ------------------------------------------------------------------ LANÇAMENTOS
function fillSelects() {
  const f = $("#tx-form").elements, keep = [f.category_id.value, f.account_id.value];
  const catOpts = '<option value="">(sem categoria)</option>' + Object.entries(GROUPS).map(([g, label]) =>
    `<optgroup label="${label}">${state.categories.filter((c) => c.group === g).map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("")}</optgroup>`).join("");
  $("#tx-form").elements.category_id.innerHTML = catOpts;
  $("#tx-form").elements.account_id.innerHTML = '<option value="">(sem conta)</option>' + state.accounts.map((a) => `<option value="${a.id}">${esc(a.name)}</option>`).join("");
  [f.category_id.value, f.account_id.value] = keep;
}

async function renderLancamentos() {
  fillSelects();
  const m = $("#tx-month");
  if (!m.value) m.value = new Date().toISOString().slice(0, 7);
  const txs = await api("GET", `/api/transactions?month=${m.value}-01`);
  const cat = Object.fromEntries(state.categories.map((c) => [c.id, c.name]));
  const acc = Object.fromEntries(state.accounts.map((a) => [a.id, a.name]));
  const total = txs.reduce((a, t) => a + t.amount, 0);
  $("#tx-table").innerHTML = `<thead><tr><th>Data</th><th>Descrição</th><th>Categoria</th><th>Conta</th><th>Valor</th><th></th></tr></thead><tbody>` +
    txs.map((t) => `<tr data-id="${t.id}"><td>${t.date.split("-").reverse().join("/")}</td><td>${esc(t.description)}</td>
      <td>${esc(cat[t.category_id] || "–")}</td><td>${esc(acc[t.account_id] || "–")}</td>
      <td class="${t.amount < 0 ? "neg" : "pos"}">${fmt2(t.amount)}</td><td><button class="ghost sm danger" data-del>Excluir</button></td></tr>`).join("") +
    `<tr class="total"><td colspan="4">Saldo do mês (${txs.length} lançamentos)</td><td>${fmt2(total)}</td><td></td></tr></tbody>`;
}

$("#tx-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target.elements;
  await api("POST", "/api/transactions", {
    date: f.date.value, description: f.description.value, amount: Number(f.amount.value),
    category_id: f.category_id.value ? +f.category_id.value : null, account_id: f.account_id.value ? +f.account_id.value : null,
  });
  f.description.value = "";
  f.amount.value = "";
  toast("Lançamento adicionado");
  renderLancamentos();
});
$("#tx-month").addEventListener("change", renderLancamentos);
$("#tx-table").addEventListener("click", async (e) => {
  if (!e.target.matches("[data-del]")) return;
  await api("DELETE", `/api/transactions/${e.target.closest("tr").dataset.id}`);
  renderLancamentos();
});
$("#tx-csv").addEventListener("change", async (e) => {
  const fd = new FormData();
  fd.append("file", e.target.files[0]);
  const r = await api("POST", "/api/transactions/import-csv", fd);
  toast(`${r.created} lançamentos importados${r.errors.length ? `, ${r.errors.length} com erro` : ""}`);
  if (r.errors.length) console.warn(r.errors);
  e.target.value = "";
  renderLancamentos();
});

// ------------------------------------------------------------------ ORÇADO x REALIZADO
async function renderOrcado() {
  const m = $("#bva-month");
  if (!m.value) m.value = (state.projection?.months[0] || new Date().toISOString()).slice(0, 7);
  const base = state.scenarios.find((s) => s.is_baseline) || currentScenario();
  if (!base) return;
  const r = await api("GET", `/api/reports/budget-vs-actual?month=${m.value}-01&scenario_id=${base.id}`);
  $("#bva-scenario").textContent = `planejado do cenário ${r.scenario.name}${r.in_horizon ? "" : " (mês fora do horizonte)"}`;
  $("#bva-summary").innerHTML = Object.entries(r.summary).map(([g, v]) => {
    const used = v.planned ? v.actual / v.planned : null;
    return `<div class="tile"><div class="label">${GROUPS[g]}</div><div class="value">${fmt(v.actual)}</div>
      <div class="sub">de ${fmt(v.planned)} planejado${used != null ? ` · ${pct(used, 0)}` : ""}</div></div>`;
  }).join("");
  $("#bva-table").innerHTML = `<thead><tr><th>Categoria</th><th>Grupo</th><th>Planejado</th><th>Realizado</th><th>Diferença</th></tr></thead><tbody>` +
    r.rows.map((x) => {
      const goodWhenPositive = x.group === "receita" || x.group === "investimento";
      const cls = Math.abs(x.diff) < 0.01 ? "" : (x.diff > 0) === goodWhenPositive ? "pos" : "neg";
      return `<tr><td>${esc(x.name)}</td><td class="muted">${GROUPS[x.group]}</td><td>${fmt2(x.planned)}</td><td>${fmt2(x.actual)}</td><td class="${cls}">${fmt2(x.diff)}</td></tr>`;
    }).join("") + "</tbody>";
}
$("#bva-month").addEventListener("change", renderOrcado);

// ------------------------------------------------------------------ CADASTROS
function renderCadastros() {
  $("#cat-table").innerHTML = `<thead><tr><th>Nome</th><th>Grupo</th><th>Tipo</th><th>Tag</th><th>Ordem</th><th>Ativa</th><th></th></tr></thead><tbody>` +
    state.categories.map((c) => `<tr data-id="${c.id}"><td><input data-k="name" value="${esc(c.name)}"></td>
      <td><select data-k="group">${Object.entries(GROUPS).map(([g, l]) => `<option value="${g}" ${g === c.group ? "selected" : ""}>${l}</option>`).join("")}</select></td>
      <td><select data-k="kind">${Object.entries(KINDS).map(([k, l]) => `<option value="${k}" ${k === c.kind ? "selected" : ""}>${l}</option>`).join("")}</select></td>
      <td><select data-k="tag">${["", "moradia", "saude"].map((t) => `<option value="${t}" ${t === (c.tag || "") ? "selected" : ""}>${t || "–"}</option>`).join("")}</select></td>
      <td><input data-k="sort_order" type="number" style="width:70px" value="${c.sort_order}"></td>
      <td><input data-k="active" type="checkbox" ${c.active ? "checked" : ""}></td>
      <td><button class="sm" data-save>Salvar</button> <button class="ghost sm danger" data-del>Excluir</button></td></tr>`).join("") + "</tbody>";
  $("#acc-table").innerHTML = `<thead><tr><th>Nome</th><th>Tipo</th><th>Saldo inicial</th><th></th></tr></thead><tbody>` +
    state.accounts.map((a) => `<tr data-id="${a.id}"><td><input data-k="name" value="${esc(a.name)}"></td>
      <td><select data-k="type">${["corrente", "investimento", "cartao", "dinheiro"].map((t) => `<option ${t === a.type ? "selected" : ""}>${t}</option>`).join("")}</select></td>
      <td><input data-k="opening_balance" type="number" step="0.01" style="width:120px" value="${a.opening_balance}"></td>
      <td><button class="sm" data-save>Salvar</button> <button class="ghost sm danger" data-del>Excluir</button></td></tr>`).join("") + "</tbody>";
}

async function crudClick(e, path, read) {
  const tr = e.target.closest("tr");
  if (!tr) return;
  const id = tr.dataset.id;
  if (e.target.matches("[data-del]")) {
    if (!confirm("Excluir registro?")) return;
    await api("DELETE", `/api/${path}/${id}`);
  } else if (e.target.matches("[data-save]")) {
    await api(id ? "PUT" : "POST", id ? `/api/${path}/${id}` : `/api/${path}`, read(tr));
    toast("Salvo");
  } else return;
  await loadBase();
  await refresh();
}
$("#cat-table").addEventListener("click", (e) => crudClick(e, "categories", (tr) => ({
  name: rowVal(tr, "name"), group: rowVal(tr, "group"), kind: rowVal(tr, "kind"), tag: rowVal(tr, "tag") || null,
  sort_order: parseInt(rowVal(tr, "sort_order") || "0", 10), active: tr.querySelector('[data-k="active"]').checked,
})));
$("#acc-table").addEventListener("click", (e) => crudClick(e, "accounts", (tr) => ({
  name: rowVal(tr, "name"), type: rowVal(tr, "type"), opening_balance: Number(rowVal(tr, "opening_balance") || 0),
})));
$("#btn-add-cat").onclick = () => {
  state.categories.push({ id: "", name: "", group: "despesa_variavel", kind: "manual", tag: null, sort_order: 999, active: true });
  renderCadastros();
};
$("#btn-add-acc").onclick = () => {
  state.accounts.push({ id: "", name: "", type: "corrente", opening_balance: 0 });
  renderCadastros();
};
async function importXlsx(input, button, report) {
  const f = input.files[0];
  if (!f) return toast("Escolha o arquivo .xlsx");
  const fd = new FormData();
  fd.append("file", f);
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "Importando…";
  try {
    const r = await api("POST", "/api/import/xlsx", fd);
    report.hidden = false;
    report.textContent = r.report.join("\n");
    toast("Planilha importada");
    await loadBase();
    await refresh();
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}
$("#btn-import").onclick = () => importXlsx($("#xlsx-file"), $("#btn-import"), $("#import-report"));
$("#btn-empty-import").onclick = () => importXlsx($("#empty-xlsx"), $("#btn-empty-import"), $("#empty-report"));
$("#btn-empty-new").onclick = () => $("#btn-new-scenario").click();

// ------------------------------------------------------------------ navegação
const RENDER = {
  painel: renderPainel, fluxo: renderFluxo, premissas: renderPremissas, consignados: renderConsignados, atrasos: renderAtrasos,
  comparar: renderComparar, lancamentos: renderLancamentos, orcado: renderOrcado, cadastros: renderCadastros,
};

function showTab(tab) {
  state.tab = tab;
  $$("#nav button").forEach((x) => x.classList.toggle("active", x.dataset.tab === tab));
  $$("section.tab").forEach((s) => s.classList.toggle("active", s.id === `tab-${tab}`));
  history.replaceState(null, "", `#${tab}`);
}

$("#nav").addEventListener("click", async (e) => {
  const b = e.target.closest("button[data-tab]");
  if (!b) return;
  showTab(b.dataset.tab);
  await RENDER[state.tab]();
  Object.values(charts).forEach((c) => c.resize());
});
$("#scenario").addEventListener("change", async (e) => {
  state.current = +e.target.value;
  await refresh();
});
$("#sankey-mode").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  $$("#sankey-mode button").forEach((x) => x.classList.toggle("active", x === b));
  drawPainelSankey();
});
$("#sankey-month").addEventListener("change", drawPainelSankey);

async function checkStatus() {
  const st = await api("GET", "/api/status");
  const warn = [];
  if (st.hosted && !st.auth) warn.push("Este endereço está público e sem senha: qualquer pessoa com o link vê seus dados. Defina FINANCI_PASSWORD nas variáveis de ambiente do Vercel e faça um novo deploy.");
  if (st.hosted && st.database === "sqlite") warn.push("DATABASE_URL não está definida: os dados não ficam salvos. Configure a connection string do Neon no Vercel.");
  const el = $("#security-banner");
  el.hidden = !warn.length;
  el.innerHTML = warn.map((w) => `<div><span class="badge negative">atenção</span> ${esc(w)}</div>`).join("");
}

(async function init() {
  checkStatus();
  await loadBase();
  const tab = location.hash.slice(1);
  if (RENDER[tab]) showTab(tab);
  await refresh();
})();
