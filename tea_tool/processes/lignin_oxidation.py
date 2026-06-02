"""Microwave-assisted lignin oxidation with PMA + electrolytic H2 regeneration.

Lab basis (per batch — user-supplied):
    Organosolv lignin (oak)   300 mg
    PMA (H3PMo12O40)          5.48 g    (catalyst, fully recycled)
    H2O reaction medium       30 mL  (~30 g)
    Chloroform extraction    ~30 mL (~44.7 g, recoverable)
    Microwave 400 W, 110 °C, 10 min ramp + 15 min hold = 25 min total

    Products
        Vanillin           4.63 mg
        Vanillic acid      1.23 mg
        Syringaldehyde     4.84 mg
        Syringic acid      0.42 mg
    Lignin reacted         93.95 mg  (31.32 % single-pass conversion)
    PMA reduction degree   30.2 %    (→ 3.624 e- per H3PMo12O40)
    H2 produced (electrolytic re-ox of reduced PMA)
        n_PMA      = 5.48 / 1825.25 = 3.0023 mmol
        n_e        = 3.0023 × 12 × 0.302 = 10.880 mmol
        n_H2       = n_e / 2 = 5.440 mmol → 10.97 mg / batch

Process flow
    1. Feedstock pretreatment (lignin handling)
    2. Microwave-assisted depolymerization (lignin + PMA + H2O at 110 °C, 25 min)
    3. Filtration (unreacted lignin returned to feed)
    4. Chloroform extraction of phenolic monomers
    5. Distillation / crystallization (chloroform recovery + product purification)
    6. Electrolysis (reduced PMA → re-oxidation, evolving H2)

The CAPEX backbone is taken from the PET-PMA template (same architecture: a
catalysed reactor + filtration + electrolysis-driven catalyst regeneration)
and tuned for a microwave reactor and an extraction/crystallization train
instead of a TPA crystallizer.  Numbers are first-cut at 1 ton lignin/batch,
CEPCI-2023 — refine through the UI's Streams / Equipment / Prices tabs.
"""
from tea_engine.components import ComponentDB
from tea_engine.streams import Stream, StreamSet
from tea_engine.equipment import Equipment, EquipmentList
from tea_engine.process import Process, ProcessSection
from tea_engine.tea import TEAInputs


def build(scenario: str = "B_industrial"):
    """Build the lignin-oxidation TEA process.

    scenario:
        "A_lab"        — lab water:lignin = 100:1 (30 mL water / 0.3 g lignin
                          straight scale-up).  MW heating cost ~ $32 M/y at
                          1 ton/batch baseline.  Use this if you want to TEA
                          the lab procedure literally.
        "B_industrial" — industrial-realistic water:lignin = 10:1 (concentrated
                          slurry).  Same MW kinetics (reaction rate set by
                          temperature & power density, not absolute mass).
                          MW heating cost ~ $8 M/y at 1 ton/batch baseline.
    """
    if scenario not in ("A_lab", "B_industrial"):
        raise ValueError(f"Unknown scenario: {scenario!r}")

    db = ComponentDB.default()

    # ---- Material streams (lab basis: 0.300 g lignin / batch) ----
    # Lignin: 31.32 % consumed per pass (93.95/300); the remaining 68.68 %
    # is filtered and recycled, so the engine treats `recovery=0.6868`
    # (= unreacted fraction returned to feed).
    # Water mass per batch — scenario-dependent
    if scenario == "A_lab":
        h2o_g = 30.0          # lab as-is (30 mL water / 0.3 g lignin = 100:1 mass)
        h2o_note = "30 mL — lab procedure as-is (water:lignin 100:1)"
        mw_cost = 32_000_000  # $/y per ton-feed/batch baseline (~119 ton heated/batch)
        scenario_label = "A — Lab water:lignin 100:1"
    else:  # B_industrial
        h2o_g = 3.0           # industrial concentrated slurry (water:lignin 10:1)
        h2o_note = "3 g — industrial concentrated slurry (water:lignin 10:1)"
        mw_cost = 8_000_000   # $/y per ton-feed/batch baseline (~29 ton heated/batch)
        scenario_label = "B — Industrial concentrated slurry (water:lignin 10:1)"

    ss = StreamSet()
    ss.add_input(Stream("Organosolv Lignin", 0.300,  recovery=0.6868))
    ss.add_input(Stream("PMA",               5.480,  recovery=1.0))     # fully regenerated electrochemically
    ss.add_input(Stream("H2O",               h2o_g,  recovery=0.0,
                        note=h2o_note))
    ss.add_input(Stream("Chloroform",        44.7,   recovery=0.9999))  # 30 mL × 1.49 g/mL, 99.99% distillation recovery

    ss.add_output(Stream("Vanillin",         0.00463))
    ss.add_output(Stream("Vanillic acid",    0.00123))
    ss.add_output(Stream("Syringaldehyde",   0.00484))
    ss.add_output(Stream("Syringic acid",    0.00042))
    ss.add_output(Stream("H2",               0.01097))   # 10.97 mg, from PMA reduction degree 30.2 %

    # ---- Sections (PFD blocks) ----
    sections = [
        ProcessSection("feed",    "Feedstock Pretreatment",
                       "Lignin conveying, drying, storage, metering",
                       kind="Pretreatment"),
        ProcessSection("mw",      "Microwave Depolymerization",
                       "PMA-catalysed oxidation, 110 °C / 25 min, 400 W microwave",
                       kind="Catalytic Reactor"),
        ProcessSection("filt",    "Filtration & Lignin Recycle",
                       "Filter unreacted lignin → recycle to feed",
                       kind="Filter / Centrifuge"),
        ProcessSection("extract", "Chloroform Extraction",
                       "Liquid–liquid extraction of phenolic monomers",
                       kind="Liquid-Liquid Sep"),
        ProcessSection("dist",    "Solvent Recovery & Product Crystallization",
                       "Chloroform recovery (distillation) + crystallization/dryer",
                       kind="Distillation Column"),
        ProcessSection("elec",    "Electrolysis (PMA Regen + H2)",
                       "Reduced PMA re-oxidised at anode; cathode evolves H2",
                       kind="Electrochemical Cell"),
    ]

    edges = [
        ("in:Organosolv Lignin", "feed", ""),
        ("feed",  "mw",  "lignin"),
        ("in:PMA", "mw", ""),
        ("in:H2O", "mw", ""),
        ("mw",    "filt", "reaction slurry"),
        ("filt",  "feed", "unreacted lignin (recycle)"),
        ("filt",  "extract", "aqueous filtrate (products + reduced PMA)"),
        ("in:Chloroform", "extract", ""),
        ("extract", "dist", "chloroform extract (monomers)"),
        ("extract", "elec", "aqueous phase (reduced PMA)"),
        ("dist", "out:Vanillin",       ""),
        ("dist", "out:Vanillic acid",  ""),
        ("dist", "out:Syringaldehyde", ""),
        ("dist", "out:Syringic acid",  ""),
        ("dist", "extract", "regen. chloroform"),
        ("elec", "mw", "regen. PMA"),
        ("elec", "out:H2", ""),
    ]

    # ---- Equipment (installed cost, 2023 USD, 1-ton lignin/batch baseline) ----
    eq = EquipmentList()
    BASE_YEAR = 2023
    CAP_REF = 1.0  # 1 ton lignin / batch

    feed_items = [
        ("Lignin storage silo",         400_000),
        ("Lignin pneumatic conveyor",   200_000),
        ("Lignin dryer / screener",     250_000),
        ("Dust collection system",      100_000),
        ("Feed metering hopper",        150_000),
        ("Pre-mixing tank",             350_000),
    ]
    for name, base in feed_items:
        eq.add(Equipment(name, "Feedstock Pretreatment", base_cost=base,
                         installation_factor=1.0, cepci_ref=BASE_YEAR,
                         cap_ref=CAP_REF, scaling_factor=0.6))

    mw_items = [
        ("Industrial microwave reactor bank (×N)", 4_500_000),
        ("PMA storage and transfer",               280_000),
        ("Water tank + recirculation pump",        120_000),
        ("Reactor effluent cooler",                 80_000),
        ("Charging / mixing tank",                 200_000),
        ("MW power supply + chiller",              420_000),
    ]
    for name, base in mw_items:
        eq.add(Equipment(name, "Microwave Depolymerization", base_cost=base,
                         installation_factor=1.0, cepci_ref=BASE_YEAR,
                         cap_ref=CAP_REF, scaling_factor=0.6))

    filt_items = [
        ("Solids filter package",                  1_500_000),
        ("Unreacted-lignin centrifuge + dryer",    450_000),
        ("Lignin recycle conveyor",                100_000),
    ]
    for name, base in filt_items:
        eq.add(Equipment(name, "Filtration & Lignin Recycle", base_cost=base,
                         installation_factor=1.0, cepci_ref=BASE_YEAR,
                         cap_ref=CAP_REF, scaling_factor=0.6))

    extract_items = [
        ("Liquid–liquid extraction column",        700_000),
        ("Decanter / phase separator",             250_000),
        ("Chloroform storage tank",                250_000),
        ("Chloroform feed/recycle pump",            50_000),
        ("Aqueous phase pump",                      50_000),
        ("Solvent feed heat exchanger",            100_000),
    ]
    for name, base in extract_items:
        eq.add(Equipment(name, "Chloroform Extraction", base_cost=base,
                         installation_factor=1.0, cepci_ref=BASE_YEAR,
                         cap_ref=CAP_REF, scaling_factor=0.6))

    dist_items = [
        ("Chloroform recovery distillation column", 1_400_000),
        ("Aldehyde crystallizer",                   1_800_000),
        ("Crystal centrifuge",                        500_000),
        ("Crystal dryer",                             450_000),
        ("Vacuum system",                             250_000),
    ]
    for name, base in dist_items:
        eq.add(Equipment(name, "Solvent Recovery & Product Crystallization",
                         base_cost=base, installation_factor=1.0,
                         cepci_ref=BASE_YEAR, cap_ref=CAP_REF, scaling_factor=0.6))

    eq.add(Equipment("Electrolyzer (PMA regen + H2)", "Electrolysis (PMA Regen + H2)",
                     base_cost=5_500_000, installation_factor=1.0,
                     cepci_ref=BASE_YEAR, cap_ref=CAP_REF, scaling_factor=0.6,
                     lifetime_years=10))
    eq.add(Equipment("H2 storage tank", "Electrolysis (PMA Regen + H2)",
                     base_cost=400_000, installation_factor=1.0,
                     cepci_ref=BASE_YEAR, cap_ref=CAP_REF, scaling_factor=0.6))
    eq.add(Equipment("Electrolyte recirculation pump", "Electrolysis (PMA Regen + H2)",
                     base_cost=80_000, installation_factor=1.0,
                     cepci_ref=BASE_YEAR, cap_ref=CAP_REF, scaling_factor=0.6))

    # ---- Utility / context coefficients ----
    # Microwave reaction electricity (only the 30-mL reaction medium is heated;
    # the lab "parallel 70-mL water reactor" was a thermal-balance artifact and
    # is excluded from the industrial scale-up):
    #   Mass to heat per ton lignin ≈ 30 ton water + 18.27 ton PMA = 48.3 ton
    #   ΔT 85 °C, Cp_water 4.186 → 17.2 GJ/ton lignin = 4,778 kWh/ton
    #   At 50 % industrial MW efficiency → 9,556 kWh/ton lignin
    #   1 ton/batch × 16,815 batches/y × 9,556 kWh × $0.0953 ≈ $15.3 M / y
    # H2 electrolysis electricity:
    #   36.6 kg H2 / ton lignin × 31.9 kWh/kg H2 × 16,815 batch/y × $0.0953
    #   = ~ $1.87 M / y at 1 ton
    # Heat / cooling / distillation utilities, mech. handling, char disposal —
    # tuned roughly proportionally to the PET template at the same scale basis.
    meta = {
        # Process knobs (tunable in the UI)
        "Lignin conversion (single pass)": 0.3132,        # 93.95 / 300
        "PMA reduction degree":            0.302,
        "Electrons per PMA (max)":         12,
        "PMA molecular weight":            1825.25,
        "Reaction temperature (C)":        110,
        "Reaction time (min)":             25,
        "Microwave power (W, lab)":        400,
        "H2O / lignin (g/g)":              h2o_g / 0.300,  # 100 (A) or 10 (B)
        "Scenario":                        scenario_label,
        "Chloroform / lignin (g/g)":       149.0,         # 30 mL × 1.49 g/mL / 0.3 g
        "Cell voltage (V)":                1.20,
        "Current density (mA/cm2)":        125,           # placeholder; tune in UI
        "Faradaic efficiency":             0.95,
        "Electrolyzer ($/m^2)":            10000,
        "H2 specific energy (kWh/kg H2)":  31.9,
        "Electricity ($/kWh)":             0.0953,

        # Annual utility costs ($/y per ton-feed/batch scale) — scenario-driven MW
        "Microwave Reaction Electricity_$_per_ton_per_y": mw_cost,
        "H2 Electrolysis Electricity_$_per_ton_per_y":     1_870_000,
        "Heat & Cooling_$_per_ton_per_y":                    300_000,
        "Mechanical Crushing_$_per_ton_per_y":                50_000,
    }

    # Per-ton distillation/extraction OPEX + char disposal + maintenance/op
    extra_opex = {
        "Chloroform Recovery & Crystallization OPEX": 800_000,
        "Char / Humins Disposal":                     150_000,
        "Maintenance (10% of CAPEX)":                 0.0,    # placeholder; using fraction below
        "Operation (10% of CAPEX)":                   0.0,    # placeholder; using fraction below
    }
    # Initial PMA inventory (one-time charge, annualized via plant CRF)
    # 5.48 g PMA / 0.300 g lignin = 18.27 kg PMA / kg lignin = 18.27 ton / ton lignin
    extra_capex_ann = {
        "PMA Initial Inventory":        18.27 * 0.01 * 0.106,   # 18.27 ton × $0.01/kg × CRF (≈ $0.0194/ton)
        # Almost zero at PMA = $0.01/kg; will become meaningful if PMA price grows.
    }

    process = Process(
        name="Microwave Lignin Oxidation (PMA + Electrolysis)",
        description=("0.300 g organosolv lignin (oak), 5.48 g PMA, 30 mL water "
                     "+ 70 mL parallel electrolyte, 110 °C, 25 min microwave (400 W). "
                     "Filter unreacted lignin → chloroform extraction → "
                     "distillation/crystallization → electrolytic PMA re-oxidation "
                     "produces H2 as co-product."),
        streams=ss,
        equipment=eq,
        sections=sections,
        edges=edges,
        meta=meta,
        extra_opex={k: v for k, v in extra_opex.items() if v != 0.0},
        extra_capex_annualized=extra_capex_ann,
    )

    inp = TEAInputs(
        discount_rate=0.10, lifetime_years=20, capacity_factor=0.8,
        cepci_target_year=2023, osbl_fraction=0.25,
        maintenance_fraction=0.10, operation_fraction=0.10,
        batch_hours=25.0 / 60.0,                    # 25 min batch
        msp_product="Vanillin",
        scales_ton=(1.0, 5.0, 10.0),
    )
    return process, db, inp
