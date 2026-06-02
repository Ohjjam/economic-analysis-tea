"""Generate a self-contained HTML "Process Dossier" for every paper, plus an
index landing page. This is the simple, no-install UI: double-click
`dossier/index.html` and browse everything. No server, no Python, no MATLAB.

    python generate_dossiers.py

Output:
    dossier/index.html        landing page (sortable summary of all papers)
    dossier/<slug>.html       one self-contained dossier per paper
"""
import os
import sys
import io
import traceback
from datetime import datetime
from pathlib import Path
from html import escape

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(__file__))

import yaml
from tea_engine import (
    load_experiment, build_process_from_experiment, run_tea,
    build_scaleup_report, render_html_viewer, validate_experiment,
    compute_scenarios, render_scenarios_html,
)
from tea_engine.viewer import auto_pfd_mermaid, pfd_mermaid_from_spec
from tea_engine.tea import sensitivity_one_param
from processes import build_pet, REGISTRY

# Papers that have a VALIDATED, hand-written / physics-backed builder use it for
# the economics (the auto-builder is only a shallow first cut — e.g. it misses
# reactor heat duty and mis-sizes electrolysis). Presentation metadata
# (references, PFD spec) still comes from the v2 experiment YAML.
_LFP_KEY = "Spent LFP Black Mass → Li2CO3 (Mechanochemical, Li-only)"
PREFERRED_BUILDER = {
    "paper_oh_2026_pet_pma": build_pet,
    "spent_lfp_ballmill_li": REGISTRY.get(_LFP_KEY),
}

HERE = Path(os.path.dirname(__file__))
EXPS = HERE / "experiments"
OUT = HERE / "dossier"


def _auto_sensitivity(process, db, inp):
    """Pick up to 2 sensible 1-param sweeps so every dossier has a chart."""
    sens = {}
    # MSP product recovery of the highest-recovery input (separation lever)
    rec_inputs = [s for s in process.streams.inputs if getattr(s, "recovery", 0) >= 0.9]
    if rec_inputs:
        comp = max(rec_inputs, key=lambda s: s.recovery).component
        vals = [0.999, 0.99, 0.95, 0.90]
        try:
            pts = sensitivity_one_param(process, db, inp, f"{comp}.recovery", vals)
            if pts and all(p[1] == p[1] for p in pts):  # no NaN
                sens[f"{comp} recovery → MSP"] = pts
        except Exception:
            pass
    # Highest-priced input price sweep
    try:
        priced = [(s.component, db.get(s.component).price_low or 0.0)
                  for s in process.streams.inputs if s.component in db]
        if priced:
            comp, base = max(priced, key=lambda x: x[1])
            if base > 0:
                vals = [base * m for m in (2.0, 1.5, 1.0, 0.5)]
                pts = sensitivity_one_param(process, db, inp, f"{comp}.price", vals)
                if pts and all(p[1] == p[1] for p in pts):
                    sens[f"{comp} price → MSP"] = pts
    except Exception:
        pass
    return sens


def build_one(yml: Path):
    """Render one paper's dossier. Returns a summary dict (or raises)."""
    exp = load_experiment(yml)
    raw = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
    rep = validate_experiment(raw)

    builder = PREFERRED_BUILDER.get(exp.meta.slug)
    if builder is not None:
        process, db, inp = builder()        # validated / physics-backed model
        model_note = "validated builder"
    else:
        process, db, inp = build_process_from_experiment(exp)  # auto first-cut
        model_note = "auto-builder (first cut)"
    # attach db so the viewer can show price sources
    process._component_db_ref = db
    result = run_tea(process, db, inp)
    scaleup = build_scaleup_report(
        process, db, inp,
        reaction_type=exp.reaction_type,
        hazardous_materials=exp.constraints.get("hazardous_materials", []),
        has_downstream=bool(exp.downstream),
        reported_msp_usd_per_kg=exp.reported_msp,
        reported_source=exp.reported_source,
    )
    sens = _auto_sensitivity(process, db, inp)
    # Prefer the curated schema-v2 PFD spec (correct by construction) over the
    # auto-derived topology (which can leave orphan nodes).
    if exp.pfd.get("units"):
        mermaid = pfd_mermaid_from_spec(exp.pfd)
    else:
        mermaid = auto_pfd_mermaid(process)
    out_html = OUT / f"{exp.meta.slug}.html"
    render_html_viewer(exp, process, result, scaleup, mermaid, out_html, sensitivity=sens)

    # Generic product-strategy scenarios: ANY paper with a `scenarios:` block
    # gets the comparison page auto-built and linked — no per-paper code.
    extra_links = []
    if (exp.scenarios.get("variable_coproducts")):
        try:
            data = compute_scenarios(process, db, inp, exp.scenarios, result=result)
            if data:
                sc_html = OUT / f"{exp.meta.slug}_scenarios.html"
                render_scenarios_html(exp, data, sc_html)
                extra_links.append(("product-strategy scenarios", sc_html.name))
        except Exception as e:
            print(f"  [warn] {exp.meta.slug} scenarios skipped: {e}")

    top = max(inp.scales_ton)
    cov = rep.coverage
    return {
        "slug": exp.meta.slug,
        "name": exp.meta.name,
        "product": inp.msp_product,
        "msp": result.msp[top],
        "reported_msp": exp.reported_msp,
        "capex_m": result.capex_total[top] / 1e6,
        "top_ton": top,
        "schema_version": rep.schema_version,
        "ref_cov": (f"{cov.get('priced_with_ref',0)}/{cov.get('priced_total',0)}"
                    if cov.get('priced_total') else "0/0"),
        "pfd": "✓" if cov.get("pfd") else "—",
        "n_warn": len(rep.warnings),
        "errors": rep.errors,
        "html": out_html.name,
        "extra_links": extra_links,
    }


INDEX_TMPL = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>TEA Process Dossiers</title>
<style>
 :root{{--bg:#fafafa;--fg:#141414;--muted:#666;--accent:#1565C0;--card:#fff;--border:#e3e3e3;--ok:#2e7d32;--warn:#e65100;}}
 @media(prefers-color-scheme:dark){{:root{{--bg:#161616;--fg:#ececec;--muted:#9a9a9a;--accent:#64B5F6;--card:#212121;--border:#333;--ok:#81c784;--warn:#ffb74d;}}}}
 body{{background:var(--bg);color:var(--fg);margin:0;font:15px/1.55 -apple-system,"Segoe UI",Roboto,Helvetica,Arial;}}
 .wrap{{max-width:1200px;margin:0 auto;padding:32px 24px 64px;}}
 h1{{margin:0 0 4px;font-size:26px;}}
 .sub{{color:var(--muted);margin:0 0 24px;}}
 .card{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:8px 0;overflow:hidden;}}
 table{{width:100%;border-collapse:collapse;}}
 th,td{{text-align:left;padding:11px 14px;border-bottom:1px solid var(--border);}}
 th{{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);cursor:pointer;user-select:none;}}
 td.num{{text-align:right;font-variant-numeric:tabular-nums;}}
 tr:last-child td{{border-bottom:none;}}
 tbody tr:hover{{background:rgba(125,125,125,.07);}}
 a.paper{{color:var(--accent);text-decoration:none;font-weight:600;}}
 a.paper:hover{{text-decoration:underline;}}
 .badge{{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;font-weight:600;}}
 .v2{{background:rgba(46,125,50,.15);color:var(--ok);}}
 .v1{{background:rgba(230,81,0,.13);color:var(--warn);}}
 .pill{{font-size:12px;color:var(--muted);}}
 .summary{{display:flex;gap:24px;flex-wrap:wrap;margin:0 0 22px;}}
 .stat{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px 20px;}}
 .stat b{{display:block;font-size:24px;}}
 .stat span{{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em;}}
 footer{{color:var(--muted);font-size:12px;margin-top:28px;}}
 .err{{color:#c62828;font-size:12px;}}
</style></head><body><div class="wrap">
<h1>📊 TEA Process Dossiers</h1>
<p class="sub">Techno-economic analysis for {n} processes · generated {ts}. Click a paper to open its full dossier (PFD, stream table, CAPEX/OPEX, MSP, sensitivity, references) — one self-contained file, no internet needed except first chart load.</p>
<div class="summary">
  <div class="stat"><b>{n}</b><span>processes</span></div>
  <div class="stat"><b>{n_v2}</b><span>schema v2 (sourced)</span></div>
  <div class="stat"><b>{n_profit}</b><span>profitable @ market</span></div>
  <div class="stat"><b>{n_fail}</b><span>render failures</span></div>
</div>
<div class="card"><table id="t">
<thead><tr>
 <th onclick="sortT(0,'s')">Process</th>
 <th onclick="sortT(1,'s')">Product</th>
 <th class="num" onclick="sortT(2,'n')">MSP $/kg</th>
 <th class="num" onclick="sortT(3,'n')">Paper $/kg</th>
 <th class="num" onclick="sortT(4,'n')">CAPEX $M</th>
 <th onclick="sortT(5,'s')">Schema</th>
 <th onclick="sortT(6,'s')">Refs</th>
 <th onclick="sortT(7,'s')">PFD</th>
</tr></thead><tbody>
{rows}
</tbody></table></div>
<footer>tea_tool · open each dossier offline · re-generate with <code>python generate_dossiers.py</code></footer>
</div>
<script>
function sortT(col,typ){{
 var t=document.getElementById('t'),tb=t.tBodies[0],rows=[].slice.call(tb.rows);
 var dir=t.getAttribute('data-c')==col&&t.getAttribute('data-d')=='1'?-1:1;
 rows.sort(function(a,b){{
  var x=a.cells[col].getAttribute('data-v')||a.cells[col].innerText;
  var y=b.cells[col].getAttribute('data-v')||b.cells[col].innerText;
  if(typ=='n'){{x=parseFloat(x);y=parseFloat(y);if(isNaN(x))x=1e18;if(isNaN(y))y=1e18;return (x-y)*dir;}}
  return x.localeCompare(y)*dir;
 }});
 rows.forEach(function(r){{tb.appendChild(r);}});
 t.setAttribute('data-c',col);t.setAttribute('data-d',dir==1?'1':'0');
}}
</script>
</body></html>
"""


def _row(s):
    msp = s["msp"]
    msp_s = f"{msp:.2f}" if msp == msp else "n/a"   # NaN check
    pap = f"{s['reported_msp']:.2f}" if s["reported_msp"] is not None else "—"
    badge = (f"<span class='badge v2'>v2</span>" if s["schema_version"] >= 2
             else "<span class='badge v1'>v1</span>")
    extra_links = ""
    for label, fn in s.get("extra_links", []):
        extra_links += (f" <a class='pill' href='{escape(fn)}' "
                        f"style='color:var(--accent)'>· {escape(label)}</a>")
    return (
        f"<tr>"
        f"<td data-v=\"{escape(s['slug'])}\"><a class='paper' href='{escape(s['html'])}'>{escape(s['name'])}</a>{extra_links}</td>"
        f"<td>{escape(str(s['product']))}</td>"
        f"<td class='num' data-v='{msp if msp==msp else 1e18}'>{msp_s}</td>"
        f"<td class='num'>{pap}</td>"
        f"<td class='num' data-v='{s['capex_m']:.4f}'>{s['capex_m']:.1f}</td>"
        f"<td>{badge}</td>"
        f"<td class='pill'>{escape(s['ref_cov'])}</td>"
        f"<td>{s['pfd']}</td>"
        f"</tr>"
    )


def _err_row(slug, msg):
    return (f"<tr><td>{escape(slug)}</td><td colspan='7' class='err'>"
            f"render failed: {escape(msg)}</td></tr>")


def _copy_vendor():
    """Copy vendored JS (mermaid, chart.js) into dossier/vendor/ so the HTML
    works offline. The dossiers reference `vendor/*.js` by relative path."""
    import shutil
    src = HERE / "vendor"
    dst = OUT / "vendor"
    if not src.is_dir():
        print("  [warn] vendor/ not found — dossiers will rely on CDN fallback.")
        return
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.glob("*.js"):
        shutil.copy2(f, dst / f.name)


def main():
    OUT.mkdir(exist_ok=True)
    _copy_vendor()
    # Skip `_`-prefixed files (templates / scaffolds, not real papers).
    ymls = sorted(p for p in EXPS.glob("*.yaml") if not p.name.startswith("_"))
    rows, summaries, failures = [], [], []
    print(f"Generating dossiers for {len(ymls)} papers → {OUT}/\n")
    for yml in ymls:
        try:
            s = build_one(yml)
            summaries.append(s)
            rows.append(_row(s))
            flag = "OK " if not s["errors"] else "ERRv2"
            msp = s["msp"]
            print(f"  [{flag}] {s['slug']:<34s} MSP={msp:>8.2f}  "
                  f"v{s['schema_version']} refs {s['ref_cov']} PFD {s['pfd']}")
        except Exception as e:
            failures.append((yml.stem, str(e)))
            rows.append(_err_row(yml.stem, str(e)))
            print(f"  [FAIL] {yml.stem}: {e}")
            traceback.print_exc()

    n = len(ymls)
    n_v2 = sum(1 for s in summaries if s["schema_version"] >= 2)
    n_profit = sum(1 for s in summaries
                   if s["reported_msp"] and s["msp"] == s["msp"]
                   and s["msp"] <= s["reported_msp"] * 1.5)
    idx = INDEX_TMPL.format(
        n=n, n_v2=n_v2, n_profit=n_profit, n_fail=len(failures),
        ts=datetime.now().strftime("%Y-%m-%d %H:%M"),
        rows="\n".join(rows),
    )
    (OUT / "index.html").write_text(idx, encoding="utf-8")
    print(f"\nWrote {OUT/'index.html'}  ({n - len(failures)}/{n} ok, "
          f"{len(failures)} failed)")
    if failures:
        print("FAILURES:")
        for slug, msg in failures:
            print(f"  - {slug}: {msg}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
