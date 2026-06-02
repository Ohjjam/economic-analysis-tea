"""Self-contained HTML viewer for PFDs (mermaid) + auto-built process info.

Double-click the generated `.html` in `design_notes/` — your default browser
opens it and renders the mermaid PFD. No Streamlit needed.

Features:
- Mermaid PFD with category-coloured nodes + dashed recycle arrows
- Topline TEA, revenue breakdown, scale-up ladder tables
- Optional sensitivity charts (Chart.js, inline)
- Dark / light mode toggle
- Multi-scenario comparison view via `render_comparison_html`

Usage
-----
>>> from tea_engine import render_html_viewer, render_comparison_html
>>> render_html_viewer(exp, process, result, scaleup_report,
...                    mermaid_pfd_text, out_path="design_notes/foo.html",
...                    sensitivity={"Lignin price": [(0.05, 1.03), (0.4, 5.41)]})
>>> render_comparison_html(scenarios, out_path="design_notes/compare.html")
"""
from __future__ import annotations
import json
from html import escape
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .experiment import Experiment
from .process import Process
from .tea import TEAResult
from .scaleup import ScaleupReport
from .equipment import CEPCI


_HTML_TEMPLATE = """<!doctype html>
<html lang="en" data-theme="auto">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>PFD — {title}</title>
<style>
  :root, html[data-theme="light"] {{
    --bg: #fafafa; --fg: #111; --muted: #555; --accent: #1565C0;
    --card: #fff; --border: #e0e0e0;
  }}
  html[data-theme="dark"] {{
    --bg: #1a1a1a; --fg: #eee; --muted: #aaa; --accent: #64B5F6;
    --card: #232323; --border: #333;
  }}
  @media (prefers-color-scheme: dark) {{
    html[data-theme="auto"] {{
      --bg: #1a1a1a; --fg: #eee; --muted: #aaa; --accent: #64B5F6;
      --card: #232323; --border: #333;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ background: var(--bg); color: var(--fg); margin: 0;
          font: 14px/1.5 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
  header {{ padding: 20px 28px; border-bottom: 1px solid var(--border);
            background: var(--card); }}
  h1 {{ margin: 0; font-size: 20px; font-weight: 600; }}
  h1 .small {{ color: var(--muted); font-weight: 400; font-size: 14px; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 24px 28px; }}
  .card {{ background: var(--card); border: 1px solid var(--border);
           border-radius: 8px; padding: 18px 22px; margin-bottom: 18px; }}
  h2 {{ margin-top: 0; font-size: 16px; color: var(--accent);
        border-bottom: 1px solid var(--border); padding-bottom: 6px; }}
  .kv {{ display: grid; grid-template-columns: 200px 1fr; gap: 6px 18px; }}
  .kv dt {{ color: var(--muted); }}
  .kv dd {{ margin: 0; font-weight: 500; }}
  table {{ width: 100%; border-collapse: collapse; margin: 6px 0; }}
  th, td {{ text-align: left; padding: 6px 10px;
            border-bottom: 1px solid var(--border); }}
  th {{ color: var(--muted); font-weight: 500; font-size: 12px;
        text-transform: uppercase; letter-spacing: 0.04em; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .pfd-wrap {{ background: var(--card); border-radius: 8px;
               border: 1px solid var(--border); padding: 14px;
               position: relative; }}
  .pfd-toolbar {{ position: absolute; top: 12px; right: 14px; z-index: 5;
                   display: flex; gap: 6px; }}
  .pfd-toolbar button {{ background: var(--card); color: var(--fg);
                          border: 1px solid var(--border); border-radius: 4px;
                          padding: 4px 10px; font-size: 13px; cursor: pointer; }}
  .pfd-toolbar button:hover {{ background: var(--accent); color: white; }}
  /* PFD scroll-host. SVG renders at its natural width (mermaid's default);
     if it's wider than the viewport the host scrolls horizontally.
     Height grows to fit the SVG so nothing is ever clipped vertically. */
  .pfd {{ width: 100%; overflow: auto; padding: 8px 0; }}
  .pfd svg {{ display: block; margin: 0 auto;
               max-width: none;
               height: auto;
               transform-origin: top left;
               transform: scale(var(--pfd-scale, 1)); }}
  .pfd .node text, .pfd .nodeLabel, .pfd .edgeLabel {{ font-size: 14px !important; }}
  .pfd-fullscreen {{ position: fixed; inset: 0; z-index: 1000;
                      background: var(--bg); padding: 60px 24px 24px;
                      overflow: auto; }}
  details.risks {{ margin-top: 8px; }}
  details.risks summary {{ cursor: pointer; color: var(--accent);
                           font-weight: 500; padding: 4px 0; }}
  details.risks ul {{ margin: 6px 0; padding-left: 24px; }}
  footer {{ color: var(--muted); font-size: 12px;
            padding: 18px 28px; text-align: center; }}
  .badge {{ display: inline-block; padding: 2px 8px;
            background: var(--accent); color: white; border-radius: 4px;
            font-size: 11px; margin-left: 6px; }}
  .theme-toggle {{ position: fixed; top: 14px; right: 16px;
                   background: var(--card); color: var(--fg);
                   border: 1px solid var(--border); border-radius: 6px;
                   padding: 6px 12px; font-size: 13px; cursor: pointer;
                   z-index: 100; }}
  .theme-toggle:hover {{ background: var(--accent); color: white; }}
  .chart-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
                 gap: 16px; }}
  .chart-box {{ background: var(--card); border: 1px solid var(--border);
                border-radius: 6px; padding: 10px 14px; }}
  .chart-box h3 {{ margin: 0 0 8px 0; font-size: 13px; color: var(--muted);
                   font-weight: 500; }}
  canvas {{ max-height: 220px; }}
</style>
</head>
<body>
<button class="theme-toggle" onclick="toggleTheme()">🌓 theme</button>
<header>
  <h1>{title} <span class="small">— {subtitle}</span></h1>
</header>
<div class="container">

  <div class="card pfd-wrap" id="pfd-card">
    <h2>📐 Process Flow Diagram</h2>
    <div class="pfd-toolbar">
      <button onclick="pfdZoom(1.25)">🔍+</button>
      <button onclick="pfdZoom(0.8)">🔍−</button>
      <button onclick="pfdReset()">↺ reset</button>
      <button onclick="pfdFullscreen()">⛶ full</button>
    </div>
    <div class="pfd" id="pfd-host">
      <pre class="mermaid">
{mermaid_block}
      </pre>
    </div>
  </div>

  {operating_conditions_block}

  {energy_breakdown_block}

  <div class="card">
    <h2>📊 Topline TEA <span class="badge">at {top_scale} t/batch</span></h2>
    <dl class="kv">
      <dt>CAPEX total</dt><dd>${capex_total_m:.2f} M</dd>
      <dt>CAPEX annualized</dt><dd>${capex_ann_m:.2f} M/y</dd>
      <dt>OPEX</dt><dd>${opex_m:.2f} M/y</dd>
      <dt>Revenue total</dt><dd>${rev_m:.2f} M/y</dd>
      <dt>Net profit</dt><dd><b>${profit_m:.2f} M/y</b></dd>
      <dt>MSP of {msp_product}</dt><dd>${msp:.2f} /kg{msp_paper_note}</dd>
    </dl>
    <p class="small" style="color:var(--muted);margin-top:6px">
      <b>MSP of {msp_product}</b> = the {msp_product} selling price at which the
      project breaks even (NPV = 0 over the plant life), <i>after</i> crediting
      revenue from all co-products. Net profit above uses current market prices
      for every product.</p>
  </div>

  {revenue_breakdown_block}

  {economics_detail_block}

  {capex_breakdown_block}

  {opex_breakdown_block}

  <div class="card">
    <h2>📈 Scale-up ladder</h2>
    <table>
      <tr><th>Stage</th><th class="num">t/batch</th>
          <th class="num">CAPEX ($M)</th><th class="num">OPEX ($M/y)</th>
          <th class="num">Revenue ($M/y)</th><th class="num">Net profit ($M/y)</th>
          <th class="num">MSP {msp_product} ($/kg)</th></tr>
      {scaleup_rows}
    </table>
    {recommendation_block}
  </div>

  {sensitivity_block}

  {risks_block}

  <div class="card">
    <h2>📦 Streams & makeup (per batch)</h2>
    <p class="small" style="color:var(--muted);margin-top:-2px">
      The PFD shows ONE arrow per reagent. The breakdown of how much is loaded
      once (initial charge) vs replenished continuously (makeup at the drag-out
      rate) is here.
    </p>
    <table>
      <tr><th>Stream</th><th>Role</th><th class="num">g/batch</th>
          <th class="num">Recovery</th><th>Behaviour</th></tr>
      {streams_rows}
    </table>
  </div>

  {price_sources_block}

  <div class="card">
    <h2>🛠️ Equipment</h2>
    <table>
      <tr><th>Section</th><th>Equipment</th><th class="num">Base cost ($)</th>
          <th>Source</th><th>Lifetime</th></tr>
      {equipment_rows}
    </table>
  </div>

  {references_block}

</div>

<footer>
  Generated by tea_tool · {timestamp}<br>
  Diagrams &amp; charts load from the local <code>vendor/</code> folder (works
  offline); if this file is moved on its own, they fall back to a CDN.
</footer>

<script>
  // ---------- theme ----------
  function toggleTheme() {{
    const cur = document.documentElement.getAttribute("data-theme");
    const next = (cur === "dark") ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("tea-theme", next);
    location.reload();
  }}
  const saved = localStorage.getItem("tea-theme");
  if (saved) document.documentElement.setAttribute("data-theme", saved);

  // ---------- robust loader: local vendor first, CDN fallback ----------
  function loadScript(local, cdn, cb) {{
    var s = document.createElement("script");
    s.src = local;
    s.onload = cb;
    s.onerror = function () {{
      var c = document.createElement("script");
      c.src = cdn; c.onload = cb;
      c.onerror = function () {{ console.warn("tea_tool: could not load " + local + " (and CDN failed)"); }};
      document.head.appendChild(c);
    }};
    document.head.appendChild(s);
  }}

  // ---------- PFD zoom / fit (independent of mermaid loading) ----------
  function setScale(s) {{
    const svg = document.querySelector("#pfd-host svg");
    if (!svg) return;
    document.documentElement.style.setProperty("--pfd-scale", String(s));
    const host = document.getElementById("pfd-host");
    host.scrollLeft = host.scrollLeft;
  }}
  function currentScale() {{
    return parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue("--pfd-scale") || 1
    ) || 1;
  }}
  function fitToWidth() {{
    const svg = document.querySelector("#pfd-host svg");
    const host = document.getElementById("pfd-host");
    if (!svg || !host) return;
    const vb = (svg.getAttribute("viewBox") || "").split(/\\s+/).map(Number);
    const nat = (vb.length === 4 && vb[2]) ? vb[2] : svg.clientWidth;
    if (!nat) return;
    const fit = (host.clientWidth - 20) / nat;
    setScale(Math.max(0.2, Math.min(3, fit)));
  }}
  window.addEventListener("resize", () => setTimeout(fitToWidth, 100));
  window.pfdZoom = (factor) => setScale(currentScale() * factor);
  window.pfdReset = () => fitToWidth();
  window.pfdFullscreen = () => {{
    const card = document.getElementById("pfd-card");
    card.classList.toggle("pfd-fullscreen");
    setTimeout(fitToWidth, 200);
  }};

  // ---------- mermaid (called once mermaid.min.js has loaded) ----------
  function pickMermaidTheme() {{
    const t = document.documentElement.getAttribute("data-theme");
    if (t === "dark") return "dark";
    if (t === "light") return "default";
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "default";
  }}
  function initMermaid() {{
    if (!window.mermaid) return;
    try {{
      mermaid.initialize({{
        startOnLoad: false,
        theme: pickMermaidTheme(),
        securityLevel: "loose",
        flowchart: {{ htmlLabels: true, curve: "basis", nodeSpacing: 50,
                     rankSpacing: 80, padding: 14, useMaxWidth: false }},
        themeVariables: {{ fontSize: "15px" }}
      }});
      var p = mermaid.run ? mermaid.run({{ querySelector: ".mermaid" }}) : null;
      if (p && p.then) p.then(() => setTimeout(fitToWidth, 300));
      else setTimeout(fitToWidth, 500);
    }} catch (e) {{ try {{ mermaid.init(); setTimeout(fitToWidth, 500); }} catch (e2) {{}} }}
  }}

  // ---------- charts (called once chart.umd.min.js has loaded) ----------
  const SENSITIVITY_DATA = {sensitivity_json};
  function initCharts() {{
    if (!window.Chart) return;
    const txt = getComputedStyle(document.documentElement).getPropertyValue("--fg").trim();
    const acc = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();
    for (const [title, points] of Object.entries(SENSITIVITY_DATA)) {{
      const id = "chart_" + title.replace(/[^a-zA-Z0-9]/g, "_");
      const el = document.getElementById(id);
      if (!el) continue;
      new Chart(el, {{
        type: "line",
        data: {{ labels: points.map(p => p[0]),
          datasets: [{{ label: "MSP ($/kg)", data: points.map(p => p[1]),
            borderColor: acc, backgroundColor: acc + "33", tension: 0.3, pointRadius: 5 }}] }},
        options: {{ responsive: true, maintainAspectRatio: false,
          scales: {{ x: {{ ticks: {{ color: txt }} }},
                    y: {{ ticks: {{ color: txt }}, title: {{ display: true, text: "MSP ($/kg)", color: txt }} }} }},
          plugins: {{ legend: {{ display: false }} }} }}
      }});
    }}
  }}

  // ---------- kick off (local-first, CDN fallback) ----------
  loadScript("vendor/mermaid.min.js",
             "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js", initMermaid);
  loadScript("vendor/chart.umd.min.js",
             "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js", initCharts);
</script>
</body>
</html>
"""


def render_html_viewer(
    exp: Experiment,
    process: Process,
    result: TEAResult,
    scaleup: Optional[ScaleupReport],
    mermaid_pfd: str,
    out_path: str | Path,
    sensitivity: Optional[Dict[str, List[Tuple[float, float]]]] = None,
) -> Path:
    """Render a single self-contained .html file with the PFD + TEA tables.

    `sensitivity` is an optional dict {title: [(x, msp), ...]} → one Chart.js
    line chart per entry.
    """
    from datetime import datetime

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    inp = result.inputs
    ton = max(inp.scales_ton)

    # Revenue breakdown block
    rev_lines = "".join(
        f"<tr><td>{escape(k)}</td><td class='num'>${v/1e6:.2f}</td></tr>"
        for k, v in result.revenue[ton].items()
    )
    revenue_breakdown = (
        f"<div class='card'><h2>💰 Revenue breakdown @ {ton:g} t/batch</h2>"
        f"<table><tr><th>Product</th><th class='num'>$M/y</th></tr>"
        f"{rev_lines}</table></div>"
    )

    # Scale-up table
    if scaleup and scaleup.stages:
        scaleup_rows = "".join(
            f"<tr><td>{escape(s.stage.name)}</td>"
            f"<td class='num'>{s.stage.ton_per_batch:g}</td>"
            f"<td class='num'>{s.capex_total_usd/1e6:.2f}</td>"
            f"<td class='num'>{s.opex_total_usd/1e6:.2f}</td>"
            f"<td class='num'>{s.revenue_total_usd/1e6:.2f}</td>"
            f"<td class='num'>{s.net_profit_usd/1e6:.2f}</td>"
            f"<td class='num'>{s.msp_usd_per_kg:.2f}</td></tr>"
            for s in scaleup.stages
        )
    else:
        scaleup_rows = "<tr><td colspan='7'><i>no scale-up report</i></td></tr>"

    recommendation_block = (
        f"<p><b>Recommendation:</b> {escape(scaleup.recommendation)}</p>"
        if (scaleup and scaleup.recommendation) else ""
    )

    # Risks block
    risks_html = ""
    if scaleup:
        parts = []
        if scaleup.general_risks:
            items = "".join(f"<li>{escape(r)}</li>" for r in scaleup.general_risks)
            parts.append(f"<details class='risks' open><summary>"
                         f"Generic ({len(scaleup.general_risks)})</summary>"
                         f"<ul>{items}</ul></details>")
        if scaleup.downstream_risks:
            items = "".join(f"<li>{escape(r)}</li>" for r in scaleup.downstream_risks)
            parts.append(f"<details class='risks'><summary>"
                         f"Downstream ({len(scaleup.downstream_risks)})</summary>"
                         f"<ul>{items}</ul></details>")
        if scaleup.safety_risks:
            items = "".join(f"<li>{escape(r)}</li>" for r in scaleup.safety_risks)
            parts.append(f"<details class='risks'><summary>"
                         f"EHS / safety ({len(scaleup.safety_risks)})</summary>"
                         f"<ul>{items}</ul></details>")
        if parts:
            risks_html = ("<div class='card'><h2>⚠️ Scale-up risks</h2>"
                          + "".join(parts) + "</div>")

    # Streams table — split out the behaviour (initial / makeup / continuous)
    def _behaviour(s):
        mode = getattr(s, "flow_mode", "continuous")
        if mode == "one_time":
            return f"initial only ({getattr(s, 'initial_charge_kg_per_ton', 0):g} kg/ton)"
        if mode == "periodic":
            mo = getattr(s, "replacement_interval_months", 0)
            return f"periodic every {mo/12:g} y"
        rec = getattr(s, "recovery", 0.0)
        if rec >= 0.95:
            return (f"continuous: initial charge + {(1-rec)*100:.1f}% / batch "
                    f"makeup (recovery {rec*100:.0f}%)")
        if rec > 0:
            return f"continuous with {rec*100:.0f}% recovery"
        return "continuous (single-pass)"

    streams_rows = "".join(
        f"<tr><td>{escape(s.component)}</td><td>input</td>"
        f"<td class='num'>{s.mass_per_batch_g:g}</td>"
        f"<td class='num'>{s.recovery:.2f}</td>"
        f"<td>{escape(_behaviour(s))}</td></tr>"
        for s in process.streams.inputs
    ) + "".join(
        f"<tr><td>{escape(s.component)}</td><td>output</td>"
        f"<td class='num'>{s.mass_per_batch_g:g}</td><td class='num'>—</td>"
        f"<td>product</td></tr>"
        for s in process.streams.outputs
    )

    # Equipment table with active source
    equipment_rows = "".join(
        f"<tr><td>{escape(e.section)}</td><td>{escape(e.name)}</td>"
        f"<td class='num'>${e.base_cost:,.0f}</td>"
        f"<td>{escape(e.active_label())}</td>"
        f"<td>{(str(e.lifetime_years)+' y') if e.lifetime_years else 'permanent'}</td></tr>"
        for e in process.equipment.items
    )

    # Price-sources table (one row per component used in the process)
    used_components: set = set()
    for s in process.streams.inputs + process.streams.outputs:
        used_components.add(s.component)
    price_rows = []
    db = result.inputs  # not actually db; we keep components on the result via TEAResult? — get from process
    # Pull from the process's database via Components in process.streams set:
    # we don't have direct DB access here; instead, expose price info via
    # the components dict stored on the Process if available. Safe fallback.
    if hasattr(process, "_component_db_ref"):
        cdb = process._component_db_ref
    else:
        cdb = None
    if cdb is not None:
        for name in sorted(used_components):
            if name not in cdb:
                continue
            c = cdb.get(name)
            active = (c.price_sources[c.active_source_index].label()
                      if c.price_sources else (c.price_ref or "default"))
            other = ""
            if c.price_sources and len(c.price_sources) > 1:
                other = "; ".join(
                    f"{s.label()} ${s.value_usd_per_kg:.2f}"
                    for i, s in enumerate(c.price_sources)
                    if i != c.active_source_index
                )
            price_rows.append(
                f"<tr><td>{escape(name)}</td><td class='num'>${c.price:.2f}</td>"
                f"<td>{escape(active)}</td><td class='small' style='color:var(--muted)'>{escape(other)}</td></tr>"
            )
    price_sources_block = ""
    if price_rows:
        price_sources_block = (
            "<div class='card'><h2>📚 Chemical price references</h2>"
            "<table><tr><th>Component</th><th class='num'>Active $/kg</th>"
            "<th>Active source</th><th>Other sources on file</th></tr>"
            + "".join(price_rows) + "</table></div>"
        )

    msp_paper_note = ""
    if exp.reported_msp is not None:
        msp_paper_note = (f"  <span class='small' style='color:var(--muted)'>"
                          f"(paper: ${exp.reported_msp:.2f}/kg)</span>")

    # Detailed per-scale economics (so net profit & its drivers are explicit,
    # not just MSP). One column per scale; rows = annualized CAPEX, OPEX split,
    # revenue per product, net profit, MSP.
    scales = list(inp.scales_ton)
    prod_names = [s.component for s in process.streams.outputs]

    def _ecorow(label, fn, bold=False, money=True):
        cells = "".join(
            f"<td class='num'>{('$'+format(fn(sc)/1e6, ',.2f')+' M') if money else format(fn(sc), ',.2f')}</td>"
            for sc in scales)
        tag = "b" if bold else "span"
        return f"<tr><td><{tag}>{escape(label)}</{tag}></td>{cells}</tr>"

    sc_hdr = "".join(f"<th class='num'>{sc:g} t/batch</th>" for sc in scales)
    eco_rows = []
    eco_rows.append(_ecorow("Annualized CAPEX", lambda s: result.capex_annualized[s]))
    eco_rows.append(_ecorow("  Feedstock OPEX",
                            lambda s: result.opex[s].get("__Feedstock Total", 0.0)))
    eco_rows.append(_ecorow("  Utility OPEX (heat + electricity)",
                            lambda s: result.opex[s].get("__Utility Total", 0.0)))
    eco_rows.append(_ecorow("  Maintenance + operation",
                            lambda s: result.opex[s].get("__Operation Total", 0.0)))
    eco_rows.append(_ecorow("OPEX total", lambda s: result.opex_total[s], bold=True))
    for pn in prod_names:
        eco_rows.append(_ecorow(f"  Revenue — {pn}",
                                lambda s, p=pn: result.revenue[s].get(p, 0.0)))
    eco_rows.append(_ecorow("Revenue total", lambda s: result.revenue_total[s], bold=True))
    eco_rows.append(_ecorow("Net profit", lambda s: result.net_profit[s], bold=True))
    eco_rows.append(
        "<tr><td><b>MSP of " + escape(inp.msp_product) + "</b></td>"
        + "".join(f"<td class='num'><b>${result.msp[s]:.2f}/kg</b></td>" for s in scales)
        + "</tr>")
    economics_detail_block = (
        "<div class='card'><h2>💵 Detailed economics by scale</h2>"
        "<table><tr><th>Line item ($M/y unless noted)</th>" + sc_hdr + "</tr>"
        + "".join(eco_rows) + "</table>"
        "<p class='small' style='color:var(--muted);margin-top:8px'>"
        "Net profit = revenue total − (annualized CAPEX + OPEX total), at current "
        "market prices. Utility OPEX bundles heat (steam/reactor duty) and "
        "electricity (electrolysis); see the Energy OPEX card for the split.</p></div>"
    )

    # ---- Itemized CAPEX breakdown (every equipment, installed cost @ top scale) ----
    cepci_val = CEPCI.get(inp.cepci_target_year, 800.8)
    capex_item_rows = []
    isbl_total = 0.0
    by_sec = {}
    for e in process.equipment.items:
        by_sec.setdefault(e.section, []).append(e)
    for sec in process.sections:
        items = by_sec.get(sec.label, [])
        if not items:
            continue
        sec_sub = 0.0
        capex_item_rows.append(
            f"<tr style='background:var(--border)'><td colspan='3'><b>{escape(sec.label)}</b></td></tr>")
        for e in items:
            c = e.installed_cost(cepci_val, ton, process.meta)
            sec_sub += c
            src = e.active_label()
            src_html = "" if src in ("default", None) else escape(str(src))
            capex_item_rows.append(
                f"<tr><td style='padding-left:20px'>{escape(e.name)}</td>"
                f"<td class='num'>${c:,.0f}</td><td class='small'>{src_html}</td></tr>")
        isbl_total += sec_sub
        capex_item_rows.append(
            f"<tr><td style='padding-left:20px;color:var(--muted)'><i>{escape(sec.label)} subtotal</i></td>"
            f"<td class='num' style='color:var(--muted)'><i>${sec_sub:,.0f}</i></td><td></td></tr>")
    osbl_val = isbl_total * inp.osbl_fraction
    capex_item_rows.append(
        f"<tr><td><b>ISBL (inside battery limits)</b></td>"
        f"<td class='num'><b>${isbl_total:,.0f}</b></td><td></td></tr>")
    capex_item_rows.append(
        f"<tr><td>OSBL ({int(inp.osbl_fraction*100)}% of ISBL)</td>"
        f"<td class='num'>${osbl_val:,.0f}</td><td class='small'>standard factor</td></tr>")
    capex_item_rows.append(
        f"<tr><td><b>Total installed CAPEX</b></td>"
        f"<td class='num'><b>${(isbl_total+osbl_val):,.0f}</b></td>"
        f"<td class='small'>× CRF {inp.crf:.4f} → ${(isbl_total+osbl_val)*inp.crf/1e6:,.2f} M/y annualized</td></tr>")
    capex_breakdown_block = (
        f"<div class='card'><h2>🏭 CAPEX breakdown (every unit, installed @ {ton:g} t/batch)</h2>"
        "<table><tr><th>Equipment</th><th class='num'>Installed cost</th><th>Source / basis</th></tr>"
        + "".join(capex_item_rows) + "</table>"
        "<p class='small' style='color:var(--muted);margin-top:8px'>"
        "Installed cost scales from the reference quote by the 0.6 power law "
        f"× CEPCI({inp.cepci_target_year}). Equipment quotes are from the source "
        "paper TEA basis unless a source is shown. Annualized via CRF = "
        f"{inp.crf:.4f} ({int(inp.discount_rate*100)}%, {inp.lifetime_years} y).</p></div>"
    )

    # ---- Itemized OPEX breakdown (every line @ top scale, with subtotals) ----
    opex_item_rows = []
    for k, v in result.opex[ton].items():
        if k == "__OPEX Total":
            continue
        if k.startswith("__"):
            name = k[2:]
            opex_item_rows.append(
                f"<tr><td style='padding-left:6px'><i>{escape(name)}</i></td>"
                f"<td class='num'><i>${v:,.0f}</i></td></tr>")
        else:
            opex_item_rows.append(
                f"<tr><td style='padding-left:22px'>{escape(k.strip())}</td>"
                f"<td class='num'>${v:,.0f}</td></tr>")
    opex_item_rows.append(
        f"<tr style='border-top:2px solid var(--accent)'><td><b>OPEX total</b></td>"
        f"<td class='num'><b>${result.opex_total[ton]:,.0f}/y</b></td></tr>")
    opex_breakdown_block = (
        f"<div class='card'><h2>🧾 OPEX breakdown (every line @ {ton:g} t/batch)</h2>"
        "<table><tr><th>Line item</th><th class='num'>$/year</th></tr>"
        + "".join(opex_item_rows) + "</table>"
        "<p class='small' style='color:var(--muted);margin-top:8px'>"
        "Feedstock = makeup × price (recovered fractions excluded). Utility = "
        "energy coefficients × throughput. Maintenance + operation per the "
        "assumptions table. Component prices &amp; their sources are listed in "
        "the price-references card below.</p></div>"
    )

    # Assumptions & References block (schema v2). References are NUMBERED [n]
    # and every sourced number shows an inline [n] marker linking to the list.
    references_block = ""
    refs = getattr(exp, "references", []) or []
    ass = getattr(exp, "assumptions", []) or []
    if refs or ass:
        num = {r.id: i + 1 for i, r in enumerate(refs)}  # id -> citation number

        def _marker(ref_id):
            if not ref_id:
                return "<sup style='color:#C62828'>[?]</sup>"
            n = num.get(ref_id)
            if n is None:
                return f"<sup style='color:#C62828'>[{escape(str(ref_id))}?]</sup>"
            return (f"<sup><a href='#ref-{n}' style='text-decoration:none;"
                    f"color:var(--accent)'>[{n}]</a></sup>")

        # Sourced feedstock prices (price_ref lives in raw)
        feed_raw = (exp.raw.get("feedstock") or {})
        price_src_rows = []
        prim = feed_raw.get("primary") or {}
        if prim.get("price_usd_per_kg") is not None:
            price_src_rows.append((prim.get("name", "feed"),
                                   prim["price_usd_per_kg"], prim.get("price_ref")))
        for r in (feed_raw.get("reagents") or []):
            if r.get("price_usd_per_kg") is not None:
                price_src_rows.append((r.get("name"), r["price_usd_per_kg"],
                                       r.get("price_ref")))

        parts = []
        if price_src_rows:
            rows = "".join(
                f"<tr><td>{escape(str(n))}</td><td class='num'>${v:g}/kg</td>"
                f"<td>{_marker(rid)}</td></tr>"
                for n, v, rid in price_src_rows)
            parts.append("<h3 style='margin:14px 0 6px'>Feedstock &amp; reagent prices</h3>"
                         "<table><tr><th>Component</th><th class='num'>$/kg</th>"
                         "<th>Ref</th></tr>" + rows + "</table>")
        if ass:
            rows = "".join(
                f"<tr><td>{escape(a.key)}</td><td class='num'>"
                f"{escape(str(a.value))}{(' ' + escape(a.unit)) if a.unit else ''}</td>"
                f"<td>{_marker(a.ref)}</td></tr>"
                for a in ass)
            parts.append("<h3 style='margin:18px 0 6px'>Key assumptions</h3>"
                         "<table><tr><th>Assumption</th><th class='num'>Value</th>"
                         "<th>Ref</th></tr>" + rows + "</table>")
        if refs:
            ref_rows = []
            for r in refs:
                n = num[r.id]
                link = ""
                if r.doi:
                    link = f" · <a href='https://doi.org/{escape(r.doi)}' target='_blank'>doi:{escape(r.doi)}</a>"
                elif r.url:
                    link = f" · <a href='{escape(r.url)}' target='_blank'>link</a>"
                ref_rows.append(
                    f"<tr id='ref-{n}'><td class='num'>[{n}]</td>"
                    f"<td>{escape(r.citation)}{link}</td>"
                    f"<td class='small' style='color:var(--muted)'>{escape(r.type)}</td></tr>")
            parts.append("<h3 style='margin:18px 0 6px'>References</h3>"
                         "<table><tr><th>#</th><th>Citation</th><th>Type</th></tr>"
                         + "".join(ref_rows) + "</table>")
        references_block = (
            "<div class='card'><h2>📚 Assumptions &amp; References</h2>"
            "<p class='small' style='color:var(--muted)'>Every sourced number "
            "carries an inline [n] marker linking to the numbered reference list "
            "below.</p>" + "".join(parts) + "</div>"
        )
    else:
        references_block = (
            "<div class='card'><h2>📚 Assumptions &amp; References</h2>"
            "<p class='small' style='color:var(--muted)'>This process is still on "
            "schema v1 — prices and assumptions are not yet linked to citations. "
            "Run <code>python -m tea_engine.validate_cli</code> to see the coverage "
            "report, and migrate to schema v2 (see the Oh-2026 PET exemplar) to "
            "populate this section.</p></div>"
        )

    # Operating conditions block — one row per chemistry stage
    op_rows = []
    for st in exp.stages:
        bits = []
        if st.get("T_C") is not None: bits.append(f"T = <b>{st['T_C']:g} °C</b>")
        if st.get("P_bar") is not None: bits.append(f"P = {st['P_bar']:g} bar")
        if st.get("residence_h") is not None:
            rh = st['residence_h']
            bits.append(f"τ = {rh*60:g} min" if rh < 1 else f"τ = {rh:g} h")
        if st.get("V") is not None: bits.append(f"V = <b>{st['V']:g} V</b>")
        if st.get("j_mA_cm2") is not None: bits.append(f"j = <b>{st['j_mA_cm2']:g} mA/cm²</b>")
        if st.get("FE_pct") is not None: bits.append(f"FE = {st['FE_pct']:g}%")
        if st.get("heating_method"): bits.append(f"heating: {escape(str(st['heating_method']))}")
        if not bits:
            continue
        op_rows.append(
            f"<tr><td><b>{escape(st.get('name','Stage'))}</b></td>"
            f"<td>{escape(st.get('type','-'))}</td><td>{' · '.join(bits)}</td></tr>"
        )
    operating_conditions_block = ""
    if op_rows:
        operating_conditions_block = (
            "<div class='card'><h2>⚙️ Operating conditions</h2>"
            "<table><tr><th>Stage</th><th>Type</th><th>Conditions</th></tr>"
            + "".join(op_rows) + "</table></div>"
        )

    # Energy OPEX breakdown — pull any opex line with electric/heat in it
    largest_ton = max(inp.scales_ton)
    energy_lines = []
    for k, v in (result.opex.get(largest_ton) or {}).items():
        if k.startswith("__"):
            continue
        if any(t in k.lower() for t in ("electric", "heat", "steam", "utility - utility")):
            energy_lines.append((k, v))
    # Also pull meta items that look like utility coefficients
    meta_lines = [(k, v * largest_ton)
                  for k, v in process.meta.items()
                  if k.endswith("_$_per_ton_per_y") or k.endswith("_$_per_ton/y")]
    energy_breakdown_block = ""
    if energy_lines or meta_lines:
        rows = "".join(
            f"<tr><td>{escape(k)}</td><td class='num'>${v:,.0f}/y</td></tr>"
            for k, v in (energy_lines or meta_lines)
        )
        # Basis & sources: pull the energy-relevant assumptions (with their
        # references) so the reader sees WHERE each coefficient came from.
        _refs2 = getattr(exp, "references", []) or []
        _num2 = {r.id: i + 1 for i, r in enumerate(_refs2)}

        def _mk2(rid):
            if not rid:
                return ""
            n = _num2.get(rid)
            return (f" <sup><a href='#ref-{n}' style='color:var(--accent);"
                    f"text-decoration:none'>[{n}]</a></sup>") if n else ""

        _ENERGY_KEYS = ("electric", "energy", "voltage", "current", "faradaic",
                        "steam", "heat", "kwh", "gj")
        basis_rows = ""
        for a in (getattr(exp, "assumptions", []) or []):
            if any(t in a.key.lower() for t in _ENERGY_KEYS):
                val = f"{escape(str(a.value))}" + (f" {escape(a.unit)}" if a.unit else "")
                basis_rows += (f"<tr><td>{escape(a.key)}</td><td class='num'>{val}"
                               f"{_mk2(a.ref)}</td></tr>")
        basis_block = ""
        if basis_rows:
            basis_block = (
                "<h3 style='margin:14px 0 6px;font-size:13px'>Basis &amp; sources</h3>"
                "<table><tr><th>Parameter</th><th class='num'>Value [ref]</th></tr>"
                + basis_rows + "</table>")
        energy_breakdown_block = (
            "<div class='card'><h2>⚡ Energy OPEX (annualised @ "
            f"{largest_ton:g} t/batch)</h2>"
            "<table><tr><th>Line item</th><th class='num'>$/year</th></tr>"
            + rows + "</table>" + basis_block +
            "<p class='small' style='color:var(--muted);margin-top:8px'>"
            "Electricity (electrolysis) = specific energy × H₂ output × $/kWh; "
            "heat = reactor/evaporation duty × $/GJ. The basis values above carry "
            "[n] links to the numbered reference list.</p></div>"
        )

    # Sensitivity block + Chart.js JSON payload
    sensitivity_block = ""
    sens_json_payload = {}
    if sensitivity:
        boxes = []
        for title, points in sensitivity.items():
            cid = "chart_" + "".join(c if c.isalnum() else "_" for c in title)
            boxes.append(
                f"<div class='chart-box'><h3>{escape(title)}</h3>"
                f"<canvas id='{cid}'></canvas></div>"
            )
            sens_json_payload[title] = [list(pt) for pt in points]
        sensitivity_block = (
            "<div class='card'><h2>📉 Sensitivity sweeps</h2>"
            "<div class='chart-grid'>" + "".join(boxes) + "</div></div>"
        )

    html = _HTML_TEMPLATE.format(
        title=escape(process.name),
        subtitle=escape(exp.meta.researcher or exp.meta.name),
        mermaid_block=mermaid_pfd,
        top_scale=f"{ton:g}",
        capex_total_m=result.capex_total[ton] / 1e6,
        capex_ann_m=result.capex_annualized[ton] / 1e6,
        opex_m=result.opex_total[ton] / 1e6,
        rev_m=result.revenue_total[ton] / 1e6,
        profit_m=result.net_profit[ton] / 1e6,
        msp=result.msp[ton],
        msp_product=escape(inp.msp_product),
        msp_paper_note=msp_paper_note,
        revenue_breakdown_block=revenue_breakdown,
        economics_detail_block=economics_detail_block,
        capex_breakdown_block=capex_breakdown_block,
        opex_breakdown_block=opex_breakdown_block,
        scaleup_rows=scaleup_rows,
        recommendation_block=recommendation_block,
        risks_block=risks_html,
        operating_conditions_block=operating_conditions_block,
        energy_breakdown_block=energy_breakdown_block,
        sensitivity_block=sensitivity_block,
        price_sources_block=price_sources_block,
        references_block=references_block,
        streams_rows=streams_rows,
        equipment_rows=equipment_rows,
        sensitivity_json=json.dumps(sens_json_payload),
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    out.write_text(html, encoding="utf-8")
    return out


# ---------------------------------------------------------------- Comparison
_COMPARE_TEMPLATE = """<!doctype html>
<html lang="en" data-theme="auto">
<head>
<meta charset="utf-8" />
<title>Scenario comparison</title>
<style>
  :root, html[data-theme="light"] {{ --bg:#fafafa; --fg:#111; --muted:#555;
    --accent:#1565C0; --card:#fff; --border:#e0e0e0; }}
  html[data-theme="dark"] {{ --bg:#1a1a1a; --fg:#eee; --muted:#aaa;
    --accent:#64B5F6; --card:#232323; --border:#333; }}
  @media (prefers-color-scheme: dark) {{
    html[data-theme="auto"] {{ --bg:#1a1a1a; --fg:#eee; --muted:#aaa;
      --accent:#64B5F6; --card:#232323; --border:#333; }}
  }}
  body {{ background: var(--bg); color: var(--fg); margin: 0;
          font: 14px/1.5 -apple-system, "Segoe UI", Roboto, Helvetica, Arial; }}
  .container {{ max-width: 1400px; margin: 0 auto; padding: 28px; }}
  h1 {{ margin: 0 0 18px 0; }}
  .card {{ background: var(--card); border: 1px solid var(--border);
           border-radius: 8px; padding: 18px 22px; margin-bottom: 18px; }}
  h2 {{ margin-top: 0; font-size: 16px; color: var(--accent);
        border-bottom: 1px solid var(--border); padding-bottom: 6px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ text-align: left; padding: 8px 10px;
            border-bottom: 1px solid var(--border); }}
  th {{ font-size: 12px; color: var(--muted); text-transform: uppercase;
        letter-spacing: 0.04em; }}
  td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .winner {{ color: #2E7D32; font-weight: 600; }}
  .loser  {{ color: #C62828; }}
  canvas {{ max-height: 320px; }}
  .theme-toggle {{ position: fixed; top: 14px; right: 16px;
                   background: var(--card); color: var(--fg);
                   border: 1px solid var(--border); border-radius: 6px;
                   padding: 6px 12px; font-size: 13px; cursor: pointer; }}
</style>
</head>
<body>
<button class="theme-toggle" onclick="toggleTheme()">🌓 theme</button>
<div class="container">
  <h1>Scenario comparison</h1>

  <div class="card">
    <h2>Summary</h2>
    <table>
      <tr><th>Scenario</th><th>MSP product</th><th class="num">Scale (t)</th>
          <th class="num">CAPEX ($M)</th><th class="num">OPEX ($M/y)</th>
          <th class="num">Revenue ($M/y)</th><th class="num">Net ($M/y)</th>
          <th class="num">MSP ($/kg)</th><th>Detail</th></tr>
      {rows}
    </table>
  </div>

  <div class="card">
    <h2>MSP across scenarios</h2>
    <canvas id="cmp_msp"></canvas>
  </div>

  <div class="card">
    <h2>CAPEX vs OPEX vs Revenue</h2>
    <canvas id="cmp_stack"></canvas>
  </div>

</div>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script>
  function toggleTheme() {{
    const cur = document.documentElement.getAttribute("data-theme");
    document.documentElement.setAttribute("data-theme",
      cur === "dark" ? "light" : "dark");
    localStorage.setItem("tea-theme",
      document.documentElement.getAttribute("data-theme"));
    location.reload();
  }}
  const saved = localStorage.getItem("tea-theme");
  if (saved) document.documentElement.setAttribute("data-theme", saved);

  const DATA = {data_json};
  const txt = getComputedStyle(document.documentElement).getPropertyValue("--fg").trim();
  const acc = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();

  new Chart(document.getElementById("cmp_msp"), {{
    type: "bar",
    data: {{
      labels: DATA.map(s => s.label),
      datasets: [{{ label: "MSP ($/kg)",
                    data: DATA.map(s => s.msp),
                    backgroundColor: acc + "AA" }}]
    }},
    options: {{ scales: {{ y: {{ beginAtZero: true,
                                ticks: {{ color: txt }},
                                title: {{ display: true, text: "MSP ($/kg)", color: txt }} }},
                          x: {{ ticks: {{ color: txt }} }} }},
                 plugins: {{ legend: {{ display: false }} }} }}
  }});

  new Chart(document.getElementById("cmp_stack"), {{
    type: "bar",
    data: {{
      labels: DATA.map(s => s.label),
      datasets: [
        {{ label: "Annualized CAPEX ($M/y)", data: DATA.map(s => s.capex_ann_m),
           backgroundColor: "#37474F" }},
        {{ label: "OPEX ($M/y)", data: DATA.map(s => s.opex_m),
           backgroundColor: "#90A4AE" }},
        {{ label: "Revenue ($M/y)", data: DATA.map(s => s.rev_m),
           backgroundColor: "#43A047" }}
      ]
    }},
    options: {{ scales: {{ y: {{ stacked: false, ticks: {{ color: txt }} }},
                          x: {{ stacked: false, ticks: {{ color: txt }} }} }} }}
  }});
</script>
</body>
</html>
"""


def render_comparison_html(
    scenarios: List[Dict],
    out_path: str | Path,
) -> Path:
    """Render a comparison page across N scenarios.

    Each scenario dict needs:
      label, msp_product, scale_t, capex_total_m, capex_ann_m,
      opex_m, rev_m, net_m, msp, html_path (optional, for detail link)
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    best_msp = min(s["msp"] for s in scenarios)
    rows = []
    for s in scenarios:
        cls = "winner" if s["msp"] == best_msp else ""
        detail = (f"<a href='{escape(s['html_path'])}'>open</a>"
                  if s.get("html_path") else "")
        rows.append(
            f"<tr><td>{escape(s['label'])}</td>"
            f"<td>{escape(s['msp_product'])}</td>"
            f"<td class='num'>{s['scale_t']:g}</td>"
            f"<td class='num'>{s['capex_total_m']:.2f}</td>"
            f"<td class='num'>{s['opex_m']:.2f}</td>"
            f"<td class='num'>{s['rev_m']:.2f}</td>"
            f"<td class='num'>{s['net_m']:.2f}</td>"
            f"<td class='num {cls}'>${s['msp']:.2f}</td>"
            f"<td>{detail}</td></tr>"
        )
    html = _COMPARE_TEMPLATE.format(
        rows="\n      ".join(rows),
        data_json=json.dumps(scenarios),
    )
    out.write_text(html, encoding="utf-8")
    return out


def _mm_label(text: str) -> str:
    """Sanitise a string so it can be embedded inside a mermaid node or
    edge label without breaking the parser.

    Mermaid is finicky about: round brackets `()`, square brackets `[]`,
    pipes `|`, hash `#`, double quotes `"`, the slash before `>` (which
    starts a comment), and `:` in some contexts. We replace them with
    safe Unicode look-alikes or HTML entities. `<br/>` is preserved.
    """
    if text is None:
        return ""
    # Preserve <br/> tokens — substitute with a sentinel, restore at the end.
    SENT = "@@BR@@"
    t = text.replace("<br/>", SENT)
    # Replace parser-hostile characters
    repl = {
        "(":  "❨",   # medium left parenthesis ornament
        ")":  "❩",   # medium right parenthesis ornament
        "[":  "⟦",
        "]":  "⟧",
        "|":  "/",
        "\"": "'",
        "#":  "♯",
        "{":  "❴",
        "}":  "❵",
        ";":  ",",
    }
    for k, v in repl.items():
        t = t.replace(k, v)
    return t.replace(SENT, "<br/>")


def auto_pfd_mermaid(process: Process) -> str:
    """Convert a Process's sections+edges into a mermaid flowchart string.

    Recycle and makeup edges are rendered dashed. Special characters in
    labels are escaped via `_mm_label` so the parser doesn't choke on
    parentheses / units / quotes.
    """
    lines = ["flowchart LR"]
    # Input stream nodes
    for s in process.streams.inputs:
        node_id = "in_" + _safe(s.component)
        lbl = _mm_label(f"{s.component}<br/>{s.mass_per_batch_g:g} g")
        lines.append(f"    {node_id}([\"{lbl}\"])")
    # Section nodes — convert newlines (e.g. operating conditions) to <br/>
    for sec in process.sections:
        node_id = "sec_" + _safe(sec.key)
        label_html = sec.label.replace("\n", "<br/>")
        lbl = _mm_label(label_html)
        lines.append(f"    {node_id}[\"{lbl}\"]")
    # Output stream nodes
    for s in process.streams.outputs:
        node_id = "out_" + _safe(s.component)
        lbl = _mm_label(f"{s.component}<br/>{s.mass_per_batch_g:g} g")
        lines.append(f"    {node_id}([\"{lbl}\"])")
    # Process edges
    sec_keys = {sec.key for sec in process.sections}
    in_names = {s.component for s in process.streams.inputs}
    out_names = {s.component for s in process.streams.outputs}
    for src, dst, lab in process.edges:
        s_id = _resolve(src, sec_keys, in_names, out_names)
        d_id = _resolve(dst, sec_keys, in_names, out_names)
        lab_lower = (lab or "").lower()
        is_recycle = "recycle" in lab_lower
        is_makeup = "makeup" in lab_lower
        # Recycle and makeup both rendered as dashed
        if is_recycle or is_makeup:
            arrow_op = "-.->"
        else:
            arrow_op = "-->"
        if lab:
            safe = _mm_label(lab)
            edge = f"    {s_id} {arrow_op}|{safe}| {d_id}"
        else:
            edge = f"    {s_id} {arrow_op} {d_id}"
        lines.append(edge)
    # Auto-bridge: output streams without explicit incoming edge → from last section
    last_sec = process.sections[-1].key if process.sections else None
    if last_sec:
        for s in process.streams.outputs:
            edge_exists = any(dst == f"out:{s.component}"
                              for src, dst, _ in process.edges)
            if not edge_exists:
                lines.append(f"    sec_{_safe(last_sec)} --> out_{_safe(s.component)}")
    # Auto-bridge: inputs without explicit outgoing edge → into first section
    first_sec = process.sections[0].key if process.sections else None
    if first_sec:
        for s in process.streams.inputs:
            edge_exists = any(src == f"in:{s.component}"
                              for src, dst, _ in process.edges)
            if not edge_exists:
                lines.append(f"    in_{_safe(s.component)} --> sec_{_safe(first_sec)}")

    # Category colouring
    CATEGORY_COLOURS = {
        "feed":               "feed",
        "catalyst":           "catalyst",
        "acid_or_base":       "acidbase",
        "solvent_extraction": "solvent",
        "solvent_reaction":   "solvent",
        "utility":            "utility",
        "consumable":         "consumable",
    }
    lines.append("    classDef feed       fill:#FFE0B2,stroke:#E65100;")
    lines.append("    classDef prod       fill:#C8E6C9,stroke:#2E7D32;")
    lines.append("    classDef rxn        fill:#E1BEE7,stroke:#6A1B9A;")
    lines.append("    classDef catalyst   fill:#F8BBD0,stroke:#AD1457;")
    lines.append("    classDef solvent    fill:#B2DFDB,stroke:#00695C;")
    lines.append("    classDef acidbase   fill:#FFCDD2,stroke:#C62828;")
    lines.append("    classDef utility    fill:#CFD8DC,stroke:#455A64;")
    lines.append("    classDef consumable fill:#D1C4E9,stroke:#4527A0;")
    # Apply
    cat_groups: Dict[str, List[str]] = {v: [] for v in set(CATEGORY_COLOURS.values()) | {"feed"}}
    for s in process.streams.inputs:
        cat = getattr(s, "category", "feed")
        klass = CATEGORY_COLOURS.get(cat, "feed")
        cat_groups[klass].append("in_" + _safe(s.component))
    for klass, ids in cat_groups.items():
        if ids:
            lines.append(f"    class {','.join(ids)} {klass};")
    out_ids = ",".join("out_" + _safe(s.component) for s in process.streams.outputs)
    sec_ids = ",".join("sec_" + _safe(sec.key) for sec in process.sections)
    if out_ids:
        lines.append(f"    class {out_ids} prod;")
    if sec_ids:
        lines.append(f"    class {sec_ids} rxn;")
    return "\n".join(lines)


def _fmt_conditions(cond: dict) -> str:
    """Format a v2 pfd unit's conditions dict into a '·'-joined readout."""
    if not cond:
        return ""
    bits = []
    if cond.get("T_C") is not None: bits.append(f"{cond['T_C']:g} °C")
    if cond.get("P_bar") is not None: bits.append(f"{cond['P_bar']:g} bar")
    if cond.get("residence_h") is not None:
        rh = cond["residence_h"]
        bits.append(f"τ {rh*60:g} min" if rh < 1 else f"τ {rh:g} h")
    if cond.get("stages") is not None: bits.append(f"{cond['stages']:g}×")
    if cond.get("V_cell") is not None: bits.append(f"{cond['V_cell']:g} V")
    if cond.get("j_mA_cm2") is not None: bits.append(f"{cond['j_mA_cm2']:g} mA/cm²")
    if cond.get("FE_pct") is not None: bits.append(f"FE {cond['FE_pct']:g}%")
    if cond.get("note"): bits.append(str(cond["note"]))
    return " · ".join(bits)


def pfd_mermaid_from_spec(pfd: dict) -> str:
    """Render a mermaid flowchart from the curated schema-v2 `pfd:` block.

    Unlike `auto_pfd_mermaid` (which guesses topology from auto-builder
    sections and can leave orphan nodes), this draws EXACTLY the units and
    streams the author specified — so the diagram is correct by construction.
    Streams with kind 'recycle' render dashed; feed/product terminals (in:/out:)
    render as rounded nodes and get coloured.
    """
    units = pfd.get("units") or []
    streams = pfd.get("streams") or []
    if not units:
        return ""
    lines = ["flowchart LR"]
    unit_keys = {u.get("key") for u in units}

    # Terminal (in:/out:) nodes discovered from stream endpoints
    feeds, prods = [], []
    for s in streams:
        for end in ("from", "to"):
            v = str(s.get(end, ""))
            if v.startswith("in:"):
                feeds.append(v[3:])
            elif v.startswith("out:"):
                prods.append(v[4:])
    for name in dict.fromkeys(feeds):
        lines.append(f"    in_{_safe(name)}([\"{_mm_label(name)}\"])")
    # Unit nodes (with operating conditions)
    for u in units:
        nid = "u_" + _safe(u.get("key", ""))
        cond = _fmt_conditions(u.get("conditions") or {})
        lbl = u.get("label", u.get("key", ""))
        if cond:
            lbl = f"{lbl}<br/>{cond}"
        lines.append(f"    {nid}[\"{_mm_label(lbl)}\"]")
    for name in dict.fromkeys(prods):
        lines.append(f"    out_{_safe(name)}([\"{_mm_label(name)}\"])")

    def _nid(tok: str) -> str:
        if tok.startswith("in:"):  return "in_" + _safe(tok[3:])
        if tok.startswith("out:"): return "out_" + _safe(tok[4:])
        return "u_" + _safe(tok)

    for s in streams:
        a, b = _nid(str(s.get("from", ""))), _nid(str(s.get("to", "")))
        kind = str(s.get("kind", "")).lower()
        arrow = "-.->" if kind == "recycle" else "-->"
        lab = s.get("label", "")
        if kind == "recycle" and "recycle" not in lab.lower():
            lab = f"♻ {lab}"
        lines.append(f"    {a} {arrow}|{_mm_label(lab)}| {b}" if lab
                     else f"    {a} {arrow} {b}")

    # Styling
    lines += [
        "    classDef feed fill:#FFE0B2,stroke:#E65100;",
        "    classDef prod fill:#C8E6C9,stroke:#2E7D32;",
        "    classDef unit fill:#E1BEE7,stroke:#6A1B9A;",
    ]
    fids = ",".join("in_" + _safe(n) for n in dict.fromkeys(feeds))
    pids = ",".join("out_" + _safe(n) for n in dict.fromkeys(prods))
    uids = ",".join("u_" + _safe(u.get("key", "")) for u in units)
    if fids: lines.append(f"    class {fids} feed;")
    if pids: lines.append(f"    class {pids} prod;")
    if uids: lines.append(f"    class {uids} unit;")
    return "\n".join(lines)


def _safe(s: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9_]+", "_", s).strip("_") or "n"


def _resolve(token: str, sec_keys, in_names, out_names) -> str:
    if token.startswith("in:"):
        return "in_" + _safe(token[3:])
    if token.startswith("out:"):
        return "out_" + _safe(token[4:])
    return "sec_" + _safe(token)
