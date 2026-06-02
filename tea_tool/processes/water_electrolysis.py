"""Green H2 via PEM water electrolysis - illustrative TEA template.

Numbers are rough industry-typical values, intended as a starting point
that the user can override in the UI.  Not tied to a specific paper.
"""
from tea_engine.components import ComponentDB
from tea_engine.streams import Stream, StreamSet
from tea_engine.equipment import Equipment, EquipmentList
from tea_engine.process import Process, ProcessSection
from tea_engine.tea import TEAInputs


def build():
    db = ComponentDB.default()

    # Stoichiometry: 2 H2O -> 2 H2 + O2  (mass: 18 -> 2 H2)
    # We use 1 g H2O per batch as lab basis -> H2 yield 0.111 g, O2 0.889 g
    ss = StreamSet()
    ss.add_input(Stream("H2O", 1.0, recovery=0.0))
    ss.add_input(Stream("KOH", 0.05, recovery=0.999))   # alkaline electrolyte makeup
    ss.add_output(Stream("H2", 0.1119))
    ss.add_output(Stream("O2", 0.8881))

    sections = [
        ProcessSection("water", "Water Treatment & Deionization",
                       "DI / RO water polishing", kind="Pretreatment"),
        ProcessSection("stack", "Electrolyzer Stack (PEM/Alkaline)",
                       "2 H2O → 2 H2 + O2",       kind="Electrochemical Cell"),
        ProcessSection("sep",   "Gas Separation & Drying",
                       "GLS + TSA dryer",         kind="Gas-Liquid Sep"),
        ProcessSection("comp",  "H2 Compression & Storage",
                       "350 bar storage",         kind="Pump / Compressor"),
    ]
    edges = [
        ("in:H2O", "water", ""),
        ("in:KOH", "stack", "electrolyte"),
        ("water", "stack", "deionised water"),
        ("stack", "sep",   "wet H2 + O2"),
        ("sep",   "comp",  "dry H2"),
        ("comp",  "out:H2", ""),
        ("sep",   "out:O2", ""),
    ]

    eq = EquipmentList()
    # 1 ton/batch H2O baseline -> ~0.11 ton H2/batch, scale 0.6
    items = [
        ("water",  "Deionization unit",            350_000),
        ("water",  "Feed water pumps",             80_000),
        ("stack",  "Electrolyzer stack",           4_500_000),
        ("stack",  "Power conditioning (rectifier)", 1_200_000),
        ("stack",  "Cooling system",               300_000),
        ("sep",    "Gas-liquid separator",         220_000),
        ("sep",    "Drying unit (TSA)",            450_000),
        ("comp",   "H2 compressor (350 bar)",      900_000),
        ("comp",   "H2 storage tank",              500_000),
    ]
    section_label = {"water": "Water Treatment & Deionization",
                     "stack": "Electrolyzer Stack (PEM/Alkaline)",
                     "sep":   "Gas Separation & Drying",
                     "comp":  "H2 Compression & Storage"}
    for sec_key, name, base in items:
        eq.add(Equipment(name, section_label[sec_key], base_cost=base,
                         installation_factor=1.0, cepci_ref=2023,
                         cap_ref=1.0, scaling_factor=0.6))

    # Electricity dominates OPEX: ~52 kWh/kg H2 * 0.111 t H2/t H2O * 1000 = 5772 kWh/t H2O
    # at $0.07/kWh -> $404/t H2O/y at 3504 batches/y... we use $/y per ton/batch:
    # 5772 kWh/batch * 3504 batch/y * $0.07 = 1,415,400 $/y
    meta = {
        "Electricity_$_per_ton_per_y":   1_415_000,
        "Cooling Water_$_per_ton_per_y": 28_000,
        "DI Water Makeup_$_per_ton_per_y": 5_000,
        # context
        "Specific energy (kWh/kg H2)": 52,
        "Electricity ($/kWh)":         0.07,
    }
    extra_opex = {}
    extra_capex_ann = {}

    process = Process(
        name="Water Electrolysis (Green H2)",
        description="Alkaline / PEM water electrolysis to produce green hydrogen and oxygen.",
        streams=ss, equipment=eq, sections=sections, edges=edges,
        meta=meta, extra_opex=extra_opex,
        extra_capex_annualized=extra_capex_ann,
    )
    inp = TEAInputs(
        discount_rate=0.08, lifetime_years=20, capacity_factor=0.9,
        cepci_target_year=2023, osbl_fraction=0.25,
        maintenance_fraction=0.05, operation_fraction=0.05,
        batch_hours=1.0, msp_product="H2",
        scales_ton=(1.0, 5.0, 10.0),
    )
    return process, db, inp
