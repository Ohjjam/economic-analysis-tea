"""Modular flow lignin valorisation + low-V H2 — paper-grade build (rev. 2).

Source paper:
    Yim, Oh, Choi, Ahn, Park, Kim, Ryu, Kim, Adv Sci 2022, 9, 2204170.
    doi:10.1002/advs.202204170

Modelling choices (rev. 2 after user review 2026-05-27):
    - Lignin is the headline feedstock. The economics question is "what is
      the per-kg-lignin profit/loss after collecting H2 + vanillin + AV
      revenue at market prices?" → use the engine's new
      `feedstock_for_economics` path; net_per_kg_feedstock is the headline.
      H2 stays as msp_product for cross-check only.
    - Vanillin & acetovanillone selectivity is set by the FRP THERMAL
      reactor (PMA-mediated lignin oxidation), not by electrolyzer area.
      Their mass-per-batch values therefore scale with lignin throughput
      (which is exactly what scaling input[0] does in the engine).
      The electrolyzer only regenerates PMA(red) → PMA(ox) and runs HER.
    - PMA basis = 0.5 M × 10 mL × 1825 g/mol / 1000 = 9.125 g/batch
      (was 5.0 g/batch in rev. 1 — MW-inconsistent).
    - Distillation train made explicit: 2-MeTHF recovery, aromatic
      concentration, AV vacuum still off the vanillin mother liquor.
    - Anode does PMA reactivation, NOT OER → cathode + anode at ~1.5 V,
      far below conventional water EC at ~1.9 V.

Key reported numbers used:
    - V_cell                 1.5 V
    - j                      20.5 mA / cm²
    - FE_H2                  100 % (1.5 V; paper)
    - Vanillin productivity  0.5 mg / h / cm²-electrode (lab anode area)
    - Acetovanillone         0.17 mg / h / cm²-electrode (lab anode area)
    - PMA recovery           99 % via in-loop recycle (paper claims ~100 %)

Numbers still flagged as rough (need paper §2.3 mass balance to refine):
    - LIGNIN_KG_PER_KG_H2 = 12.5 (Faraday-law + selectivity back-calc)
    - VANILLIN/AV per-kg-H2 ratios (lab-to-commercial extrapolation)
"""
from tea_engine.components import Component, ComponentDB
from tea_engine.streams import Stream, StreamSet
from tea_engine.equipment import Equipment, EquipmentList
from tea_engine.process import Process, ProcessSection
from tea_engine.tea import TEAInputs


# =============================================================================
# LEVERS (lab-default values). Pass overrides to build(...) to sweep.
# Each lever name is the keyword arg name for build(), which is also what the
# sensitivity / breakeven / gap-report tools use to identify which knob to turn.
#
#   vanillin_selectivity      FRP-thermal yield of vanillin (kg / kg-lignin)
#   acetovanillone_selectivity   same for acetovanillone
#   lignin_to_h2              Faraday + selectivity stoichiometry (kg / kg)
#   j_mA_per_cm2              electrolyzer current density — drives cell area
#   fe_h2                     Faradaic efficiency for H2 production (0..1)
#   cell_voltage              V — drives electricity OPEX
#   pma_recovery              fraction recycled per pass (0..1)
#   solvent_recovery_2methf   fraction of 2-MeTHF recovered (0..1)
#
# Numbers below are back-derived from the paper's productivity report
# (0.5 mg vanillin / h / cm²-anode, 0.17 mg AV / h / cm²-anode) combined
# with the lignin:H2 stoichiometry. Refine against §2.3 mass balance when
# paper text is accessible.
# =============================================================================
LAB_DEFAULTS = {
    "vanillin_selectivity":      0.00192,   # kg vanillin / kg-lignin (~0.19%)
    "acetovanillone_selectivity": 0.00064,  # kg AV / kg-lignin (~0.064%)
    "lignin_to_h2":              12.5,      # kg-lignin / kg-H2
    "j_mA_per_cm2":              20.5,      # lab current density
    "fe_h2":                     1.0,       # 100 % FE @ 1.5 V (paper)
    "cell_voltage":              1.5,       # V — vs 1.9 V conventional water EC
    "pma_recovery":              0.99,      # in-loop recycle
    "solvent_recovery_2methf":   0.99,      # distilled and recycled
}

# Commercial-target reference (for gap reports / breakeven framing).
# These are the order-of-magnitude commercial targets we'd want to hit;
# not used in calculation, just shown by the gap-report tool.
COMMERCIAL_TARGETS = {
    "j_mA_per_cm2":              200.0,     # typical PEM electrolyzer j
    "vanillin_selectivity":      0.05,      # 5 % aromatic yield
    "acetovanillone_selectivity": 0.02,
    "pma_recovery":              0.995,
    "solvent_recovery_2methf":   0.995,
}


def build(**overrides):
    """Build the Yim 2022 lignin process at a specific operating point.

    All numeric levers default to LAB_DEFAULTS. Pass any subset as kwargs to
    explore alternative operating points — e.g. build(j_mA_per_cm2=200) builds
    the same plant at commercial-grade current density.

    Recognised overrides: see LAB_DEFAULTS keys above.
    """
    p = {**LAB_DEFAULTS, **overrides}
    # Sanity-check that callers aren't passing typos:
    unknown = set(overrides) - set(LAB_DEFAULTS)
    if unknown:
        raise ValueError(f"Unknown lever(s): {unknown}. "
                         f"Known levers: {list(LAB_DEFAULTS)}")

    vanillin_sel = p["vanillin_selectivity"]
    av_sel = p["acetovanillone_selectivity"]
    lignin_to_h2 = p["lignin_to_h2"]
    j = p["j_mA_per_cm2"]
    fe = p["fe_h2"]
    Vcell = p["cell_voltage"]
    pma_rec = p["pma_recovery"]
    solv_rec = p["solvent_recovery_2methf"]

    db = ComponentDB.default()
    if "Acetovanillone" not in db:
        db.add(Component("Acetovanillone", mw=166.17, price_low=30.0, role="output",
                         price_ref="Sigma 2024 specialty"))

    # Per-batch lab basis: `lignin_to_h2` g lignin → 1 g H2 + selectivity × lignin
    # g aromatic. Lignin is input[0] so engine's scale_factor uses kg-lignin as
    # the per-batch basis; everything else scales from there.
    ss = StreamSet()
    ss.add_input(Stream("Organosolv Lignin", lignin_to_h2,
                        recovery=0.0, category="feed",
                        note="Kraft lignin, 0.092 g/mL in 1 M H2SO4 — feedstock basis"))
    ss.add_input(Stream("PMA", 9.125, recovery=pma_rec, category="catalyst",
                        flow_mode="periodic",
                        initial_charge_kg_per_ton=80.0,
                        replacement_interval_months=36,
                        note="0.5 M × 10 mL × MW 1825 g/mol = 9.125 g/batch; "
                             "lever: pma_recovery"))
    ss.add_input(Stream("H2SO4", 0.5, recovery=0.97, category="acid_or_base",
                        note="1 M acid electrolyte"))
    ss.add_input(Stream("H2O", 12.0, recovery=0.95, category="utility"))
    ss.add_input(Stream("2-MeTHF", 4.0, recovery=solv_rec, category="solvent_extraction",
                        note="Green solvent — replaces chloroform; lever: solvent_recovery_2methf"))
    ss.add_input(Stream("Nafion 117", 0.0, category="consumable",
                        flow_mode="periodic",
                        initial_charge_kg_per_ton=0.05,
                        replacement_interval_months=60,
                        note="Membrane area scales linearly with cell stack"))

    # Output masses derived from levers:
    #   H2 mass = lignin / lignin_to_h2 × fe_h2  (Faraday law + FE haircut)
    #   Aromatic outputs = lignin × selectivity (FRP thermal property)
    h2_g_per_batch = lignin_to_h2 / lignin_to_h2 * fe   # = fe (since lignin/lignin=1)
    ss.add_output(Stream("H2", h2_g_per_batch,
                         note=f"Low-voltage HER product; lever: fe_h2 (currently {fe})"))
    ss.add_output(Stream("Vanillin", lignin_to_h2 * vanillin_sel,
                         note=f"FRP-thermal selectivity × lignin (currently {vanillin_sel:.4f}); $15/kg specialty"))
    ss.add_output(Stream("Acetovanillone", lignin_to_h2 * av_sel,
                         note=f"FRP-thermal selectivity × lignin (currently {av_sel:.4f}); $30/kg specialty"))

    # Sections — modular flow design from the paper, with explicit distillation train.
    sections = [
        ProcessSection("feedprep", "Feedstock Pretreatment",
                       "Lignin dispersion + PMA mixing tank",
                       kind="Mixer / Splitter"),
        ProcessSection("frp",      "Flow Reaction Platform (FRP × 3)",
                       "Three serial FRP plates with heat exchanger; 32 min residence. "
                       "PMA-mediated lignin oxidation — vanillin/AV selectivity is set HERE, "
                       "not at the electrolyzer.",
                       kind="Catalytic Reactor"),
        ProcessSection("ext",      "In-line LL Extraction",
                       "2-MeTHF extraction of aromatic byproducts",
                       kind="Liquid-Liquid Sep"),
        ProcessSection("dpt",      "Density Phase Separator",
                       "DPT module — aqueous PMA solution vs 2-MeTHF phase",
                       kind="Filter / Centrifuge"),
        ProcessSection("solvrec",  "Solvent Recovery (2-MeTHF still)",
                       "2-MeTHF distillation, 99 % recovery (bp 80 °C)",
                       kind="Distillation Column"),
        ProcessSection("conc",     "Aromatic Concentration",
                       "Pre-concentrate aromatic residue (vanillin + AV) before "
                       "crystallisation; reduces crystalliser duty ~3× and limits "
                       "vanillin co-loss to mother liquor.",
                       kind="Distillation Column"),
        ProcessSection("cryst",    "Vanillin Crystallisation",
                       "Cooling + pH-shift crystallisation — recovers vanillin "
                       "preferentially (it's the more crystallizable of the pair).",
                       kind="Crystallizer"),
        ProcessSection("avstill",  "AV Recovery (vacuum still)",
                       "Vacuum distillation of vanillin mother liquor to recover "
                       "acetovanillone (bp 296 °C at 1 atm → ~150 °C at 50 mbar).",
                       kind="Distillation Column"),
        ProcessSection("ec",       "Flow Electrolyzer (PMA + HER)",
                       "PMA(red) → PMA(ox) anode; HER cathode @ 1.5 V. "
                       "Sized for H2 throughput, NOT for aromatic productivity.",
                       kind="Electrochemical Cell"),
        ProcessSection("bop",      "Balance of Plant",
                       "Heat exchanger, pumps, PMA recycle line",
                       kind="Utility / BoP"),
    ]
    edges = [
        ("in:Organosolv Lignin", "feedprep", "lignin slurry"),
        ("in:H2SO4",             "feedprep", "acid"),
        ("in:PMA",               "feedprep", "PMA(ox)"),
        ("feedprep",             "frp",      "anolyte feed"),
        ("frp",                  "ext",      "PMA(red) + aromatics"),
        ("in:2-MeTHF",           "ext",      "extraction solvent"),
        ("ext",                  "dpt",      "two-phase mixture"),
        ("dpt",                  "solvrec",  "organic phase"),
        ("dpt",                  "ec",       "PMA(red) aqueous"),
        ("solvrec",              "conc",     "aromatic residue"),
        ("solvrec",              "ext",      "recycled 2-MeTHF"),    # recycle
        ("conc",                 "cryst",    "concentrated aromatics"),
        ("cryst",                "out:Vanillin", "vanillin crystals"),
        ("cryst",                "avstill",  "mother liquor (AV-rich)"),
        ("avstill",              "out:Acetovanillone", "AV distillate"),
        ("in:H2O",               "ec",       "anolyte makeup"),
        ("in:Nafion 117",        "ec",       "membrane"),
        ("ec",                   "out:H2",   "cathode product"),
        ("ec",                   "feedprep", "PMA(ox) recycle"),     # PMA loop
        ("ec",                   "bop",      ""),
    ]

    # Equipment.
    #   - Electrolyzer components scale linearly with LIGNIN throughput
    #     (since H2 output = lignin/12.5, and cell area = $/m² × m²/ton-H2/y
    #     × ton-H2/y).  Implementation note: the engine's `linear_with` path
    #     does NOT scale with capacity (latent bug, see equipment.py:90), so
    #     we use power-law with scaling_factor=1.0 instead and pre-compute
    #     the cost at cap_ref=1 t-lignin/batch.
    #   - Everything else scales 0.6 power-law with lignin throughput (input[0]).
    eq = EquipmentList()
    # Cell-area calibration at 1 t-lignin/batch (derived from levers):
    #   - H2 mass rate = lignin throughput / lignin_to_h2 × fe_h2
    #   - Required current at 100% FE: I = (kg-H2/h × 1000 g/kg) / (2 g/mol)
    #                                       × 2 e-/H2 × 96,485 C/mol-e- / 3600 s/h
    #   - Cell area = I / (j × 0.0001 cm²->m² × 1000 mA->A)
    # At 1 t-lignin/batch & 1-h batches, lignin throughput = 1 t/h = 1000 kg/h.
    BATCH_HOURS_REF = 1.0                       # matches inp.batch_hours below
    LIGNIN_KG_PER_H_AT_REF = 1000.0 / BATCH_HOURS_REF
    h2_kg_per_h_ref = LIGNIN_KG_PER_H_AT_REF / lignin_to_h2 * fe
    # 2-electron H2 + 96485 C/mol-e- + 2.016 g/mol H2 + 3600 s/h
    current_kA_ref = (h2_kg_per_h_ref * 1000.0 / 2.016) * 2 * 96485.0 / 3600.0 / 1000.0
    # j in mA/cm² → A/m² is × 10
    area_m2_ref = current_kA_ref * 1000.0 / (j * 10.0)
    ELECTRODE_AREA_AT_1TON = area_m2_ref
    MEMBRANE_AREA_AT_1TON = area_m2_ref * 4.0
    items_linear = [
        # (section, name, $/m², area at 1 t-lignin/batch, lifetime_years)
        ("Flow Electrolyzer (PMA + HER)", "Cell housing",
            10_000, ELECTRODE_AREA_AT_1TON, 30),
        ("Flow Electrolyzer (PMA + HER)", "Electrodes (Pt-free)",
            964, ELECTRODE_AREA_AT_1TON, 5),
        ("Flow Electrolyzer (PMA + HER)", "Nafion 117 membrane",
            180, MEMBRANE_AREA_AT_1TON, 5),
    ]
    for sec, name, dollar_per_m2, area_at_ref, life in items_linear:
        eq.add(Equipment(name=name, section=sec,
                         base_cost=dollar_per_m2 * area_at_ref,
                         cap_ref=1.0, scaling_factor=1.0,
                         cepci_ref=2023,
                         lifetime_years=life,
                         note=f"${dollar_per_m2:,}/m² × {area_at_ref:,.0f} m² at 1 t-lignin; linear scale-up"))

    # Non-linear (power-law 0.6) — rest of plant
    items_pl = [
        ("Feedstock Pretreatment",            "Lignin dissolution tank",     240_000),
        ("Feedstock Pretreatment",            "PMA mixing / dosing",         180_000),
        ("Flow Reaction Platform (FRP × 3)",  "FRP plates + heat exchanger", 1_950_000),
        ("In-line LL Extraction",             "Static mixer + extractor",    320_000),
        ("Density Phase Separator",           "DPT vessels",                 180_000),
        ("Solvent Recovery (2-MeTHF still)",  "2-MeTHF column + reboiler",   1_350_000),
        ("Aromatic Concentration",            "Concentration column + reb",  580_000),
        ("Vanillin Crystallisation",          "Crystallizer + centrifuge",   720_000),
        ("AV Recovery (vacuum still)",        "Vacuum column + vacuum pump", 940_000),
        ("Balance of Plant",                  "Pumps, HX, control",          980_000),
    ]
    for sec, name, base in items_pl:
        eq.add(Equipment(name, sec, base_cost=base, installation_factor=1.0,
                         cepci_ref=2023, cap_ref=1.0, scaling_factor=0.6))

    # Electricity OPEX from cell voltage and FE:
    # kWh/kg-H2 = Vcell × 2 × 96485 / (fe × 2.016 × 3600) ≈ Vcell × 26.6 / fe
    kwh_per_kg_h2 = Vcell * 2 * 96485.0 / (fe * 2.016 * 3600.0)
    electricity_per_ton_lignin_y = kwh_per_kg_h2 * 1000.0 / lignin_to_h2 * 0.116  # $/t-lignin/y
    meta = {
        # Lever-derived (DO NOT edit by hand — re-run build() with overrides)
        "Cell voltage (V)":                       Vcell,
        "Current density (mA/cm2)":               j,
        "FE (H2)":                                fe,
        "Vanillin selectivity (kg/kg-lignin)":    vanillin_sel,
        "Acetovanillone selectivity (kg/kg-lignin)": av_sel,
        "Lignin:H2 ratio (kg/kg)":                lignin_to_h2,
        "PMA recovery":                           pma_rec,
        "2-MeTHF recovery":                       solv_rec,
        # Derived
        "Electrolyzer area at 1 t-lignin/batch (m²)": ELECTRODE_AREA_AT_1TON,
        "kWh per kg-H2":                          kwh_per_kg_h2,
        "Electricity_$_per_ton_per_y":            electricity_per_ton_lignin_y,
        # Paper anchors (informational)
        "Vanillin productivity (mg/h/cm²)":       0.5,
        "Acetovanillone productivity (mg/h/cm²)": 0.17,
        "OER-free credit (kWh/kg H2 saved)":      35,
    }
    extra_opex = {
        "Heat exchanger LPS":                 24_000,
        "PMA inventory maintenance":          12_000,
    }
    extra_capex_ann = {}

    process = Process(
        name="Modular Flow Lignin Valorisation + Low-V H2 (Yim 2022 paper-grade)",
        description=("Continuous PMA-mediated lignin oxidation in 3 FRP stages, "
                     "in-line 2-MeTHF extraction (replaces chloroform), DPT "
                     "phase separator, flow electrolyzer with 1.5 V PMA-coupled "
                     "HER (no OER). H2 is the MSP product; vanillin + "
                     "acetovanillone are revenue. Source: Yim, Oh et al., "
                     "Adv Sci 9, 2204170 (2022)."),
        streams=ss, equipment=eq, sections=sections, edges=edges,
        meta=meta, extra_opex=extra_opex,
        extra_capex_annualized=extra_capex_ann,
    )
    inp = TEAInputs(
        discount_rate=0.10, lifetime_years=20, capacity_factor=0.90,
        cepci_target_year=2023, osbl_fraction=0.25,
        maintenance_fraction=0.04, operation_fraction=0.05,
        batch_hours=1.0,
        # H2 kept as msp_product for cross-check / sensitivity sweeps, but the
        # headline economics metric is $/kg-lignin (net_per_kg_feedstock).
        msp_product="H2",
        feedstock_for_economics="Organosolv Lignin",
        scales_ton=(1.0, 10.0, 100.0),
    )
    return process, db, inp
