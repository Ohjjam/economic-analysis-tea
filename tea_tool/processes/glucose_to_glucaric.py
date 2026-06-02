"""Glucose electrolysis -> glucaric acid + H2 (paper-grade).

Source paper:
    Liu, Xu, Zhao et al., Nat Commun 11, 265 (2020).
    "Efficient electrochemical production of glucaric acid and H2 via
     glucose electrolysis"

Key reported numbers:
    - Cell voltage          1.39 V at 100 mA/cm²
    - Faradaic efficiency   87 %
    - Glucaric acid yield   83 %
    - Catalyst              NiFeOx / NiFeNx on Ni-foam
    - Reported              "54 % cheaper than chemical (nitric-acid) route"
                            i.e. ≈ $2.50/kg vs $5.40/kg market
"""
from tea_engine.components import ComponentDB
from tea_engine.streams import Stream, StreamSet
from tea_engine.equipment import Equipment, EquipmentList
from tea_engine.process import Process, ProcessSection
from tea_engine.tea import TEAInputs


def build():
    db = ComponentDB.default()

    ss = StreamSet()
    ss.add_input(Stream("Glucose", 1.20, recovery=0.0,
                        note="Bulk biomass-derived glucose"))
    ss.add_input(Stream("KOH", 1.0, recovery=0.99,
                        flow_mode="periodic",
                        initial_charge_kg_per_ton=25.0,
                        replacement_interval_months=24))
    ss.add_input(Stream("H2O", 12.0, recovery=0.95))
    ss.add_output(Stream("Glucaric acid", 1.0,
                         note="Target product, 98% purity"))
    ss.add_output(Stream("H2", 0.067,
                         note="HER co-product, $2-8/kg"))

    sections = [
        ProcessSection("feedprep", "Glucose dissolution",
                       "1 M KOH glucose solution prep",
                       kind="Mixer / Splitter"),
        ProcessSection("elec",   "Paired Glucose Electrolyzer",
                       "Anode: glucose -> glucaric acid (NiFe); Cathode: HER",
                       kind="Electrochemical Cell"),
        ProcessSection("sep",   "Glucaric crystallization",
                       "Acidification + cooling crystallization",
                       kind="Crystallizer"),
        ProcessSection("psa",   "H2 polishing",
                       "PSA / membrane",
                       kind="Membrane / PSA"),
    ]
    edges = [
        ("in:Glucose", "feedprep", ""),
        ("in:KOH",     "feedprep", ""),
        ("in:H2O",     "feedprep", ""),
        ("feedprep",   "elec",     "anolyte + catholyte"),
        ("elec",       "sep",      "alkaline glucarate"),
        ("elec",       "psa",      "wet H2"),
        ("sep",        "out:Glucaric acid", ""),
        ("psa",        "out:H2",   ""),
    ]

    eq = EquipmentList()
    items = [
        ("Glucose dissolution",        "Mix tank + dosing",     180_000),
        ("Paired Glucose Electrolyzer","Stack (NiFe / Ni foam)", 2_900_000),
        ("Paired Glucose Electrolyzer","Power conditioning",     950_000),
        ("Paired Glucose Electrolyzer","Cooling system",         280_000),
        ("Glucaric crystallization",   "Crystallizer",           650_000),
        ("Glucaric crystallization",   "Centrifuge + dryer",     420_000),
        ("H2 polishing",               "PSA + dehumidifier",     480_000),
    ]
    for sec, name, base in items:
        eq.add(Equipment(name, sec, base_cost=base, installation_factor=1.0,
                         cepci_ref=2023, cap_ref=1.0, scaling_factor=0.6))

    meta = {
        "Electricity_$_per_ton_per_y":    45_000,   # 1.39 V, 100 mA/cm²
        "BoP utilities_$_per_ton_per_y":  18_000,
        "Cell voltage (V)":               1.39,
        "Current density (mA/cm2)":       100,
        "FE (Glucaric)":                  0.87,
        "Yield (Glucaric)":               0.83,
        "Electricity ($/kWh)":            0.07,
    }
    extra_opex = {}
    extra_capex_ann = {}

    process = Process(
        name="Glucose -> Glucaric acid + H2 (Liu 2020)",
        description=("Paired glucose electrolysis on NiFe oxide / nitride "
                     "anode. 100 mA/cm² at 1.39 V, FE 87 %, yield 83 %. "
                     "Source: Liu et al., Nat Commun 11, 265 (2020)."),
        streams=ss, equipment=eq, sections=sections, edges=edges,
        meta=meta, extra_opex=extra_opex,
        extra_capex_annualized=extra_capex_ann,
    )
    inp = TEAInputs(
        discount_rate=0.08, lifetime_years=20, capacity_factor=0.92,
        cepci_target_year=2023, osbl_fraction=0.25,
        maintenance_fraction=0.025, operation_fraction=0.05,
        batch_hours=2.0, msp_product="Glucaric acid",
        scales_ton=(1.0, 5.0, 10.0),
    )
    return process, db, inp
