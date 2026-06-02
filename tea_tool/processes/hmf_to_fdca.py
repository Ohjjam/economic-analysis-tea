"""HMF -> FDCA electrochemical oxidation (paper-grade).

Source paper:
    Roylance & Choi et al., TEA of FDCA production through electrocatalytic
    processes (Green Chem / Joule families).

Key numbers from TEA:
    - Productivity target  10 000 ton FDCA / y
    - Cell voltage         1.45 V (typical) at 120 mA/cm²
    - Faradaic efficiency  80 %
    - FDCA yield           90 %
    - Separation           two-step pH-shift crystallisation, 95 % each
    - Reported MSP         €3.67/kg ≈ $4.00/kg
    - Catalyst             Ni/NiOOH foam (non-noble)
"""
from tea_engine.components import ComponentDB
from tea_engine.streams import Stream, StreamSet
from tea_engine.equipment import Equipment, EquipmentList
from tea_engine.process import Process, ProcessSection
from tea_engine.tea import TEAInputs


def build():
    db = ComponentDB.default()

    ss = StreamSet()
    ss.add_input(Stream("HMF", 1.0, recovery=0.0,
                        note="Bio-derived HMF, ~$2.5/kg bulk"))
    ss.add_input(Stream("KOH", 1.7, recovery=0.99,
                        flow_mode="periodic",
                        initial_charge_kg_per_ton=40.0,
                        replacement_interval_months=24))
    ss.add_input(Stream("H2O", 25.0, recovery=0.95))
    ss.add_output(Stream("FDCA", 1.0, note="2,5-furandicarboxylic acid"))
    ss.add_output(Stream("H2", 0.0387, note="HER cathode product"))

    sections = [
        ProcessSection("feedprep", "HMF dissolution",
                       "Saturated KOH-HMF anolyte preparation",
                       kind="Mixer / Splitter"),
        ProcessSection("elec",   "FDCA Electrolyzer (Ni/NiOOH)",
                       "Anode: HMF -> FDCA; Cathode: HER",
                       kind="Electrochemical Cell"),
        ProcessSection("cryst1","pH-shift crystallization (step 1)",
                       "Acidification to pH 1, FDCA precipitate",
                       kind="Crystallizer"),
        ProcessSection("cryst2","pH-shift crystallization (step 2)",
                       "Re-dissolution, second crystallization",
                       kind="Crystallizer"),
        ProcessSection("filter","Filtration / drying",
                       "Centrifuge + dryer",
                       kind="Filter / Centrifuge"),
        ProcessSection("psa", "H2 polishing", "PSA", kind="Membrane / PSA"),
    ]
    edges = [
        ("in:HMF",     "feedprep", ""),
        ("in:KOH",     "feedprep", ""),
        ("in:H2O",     "feedprep", ""),
        ("feedprep",   "elec",     "alkaline HMF"),
        ("elec",       "cryst1",   "alkaline FDCA"),
        ("cryst1",     "cryst2",   "wet FDCA"),
        ("cryst2",     "filter",   ""),
        ("filter",     "out:FDCA", ""),
        ("elec",       "psa",      "wet H2"),
        ("psa",        "out:H2",   ""),
    ]

    eq = EquipmentList()
    items = [
        ("HMF dissolution",                  "Mix tank + dosing",     180_000),
        ("FDCA Electrolyzer (Ni/NiOOH)",     "Stack (Ni/NiOOH foam)", 3_400_000),
        ("FDCA Electrolyzer (Ni/NiOOH)",     "Power conditioning",    1_000_000),
        ("FDCA Electrolyzer (Ni/NiOOH)",     "Cooling system",        260_000),
        ("pH-shift crystallization (step 1)","Crystallizer + agitator", 720_000),
        ("pH-shift crystallization (step 2)","Crystallizer",          560_000),
        ("Filtration / drying",              "Centrifuge + dryer",    420_000),
        ("H2 polishing",                     "PSA + dehumidifier",    430_000),
    ]
    for sec, name, base in items:
        eq.add(Equipment(name, sec, base_cost=base, installation_factor=1.0,
                         cepci_ref=2023, cap_ref=1.0, scaling_factor=0.6))

    meta = {
        "Electricity_$_per_ton_per_y":   60_000,
        "Cell voltage (V)":              1.45,
        "Current density (mA/cm2)":      120,
        "FE (FDCA)":                     0.80,
        "Yield (FDCA)":                  0.90,
        "Electricity ($/kWh)":           0.07,
    }
    extra_opex = {}
    extra_capex_ann = {}

    process = Process(
        name="HMF -> FDCA (Ni/NiOOH, electrochemical)",
        description=("Continuous electrochemical oxidation of HMF on "
                     "Ni/NiOOH foam followed by two-step pH-shift "
                     "crystallisation. TEA target 10 000 t/y, MSP $4/kg."),
        streams=ss, equipment=eq, sections=sections, edges=edges,
        meta=meta, extra_opex=extra_opex,
        extra_capex_annualized=extra_capex_ann,
    )
    inp = TEAInputs(
        discount_rate=0.08, lifetime_years=20, capacity_factor=0.92,
        cepci_target_year=2023, osbl_fraction=0.25,
        maintenance_fraction=0.025, operation_fraction=0.05,
        batch_hours=2.0, msp_product="FDCA",
        scales_ton=(1.0, 5.0, 10.0),
    )
    return process, db, inp
