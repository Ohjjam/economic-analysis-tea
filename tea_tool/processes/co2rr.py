"""CO2 electroreduction (CO2RR) → CO + HCOOH + C2H4 - illustrative TEA template.

Default numbers reflect the order-of-magnitude figures in:
  - Nat Commun 12, 4679 (2021)  (electrolyzer cost & FE assumptions)
  - Joule 2 (2018) 825-832       (Cu-based CO2RR economics)
The user can override every number in the UI.
"""
from tea_engine.components import ComponentDB
from tea_engine.streams import Stream, StreamSet
from tea_engine.equipment import Equipment, EquipmentList
from tea_engine.process import Process, ProcessSection
from tea_engine.tea import TEAInputs


def build():
    db = ComponentDB.default()

    # Per-batch lab basis: 1 g CO2.  Product distribution is illustrative.
    ss = StreamSet()
    ss.add_input(Stream("CO2", 1.0, recovery=0.0))
    ss.add_input(Stream("H2O", 0.41, recovery=0.0))
    ss.add_input(Stream("KOH", 0.10, recovery=0.999))
    ss.add_output(Stream("CO",    0.30))
    ss.add_output(Stream("HCOOH", 0.25))
    ss.add_output(Stream("C2H4",  0.10))

    sections = [
        ProcessSection("capture", "CO2 Capture / Compression",
                       "Compress CO2 feed, optional capture", kind="Pump / Compressor"),
        ProcessSection("ec",      "CO2RR Electrolyzer",
                       "Cu-GDE cathode → CO/HCOOH/C2H4",       kind="Electrochemical Cell"),
        ProcessSection("sep",     "Gas-Liquid Separation",
                       "Splits cathode liquor / gas",          kind="Gas-Liquid Sep"),
        ProcessSection("dist",    "Product Distillation",
                       "HCOOH/EtOH purification",              kind="Distillation Column"),
    ]
    edges = [
        ("in:CO2", "capture", ""),
        ("capture", "ec", "compressed CO2"),
        ("in:H2O", "ec", ""),
        ("in:KOH", "ec", "electrolyte"),
        ("ec", "sep", "raw effluent"),
        ("sep", "dist", "liquid"),
        ("sep", "out:CO", "gas"),
        ("dist", "out:HCOOH", ""),
        ("dist", "out:C2H4", ""),
    ]

    eq = EquipmentList()
    items = [
        ("CO2 Capture / Compression", "CO2 compressor",       1_200_000),
        ("CO2 Capture / Compression", "CO2 storage tank",     350_000),
        ("CO2RR Electrolyzer",        "Cu-GDE electrolyzer stack", 6_500_000),
        ("CO2RR Electrolyzer",        "Power conditioning",   1_400_000),
        ("CO2RR Electrolyzer",        "Cooling system",       300_000),
        ("Gas-Liquid Separation",     "GLS package",          480_000),
        ("Gas-Liquid Separation",     "PSA for CO purification", 1_100_000),
        ("Product Distillation",      "HCOOH distillation column", 850_000),
        ("Product Distillation",      "C2H4 cryo-distillation",    2_300_000),
    ]
    for section, name, base in items:
        eq.add(Equipment(name, section, base_cost=base,
                         installation_factor=1.0, cepci_ref=2023,
                         cap_ref=1.0, scaling_factor=0.6))

    meta = {
        # rough energy: ~7 kWh/kg CO2 → $0.07 → $0.49/kg CO2.  3504 batches/y on 1 t basis -> 1,716,960 $/y
        "Electricity_$_per_ton_per_y":      1_716_000,
        "Heat_$_per_ton_per_y":             310_000,
        "Cooling Water_$_per_ton_per_y":    65_000,
        "Specific energy (kWh/kg CO2)":     7.0,
        "Electricity ($/kWh)":              0.07,
        "Faradaic efficiency (CO)":         0.6,
        "Faradaic efficiency (C2H4)":       0.3,
    }
    extra_opex = {
        "Distillation OPEX": 380_000,
    }
    extra_capex_ann = {}

    process = Process(
        name="CO2 Electroreduction (CO2RR)",
        description="Electrocatalytic CO2 reduction to CO, HCOOH and C2H4 with KOH electrolyte.",
        streams=ss, equipment=eq, sections=sections, edges=edges,
        meta=meta, extra_opex=extra_opex,
        extra_capex_annualized=extra_capex_ann,
    )
    inp = TEAInputs(
        discount_rate=0.10, lifetime_years=20, capacity_factor=0.85,
        cepci_target_year=2023, osbl_fraction=0.25,
        maintenance_fraction=0.05, operation_fraction=0.07,
        batch_hours=1.0, msp_product="HCOOH",
        scales_ton=(1.0, 5.0, 10.0),
    )
    return process, db, inp
