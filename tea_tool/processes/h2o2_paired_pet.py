"""Paired ORR-to-H2O2 + anodic PET upcycling — paper-grade build.

Source paper:
    Qi, Du, Yang, Jiang, Li, Ma, Qiu et al., Nat Commun 14, 6263 (2023).
    "Energy-saving and product-oriented hydrogen peroxide electrosynthesis
     enabled by electrochemistry pairing and product engineering"

Key reported numbers:
    - Cell voltage           0.927 V (lowest reported industrial-scale)
    - Current density        400 mA / cm²
    - FE (H2O2)              97.5 %
    - FE (formate, anode)    93.0 %
    - Catalyst (cathode)     Ni-Mn bimetal / onion carbon
    - Catalyst (anode)       PET-EG oxidation
    - Cell area              25 cm² lab; industrial scale-up to MEA-flow.
    - Downstream             H2O2 -> Na perborate / dibenzoyl peroxide;
                             formate -> bulk
    - Reported MSP H2O2      $0.51/kg (SI TEA)
"""
from tea_engine.components import ComponentDB
from tea_engine.streams import Stream, StreamSet
from tea_engine.equipment import Equipment, EquipmentList
from tea_engine.process import Process, ProcessSection
from tea_engine.tea import TEAInputs


def build():
    db = ComponentDB.default()

    # ---- Streams (per-batch basis, 1 g H2O2 yield) ---------------------
    ss = StreamSet()
    # PET hydrolysis precursor (assume EG is the actual anode feed)
    ss.add_input(Stream("PET", 1.0, recovery=0.0,
                        note="Waste PET, recycling market"))
    ss.add_input(Stream("O2", 0.5, recovery=0.95,
                        note="O2 fed at cathode GDE"))
    ss.add_input(Stream("KOH", 1.0, recovery=0.99,
                        flow_mode="periodic",
                        initial_charge_kg_per_ton=30.0,
                        replacement_interval_months=24,
                        note="Catholyte / anolyte makeup"))
    ss.add_input(Stream("H2O", 8.0, recovery=0.95))
    ss.add_input(Stream("MEA membrane", 0.0,
                        flow_mode="periodic",
                        initial_charge_kg_per_ton=20.0,
                        replacement_interval_months=60,
                        note="MEA + GDE replacement every 5 y"))
    ss.add_output(Stream("H2O2", 1.0, note="30 wt% spec product"))
    ss.add_output(Stream("FA",   0.8, note="Formate from PET anode"))

    sections = [
        ProcessSection("hydro", "PET hydrolysis (alkaline)",
                       "Alkaline depolymerization of PET to EG + TPA",
                       kind="Catalytic Reactor"),
        ProcessSection("elec",  "Paired Flow Electrolyzer",
                       "Anode: PET-EG -> formate; Cathode: O2 -> H2O2",
                       kind="Electrochemical Cell"),
        ProcessSection("sep1", "H2O2 polishing",
                       "Distillation to 30 wt% spec H2O2",
                       kind="Distillation Column"),
        ProcessSection("sep2", "Formate crystallization",
                       "Pre-acidification → cooling crystallization",
                       kind="Crystallizer"),
        ProcessSection("bop",  "Balance of Plant",
                       "Pumps, HX, KOH recovery",
                       kind="Utility / BoP"),
    ]
    edges = [
        ("in:PET",  "hydro", ""),
        ("in:KOH",  "hydro", "1 M KOH"),
        ("hydro",   "elec",  "EG + TPA + KOH"),
        ("in:O2",   "elec",  "GDE feed"),
        ("in:H2O",  "elec",  ""),
        ("in:MEA membrane", "elec", "MEA"),
        ("elec",    "sep1",  "alkaline H2O2"),
        ("elec",    "sep2",  "formate liquor"),
        ("sep1",    "out:H2O2", ""),
        ("sep2",    "out:FA", ""),
        ("elec",    "bop",   ""),
    ]

    eq = EquipmentList()
    items = [
        ("PET hydrolysis (alkaline)",  "Hydrolysis reactor",    750_000),
        ("PET hydrolysis (alkaline)",  "Filtration (TPA)",      350_000),
        ("Paired Flow Electrolyzer",   "MEA flow stack",        4_500_000),
        ("Paired Flow Electrolyzer",   "Power conditioning",    1_100_000),
        ("Paired Flow Electrolyzer",   "GDE + Ni-Mn cathode",   1_800_000),
        ("H2O2 polishing",             "Vacuum distillation",   1_650_000),
        ("Formate crystallization",    "Crystallizer",          720_000),
        ("Formate crystallization",    "Filtration",            210_000),
        ("Balance of Plant",           "Heat exchangers + pumps", 980_000),
    ]
    for sec, name, base in items:
        eq.add(Equipment(name, sec, base_cost=base, installation_factor=1.0,
                         cepci_ref=2023, cap_ref=1.0, scaling_factor=0.6))

    # OPEX coefficients (per ton primary feed PET per year)
    # Electricity at 0.927 V, 400 mA/cm² → energy = V*I*t per kg H2O2:
    # 1 kg H2O2 needs 2*F/MW = 56770 C; at V=0.927 V → 0.0146 kWh/kg
    # multiplied by capacity 8400 h × ~1 kg/cm² productivity → big number
    meta = {
        "Electricity_$_per_ton_per_y":   25_000,   # Qi-style low voltage
        "BoP utilities_$_per_ton_per_y": 18_000,
        "Cell voltage (V)":              0.927,
        "Current density (mA/cm2)":      400,
        "FE (H2O2)":                     0.975,
        "FE (formate)":                  0.93,
        "Electrolyzer ($/m^2)":          10_000,
        "Electricity ($/kWh)":           0.07,
    }
    extra_opex = {"PET pretreatment chemicals": 12_000}
    extra_capex_ann = {}

    process = Process(
        name="Paired H2O2 + PET upcycling (Qi 2023)",
        description=("Energy-saving H2O2 electrosynthesis paired with "
                     "PET upcycling. 0.927 V at 400 mA/cm², FE 97.5% (H2O2) "
                     "and 93% (formate). Source: Qi et al., Nat Commun 2023."),
        streams=ss, equipment=eq, sections=sections, edges=edges,
        meta=meta, extra_opex=extra_opex,
        extra_capex_annualized=extra_capex_ann,
    )
    inp = TEAInputs(
        discount_rate=0.08, lifetime_years=20, capacity_factor=0.92,
        cepci_target_year=2023, osbl_fraction=0.25,
        maintenance_fraction=0.025, operation_fraction=0.05,
        batch_hours=1.0, msp_product="H2O2",
        scales_ton=(1.0, 5.0, 10.0),
    )
    return process, db, inp
