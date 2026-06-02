"""PET depolymerization with PMA + electrolytic H2 (replicates the reference xlsx).

Source: 260402 TEA summary.xlsx (0.1 g PET, 0.5 M PMA, 10 mL 1:1 H2SO4:DMSO, 2 h).

Equipment installed costs are taken at the 1-ton, CEPCI-2023 baseline (the
"V" column of the source workbook).  CAPEX scaling to 5/10 ton uses the 0.6
power rule, which exactly reproduces the source numbers.

Physics-based sizing (optional):
    When `data/matlab_sizing_pet.json` exists (from MATLAB's run_sizing_pet.m
    or the Python mirror `tea_engine.physics.run_sizing_pet`), build() reads it
    and DERIVES from first principles, instead of hard-coding:
      • Electrolyzer CAPEX        ← Faraday's law: H2 rate → current → area → $
      • Electricity OPEX          ← cell voltage → kWh/kg H2
      • Reactor heat (steam) OPEX ← enthalpy balance over the solution
    These reproduce the paper's own hand calculations (area 595.8 m², $5.96M,
    31.9 kWh/kg, 16.15 GJ/batch). Precedence: kwargs > JSON > hard-coded.
    Without the JSON file the numbers are byte-identical to the validated
    reference reproduction (smoke tests stay green).
"""
import json
from pathlib import Path
from typing import Any, Dict, Optional

from tea_engine.components import ComponentDB
from tea_engine.streams import Stream, StreamSet
from tea_engine.equipment import Equipment, EquipmentList
from tea_engine.process import Process, ProcessSection
from tea_engine.tea import TEAInputs


_PET_JSON_PATH = Path(__file__).resolve().parent.parent / "data" / "matlab_sizing_pet.json"
_PET_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "matlab" / "sizing_schema_pet.json"
_SCHEMA_SUPPORTED = {"1.0"}


def _validate_pet_schema(data: Dict[str, Any]) -> bool:
    """Best-effort JSON-Schema validation (soft-skip if jsonschema/schema absent)."""
    try:
        import jsonschema
    except ImportError:
        return True
    try:
        with open(_PET_SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema = json.load(f)
    except (OSError, json.JSONDecodeError):
        return True
    try:
        jsonschema.validate(instance=data, schema=schema)
        return True
    except jsonschema.ValidationError:
        return False


def _load_pet_sizing(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Read data/matlab_sizing_pet.json if present, valid, and for this process."""
    p = Path(path) if path else _PET_JSON_PATH
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("schema_version") not in _SCHEMA_SUPPORTED:
        return None
    if data.get("process") != "pet_depolymerization":
        return None
    if not _validate_pet_schema(data):
        return None
    return data


def build(matlab_sizing=True):
    """Build the PET process.

    matlab_sizing : True (auto-load data/matlab_sizing_pet.json if present),
                    False (force the hard-coded reference values), or a path.
    """
    if matlab_sizing is False:
        sizing = None
    elif matlab_sizing is True:
        sizing = _load_pet_sizing()
    else:
        sizing = _load_pet_sizing(Path(matlab_sizing))

    db = ComponentDB.default()

    # ---- Material streams (lab basis: 0.1 g PET / batch) ----
    ss = StreamSet()
    ss.add_input(Stream("PET",   0.1,        recovery=0.0))
    ss.add_input(Stream("PMA",   9.12625,    recovery=1.0))     # fully recycled
    ss.add_input(Stream("H2SO4", 0.4904,     recovery=1.0))     # fully recycled
    # NOTE: source xlsx tags DMSO recovery as 99.999 % but the OPEX numbers
    # are computed against 99.9 %.  We match the OPEX numbers, not the label.
    ss.add_input(Stream("DMSO",  5.5,        recovery=0.999))
    ss.add_input(Stream("H2O",   4.8096,     recovery=0.0))     # makeup
    ss.add_output(Stream("TPA",  0.0863876))
    ss.add_output(Stream("FA",   0.0405064))
    ss.add_output(Stream("H2",   0.00532224))

    # ---- Sections (PFD blocks) ----
    sections = [
        ProcessSection("feed",   "Feedstock Pretreatment",
                       "PET conveying, dust, storage, shredder, extruder, microgranulator",
                       kind="Pretreatment"),
        ProcessSection("depoly", "PET Depolymerization",
                       "PMA-catalysed reaction in DMSO/H2SO4 at 100 °C",
                       kind="Catalytic Reactor"),
        ProcessSection("filt",   "TPA Filtration & Crystallization",
                       "Filter, crystallizer, centrifuge, dryer",
                       kind="Crystallizer"),
        ProcessSection("elec",   "Electrolysis",
                       "Reduced PMA → re-oxidation produces H2",
                       kind="Electrochemical Cell"),
    ]

    edges = [
        ("in:PET", "feed", ""),
        ("feed",   "depoly", "shredded PET"),
        ("in:PMA", "depoly", ""),
        ("in:H2SO4", "depoly", ""),
        ("in:DMSO",  "depoly", ""),
        ("in:H2O",   "depoly", ""),
        ("depoly", "filt", "reaction mixture"),
        ("depoly", "elec", "reduced PMA"),
        ("filt", "out:TPA", ""),
        ("filt", "out:FA",  ""),
        ("elec", "out:H2",  ""),
        ("elec", "depoly",  "regen. PMA"),
    ]

    # ---- Equipment (installed cost in 2023 USD at 1 ton/batch baseline) ----
    eq = EquipmentList()
    BASE_YEAR = 2023
    CAP_REF = 1.0  # 1 ton PET / batch

    feed_items = [
        ("Conveyor transfer system",   3292110.07),
        ("Truck dumper package",       188213.38),
        ("Dust collection system",     47597.55),
        ("Feedstock storage dome",     595185.36),
        ("Shredder",                   175754.09),
        ("Extruder",                   2016685.26),
        ("Microgranulator",            564333.82),
    ]
    for name, base in feed_items:
        eq.add(Equipment(name, "Feedstock Pretreatment", base_cost=base,
                         installation_factor=1.0, cepci_ref=BASE_YEAR,
                         cap_ref=CAP_REF, scaling_factor=0.6))

    depoly_items = [
        ("Small particle conveyor",    403960.19),
        ("PMA storage and transfer",   285763.62),
        ("Water recirculation pump",   7266.03),
        ("Depolymerization reactor (×7)", 5689918.10),
        ("Storage tanks",              97624.64),
        ("Reactor effluent cooler",    42057.66),
        ("Caustic storage and transfer", 134649.75),
    ]
    for name, base in depoly_items:
        eq.add(Equipment(name, "PET Depolymerization", base_cost=base,
                         installation_factor=1.0, cepci_ref=BASE_YEAR,
                         cap_ref=CAP_REF, scaling_factor=0.6))

    filt_items = [
        ("Solids filter package",      1927537.17),
        ("rTPA crystallizer",          3530857.78),
        ("rTPA centrifuge",            723955.51),
        ("rTPA crystals dryer",        681880.08),
    ]
    for name, base in filt_items:
        eq.add(Equipment(name, "TPA Filtration & Crystallization", base_cost=base,
                         installation_factor=1.0, cepci_ref=BASE_YEAR,
                         cap_ref=CAP_REF, scaling_factor=0.6))

    # Electrolyzer base cost: physics-derived from Faraday's law when the
    # sizing JSON is present (reproduces the paper's $5.96M), else hard-coded.
    electrolyzer_base = 5958371.93
    if sizing is not None:
        ez = sizing.get("electrolyzer", {})
        if "base_cost_usd" in ez:
            electrolyzer_base = float(ez["base_cost_usd"])
    eq.add(Equipment("Electrolyzer", "Electrolysis", base_cost=electrolyzer_base,
                     installation_factor=1.0, cepci_ref=BASE_YEAR,
                     cap_ref=CAP_REF, scaling_factor=0.6))
    eq.add(Equipment("H2 storage tank", "Electrolysis", base_cost=384000.53,
                     installation_factor=1.0, cepci_ref=BASE_YEAR,
                     cap_ref=CAP_REF, scaling_factor=0.6))

    # ---- Utility coefficients ($/y per ton feedstock) ----
    # H2 electrolysis electricity: 31.9 kWh/kg H2 × 53.2224 kg H2/batch × 3504 batch/y × $0.0953
    # Heat: per source xlsx 269,982 $/y at 1 ton PET (heat duty 16.15 GJ/batch...)
    # Mech crushing: $13/ton PET × 3504 ton/y = 45552 $/y at 1 ton
    # Electricity (electrolysis) and Heat (reactor steam) OPEX coefficients
    # are physics-derived when the sizing JSON is present (Faraday + enthalpy
    # balance), else the hard-coded reference values. Both reproduce the paper.
    elec_opex = 566946.57
    heat_opex = 269982.09
    if sizing is not None:
        ez = sizing.get("electrolyzer", {})
        rh = sizing.get("reactor_heat", {})
        if "electricity_usd_per_t_feed_per_y" in ez:
            elec_opex = float(ez["electricity_usd_per_t_feed_per_y"])
        if "heat_usd_per_t_feed_per_y" in rh:
            heat_opex = float(rh["heat_usd_per_t_feed_per_y"])

    meta = {
        "Electricity (H2 Electrolysis)_$_per_ton_per_y": elec_opex,
        "Heat_$_per_ton_per_y":                          heat_opex,
        "Mechanical Crushing_$_per_ton_per_y":           45552.0,
        # context numbers (shown in assumptions)
        "Electrolyzer ($/m^2)":                          10000,
        "H2 specific energy (kWh/kg H2)":                31.9,
        "Cell voltage (V)":                              1.2,
        "Current density (mA/cm2)":                      125,
        "Faradaic efficiency":                           0.95,
        "Electricity ($/kWh)":                           0.0953,
    }
    if sizing is not None:
        ez = sizing.get("electrolyzer", {})
        rh = sizing.get("reactor_heat", {})
        meta["__matlab_sizing_pet"] = {
            "schema_version":           sizing.get("schema_version"),
            "generated_by":             sizing.get("generated_by"),
            "generated_at":             sizing.get("generated_at"),
            "design_point_ton":         sizing.get("design_point_ton_per_batch"),
            "electrolyzer_area_m2":     ez.get("required_area_m2"),
            "electrolyzer_current_A":   ez.get("required_current_A"),
            "electrolyzer_base_cost_usd": ez.get("base_cost_usd"),
            "specific_energy_kWh_per_kg_H2": ez.get("specific_energy_kWh_per_kg_H2"),
            "electricity_usd_per_t_feed_per_y": ez.get("electricity_usd_per_t_feed_per_y"),
            "Q_heating_GJ_per_batch":   rh.get("Q_heating_GJ_per_batch"),
            "Q_net_GJ_per_batch":       rh.get("Q_net_GJ_per_batch"),
            "heat_recovery_fraction":   rh.get("heat_recovery_fraction"),
            "heat_usd_per_t_feed_per_y": rh.get("heat_usd_per_t_feed_per_y"),
        }

    # The reference xlsx tabulates Maintenance & Operation as a fixed $/y
    # at the 1-ton baseline (which happens to be ~1.1% of the engine's total
    # CAPEX, not 10% — the "10% of CAPEX" label is a misnomer carried over
    # from the source workbook). We anchor on that 1-ton paper number and
    # scale with the 0.6 power-law so 5/10-ton M+O tracks the CAPEX growth
    # instead of throughput (the linear path over-estimated M+O at scale).
    # FA Distillation OPEX is genuinely throughput-coupled → linear.
    extra_opex = {
        "FA Distillation OPEX":         1225309.96,
        "Maintenance (~CAPEX 0.6-power)": {
            "value_at_ref": 363031.69,
            "scaling_factor": 0.6,
            "cap_ref": 1.0,
        },
        "Operation (~CAPEX 0.6-power)": {
            "value_at_ref": 363031.69,
            "scaling_factor": 0.6,
            "cap_ref": 1.0,
        },
    }
    extra_capex_ann = {
        "Feedstock (Initial inventory)": 83594.07,
        "FA Distillation column":        125538.87,
    }

    process = Process(
        name="PET Depolymerization (PMA + Electrolysis)",
        description=("0.1 g PET, 0.5 M PMA, 10 mL (1 M H2SO4 : DMSO = 1:1 v/v), "
                     "2 h batch.  Outputs: TPA, FA, H2 via electrolytic re-oxidation."),
        streams=ss,
        equipment=eq,
        sections=sections,
        edges=edges,
        meta=meta,
        extra_opex=extra_opex,
        extra_capex_annualized=extra_capex_ann,
    )

    inp = TEAInputs(
        discount_rate=0.10, lifetime_years=30, capacity_factor=0.8,
        cepci_target_year=2023, osbl_fraction=0.25,
        # Maintenance + Operation are taken as $/ton coefficients via extra_opex,
        # to match the reference xlsx exactly.
        maintenance_fraction=0.0, operation_fraction=0.0,
        batch_hours=2.0, msp_product="TPA",
        scales_ton=(1.0, 5.0, 10.0),
    )
    return process, db, inp
