"""Generic product-strategy scenario engine (config-driven).

Any v2 experiment can declare a `scenarios:` block; the dossier generator then
auto-builds a cumulative-recovery comparison + a per-co-product marginal table
("is it worth recovering?") + feasibility notes — exactly like the PET case,
but for ANY paper, with no bespoke code.

YAML `scenarios:` block (all keys optional except primary_product + variable_coproducts):

    scenarios:
      basis_scale_ton: 10.0           # which scale to evaluate (default: largest)
      primary_product: "TPA"          # the product whose MSP is reported
      base_coproducts: ["H2"]         # always sold, part of the base case
      base_opex_excludes_usd_per_ton: 1225309.96   # OPEX baked into the builder
                                                    # that belongs to a variable
                                                    # co-product (removed from base)
      variable_coproducts:            # toggled on, cumulatively
        - key: "EG"
          name: "Ethylene glycol"
          kg_per_kg_feed: 0.20
          amount_basis: "[stoich/est] ..."         # provenance of the amount
          price_usd_kg: 0.60
          price_ref: "echemi"                       # references[].id (optional)
          sep_capex_usd_per_kg: 0.0884              # one-time per annual kg
          sep_opex_usd_per_kg: 0.8633               # annual
          sep_difficulty: 1.3                        # multiplier on separation cost
          sep_ref: "iecr2021"
          feasibility: "Feasible but energy-heavy: EG bp 197 C ..."

Economic model (marginal): recovering co-product i adds
    revenue_i  −  (annualised sep CAPEX_i + sep OPEX_i)
If that is negative, recovering it destroys value. No bonus-product credits are
assumed for un-recovered material.
"""
from __future__ import annotations
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional

from .tea import run_tea


def compute_scenarios(process, db, inp, cfg: Dict[str, Any],
                      result=None) -> Optional[Dict[str, Any]]:
    """Compute base, cumulative scenarios, and per-co-product marginal economics."""
    cps = cfg.get("variable_coproducts") or []
    primary = cfg.get("primary_product")
    if not cps or not primary:
        return None
    if result is None:
        result = run_tea(process, db, inp)
    scale = float(cfg.get("basis_scale_ton") or max(inp.scales_ton))
    if scale not in result.opex_total:
        scale = max(inp.scales_ton)

    feed = process.streams.inputs[0].component if process.streams.inputs else None
    feed_kg_y = result.flows_annual_kg[scale].get(feed, 0.0) if feed else 0.0
    primary_kg_y = result.flows_annual_kg[scale].get(primary, 0.0)
    capex_ann = result.capex_annualized[scale]
    base_excl = float(cfg.get("base_opex_excludes_usd_per_ton", 0.0)) * scale
    opex_base = result.opex_total[scale] - base_excl
    primary_rev = result.revenue[scale].get(primary, 0.0)
    base_cop_rev = sum(result.revenue[scale].get(p, 0.0)
                       for p in (cfg.get("base_coproducts") or []))
    crf = inp.crf

    # per-co-product marginal economics
    marg = []
    cp_calc = {}
    for cp in cps:
        amt = float(cp.get("kg_per_kg_feed", 0.0)) * feed_kg_y
        rev = amt * float(cp.get("price_usd_kg", 0.0))
        diff = float(cp.get("sep_difficulty", 1.0))
        sep_capex = amt * float(cp.get("sep_capex_usd_per_kg", 0.0)) * diff * crf
        sep_opex = amt * float(cp.get("sep_opex_usd_per_kg", 0.0)) * diff
        cp_calc[cp["key"]] = {"rev": rev, "sep_capex": sep_capex, "sep_opex": sep_opex}
        marg.append({
            "key": cp["key"], "name": cp.get("name", cp["key"]),
            "amount_t_y": amt / 1e3, "price": float(cp.get("price_usd_kg", 0.0)),
            "price_ref": cp.get("price_ref"), "sep_ref": cp.get("sep_ref"),
            "revenue": rev, "sep_cost": sep_capex + sep_opex,
            "gain": rev - sep_capex - sep_opex,
            "amount_basis": cp.get("amount_basis", ""),
            "feasibility": cp.get("feasibility", ""),
        })

    # cumulative scenarios
    order = [cp["key"] for cp in cps]
    rows = []
    for k in range(len(order) + 1):
        recovered = order[:k]
        add_rev = sum(cp_calc[x]["rev"] for x in recovered)
        add_capex = sum(cp_calc[x]["sep_capex"] for x in recovered)
        add_opex = sum(cp_calc[x]["sep_opex"] for x in recovered)
        revenue = primary_rev + base_cop_rev + add_rev
        opex = opex_base + add_opex
        capex = capex_ann + add_capex
        net = revenue - (capex + opex)
        credit = base_cop_rev + add_rev
        msp = (capex + opex - credit) / primary_kg_y if primary_kg_y else float("nan")
        label = primary + ("" if not recovered else " + " + " + ".join(recovered))
        rows.append({"label": label, "recovered": recovered, "revenue": revenue,
                     "capex_ann": capex, "opex": opex, "net": net, "msp": msp})

    return {"scale": scale, "primary": primary, "rows": rows, "marginal": marg}


def render_scenarios_html(exp, data: Dict[str, Any], out_path) -> Path:
    """Render the scenario comparison as a self-contained HTML page."""
    refs = getattr(exp, "references", []) or []
    num = {r.id: i + 1 for i, r in enumerate(refs)}

    def mk(rid):
        n = num.get(rid)
        return f" <sup style='color:#1565C0'>[{n}]</sup>" if n else ""

    rows = data["rows"]
    marg = data["marginal"]
    primary = data["primary"]
    best = max(rows, key=lambda x: x["net"]) if rows else None
    money = lambda x: f"${x/1e6:,.2f} M"

    scen_rows = "".join(
        f"<tr class='{'winner' if best and rw['label']==best['label'] else ''}'>"
        f"<td><b>{escape(rw['label'])}</b></td>"
        f"<td class='num'>{money(rw['revenue'])}</td>"
        f"<td class='num'>{money(rw['capex_ann'])}</td>"
        f"<td class='num'>{money(rw['opex'])}</td>"
        f"<td class='num'><b>{money(rw['net'])}</b></td>"
        f"<td class='num'>${rw['msp']:.2f}/kg</td></tr>"
        for rw in rows)
    marg_rows = "".join(
        f"<tr><td>{escape(m['name'])}</td>"
        f"<td class='num'>{m['amount_t_y']:,.0f} t/y</td>"
        f"<td class='num'>${m['price']:g}{mk(m['price_ref'])}</td>"
        f"<td class='num'>${m['revenue']/1e6:,.2f} M</td>"
        f"<td class='num'>${m['sep_cost']/1e6:,.2f} M{mk(m['sep_ref'])}</td>"
        f"<td class='num' style='color:{'#2e7d32' if m['gain']>0 else '#c62828'}'>"
        f"<b>${m['gain']/1e6:+,.2f} M</b></td>"
        f"<td class='small'>{escape(m['feasibility'])}</td></tr>"
        for m in marg)
    amt_notes = "".join(f"<li><b>{escape(m['name'])}</b>: {escape(m['amount_basis'])}</li>"
                        for m in marg if m["amount_basis"])
    ref_list = "".join(
        f"<li>[{num[r.id]}] {escape(r.citation)}"
        + (f" · <a href='https://doi.org/{escape(r.doi)}' target='_blank'>doi</a>" if r.doi
           else (f" · <a href='{escape(r.url)}' target='_blank'>link</a>" if r.url else ""))
        + "</li>"
        for r in refs)

    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Product-strategy scenarios — {escape(exp.meta.name)}</title>
<style>
 :root{{--bg:#fafafa;--fg:#141414;--muted:#666;--accent:#1565C0;--card:#fff;--border:#e3e3e3;}}
 @media(prefers-color-scheme:dark){{:root{{--bg:#161616;--fg:#ececec;--muted:#9a9a9a;--accent:#64B5F6;--card:#212121;--border:#333;}}}}
 body{{background:var(--bg);color:var(--fg);margin:0;font:15px/1.55 -apple-system,"Segoe UI",Roboto,Arial;}}
 .wrap{{max-width:1100px;margin:0 auto;padding:30px 22px 60px;}}
 h1{{margin:0 0 4px;font-size:23px;}} .sub{{color:var(--muted);margin:0 0 22px;}}
 a.back{{color:var(--accent);text-decoration:none;}}
 .card{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px 20px;margin-bottom:18px;}}
 h2{{font-size:16px;color:var(--accent);border-bottom:1px solid var(--border);padding-bottom:6px;margin-top:0;}}
 table{{width:100%;border-collapse:collapse;}} th,td{{text-align:left;padding:9px 11px;border-bottom:1px solid var(--border);}}
 th{{font-size:12px;text-transform:uppercase;letter-spacing:.03em;color:var(--muted);}}
 td.num,th.num{{text-align:right;font-variant-numeric:tabular-nums;}}
 tr.winner{{background:rgba(46,125,50,.12);}} .small{{font-size:12px;}} .muted{{color:var(--muted);}}
 .flag{{background:rgba(230,81,0,.12);border-left:3px solid #e65100;padding:10px 14px;border-radius:6px;margin-top:10px;}}
 ol,ul{{margin:6px 0;}}
</style></head><body><div class="wrap">
<p><a class="back" href="{escape(exp.meta.slug)}.html">← back to dossier</a></p>
<h1>Product-strategy scenarios</h1>
<p class="sub">{escape(exp.meta.name)} — recover &amp; sell each co-product, or not?
Trade-off = extra product revenue vs. extra separation cost. Basis: {data['scale']:g} t feed/batch.</p>

<div class="card"><h2>Scenario comparison (cumulative recovery)</h2>
<table><tr><th>Scenario</th><th class="num">Revenue</th><th class="num">Ann. CAPEX</th>
<th class="num">OPEX</th><th class="num">Net profit</th><th class="num">MSP of {escape(primary)}</th></tr>
{scen_rows}</table>
<p class="small muted">Highlighted = highest net profit. MSP of {escape(primary)} credits all co-product revenue.</p></div>

<div class="card"><h2>Per-co-product marginal economics — "is it worth recovering?"</h2>
<table><tr><th>Co-product</th><th class="num">Amount</th><th class="num">Price</th>
<th class="num">Revenue</th><th class="num">Separation cost</th><th class="num">Net gain</th><th>Feasibility</th></tr>
{marg_rows}</table>
<p class="small muted">Net gain = revenue − (annualised separation CAPEX + OPEX). Green = worth recovering; red = costs more than the sale.</p></div>

<div class="card"><h2>References</h2><ol>{ref_list}</ol>
<div class="flag"><b>⚠ Amounts to confirm against the paper's measured stream table:</b>
<ul style="margin:6px 0 0">{amt_notes}</ul></div></div>
</div></body></html>
"""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out
