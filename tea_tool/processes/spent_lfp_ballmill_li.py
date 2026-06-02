"""Spent LFP black mass → Li₂CO₃ via mechanochemical ball-mill leach.

Scenario:
    Recover ONLY Li from spent LFP (LiFePO₄) batteries. Fe/P stay in the
    spent solid and are treated as landfill waste (cost, not revenue).
    Reflects a worst-case economic framing — most commercial plants try to
    sell FePO₄ back into the LFP supply chain, but here we test the harder
    economics of pure Li recovery.

Physics-based sizing:
    When `data/matlab_sizing.json` exists (produced by either MATLAB's
    `run_sizing.m` or the Python mirror `tea_engine.physics.run_sizing`),
    `build()` reads it and overrides three things:
      • ball_mill_energy_kwh_per_t        ← Bond + Hogg-Fuerstenau result
      • Water-Leach equipment base_cost   ← SCM ODE -> volume -> 6/10ths cost
      • LPS steam OPEX meta key           ← evaporator enthalpy balance
      • Cooling water OPEX meta key       ← ball mill heat balance
    User kwargs > MATLAB JSON > LAB_DEFAULTS, so explicit overrides still win.
    Without the JSON file, behaviour is identical to the original flat-default
    version — smoke tests stay green.

Process train (mechanochemical activation route):
    1. Discharge + shredding
    2. Black-mass separation (magnetic + sieving — removes Cu/Al foil scrap)
    3. Ball-mill WITH reagent (NH₄Cl or organic acid) — mechanochemical
       activation breaks LFP lattice and converts Li to soluble form
    4. Water leach (Li → solution, FePO₄ stays in solid)
    5. S/L filtration
    6. Activated-carbon impurity removal (organic / electrolyte residue)
    7. Na₂CO₃ addition → Li₂CO₃ precipitation
    8. Drying → battery-grade Li₂CO₃ output
    9. Wastewater treatment (NH₃ stripping, pH neutralisation)
   10. Iron-phosphate solid waste disposal (cost)
   11. Balance of plant

Levers (build kwargs):
    li_content_in_feed         Li wt% in dried black mass (LFP ≈ 4 %)
    li_recovery                fraction of feed Li → product Li₂CO₃
    ball_mill_energy_kwh_per_t electricity for mechanochemical step
    reagent_stoich_factor      kg-NH₄Cl per stoichiometric requirement (excess)
    na2co3_stoich_factor       kg-Na₂CO₃ per stoichiometric Li (excess)
    water_recovery             fraction of water recycled
    fe_waste_disposal_usd_per_kg  landfill cost for Fe-bearing solids

Reference market prices (mid-2024 baseline):
    LFP black mass purchase:  $1.50/kg
    Battery-grade Li₂CO₃:    $20/kg
    NH₄Cl:                   $0.50/kg
    Na₂CO₃:                  $0.30/kg
    Fe-bearing waste landfill: $0.15/kg disposal
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from tea_engine.components import Component, ComponentDB
from tea_engine.streams import Stream, StreamSet
from tea_engine.equipment import Equipment, EquipmentList
from tea_engine.process import Process, ProcessSection
from tea_engine.tea import TEAInputs


_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_MATLAB_JSON_PATH = _DATA_DIR / "matlab_sizing.json"
_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "matlab" / "sizing_schema.json"
_SCHEMA_SUPPORTED = {"1.0"}


def _validate_against_schema(data: Dict[str, Any]) -> bool:
    """Best-effort JSON-Schema validation against matlab/sizing_schema.json.

    Returns True if valid OR if validation can't run (jsonschema missing /
    schema file absent) — i.e. validation never *blocks* on infrastructure,
    it only rejects data that is provably malformed. A False result means the
    JSON is structurally wrong and must NOT be trusted to drive economics.
    """
    try:
        import jsonschema  # optional dependency
    except ImportError:
        return True  # soft-skip: can't validate, don't block
    try:
        with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema = json.load(f)
    except (OSError, json.JSONDecodeError):
        return True  # schema file unavailable -> soft-skip
    try:
        jsonschema.validate(instance=data, schema=schema)
        return True
    except jsonschema.ValidationError:
        return False


def _load_matlab_sizing(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Read data/matlab_sizing.json if present, schema-valid, and for us.

    Returns None (→ fall back to LAB_DEFAULTS, never corrupt economics) when:
      • the file does not exist (smoke tests on a clean checkout)
      • the file is unreadable / malformed JSON
      • the schema_version is not in _SCHEMA_SUPPORTED
      • the process field does not match this module
      • the payload fails JSON-Schema validation (structurally wrong)
    """
    p = Path(path) if path else _MATLAB_JSON_PATH
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("schema_version") not in _SCHEMA_SUPPORTED:
        return None
    if data.get("process") != "spent_lfp_ballmill_li":
        return None
    if not _validate_against_schema(data):
        return None
    return data


LAB_DEFAULTS = {
    # Process levers
    "li_content_in_feed":          0.040,    # 4 wt% Li in dried LFP black mass
    "li_recovery":                 0.90,     # lab ~90 %, commercial ~98 %
    "ball_mill_energy_kwh_per_t":  150.0,    # planetary mill; commercial 50-80
    "reagent_stoich_factor":       1.5,      # 50 % excess NH₄Cl
    "na2co3_stoich_factor":        1.2,      # 20 % excess Na₂CO₃
    "water_recovery":              0.80,     # process water recycle
    "fe_waste_disposal_usd_per_kg": 0.15,    # Class I non-hazardous landfill
    # Market price levers (override component DB at build time)
    "li2co3_price":                20.0,     # $/kg battery-grade (2024 baseline)
    "lfp_feed_price":              1.50,     # $/kg LFP black mass purchase
    "nh4cl_price":                 0.50,     # $/kg industrial bulk
    "na2co3_price":                0.30,     # $/kg industrial bulk
}

COMMERCIAL_TARGETS = {
    "li_recovery":                 0.98,
    "ball_mill_energy_kwh_per_t":  80.0,
    "reagent_stoich_factor":       1.1,
    "na2co3_stoich_factor":        1.05,
    "water_recovery":              0.95,
}


def build(**overrides):
    """Build the LFP-Li process at a specific operating point.

    Numeric levers resolve in this precedence:
        explicit kwargs   >   data/matlab_sizing.json   >   LAB_DEFAULTS

    Pass ``matlab_sizing=False`` to disable JSON loading even if the file
    exists. Pass ``matlab_sizing=<path>`` to point at a different JSON.
    """
    # Extract the matlab_sizing knob before mixing into p (it's not a lever).
    matlab_arg = overrides.pop("matlab_sizing", True)
    if matlab_arg is False:
        sizing = None
    elif matlab_arg is True:
        sizing = _load_matlab_sizing()
    else:
        sizing = _load_matlab_sizing(Path(matlab_arg))

    # Build effective defaults: start from LAB_DEFAULTS, fold in any physics-
    # based overrides from the MATLAB JSON, then let user kwargs win on top.
    physics_defaults: Dict[str, Any] = {}
    if sizing is not None:
        bm = sizing.get("ball_mill", {})
        if "kWh_per_t_feed" in bm:
            physics_defaults["ball_mill_energy_kwh_per_t"] = float(bm["kWh_per_t_feed"])

    p = {**LAB_DEFAULTS, **physics_defaults, **overrides}
    unknown = set(overrides) - set(LAB_DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown lever(s): {unknown}. "
                         f"Known: {list(LAB_DEFAULTS)}")

    li_frac = p["li_content_in_feed"]
    li_rec = p["li_recovery"]
    ball_kwh_per_t = p["ball_mill_energy_kwh_per_t"]
    nh4cl_excess = p["reagent_stoich_factor"]
    na2co3_excess = p["na2co3_stoich_factor"]
    water_rec = p["water_recovery"]
    fe_disposal = p["fe_waste_disposal_usd_per_kg"]

    # -------- Component DB (with market-price overrides) --------
    db = ComponentDB.default()
    if "LFP Black Mass" not in db:
        db.add(Component("LFP Black Mass", mw=160.0, price_low=p["lfp_feed_price"],
                         role="input", price_ref="2024 EU recycler avg"))
    else:
        db.get("LFP Black Mass").price_low = p["lfp_feed_price"]

    if "Li2CO3" not in db:
        db.add(Component("Li2CO3", mw=73.89, price_low=p["li2co3_price"],
                         role="output", price_ref="2024 battery-grade"))
    else:
        db.get("Li2CO3").price_low = p["li2co3_price"]

    if "NH4Cl" not in db:
        db.add(Component("NH4Cl", mw=53.49, price_low=p["nh4cl_price"],
                         role="input", price_ref="2024 industrial bulk"))
    else:
        db.get("NH4Cl").price_low = p["nh4cl_price"]

    if "Na2CO3" not in db:
        db.add(Component("Na2CO3", mw=105.99, price_low=p["na2co3_price"],
                         role="input", price_ref="2024 industrial bulk"))
    else:
        db.get("Na2CO3").price_low = p["na2co3_price"]

    if "Activated Carbon" not in db:
        db.add(Component("Activated Carbon", mw=12.01, price_low=2.00,
                         role="input", price_ref="2024 powdered AC"))

    if "Ball-mill Electricity" not in db:
        db.add(Component("Ball-mill Electricity", mw=1.0, price_low=0.10,
                         role="input", price_ref="Grid power baseline ($/kWh)"))
    else:
        db.get("Ball-mill Electricity").price_low = 0.10

    if "Fe-rich Waste" not in db:
        db.add(Component("Fe-rich Waste", mw=1.0, price_low=-fe_disposal,
                         role="output", price_ref="Landfill disposal fee ($/kg)"))
    else:
        db.get("Fe-rich Waste").price_low = -fe_disposal

    # -------- Per-batch lab basis (1 kg LFP black mass / batch) --------
    # Stoichiometry per 1 kg feed:
    #   Li in feed:   li_frac × 1000 g
    #   Li recovered: li_rec × li_frac × 1000 g
    #   Li2CO3 out:   Li_rec × MW(Li2CO3)/(2×MW(Li)) = × 5.32 (mass basis)
    li_in_feed_g = li_frac * 1000.0
    li_recovered_g = li_rec * li_in_feed_g
    li2co3_out_g = li_recovered_g * 73.89 / (2 * 6.94)        # ~5.32×

    # Reagent: NH4Cl stoich = 3 mol NH4Cl per mol LFP (rough for mechanochem)
    # Lab basis: 1 kg LFP black mass × (fraction that's LFP, assume 60%) /
    #            MW(LFP)=158 × 3 mol × MW(NH4Cl)=53.5 × excess factor
    nh4cl_g = 1000.0 * 0.60 / 158.0 * 3.0 * 53.49 * nh4cl_excess  # ~610 g × excess

    # Na2CO3: 1 mol per mol Li2CO3 product
    na2co3_g = li2co3_out_g / 73.89 * 105.99 * na2co3_excess        # ~287 g × excess

    # Activated carbon for impurity removal (rough: 1% of feed)
    ac_g = 10.0

    # Water: 5 L per kg LFP, recycled
    water_g = 5000.0

    # Fe-bearing solid waste: feed mass - Li2CO3 mass extracted - water loss
    # ~0.7 kg solid waste per kg feed (LFP gives ~0.5 kg FePO4 + rest is C/binder)
    fe_waste_g = 700.0

    # -------- Streams --------
    ss = StreamSet()
    ss.add_input(Stream("LFP Black Mass", 1000.0, recovery=0.0, category="feed",
                        note=f"Dried black mass, {li_frac*100:.1f}% Li; lever: li_content_in_feed"))
    ss.add_input(Stream("NH4Cl", nh4cl_g, recovery=0.0, category="catalyst",
                        note=f"Mechanochemical reagent; lever: reagent_stoich_factor (={nh4cl_excess})"))
    ss.add_input(Stream("Na2CO3", na2co3_g, recovery=0.0, category="acid_or_base",
                        note=f"Li precipitation; lever: na2co3_stoich_factor (={na2co3_excess})"))
    ss.add_input(Stream("H2O", water_g, recovery=water_rec, category="utility",
                        note=f"Process water; lever: water_recovery"))
    ss.add_input(Stream("Activated Carbon", ac_g, recovery=0.0, category="consumable"))
    ss.add_input(Stream("Ball-mill Electricity", ball_kwh_per_t * 0.001, recovery=0.0, category="utility",
                        note=f"Ball-mill electricity; lever: ball_mill_energy_kwh_per_t"))

    ss.add_output(Stream("Li2CO3", li2co3_out_g,
                         note=f"Battery-grade Li2CO3; recovery lever: li_recovery (={li_rec})"))
    ss.add_output(Stream("Fe-rich Waste", fe_waste_g,
                         note="Fe-bearing solid waste residue to landfill (disposal cost)"))

    # -------- Sections --------
    sections = [
        ProcessSection("discharge", "Discharge & Shredding",
                       "Cell discharge then mechanical shredding to release black mass",
                       kind="Pretreatment"),
        ProcessSection("bm_sep",    "Black-mass Separation",
                       "Magnetic + sieve to remove Cu/Al foil scrap",
                       kind="Filter / Centrifuge"),
        ProcessSection("ballmill",  "Mechanochemical Ball-mill",
                       "Ball-mill black mass WITH NH4Cl — activates LFP for "
                       "selective Li dissolution. Key OPEX (electricity-heavy).",
                       kind="Pretreatment"),
        ProcessSection("leach",     "Water Leach",
                       "Stirred-tank water leach; Li dissolves, FePO4 remains solid",
                       kind="Catalytic Reactor"),
        ProcessSection("filter",    "S/L Filtration",
                       "Pressure filter — Li-bearing filtrate + Fe-rich filter cake",
                       kind="Filter / Centrifuge"),
        ProcessSection("li_purif",  "Li Solution Purification",
                       "Activated-carbon column for organic residue + ion exchange "
                       "for trace metal polishing",
                       kind="Absorber / Stripper"),
        ProcessSection("li_precip", "Li2CO3 Crystallization",
                       "Add Na2CO3, crystallize Li2CO3 (sat. solubility 13 g/L @ 20°C)",
                       kind="Crystallizer"),
        ProcessSection("dry",       "Final Drying",
                       "Rotary or fluidized-bed dryer to battery-grade spec",
                       kind="Dryer"),
        ProcessSection("ww",        "Wastewater Treatment",
                       "NH3 stripping (recover NH4Cl), pH neutralization, "
                       "ion-exchange polishing before discharge",
                       kind="Wastewater Treatment"),
        ProcessSection("fe_dispo",  "Fe-waste Disposal Handling",
                       "Containerise + transport Fe-rich filter cake to landfill",
                       kind="Utility / BoP"),
        ProcessSection("bop",       "Balance of Plant",
                       "Pumps, HX, control, dust collection",
                       kind="Utility / BoP"),
    ]

    edges = [
        ("in:LFP Black Mass",     "discharge",    "spent cells"),
        ("discharge",             "bm_sep",       "shredded mix"),
        ("bm_sep",                "ballmill",     "black mass powder"),
        ("bm_sep",                "fe_dispo",     "foil scrap (offset by metal sale, ignored)"),
        ("in:NH4Cl",              "ballmill",     "mechanochemical reagent"),
        ("in:Ball-mill Electricity", "ballmill",   "process power"),
        ("ballmill",              "leach",        "activated powder"),
        ("in:H2O",                "leach",        "process water"),
        ("leach",                 "filter",       "Li-rich slurry"),
        ("filter",                "li_purif",     "Li-bearing filtrate"),
        ("filter",                "fe_dispo",     "FePO4 + C filter cake"),
        ("in:Activated Carbon",   "li_purif",     "AC for impurity removal"),
        ("li_purif",              "li_precip",    "polished Li solution"),
        ("in:Na2CO3",             "li_precip",    "precipitation agent"),
        ("li_precip",             "dry",          "Li2CO3 crystals"),
        ("li_precip",             "ww",           "Na/NH4 mother liquor"),
        ("dry",                   "out:Li2CO3",   "battery-grade Li2CO3"),
        ("ww",                    "leach",        "recycled water"),     # recycle
        ("ww",                    "bop",          "treated effluent"),
        ("fe_dispo",              "out:Fe-rich Waste", "to landfill"),
    ]

    # In physics mode, splice an Evaporator/Concentrator between purification
    # and crystallization (it carries the LPS-steam OPEX). The mother liquor
    # must be concentrated before Li2CO3 crystallizes (solubility ~13 g/L).
    if sizing is not None and float(sizing.get("evaporator", {})
                                    .get("base_cost_usd", 0.0)) > 0:
        sections.insert(
            sections.index(next(s for s in sections if s.key == "li_precip")),
            ProcessSection("evap", "Evaporator / Concentrator",
                           "Multi-effect evaporator concentrates Li filtrate "
                           "before crystallization (LPS-steam OPEX; physics-sized).",
                           kind="Heat Exchanger"))
        # Re-route li_purif -> li_precip through the evaporator.
        edges = [e for e in edges
                 if not (e[0] == "li_purif" and e[1] == "li_precip")]
        edges += [
            ("li_purif", "evap",      "polished Li solution"),
            ("evap",     "li_precip", "concentrated Li liquor"),
        ]

    # -------- Equipment (0.6 power-law unless noted) --------
    # Several base costs can be physics-overridden from MATLAB sizing JSON.
    # At the reference operating point these equal the original quotes
    # exactly, so the no-JSON path stays byte-identical (see regression test).
    water_leach_base = 340_000        # leach.base_cost_usd (= $340k at 90% recovery)
    ballmill_base = 2_100_000         # ball_mill.base_cost_usd (= $2.1M at ref duty)
    if sizing is not None:
        lk = sizing.get("leach_tank", {})
        if "base_cost_usd" in lk:
            water_leach_base = float(lk["base_cost_usd"])
        bm_s = sizing.get("ball_mill", {})
        if "base_cost_usd" in bm_s:
            ballmill_base = float(bm_s["base_cost_usd"])

    eq = EquipmentList()
    items_pl = [
        ("Discharge & Shredding",         "Discharger + shredder line", 1_500_000),
        ("Black-mass Separation",         "Magnetic + vibrating sieve",   420_000),
        ("Mechanochemical Ball-mill",     "Industrial planetary mill",  ballmill_base),
        ("Water Leach",                   "Stirred leaching tanks",       water_leach_base),
        ("S/L Filtration",                "Pressure filter + buffer",     520_000),
        ("Li Solution Purification",      "AC column + IX skid",          280_000),
        ("Li2CO3 Crystallization",        "Crystallizer + agitator",      720_000),
        ("Final Drying",                  "Rotary dryer + bag filter",    410_000),
        ("Wastewater Treatment",          "NH3 stripper + neutralization",1_050_000),
        ("Fe-waste Disposal Handling",    "Containerization + conveyor",  220_000),
        ("Balance of Plant",              "Pumps, HX, control, dust",     820_000),
    ]
    # Evaporator/Concentrator is added ONLY in physics mode, paired with its
    # steam OPEX, so we never book OPEX for a unit absent from the CAPEX side.
    if sizing is not None:
        ev_base = float(sizing.get("evaporator", {}).get("base_cost_usd", 0.0))
        if ev_base > 0:
            items_pl.append(
                ("Evaporator / Concentrator", "MEE concentrator", ev_base))
    for sec, name, base in items_pl:
        eq.add(Equipment(name, sec, base_cost=base, installation_factor=1.0,
                         cepci_ref=2023, cap_ref=1.0, scaling_factor=0.6))

    # -------- Meta (informational + lever read-outs) --------
    meta = {
        "Li content in feed (%)":         li_frac * 100,
        "Li recovery":                    li_rec,
        "Li2CO3 yield (kg/kg-feed)":      li2co3_out_g / 1000.0,
        "Ball-mill energy (kWh/t-feed)":  ball_kwh_per_t,
        "NH4Cl stoich factor":            nh4cl_excess,
        "Na2CO3 stoich factor":           na2co3_excess,
        "Water recovery":                 water_rec,
        "Fe waste disposal ($/kg)":       fe_disposal,
    }

    # -------- Extra OPEX (handled dynamically via utility and waste streams) --------
    extra_opex = {}

    extra_capex_ann = {}

    # -------- Physics-based utility lines (from MATLAB sizing JSON) --------
    # The TEA engine recognises any meta key ending in "_$_per_ton_per_y"
    # as a linear-scaling utility OPEX. The keys below are populated only
    # when the JSON file is present, so they are additive features rather
    # than required defaults.
    if sizing is not None:
        bm = sizing.get("ball_mill", {})
        ev = sizing.get("evaporator", {})
        cw_per_t_per_y = float(bm.get("cooling_water_usd_per_t_feed_per_y", 0.0))
        if cw_per_t_per_y > 0:
            meta["Cooling_Water_BallMill_$_per_ton_per_y"] = cw_per_t_per_y
        lps_per_t_per_y = float(ev.get("lps_steam_usd_per_t_feed_per_y", 0.0))
        if lps_per_t_per_y > 0:
            meta["LPS_Steam_Evap_$_per_ton_per_y"] = lps_per_t_per_y
        # Stash sizing provenance so the design-note generator and any
        # downstream report can show "where did these numbers come from?".
        _lk = sizing.get("leach_tank", {})
        meta["__matlab_sizing"] = {
            "schema_version":         sizing.get("schema_version"),
            "generated_by":           sizing.get("generated_by"),
            "generated_at":           sizing.get("generated_at"),
            "design_point_ton":       sizing.get("design_point_ton_per_batch"),
            # ball mill
            "ball_mill_kWh_per_t":    bm.get("kWh_per_t_feed"),
            "ball_mill_motor_kW":     bm.get("motor_kW_at_design_point"),
            "ball_mill_base_cost_usd": bm.get("base_cost_usd"),
            "ball_mill_bond_fraction": bm.get("bond_fraction_of_total"),
            "ball_mill_D_m":          bm.get("mill_diameter_m"),
            "ball_mill_L_m":          bm.get("mill_length_m"),
            # leach
            "leach_residence_h":      _lk.get("residence_time_h"),
            "leach_volume_m3":        _lk.get("reactor_volume_m3"),
            "leach_base_cost_usd":    _lk.get("base_cost_usd"),
            "leach_base_cost_orig":   _lk.get("base_cost_usd_orig"),
            "leach_reference_recovery": _lk.get("reference_recovery"),
            # evaporator
            "evap_Q_MJ_per_batch":    ev.get("Q_evap_MJ_per_batch"),
            "evap_steam_kg_per_batch": ev.get("lps_steam_kg_per_batch"),
            "evap_area_m2":           ev.get("heat_transfer_area_m2"),
            "evap_base_cost_usd":     ev.get("base_cost_usd"),
            "evap_effects":           ev.get("effects"),
        }

    process = Process(
        name="Spent LFP Black Mass → Li2CO3 (mechanochemical, Li-only)",
        description=("Mechanochemical ball-mill activation of LFP black mass "
                     "with NH4Cl reagent, water leach, S/L separation, AC/IX "
                     "polish, Na2CO3 precipitation → battery-grade Li2CO3. "
                     "Fe-bearing residue to landfill (cost). "
                     "Lab/commercial gap analysis target: which lever moves "
                     "$/kg-feed across breakeven?"),
        streams=ss, equipment=eq, sections=sections, edges=edges,
        meta=meta, extra_opex=extra_opex,
        extra_capex_annualized=extra_capex_ann,
    )

    inp = TEAInputs(
        discount_rate=0.10, lifetime_years=15, capacity_factor=0.85,
        cepci_target_year=2023, osbl_fraction=0.25,
        maintenance_fraction=0.04, operation_fraction=0.05,
        batch_hours=1.0,
        msp_product="Li2CO3",
        feedstock_for_economics="LFP Black Mass",
        scales_ton=(0.1, 1.0, 5.0),   # smaller scales — battery recycling is regional
    )
    return process, db, inp
