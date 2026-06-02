"""Biomass fermentation (glucose → ethanol) - illustrative TEA template.

Stoichiometry: C6H12O6 → 2 C2H5OH + 2 CO2 (theoretical 0.51 kg EtOH / kg glucose).
We use 0.46 kg/kg yield to reflect typical Saccharomyces cerevisiae performance.
"""
from tea_engine.components import ComponentDB
from tea_engine.streams import Stream, StreamSet
from tea_engine.equipment import Equipment, EquipmentList
from tea_engine.process import Process, ProcessSection
from tea_engine.tea import TEAInputs


def build():
    db = ComponentDB.default()

    ss = StreamSet()
    ss.add_input(Stream("Glucose", 1.0, recovery=0.0))
    ss.add_input(Stream("H2O",     5.0, recovery=0.0))
    ss.add_output(Stream("Ethanol", 0.46))
    ss.add_output(Stream("CO2",     0.44))

    sections = [
        ProcessSection("pretreat", "Biomass Pretreatment & Hydrolysis",
                       "Acid/enzymatic hydrolysis", kind="Catalytic Reactor"),
        ProcessSection("ferment",  "Fermentation",
                       "Yeast: glucose → ethanol",  kind="Bioreactor"),
        ProcessSection("dist",     "Distillation & Dehydration",
                       "Beer column + molecular sieve", kind="Distillation Column"),
        ProcessSection("waste",    "Stillage Treatment",
                       "Centrifuge + evaporator",   kind="Filter / Centrifuge"),
    ]
    edges = [
        ("in:Glucose", "pretreat", ""),
        ("in:H2O",     "pretreat", ""),
        ("pretreat", "ferment", "hydrolysate"),
        ("ferment",  "dist", "beer (10-12 % EtOH)"),
        ("ferment",  "out:CO2", "off-gas"),
        ("dist",     "out:Ethanol", ""),
        ("dist",     "waste", "stillage"),
    ]

    eq = EquipmentList()
    items = [
        ("Biomass Pretreatment & Hydrolysis", "Hydrolysis reactor",       1_800_000),
        ("Biomass Pretreatment & Hydrolysis", "Heat exchangers",          420_000),
        ("Fermentation",                      "Fermenter (×4)",           3_500_000),
        ("Fermentation",                      "Yeast propagation tank",   320_000),
        ("Distillation & Dehydration",        "Beer column",              1_400_000),
        ("Distillation & Dehydration",        "Rectifier column",         900_000),
        ("Distillation & Dehydration",        "Molecular sieve unit",     1_100_000),
        ("Stillage Treatment",                "Centrifuge",               260_000),
        ("Stillage Treatment",                "Evaporator",               850_000),
    ]
    for section, name, base in items:
        eq.add(Equipment(name, section, base_cost=base,
                         installation_factor=1.0, cepci_ref=2023,
                         cap_ref=1.0, scaling_factor=0.6))

    meta = {
        "Electricity_$_per_ton_per_y":   240_000,
        "Heat_$_per_ton_per_y":          580_000,
        "Cooling Water_$_per_ton_per_y": 95_000,
        "Yeast & Nutrients_$_per_ton_per_y": 35_000,
        "Yield (kg EtOH/kg glucose)":    0.46,
        "Fermentation time (h)":         48,
    }
    extra_opex = {
        "Wastewater treatment": 120_000,
    }
    extra_capex_ann = {}

    process = Process(
        name="Biomass Fermentation (Glucose → Ethanol)",
        description="Yeast fermentation of glucose with downstream distillation and dehydration to fuel-grade ethanol.",
        streams=ss, equipment=eq, sections=sections, edges=edges,
        meta=meta, extra_opex=extra_opex,
        extra_capex_annualized=extra_capex_ann,
    )
    inp = TEAInputs(
        discount_rate=0.10, lifetime_years=20, capacity_factor=0.9,
        cepci_target_year=2023, osbl_fraction=0.25,
        maintenance_fraction=0.05, operation_fraction=0.08,
        batch_hours=2.0, msp_product="Ethanol",
        scales_ton=(1.0, 5.0, 10.0),
    )
    return process, db, inp
