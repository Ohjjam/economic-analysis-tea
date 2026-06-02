"""Low-temperature CO2 electrolysis to formic acid (BPM cell) - replicas of
the Shin / Hansen / Jiao baseline.

Source paper:
    Shin, Hansen, Jiao, Nature Sustainability 2021.
    "Techno-economic assessment of low-temperature carbon dioxide electrolysis"

Default product: formic acid (HCOOH) on a bipolar-membrane MEA.
The paper also reports CO (AEM, $0.44/kg), C2H4, EtOH variants — switch
`msp_product` and the relevant FE / Ar coefficients to model those.

Key numbers used (Table S7 + main text):
    - Electrolyzer stack cost   $250 / kW  (target)
    - Electricity               $0.03 / kWh
    - CO2 feedstock             $0.03 / kg
    - H2 byproduct credit       $2 / kg
    - Plant life                20 y
    - Capacity factor           96 %
    - Plant scale               50 000 kg-product / day  (≈ 18 250 t/y)
    - HCOOH baseline            FE 90 %, i = 100 mA/cm² (BPM penalty)
    - Reported MSP HCOOH        $0.59 / kg  (already feasible vs $0.50 market)
"""
from tea_engine.components import ComponentDB
from tea_engine.streams import Stream, StreamSet
from tea_engine.equipment import Equipment, EquipmentList
from tea_engine.process import Process, ProcessSection
from tea_engine.tea import TEAInputs


def build():
    db = ComponentDB.default()

    # CO2 + H2O → HCOOH + ½ O2.  Stoich: 1 g HCOOH needs 0.957 g CO2 and
    # 0.39 g H2O (assuming ~50 % single-pass conversion / target case).
    ss = StreamSet()
    ss.add_input(Stream("CO2", 1.05,  recovery=0.0,
                        note="Industrial source @ $0.03/kg, single-pass"))
    ss.add_input(Stream("H2O", 0.45,  recovery=0.0,
                        note="anolyte feed"))
    ss.add_output(Stream("HCOOH", 1.0,
                         note="Target product, BPM cell, FE 90 %"))
    ss.add_output(Stream("O2",    0.32))
    ss.add_output(Stream("H2",    0.02,
                         note="HER side-product, $2/kg credit"))

    sections = [
        ProcessSection("co2",   "CO2 Supply / Compression",
                       "Industrial CO2 @ $0.03/kg, compressed to feed",
                       kind="Pump / Compressor"),
        ProcessSection("elec",  "MEA Electrolyzer (BPM)",
                       "Bipolar-membrane MEA cell, Sn / Bi cathode → HCOOH",
                       kind="Electrochemical Cell"),
        ProcessSection("sep",   "Cathode gas/liquid separation",
                       "Flash drum: removes H2 off-gas",
                       kind="Gas-Liquid Sep"),
        ProcessSection("psa",   "Anode PSA (O2 / CO2)",
                       "Pressure swing adsorption",
                       kind="Membrane / PSA"),
        ProcessSection("dist",  "HCOOH Distillation",
                       "10 % feed concentration → product-grade HCOOH",
                       kind="Distillation Column"),
    ]
    edges = [
        ("in:CO2",  "co2",  ""),
        ("co2",     "elec", "compressed CO2"),
        ("in:H2O",  "elec", "anolyte"),
        ("elec",    "sep",  "cathode liquor"),
        ("elec",    "psa",  "anode gas"),
        ("sep",     "dist", "10 wt% HCOOH"),
        ("sep",     "out:H2", "off-gas H2"),
        ("dist",    "out:HCOOH", ""),
        ("psa",     "out:O2", ""),
    ]

    eq = EquipmentList()
    items = [
        ("CO2 Supply / Compression",      "CO2 compressor",           700_000),
        ("CO2 Supply / Compression",      "CO2 buffer tank",          250_000),
        ("MEA Electrolyzer (BPM)",        "Stack ($250/kW)",          3_800_000),
        ("MEA Electrolyzer (BPM)",        "Power conditioning",       1_100_000),
        ("MEA Electrolyzer (BPM)",        "Cooling system",           260_000),
        ("Cathode gas/liquid separation", "Flash drum",               160_000),
        ("Cathode gas/liquid separation", "Liquid pump",               45_000),
        ("Anode PSA (O2 / CO2)",          "PSA unit",                 980_000),
        ("HCOOH Distillation",            "Distillation column",     1_350_000),
        ("HCOOH Distillation",            "Reboiler / condenser",     420_000),
    ]
    for sec, name, base in items:
        eq.add(Equipment(name, sec, base_cost=base, installation_factor=1.0,
                         cepci_ref=2023, cap_ref=1.0, scaling_factor=0.6))

    # HCOOH baseline: 0.6 kWh / kg-HCOOH → at 0.96 CF and $0.03/kWh:
    #   1000 kg / y × 0.6 kWh × 0.03 = $18 / y per kg-y... too small at 1 ton baseline
    #   Use Shin's "energy efficiency 50 %" giving ~3 kWh/kg → $90/y/kg-product/y
    # Per ton-feedstock-per-year basis (1 ton product/y): roughly $90 k/y per ton.
    meta = {
        "Electricity_$_per_ton_per_y":         90_000,
        "Distillation Heat_$_per_ton_per_y":   45_000,
        "Cell voltage (V)":                    3.5,
        "Current density (mA/cm2)":            100,
        "Faradaic efficiency (HCOOH)":         0.90,
        "Electrolyzer stack ($/kW)":           250,
        "Electricity ($/kWh)":                 0.03,
        "CO2 ($/kg)":                          0.03,
    }
    extra_opex = {
        "MEA replacement (5 y)":               25_000,
    }
    extra_capex_ann = {}

    process = Process(
        name="Low-T CO2 Electrolysis → HCOOH (BPM)",
        description=("MEA-based bipolar-membrane cell producing formic acid "
                     "from CO2.  Source: Shin, Hansen, Jiao, Nat Sustain 2021. "
                     "Baseline FE 90 %, i 100 mA/cm², stack $250/kW, "
                     "electricity $0.03/kWh."),
        streams=ss, equipment=eq, sections=sections, edges=edges,
        meta=meta, extra_opex=extra_opex,
        extra_capex_annualized=extra_capex_ann,
    )
    inp = TEAInputs(
        discount_rate=0.08, lifetime_years=20, capacity_factor=0.96,
        cepci_target_year=2023, osbl_fraction=0.25,
        maintenance_fraction=0.04, operation_fraction=0.04,
        batch_hours=1.0, msp_product="HCOOH",
        scales_ton=(1.0, 5.0, 10.0),
    )
    return process, db, inp
