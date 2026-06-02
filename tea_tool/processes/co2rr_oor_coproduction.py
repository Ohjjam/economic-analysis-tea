"""Paired CO2RR + organic-oxidation reaction (OOR) coproduction electrolyzer.

Source paper:
    Na, Seo, Brown et al., Nat Commun 2019.
    "General technoeconomic analysis for electrochemical coproduction
     coupling carbon dioxide reduction with organic oxidation."

Worked example used here: cathodic CO2 → CO  +  anodic furfural → 2-furoic
acid in a single PEM cell.  The paper shows similar template for HMF→FDCA,
glycerol→glycolic acid, and others — switch the input stream and product
stream to model those.

Key numbers (CO/2-furoic-acid case):
    - CO2 capture cost          $0.06 / kg-CO2
    - Furfural feed             $1.17-1.81 / kg
    - CO market price           $0.60 / kg
    - Electrolyte (KHCO3)       $1.38 / kg, recycled 90 %
    - Organics recycle          90 %
    - PV-driven, CF = 20 %      (or grid; configurable)
    - Plant life                15 y
    - LCC mean (HER-OOR)        2-furoic acid $1.73/kg, FDCA $1.51/kg,
                                lactic acid $1.84/kg, ethyl acetate $6.06/kg
    - LCC mean (CO2RR-OER)      formic acid $8.83/kg, CO $14.18/kg,
                                methanol $30.23/kg, etc. (mostly infeasible
                                without anodic credit)
"""
from tea_engine.components import ComponentDB
from tea_engine.streams import Stream, StreamSet
from tea_engine.equipment import Equipment, EquipmentList
from tea_engine.process import Process, ProcessSection
from tea_engine.tea import TEAInputs


def build():
    db = ComponentDB.default()
    # Add furan-family components if not in default DB
    from tea_engine.components import Component
    if "Furfural" not in db:
        db.add(Component("Furfural", mw=96.08, price_low=1.50, role="input",
                         price_ref="Na 2019"))
    if "FuroicAcid" not in db:
        db.add(Component("FuroicAcid", mw=112.08, price_low=5.0, role="output",
                         price_ref="Na 2019 market"))

    # Per-batch lab basis: produce 1 g CO + 1 g 2-furoic acid (paired stoich).
    ss = StreamSet()
    ss.add_input(Stream("CO2",      1.57, recovery=0.9,
                        note="$0.06/kg-CO2, captured + recycled 90 %"))
    ss.add_input(Stream("Furfural", 0.86, recovery=0.9,
                        note="Anode feed, recycled 90 %"))
    ss.add_input(Stream("KHCO3",    0.10, recovery=0.9,
                        note="Catholyte 0.1 M, recycled 90 %"))
    ss.add_input(Stream("H2O",      2.5,  recovery=0.0))
    ss.add_output(Stream("CO",         1.0))
    ss.add_output(Stream("FuroicAcid", 1.0))

    sections = [
        ProcessSection("capture", "CO2 Capture (MEA)",
                       "Postcombustion MEA, $60/tCO2 base",
                       kind="CO2 Capture"),
        ProcessSection("feedprep","Feed Preparation",
                       "CO2 mixing tank + KHCO3; furfural feed prep",
                       kind="Mixer / Splitter"),
        ProcessSection("elec",    "Paired PEM Electrolyzer",
                       "Cathode: CO2 → CO   |   Anode: furfural → 2-furoic acid",
                       kind="Electrochemical Cell"),
        ProcessSection("catsep",  "Cathode Separation",
                       "Flash + PSA: CO/CO2/H2 split (zeolite LiX)",
                       kind="Membrane / PSA"),
        ProcessSection("ansep",   "Anode Separation",
                       "Flash → MTBE liquid-liquid extraction → distillation",
                       kind="Liquid-Liquid Sep"),
        ProcessSection("recycle", "Recycle (90 %)",
                       "Pump electrolyte and unreacted feed back",
                       kind="Recycle"),
    ]
    edges = [
        ("in:CO2",      "capture", ""),
        ("capture",     "feedprep","CO2 stream"),
        ("in:KHCO3",    "feedprep","catholyte"),
        ("in:Furfural", "feedprep","anolyte"),
        ("feedprep",    "elec",    "anolyte + catholyte"),
        ("in:H2O",      "elec",    ""),
        ("elec",        "catsep",  "cathode off-gas"),
        ("elec",        "ansep",   "anode liquid"),
        ("catsep",      "out:CO",  ""),
        ("ansep",       "out:FuroicAcid", ""),
        ("catsep",      "recycle", "unreacted CO2"),
        ("ansep",       "recycle", "unreacted furfural"),
        ("recycle",     "feedprep",""),
    ]

    eq = EquipmentList()
    items = [
        ("CO2 Capture (MEA)",        "MEA absorber column",    3_500_000),
        ("CO2 Capture (MEA)",        "Stripper + reboiler",    1_900_000),
        ("Feed Preparation",         "CO2 mixing tank",        220_000),
        ("Feed Preparation",         "Furfural storage",       180_000),
        ("Paired PEM Electrolyzer",  "PEM stack (paired)",     7_200_000),
        ("Paired PEM Electrolyzer",  "Power conditioning",     1_600_000),
        ("Paired PEM Electrolyzer",  "Cooling system",         350_000),
        ("Cathode Separation",       "Cathode flash",          150_000),
        ("Cathode Separation",       "PSA (zeolite LiX)",      1_350_000),
        ("Anode Separation",         "Anode flash",            150_000),
        ("Anode Separation",         "MTBE extraction (RDC)",  1_950_000),
        ("Anode Separation",         "Distillation column",    1_650_000),
        ("Recycle (90 %)",           "Recycle pumps + tanks",  280_000),
    ]
    for sec, name, base in items:
        eq.add(Equipment(name, sec, base_cost=base, installation_factor=1.0,
                         cepci_ref=2023, cap_ref=1.0, scaling_factor=0.6))

    meta = {
        "Electricity_$_per_ton_per_y":           220_000,
        "Heat (MEA reboiler)_$_per_ton_per_y":   140_000,
        "Solvent (MTBE) makeup_$_per_ton_per_y":  60_000,
        "PEM stack ($/kW)":                      900,
        "CO2 capture ($/kg-CO2)":                0.06,
        "Cell voltage (V)":                      2.4,
        "Current density (mA/cm2)":              200,
        "FE_CO":                                 0.85,
        "FE_furoic":                             0.85,
    }
    extra_opex = {}
    extra_capex_ann = {}

    process = Process(
        name="Paired CO2RR + OOR Coproduction (CO + 2-Furoic acid)",
        description=("Paired PEM electrolyzer with CO2 → CO at the cathode and "
                     "furfural → 2-furoic acid at the anode.  90 % electrolyte "
                     "and organic recycle.  Source: Na et al., Nat Commun 2019."),
        streams=ss, equipment=eq, sections=sections, edges=edges,
        meta=meta, extra_opex=extra_opex,
        extra_capex_annualized=extra_capex_ann,
    )
    inp = TEAInputs(
        discount_rate=0.10, lifetime_years=15, capacity_factor=0.85,
        cepci_target_year=2023, osbl_fraction=0.25,
        maintenance_fraction=0.05, operation_fraction=0.05,
        batch_hours=1.0, msp_product="FuroicAcid",
        scales_ton=(1.0, 5.0, 10.0),
    )
    return process, db, inp
