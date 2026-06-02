"""Nitrate-to-hydroxylamine via electrochemical reduction of waste NO3⁻.

Source paper:
    Mosalpuri, Li, Wright, ACS Sust Chem Eng 2023.
    "Techno-Economic Analysis and Life Cycle Assessment of Hydroxylamine
     Eco-Manufacturing via Wastewater Electrochemical."

Two-step electrochemical reduction:
    NO3⁻  →  NO2⁻   (FE 95 %, OD-Ag cathode, step 1)
    NO2⁻  →  NH2OH  (selective second step)

Concentrates dilute waste nitrate (7.14 mM) up to 2 M via electrodialysis,
then reduces to NH2OH and separates with a second ED unit.

Key numbers (large-scale 50 000 kg-NH2OH/d basis):
    - Reported MSP                  $5.37 / kg-NH2OH (current)
                                    $2.06 / kg-NH2OH (optimistic)
    - Market reference              $1.72 / kg
    - Electricity                   ~2.9 kWh / kg-NH2OH
    - Wastewater treatment cost     $1.48 / kg-NH2OH
    - Electrolyte cost              $1.48 / kg-NH2OH (dominant)
    - Separations cost              $0.96 / kg-NH2OH
    - Fixed cost                    $0.53 / kg-NH2OH
    - FE step 1 (NO2⁻)              95 %
    - FE step 2 (NH2OH)             60-93 % (literature)
"""
from tea_engine.components import ComponentDB
from tea_engine.streams import Stream, StreamSet
from tea_engine.equipment import Equipment, EquipmentList
from tea_engine.process import Process, ProcessSection
from tea_engine.tea import TEAInputs


def build():
    db = ComponentDB.default()
    # Add NH2OH if not present (component DB seeded by prices.yaml at runtime,
    # but keep a safe default here).
    if "NH2OH" not in db:
        from tea_engine.components import Component
        db.add(Component("NH2OH", mw=33.03, price_low=1.72, role="output",
                         price_ref="Mosalpuri 2023"))
    if "NaNO3" not in db:
        from tea_engine.components import Component
        db.add(Component("NaNO3", mw=84.99, price_low=0.50, role="input"))

    # Per-batch lab basis: produce 1 g NH2OH.
    # Stoichiometry: NaNO3 (or NO3⁻ in waste stream) → NH2OH:
    #   62 g NO3⁻ → 33 g NH2OH (theoretical) → 1.88 g NO3⁻/g NH2OH
    #   Use waste NO3⁻ (free) but charge wastewater treatment as OPEX line.
    ss = StreamSet()
    ss.add_input(Stream("NaNO3", 2.6,  recovery=0.0,
                        note="Equivalent NO3⁻ from waste stream; treat as free feedstock"))
    ss.add_input(Stream("H2O",   60.0, recovery=0.0,
                        note="Concentration step needs ~0.06 L water / g NH2OH"))
    ss.add_input(Stream("KOH",   0.05, recovery=0.999,
                        note="Catholyte make-up only"))
    ss.add_output(Stream("NH2OH", 1.0,
                         note="Target product, market $1.72/kg"))
    ss.add_output(Stream("O2",    0.5,
                         note="OER anode product"))

    sections = [
        ProcessSection("wwtp",  "Wastewater Pretreatment",
                       "Activated sludge, removes BOD/COD before NO3⁻ recovery",
                       kind="Wastewater Treatment"),
        ProcessSection("ed1",   "Nitrate Concentration (ED)",
                       "Electrodialysis: 7.14 mM → 2 M NO3⁻",
                       kind="Electrodialysis"),
        ProcessSection("ec1",   "NO3⁻ → NO2⁻ Reduction",
                       "OD-Ag cathode, FE_NO2⁻ ≈ 95 %",
                       kind="Electrochemical Cell"),
        ProcessSection("ec2",   "NO2⁻ → NH2OH Reduction",
                       "Selective second-step reduction",
                       kind="Electrochemical Cell"),
        ProcessSection("sep",   "Product Separation (ED)",
                       "Membrane ED to recover NH2OH",
                       kind="Electrodialysis"),
    ]
    edges = [
        ("in:NaNO3", "wwtp", "waste NO3⁻"),
        ("wwtp",     "ed1",  "treated stream"),
        ("in:H2O",   "ed1",  ""),
        ("ed1",      "ec1",  "concentrated NO3⁻ (2 M)"),
        ("in:KOH",   "ec1",  "electrolyte"),
        ("ec1",      "ec2",  "NO2⁻"),
        ("ec2",      "sep",  "NH2OH solution"),
        ("sep",      "out:NH2OH", ""),
        ("ec1",      "out:O2", "anode O2"),
        ("ec2",      "out:O2", ""),
    ]

    eq = EquipmentList()
    items = [
        ("Wastewater Pretreatment",     "Activated sludge tanks",   2_800_000),
        ("Wastewater Pretreatment",     "Aeration & blowers",       420_000),
        ("Nitrate Concentration (ED)",  "ED stack (concentration)", 3_100_000),
        ("Nitrate Concentration (ED)",  "Pumps + power",            520_000),
        ("NO3⁻ → NO2⁻ Reduction",       "EC reactor (OD-Ag)",       2_400_000),
        ("NO3⁻ → NO2⁻ Reduction",       "Power conditioning",       540_000),
        ("NO2⁻ → NH2OH Reduction",      "EC reactor (step 2)",      2_400_000),
        ("NO2⁻ → NH2OH Reduction",      "Power conditioning",       540_000),
        ("Product Separation (ED)",     "ED stack (NH2OH recovery)",1_700_000),
    ]
    for sec, name, base in items:
        eq.add(Equipment(name, sec, base_cost=base, installation_factor=1.0,
                         cepci_ref=2023, cap_ref=1.0, scaling_factor=0.6))

    # Electricity broken down per the paper ($/y per ton-NH2OH/y at 1 ton baseline):
    #   - NO3⁻ concentration:  0.72 kWh/kg × 1000 kg × 0.0953 $/kWh × 8400h utilization-equiv
    #   - NO3⁻ reduction:      2.06 kWh/kg
    #   - Separation:          0.13 kWh/kg
    # For ton-product baseline → multiply by 1000 kg × $0.07/kWh × duty cycle
    meta = {
        "Electrolyte_$_per_ton_per_y":          1_480_000,   # paper "electrolyte" line
        "WastewaterTreatment_$_per_ton_per_y":  1_480_000,   # paper $1.48/kg × 1000 kg/y per ton
        "Separation_Electricity_$_per_ton_per_y":  960_000,
        "EC Electricity_$_per_ton_per_y":          340_000,
        "Concentration Electricity_$_per_ton_per_y": 70_000,
        "FE step 1 (NO2-)":                     0.95,
        "FE step 2 (NH2OH)":                    0.75,
        "Electricity ($/kWh)":                  0.07,
        "Concentration step kWh/kg":            0.72,
        "Reduction step kWh/kg":                2.06,
    }
    extra_opex = {
        "Catalyst replacement":                 60_000,
    }
    extra_capex_ann = {}

    process = Process(
        name="Nitrate → Hydroxylamine (Eco-Mfg)",
        description=("Two-step electrochemical reduction of waste nitrate "
                     "(7.14 mM → NO2⁻ → NH2OH) integrated with a wastewater "
                     "treatment plant.  Source: Mosalpuri, Li, Wright, "
                     "ACS Sust Chem Eng 2023."),
        streams=ss, equipment=eq, sections=sections, edges=edges,
        meta=meta, extra_opex=extra_opex,
        extra_capex_annualized=extra_capex_ann,
    )
    inp = TEAInputs(
        discount_rate=0.10, lifetime_years=20, capacity_factor=0.9,
        cepci_target_year=2023, osbl_fraction=0.25,
        maintenance_fraction=0.04, operation_fraction=0.05,
        batch_hours=2.0, msp_product="NH2OH",
        scales_ton=(1.0, 5.0, 10.0),
    )
    return process, db, inp
