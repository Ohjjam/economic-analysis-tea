"""CO2 electrolysis to ethylene - alkaline GDE Cu cathode.

Source paper:
    Bagemihl et al., ACS Sust. Chem. Eng. 2023.
    "Techno-economic Assessment of CO2 Electrolysis: How Interdependencies
     between Model Variables Propagate across Different Modeling Scales"

Key numbers used (from paper main text & SI):
    - DAC CO2 cost           $0.04 / kg
    - Electricity            $0.03 / kWh
    - Electrolyzer capital   $920 / m²  (Jouny 2018)
    - Balance-of-plant       BoP = 35/65 × C_electrolyzer
    - Maintenance            2.5 % / y of electrolyzer capital
    - Plant life             20 y (1 build + 19 op)
    - Discount rate          10 %
    - Capacity factor        96 %  (8400 h / y)
    - Cell voltage           3.69 V (M1 baseline)
    - Faradaic efficiency    0.70 (M1 base) → 0.85-0.89 (optimised)
    - Current density        99-209 mA/cm²  (optimum found at ~100 mA/cm²)
    - Plant target           10 000 kg-C2H4 / day  →  3 500 000 kg / y
    - Reported MSP           paper reports NPV (relative), not MSP — at $1.30/kg
                             ethylene the optimised case still gave NPV ≈ -22 to -24 M$.
"""
from tea_engine.components import ComponentDB
from tea_engine.streams import Stream, StreamSet
from tea_engine.equipment import Equipment, EquipmentList
from tea_engine.process import Process, ProcessSection
from tea_engine.tea import TEAInputs


def build():
    db = ComponentDB.default()

    # ---------------------------------------------------------------- streams
    # Lab basis: 1 g C2H4 / batch (per-batch units kept consistent across
    # the rest of the tool).  CO2 stoich (1+ξ_hom/ξ_het) × (44/28) ≈ 1.84
    # at base case → 1.84 g CO2 per g C2H4.
    ss = StreamSet()
    ss.add_input(Stream("CO2",   1.84, recovery=0.0,
                        note="DAC CO2 @ $0.04/kg, fed once-through"))
    # KHCO3 catholyte: initial inventory loaded at t=0, plus continuous
    # make-up (existing 0.10 g/batch) for evaporation/purge losses.
    ss.add_input(Stream("KHCO3", 0.10, recovery=0.0,
                        note="1 M catholyte: continuous make-up + 50 kg/ton "
                             "initial inventory (one_time charge)",
                        flow_mode="one_time",
                        initial_charge_kg_per_ton=50.0))
    ss.add_input(Stream("H2O",   0.50, recovery=0.0))
    # MEA membrane: replaced every 5 y. 100 kg/ton × $4000/kg = $400k/ton
    # per replacement → $80k/ton/y annualized, matching Bagemihl.
    ss.add_input(Stream("MEA membrane", 0.0, recovery=0.0,
                        note="MEA / membrane replacement, every 5 years",
                        flow_mode="periodic",
                        initial_charge_kg_per_ton=100.0,
                        replacement_interval_months=60))
    ss.add_output(Stream("C2H4", 1.0,
                         note="Target product, $1.30/kg market"))
    ss.add_output(Stream("O2",   1.14,
                         note="OER anode product"))

    # ---------------------------------------------------------------- sections
    sections = [
        ProcessSection("dac",   "CO2 Capture (DAC)",
                       "Direct air capture, $0.04/kg-CO2 baseline",
                       kind="CO2 Capture"),
        ProcessSection("comp",  "CO2 Compression",
                       "5-bar feed compression",
                       kind="Pump / Compressor"),
        ProcessSection("elec",  "Alkaline GDE Electrolyzer",
                       "1 M KHCO3 catholyte, Cu GDE cathode → C2H4; OER anode",
                       kind="Electrochemical Cell"),
        ProcessSection("psa",   "Pressure Swing Adsorption",
                       "Separates CO2 / C2H4 / H2 in cathode off-gas",
                       kind="Membrane / PSA"),
        ProcessSection("bop",   "Balance of Plant",
                       "Heat exchangers, pumps, utilities",
                       kind="Utility / BoP"),
    ]

    edges = [
        ("in:CO2",   "dac",  ""),
        ("dac",      "comp", "CO2 (1 atm)"),
        ("comp",     "elec", "compressed CO2"),
        ("in:KHCO3", "elec", "catholyte"),
        ("in:H2O",   "elec", "anolyte feed"),
        ("elec",     "psa",  "raw cathode gas"),
        ("psa",      "out:C2H4", ""),
        ("elec",     "out:O2", "anode O2"),
        ("elec",     "bop",  ""),
    ]

    # ---------------------------------------------------------------- equipment
    # Sized at 1-ton C2H4/batch baseline → CEPCI 2023 USD installed cost.
    # Electrolyzer: $920/m² @ ~i_tot=100 mA/cm² and FE=0.85, V_cell=3.5 V.
    # For 1 ton C2H4/y throughput, area ≈ (1000 kg × 12 × 96485) / (FE×i_tot×Ar)
    # the absolute number below is illustrative — overridable in the UI.
    eq = EquipmentList()
    # Each item: (section, name, base_cost, lifetime_y_or_None)
    # Bagemihl assumes 20-y plant life with a stack swap roughly every 7 y;
    # MEA membranes are tracked separately as a periodic stream below.
    items = [
        ("CO2 Capture (DAC)",        "DAC contactor + regen",     2_500_000, None),
        ("CO2 Capture (DAC)",        "Solvent storage",           450_000,   None),
        ("CO2 Compression",          "CO2 compressor (5 bar)",    900_000,   None),
        ("Alkaline GDE Electrolyzer","GDE cell stack",            5_500_000, 7),
        ("Alkaline GDE Electrolyzer","Power conditioning",        1_400_000, None),
        ("Alkaline GDE Electrolyzer","Catholyte circulation",     320_000,   None),
        ("Pressure Swing Adsorption","PSA package (1000 m³/h ref)", 1_990_000, None),
        ("Balance of Plant",         "Heat exchangers + pumps",   2_960_000, None),
    ]
    for sec, name, base, life_y in items:
        eq.add(Equipment(name, sec, base_cost=base, installation_factor=1.0,
                         cepci_ref=2023, cap_ref=1.0, scaling_factor=0.6,
                         lifetime_years=life_y,
                         replacement_interval_years=life_y))

    # ---------------------------------------------------------------- meta + utility
    # Electricity dominates: V × i × Ar at FE 0.85, V=3.5, i=100 mA/cm², 1 ton C2H4/y
    # gives ~5.6 GWh/y → $168 k/y at $0.03/kWh.  Per ton/y at 1-ton baseline:
    meta = {
        "Electricity_$_per_ton_per_y":        168_000,
        "PSA Electricity_$_per_ton_per_y":    32_000,
        "Cell voltage (V)":                   3.69,
        "Current density (mA/cm2)":           100,
        "Faradaic efficiency (C2H4)":         0.85,
        "Electrolyzer ($/m^2)":               920,
        "Electricity ($/kWh)":                0.03,
        "DAC CO2 ($/kg)":                     0.04,
        "BoP fraction of electrolyzer":       35/65,
    }
    # MEA / membrane replacement is now expressed as a periodic Stream above
    # ($400k per replacement × 1/5y = $80k/ton/y annualized), so no flat
    # extra_opex line is needed.
    extra_opex = {}
    extra_capex_ann = {}

    process = Process(
        name="CO2 Electrolysis → Ethylene (alkaline GDE)",
        description=("Cu-GDE alkaline electrolyzer producing ethylene from "
                     "DAC-captured CO2, with PSA gas separation. "
                     "Source: Bagemihl et al., ACS Sust Chem Eng 2023."),
        streams=ss, equipment=eq, sections=sections, edges=edges,
        meta=meta, extra_opex=extra_opex,
        extra_capex_annualized=extra_capex_ann,
    )
    inp = TEAInputs(
        discount_rate=0.10, lifetime_years=20, capacity_factor=0.96,
        cepci_target_year=2023, osbl_fraction=0.25,
        maintenance_fraction=0.025, operation_fraction=0.05,
        batch_hours=1.0, msp_product="C2H4",
        scales_ton=(1.0, 5.0, 10.0),
    )
    return process, db, inp
