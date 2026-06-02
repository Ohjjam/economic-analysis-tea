"""Quick validation: build PET process, run TEA, print numbers next to reference."""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(__file__))

from processes import build_pet, REGISTRY
from tea_engine import (run_tea, export_tea_xlsx, material_timeline,
                        cashflow_timeline, stream_events, equipment_events)

process, db, inp = build_pet()
result = run_tea(process, db, inp)

print("=" * 70)
print("PET TEA — Validation (vs. reference 260402 TEA summary.xlsx)")
print("=" * 70)
print(f"CRF                : {inp.crf:.6f}   (ref 0.106079)")
print(f"Batches/year       : {inp.batches_per_year:.1f}     (ref 3504)")
print()
print("CAPEX section costs at 1 ton (ref → calc):")
ref_1t = {
    "Feedstock Pretreatment": 6_879_879.53,
    "PET Depolymerization":   6_661_239.98,
    "TPA Filtration & Crystallization": 6_864_230.53,
    "Electrolysis":           6_342_372.46,
    "OSBL (25% of ISBL)":     6_686_930.63,
}
for k, v in ref_1t.items():
    calc = result.capex_section[1.0].get(k, 0.0)
    pct = 100 * (calc - v) / v if v else 0
    print(f"  {k:<40s} ref={v:>14,.0f}   calc={calc:>14,.0f}   Δ={pct:+5.2f}%")

print()
print("CAPEX totals (ref → calc):")
ref_tot = {1.0: 33_434_653, 5.0: 87_817_046, 10.0: 133_105_752}
for sc, v in ref_tot.items():
    print(f"  {sc:>4} ton  ref={v:>14,.0f}   calc={result.capex_total[sc]:>14,.0f}")

print()
print("Annualized CAPEX  (ref → calc):")
ref_ann = {1.0: 3_755_855.81, 5.0: 10_361_230.95, 10.0: 16_211_087.50}
for sc, v in ref_ann.items():
    print(f"  {sc:>4} ton  ref={v:>14,.0f}   calc={result.capex_annualized[sc]:>14,.0f}")

print()
print("OPEX totals (ref → calc):")
ref_opex = {1.0: 3_510_410, 5.0: 17_552_051, 10.0: 33_352_103}
for sc, v in ref_opex.items():
    print(f"  {sc:>4} ton  ref={v:>14,.0f}   calc={result.opex_total[sc]:>14,.0f}")

print()
print("Revenue (ref → calc):")
ref_rev = {1.0: 5_529_580, 5.0: 27_647_899, 10.0: 55_295_797}
for sc, v in ref_rev.items():
    print(f"  {sc:>4} ton  ref={v:>14,.0f}   calc={result.revenue_total[sc]:>14,.0f}")

print()
print("MSP TPA ($/kg) (ref → calc):")
ref_msp = {1.0: 1.5137, 5.0: 0.9575, 10.0: 0.7506}
for sc, v in ref_msp.items():
    print(f"  {sc:>4} ton  ref={v:>7.4f}   calc={result.msp[sc]:>7.4f}")

# Export xlsx
out_path = os.path.join(os.path.dirname(__file__), "output", "PET_TEA_generated.xlsx")
sens = {
    "DMSO Recovery (%)": {"param": "DMSO.recovery",
                          "values": [0.99999, 0.9999, 0.999, 0.99]},
    "H2 Price ($/kg)":   {"param": "H2.price",
                          "values": [8, 6, 4, 2]},
}
export_tea_xlsx(out_path, process, db, inp, result, sensitivity_specs=sens)
print(f"\nWrote: {out_path}")


# ============================================================================
# Time-profile pipeline regression
# ============================================================================
print()
print("=" * 70)
print("Time-profile pipeline (every registered process)")
print("=" * 70)
for name, builder in REGISTRY.items():
    p, db_, inp_ = builder()
    if not p.streams.inputs or not p.streams.outputs:
        print(f"  [skip] {name}: empty process")
        continue
    try:
        r = run_tea(p, db_, inp_)
        scale = max(inp_.scales_ton)
        mt = material_timeline(p, db_, scale, inp_)
        cf = cashflow_timeline(p, db_, scale, inp_, r.opex[scale],
                               r.revenue[scale], r.capex_total[scale])
        ev1 = stream_events(p, db_, scale, inp_)
        ev2 = equipment_events(p, scale, inp_)
        print(f"  [OK] {name[:60]:<60s}  "
              f"rows={len(mt):4d}  events(stream)={len(ev1):2d}  "
              f"events(eq)={len(ev2):2d}  "
              f"MSP@{scale:g}t=${r.msp[scale]:.4f}/kg")
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        raise


# ============================================================================
# Experiment-YAML pipeline regression (auto-builder)
# ============================================================================
from pathlib import Path
from tea_engine import (
    load_experiment, build_process_from_experiment,
    build_scaleup_report, render_design_note,
)
print()
print("=" * 70)
print("Experiment-YAML pipeline (every file in experiments/)")
print("=" * 70)
EXPS = Path(os.path.dirname(__file__)) / "experiments"
for yml in sorted(p for p in EXPS.glob("*.yaml") if not p.name.startswith("_")):
    try:
        exp = load_experiment(yml)
        p, db_, inp_ = build_process_from_experiment(exp)
        r = run_tea(p, db_, inp_)
        scale = max(inp_.scales_ton)
        rep = build_scaleup_report(
            p, db_, inp_,
            reaction_type=exp.reaction_type,
            hazardous_materials=exp.constraints.get("hazardous_materials", []),
            has_downstream=bool(exp.downstream),
            recommendation_msp_threshold=None,
        )
        assert len(rep.stages) == 5, "scale-up must produce 5 stages"
        _ = render_design_note(exp)
        print(f"  [OK] {yml.stem:<38s}  "
              f"MSP@{scale:g}t = ${r.msp[scale]:>8.2f}/kg  "
              f"CAPEX = ${r.capex_total[scale]/1e6:.2f}M  "
              f"OPEX = ${r.opex_total[scale]/1e6:.2f}M/y")
    except Exception as e:
        print(f"  [FAIL] {yml.name}: {e}")
        raise


# ============================================================================
# Physics-sizing layer regression (MATLAB / Python mirror)
# ============================================================================
import math as _math
import tempfile as _tempfile
import json as _json
from processes.spent_lfp_ballmill_li import build as _lfp_build, _load_matlab_sizing
from tea_engine.physics.run_sizing import build_payload as _build_payload

print()
print("=" * 70)
print("Physics-sizing layer regression")
print("=" * 70)


def _check(name, cond):
    status = "OK" if cond else "FAIL"
    print(f"  [{status}] {name}")
    if not cond:
        raise AssertionError(f"physics regression failed: {name}")


# 1) Legacy fallback (no JSON) must reproduce the original flat-default MSPs.
_legacy_expected = {0.1: 15.4653, 1.0: 13.0074, 5.0: 12.2356}
_p, _db, _inp = _lfp_build(matlab_sizing=False)
_r = run_tea(_p, _db, _inp)
for _t, _exp in _legacy_expected.items():
    _check(f"legacy MSP@{_t}t == {_exp:.4f} (got {_r.msp[_t]:.4f})",
           abs(_r.msp[_t] - _exp) < 0.01)
_check("legacy build has 11 sections (no evaporator)", len(_p.sections) == 11)
_check("legacy build adds no __matlab_sizing provenance",
       "__matlab_sizing" not in _p.meta)
_check("legacy build adds no utility $/ton/y meta keys",
       not [k for k in _p.meta if k.endswith("_$_per_ton_per_y")])

# 2) Precedence: explicit kwarg > JSON > LAB_DEFAULTS.
_p_phys, _, _ = _lfp_build()  # JSON present -> physics kWh/t
_kwh_phys = _p_phys.meta["Ball-mill energy (kWh/t-feed)"]
_check(f"JSON drives kWh/t (~114.9, got {_kwh_phys:.1f})",
       110 < _kwh_phys < 120)
_p_kw, _, _ = _lfp_build(ball_mill_energy_kwh_per_t=42.0)
_check("explicit kwarg overrides JSON (42.0)",
       abs(_p_kw.meta["Ball-mill energy (kWh/t-feed)"] - 42.0) < 1e-9)
_p_off, _, _ = _lfp_build(matlab_sizing=False, ball_mill_energy_kwh_per_t=42.0)
_check("kwarg wins with JSON disabled too (42.0)",
       abs(_p_off.meta["Ball-mill energy (kWh/t-feed)"] - 42.0) < 1e-9)
_check("JSON-disabled default falls back to 150 kWh/t",
       abs(_lfp_build(matlab_sizing=False)[0].meta["Ball-mill energy (kWh/t-feed)"] - 150.0) < 1e-9)

# 3) Leach V_ref self-consistency: cost at reference recovery == $340k quote.
_pl = _build_payload(target_recovery=0.90)["leach_tank"]
_check(f"leach base_cost==$340k at 90% recovery (got ${_pl['base_cost_usd']:,.0f})",
       abs(_pl["base_cost_usd"] - 340000) < 1.0)
_pl98 = _build_payload(target_recovery=0.98)["leach_tank"]
_check(f"leach cost rises at 98% recovery (got ${_pl98['base_cost_usd']:,.0f})",
       _pl98["base_cost_usd"] > _pl["base_cost_usd"] * 1.1)

# 4) Ball-mill CAPEX calibrated to ~$2.1M at reference duty.
_pb = _build_payload()["ball_mill"]
_check(f"ball-mill CAPEX ~$2.1M at ref (got ${_pb['base_cost_usd']:,.0f})",
       2.0e6 < _pb["base_cost_usd"] < 2.2e6)
_check("ball-mill geometry flagged readout-only",
       _pb.get("geometry_is_readout_only") is True)

# 5) mechanochem_intensity_factor must NOT change economics (readout only).
_p_a = _build_payload(ball_mill_overrides={"mechanochem_intensity_factor": 30.0})["ball_mill"]
_p_b = _build_payload(ball_mill_overrides={"mechanochem_intensity_factor": 80.0})["ball_mill"]
_check("intensity_factor changes geometry readout (D differs)",
       abs(_p_a["mill_diameter_m"] - _p_b["mill_diameter_m"]) > 1e-3)
_check("intensity_factor does NOT change kWh/t (economic)",
       abs(_p_a["kWh_per_t_feed"] - _p_b["kWh_per_t_feed"]) < 1e-9)
_check("intensity_factor does NOT change ball-mill CAPEX",
       abs(_p_a["base_cost_usd"] - _p_b["base_cost_usd"]) < 1e-6)

# 6) Drivetrain scale effect: kWh/t decreases with scale (mild, monotone).
_bs = _pb["kWh_per_t_feed_by_scale"]
_vals = [row["kWh_per_t"] for row in sorted(_bs, key=lambda r: r["scale_ton"])]
_check(f"kWh/t decreases with scale {[round(v) for v in _vals]}",
       _vals[0] > _vals[-1] and all(_vals[i] >= _vals[i+1] for i in range(len(_vals)-1)))

# 7) Evaporator effects trade-off: CAPEX up, steam OPEX down with effects.
_e1 = _build_payload(evaporator_overrides={"effects": 1})["evaporator"]
_e3 = _build_payload(evaporator_overrides={"effects": 3})["evaporator"]
_check("triple-effect cuts steam OPEX vs single",
       _e3["lps_steam_usd_per_t_feed_per_y"] < _e1["lps_steam_usd_per_t_feed_per_y"])
_check("triple-effect raises evaporator CAPEX vs single",
       _e3["base_cost_usd"] > _e1["base_cost_usd"])
_check("evaporator OPEX paired with CAPEX (both > 0)",
       _e1["base_cost_usd"] > 0 and _e1["lps_steam_usd_per_t_feed_per_y"] > 0)

# 8) Physics-mode flowsheet gains the evaporator node (CAPEX for the OPEX).
_check("physics build has 12 sections (evaporator spliced in)",
       len(_p_phys.sections) == 12)
_check("physics build has an Evaporator / Concentrator section",
       any(s.label == "Evaporator / Concentrator" for s in _p_phys.sections))
_lps_keys = [k for k in _p_phys.meta if k.endswith("_$_per_ton_per_y")]
_check(f"physics build exposes utility $/ton/y meta keys {_lps_keys}",
       len(_lps_keys) >= 1)

# 9) Schema validation rejects malformed JSON (so it can't corrupt economics).
try:
    import jsonschema as _js  # noqa: F401
    _bad = _tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                        encoding="utf-8")
    _json.dump({"schema_version": "1.0", "process": "spent_lfp_ballmill_li",
                "ball_mill": {}, "leach_tank": {}, "evaporator": {}}, _bad)
    _bad.close()
    _check("malformed JSON (missing required fields) is rejected -> None",
           _load_matlab_sizing(Path(_bad.name)) is None)
    os.unlink(_bad.name)
except ImportError:
    print("  [skip] jsonschema not installed — schema-rejection test skipped")

print()
print("All physics-sizing (LFP) regression checks passed.")


# ============================================================================
# PET physics-sizing layer regression (electrolyzer + reactor heat)
# ============================================================================
from processes import build_pet as _pkg_build_pet   # YAML prices + physics (JSON)
from processes.pet_depolymerization import build as _pet_build, _load_pet_sizing
from tea_engine.physics.run_sizing_pet import build_payload as _pet_payload

print()
print("=" * 70)
print("PET physics-sizing layer regression (Faraday electrolyzer + heat)")
print("=" * 70)

# 1) Physics layer DERIVES the paper's electrolyzer/heat numbers (<0.1%).
_pp = _pet_payload(design_point_ton=1.0)
_ez, _rh = _pp["electrolyzer"], _pp["reactor_heat"]
_check(f"electrolyzer area ~595.8 m^2 (got {_ez['required_area_m2']:.1f})",
       abs(_ez["required_area_m2"] - 595.84) < 1.0)
_check(f"electrolyzer CAPEX ~$5.96M (got ${_ez['base_cost_usd']:,.0f})",
       abs(_ez["base_cost_usd"] - 5_958_372) / 5_958_372 < 0.001)
_check(f"specific energy ~31.9 kWh/kg (got {_ez['specific_energy_kWh_per_kg_H2']:.2f})",
       abs(_ez["specific_energy_kWh_per_kg_H2"] - 31.9) < 0.1)
_check(f"electricity OPEX ~$566,947 (got ${_ez['electricity_usd_per_t_feed_per_y']:,.0f})",
       abs(_ez["electricity_usd_per_t_feed_per_y"] - 566_946.57) / 566_946.57 < 0.001)
_check(f"reactor net heat ~16.15 GJ/batch (got {_rh['Q_net_GJ_per_batch']:.2f})",
       abs(_rh["Q_net_GJ_per_batch"] - 16.153) < 0.05)
_check(f"heat OPEX ~$269,982 (got ${_rh['heat_usd_per_t_feed_per_y']:,.0f})",
       abs(_rh["heat_usd_per_t_feed_per_y"] - 269_982.09) / 269_982.09 < 0.001)

# 2) Package build_pet (YAML prices + physics via JSON) reproduces paper MSP.
_pp_on, _db_on, _inp_on = _pkg_build_pet()
_r_on = run_tea(_pp_on, _db_on, _inp_on)
_check(f"PET physics MSP@1t ~1.5137 (got {_r_on.msp[1.0]:.4f})",
       abs(_r_on.msp[1.0] - 1.5137) < 0.002)
_check("PET physics build carries provenance",
       "__matlab_sizing_pet" in _pp_on.meta)

# 3) Physics-vs-hard-coded equivalence at the raw-module level (same prices on
#    both sides, so this isolates the physics override). MSPs must agree <0.1%.
_pp_phys, _dbp, _inpp = _pet_build()                  # physics on (JSON)
_pp_hard, _dbh, _inph = _pet_build(matlab_sizing=False)  # hard-coded
_r_phys = run_tea(_pp_phys, _dbp, _inpp)
_r_hard = run_tea(_pp_hard, _dbh, _inph)
_check(f"PET physics≈hard-coded MSP@1t within 0.1% "
       f"({_r_phys.msp[1.0]:.4f} vs {_r_hard.msp[1.0]:.4f})",
       abs(_r_phys.msp[1.0] - _r_hard.msp[1.0]) / _r_hard.msp[1.0] < 0.001)
_check("PET physics-off build carries NO provenance",
       "__matlab_sizing_pet" not in _pp_hard.meta)

# 4) Faraday scaling sanity: double current density halves area.
_pp_j = _pet_payload(design_point_ton=1.0,
                     electrolyzer_overrides={"current_density_mA_cm2": 250.0})
_check("doubling current density halves electrolyzer area",
       abs(_pp_j["electrolyzer"]["required_area_m2"]
           - _ez["required_area_m2"] / 2) < 1.0)

print()
print("All PET physics-sizing regression checks passed.")


# ============================================================================
# Schema v2 validation regression (references + PFD)
# ============================================================================
import yaml as _yaml
from tea_engine import validate_experiment as _validate

print()
print("=" * 70)
print("Schema validation (v1 lenient, v2 strict) — completeness report")
print("=" * 70)
_EXPS = Path(os.path.dirname(__file__)) / "experiments"
_any_block = False
for _yml in sorted(p for p in _EXPS.glob("*.yaml") if not p.name.startswith("_")):
    _raw = _yaml.safe_load(_yml.read_text(encoding="utf-8")) or {}
    _rep = _validate(_raw)
    cov = _rep.coverage
    flag = "OK " if _rep.ok else "ERR"
    print(f"  [{flag}] {_yml.stem:<34s} v{_rep.schema_version}  "
          f"refs {cov.get('priced_with_ref',0)}/{cov.get('priced_total',0)}  "
          f"PFD {'Y' if cov.get('pfd') else '-'}  "
          f"({len(_rep.errors)} err, {len(_rep.warnings)} warn)")
    if _rep.errors:
        _any_block = True
        for _e in _rep.errors:
            print(f"        ERROR: {_e}")

# The v2 exemplar must validate clean and fully.
_pet_raw = _yaml.safe_load((_EXPS / "paper_oh_2026_pet_pma.yaml").read_text(encoding="utf-8"))
_pet_rep = _validate(_pet_raw)
_check("v2 exemplar (PET) has schema_version 2", _pet_rep.schema_version == 2)
_check("v2 exemplar validates with zero errors", _pet_rep.ok)
_check(f"v2 exemplar: all prices sourced "
       f"({_pet_rep.coverage['priced_with_ref']}/{_pet_rep.coverage['priced_total']})",
       _pet_rep.coverage["priced_with_ref"] == _pet_rep.coverage["priced_total"]
       and _pet_rep.coverage["priced_total"] > 0)
_check("v2 exemplar: PFD present with units + streams",
       _pet_rep.coverage["pfd"] and _pet_rep.coverage["pfd_units"] >= 2
       and _pet_rep.coverage["pfd_streams"] >= 2)
_check("no experiment file has BLOCKING validation errors", not _any_block)

print()
print("All schema-validation regression checks passed.")


# ============================================================================
# HTML dossier regression (the user-facing UI)
# ============================================================================
import tempfile as _tf
import re as _re
from tea_engine import render_html_viewer as _render, build_scaleup_report as _scaleup
from tea_engine.viewer import auto_pfd_mermaid as _pfd

print()
print("=" * 70)
print("HTML dossier rendering (user-facing UI)")
print("=" * 70)

_exp = load_experiment(_EXPS / "paper_oh_2026_pet_pma.yaml")
_pp, _db2, _inp2 = build_process_from_experiment(_exp)
_pp._component_db_ref = _db2
_res = run_tea(_pp, _db2, _inp2)
_su = _scaleup(_pp, _db2, _inp2, reaction_type=_exp.reaction_type,
               has_downstream=bool(_exp.downstream),
               reported_msp_usd_per_kg=_exp.reported_msp)
_tmp = Path(_tf.gettempdir()) / "tea_dossier_test.html"
_render(_exp, _pp, _res, _su, _pfd(_pp), _tmp)
_doc = _tmp.read_text(encoding="utf-8")

_check("dossier file written and non-trivial", len(_doc) > 5000)
for _section in ["Assumptions &amp; References", "Equipment", "class=\"mermaid\"",
                 "Scale-up", "MSP"]:
    _check(f"dossier contains section: {_section[:32]}", _section in _doc)
# no unfilled {placeholder} tokens leaked into the output
_leftover = _re.findall(r"\{[a-z_]{3,}\}", _doc)
_check(f"dossier has no unfilled placeholders ({_leftover[:3]})", not _leftover)
# v2 references actually rendered (citation + doi link)
_check("dossier shows the paper's references (Green Chem + doi)",
       "Green Chem" in _doc and "doi.org" in _doc)
# PFD distinguishes initial charge vs makeup (engineering correctness)
_check("dossier PFD shows initial-vs-makeup streams",
       "initial charge" in _doc and "makeup" in _doc)
_tmp.unlink(missing_ok=True)

print()
print("All HTML dossier regression checks passed.")
