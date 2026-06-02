"""Process template recommender.

Given a reaction class (and optionally a substrate / product set), return a
default unit-op train so the user doesn't start from a blank file when
sketching a new experiment.

The output is a "template dict" that you can hand to `materialize_template`
to get a runnable Process + TEAInputs at lab-default operating points.

Currently shipped templates:
    - electrochemical_oxidation   (e.g. lignin → aromatics + H2)
    - heterogeneous_hydrogenation (e.g. CO2 → MeOH)
    - catalytic_depolymerization  (e.g. PET → BHET; lignin → bio-oil)
    - fermentation                (e.g. glucose → ethanol)
    - biocatalytic_cascade        (enzyme stages with cell separation)

API:
    from tea_engine.templates import list_templates, suggest_unit_ops
    list_templates()
    tpl = suggest_unit_ops("electrochemical_oxidation",
                           substrate="lignin", products=["vanillin", "H2"])
    print(tpl["notes"])
    print(tpl["sections"])

    # to actually build a Process:
    from tea_engine.templates import materialize_template
    process, db, inp = materialize_template(tpl)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .components import Component, ComponentDB
from .streams import Stream, StreamSet
from .equipment import Equipment, EquipmentList
from .process import Process, ProcessSection
from .tea import TEAInputs


# ----------------------------------------------------------------------------
# Internal template-building helpers
# ----------------------------------------------------------------------------

@dataclass
class _SectionSpec:
    key: str
    label: str
    description: str
    kind: str


@dataclass
class _EquipmentSpec:
    section: str
    name: str
    base_cost: float
    scaling_factor: float = 0.6
    cap_ref: float = 1.0
    lifetime_years: int = 30


def _mk_template(name: str, sections: List[_SectionSpec],
                 equipment: List[_EquipmentSpec],
                 edges: List[Tuple[str, str, str]],
                 default_levers: Dict[str, float],
                 default_meta: Dict[str, float],
                 notes: str) -> Dict[str, Any]:
    return {
        "name": name,
        "sections": sections,
        "equipment": equipment,
        "edges": edges,
        "default_levers": dict(default_levers),
        "default_meta": dict(default_meta),
        "notes": notes,
    }


# ----------------------------------------------------------------------------
# Templates
# ----------------------------------------------------------------------------

def _t_electrochemical_oxidation() -> Dict[str, Any]:
    sections = [
        _SectionSpec("feedprep", "Feedstock Pretreatment",
                     "Substrate dispersion + catalyst/mediator mixing",
                     "Mixer / Splitter"),
        _SectionSpec("rxr", "Catalytic / Flow Reactor",
                     "Mediator-driven oxidation (selectivity set here)",
                     "Catalytic Reactor"),
        _SectionSpec("ext", "Liquid-Liquid Extraction",
                     "Strip aromatic products into organic solvent",
                     "Liquid-Liquid Sep"),
        _SectionSpec("sep", "Phase Separator",
                     "Decant aqueous (mediator) vs organic (product) phase",
                     "Filter / Centrifuge"),
        _SectionSpec("solvrec", "Solvent Recovery (distillation)",
                     "Distill extraction solvent, recycle",
                     "Distillation Column"),
        _SectionSpec("conc", "Aromatic Concentration",
                     "Pre-concentrate aromatic residue",
                     "Distillation Column"),
        _SectionSpec("cryst", "Crystallization",
                     "Preferential crystallization of main product",
                     "Crystallizer"),
        _SectionSpec("byprod", "Byproduct Recovery (vacuum still)",
                     "Vacuum distillation of mother liquor for secondary product",
                     "Distillation Column"),
        _SectionSpec("ec", "Flow Electrolyzer",
                     "Mediator regeneration + co-product at counter electrode",
                     "Electrochemical Cell"),
        _SectionSpec("bop", "Balance of Plant",
                     "Pumps, HX, control, recycle lines",
                     "Utility / BoP"),
    ]
    equipment = [
        _EquipmentSpec("feedprep", "Dissolution tank",              240_000),
        _EquipmentSpec("feedprep", "Mediator dosing skid",          180_000),
        _EquipmentSpec("rxr",      "Flow reactor plates + HX",     1_950_000),
        _EquipmentSpec("ext",      "Static mixer + LL extractor",   320_000),
        _EquipmentSpec("sep",      "Phase separator vessels",       180_000),
        _EquipmentSpec("solvrec",  "Solvent column + reboiler",   1_350_000),
        _EquipmentSpec("conc",     "Concentration column",          580_000),
        _EquipmentSpec("cryst",    "Crystallizer + centrifuge",     720_000),
        _EquipmentSpec("byprod",   "Vacuum column + vac pump",      940_000),
        _EquipmentSpec("ec",       "Electrolyzer cell stack",     2_000_000, 1.0, 1.0, 30),
        _EquipmentSpec("ec",       "Electrodes (5-y life)",         100_000, 1.0, 1.0, 5),
        _EquipmentSpec("ec",       "Ion-exchange membrane",          50_000, 1.0, 1.0, 5),
        _EquipmentSpec("bop",      "Pumps, HX, control",            980_000),
    ]
    edges = [
        ("in:substrate",     "feedprep", "feed"),
        ("in:mediator",      "feedprep", "redox mediator"),
        ("in:electrolyte",   "feedprep", "supporting electrolyte"),
        ("feedprep",         "rxr",      "reaction mixture"),
        ("rxr",              "ext",      "products + mediator(red)"),
        ("in:solvent",       "ext",      "extraction solvent"),
        ("ext",              "sep",      "two-phase mix"),
        ("sep",              "solvrec",  "organic phase"),
        ("sep",              "ec",       "aqueous (mediator-red)"),
        ("solvrec",          "conc",     "residue"),
        ("solvrec",          "ext",      "recovered solvent"),
        ("conc",             "cryst",    "concentrated product"),
        ("cryst",            "out:main_product", "crystals"),
        ("cryst",            "byprod",   "mother liquor"),
        ("byprod",           "out:byproduct", "vacuum distillate"),
        ("ec",               "out:co_product", "cathode product (e.g. H2)"),
        ("ec",               "feedprep", "mediator(ox) recycle"),
        ("ec",               "bop",      ""),
    ]
    default_levers = {
        "selectivity_main":    0.05,   # 5 % yield of main product
        "selectivity_byproduct": 0.02,
        "substrate_to_coproduct": 12.5,  # kg-substrate per kg-co_product
        "j_mA_per_cm2":        200.0,
        "fe_coproduct":        1.0,
        "cell_voltage":        1.5,
        "mediator_recovery":   0.99,
        "solvent_recovery":    0.99,
    }
    default_meta = {
        "Cell voltage (V)":                1.5,
        "Current density (mA/cm2)":      200.0,
        "FE (co_product)":                 1.0,
    }
    notes = (
        "Electrochemical oxidation template (e.g. lignin → vanillin + H2).\n"
        "Selectivity is set in the catalytic reactor (rxr), NOT the electrolyzer.\n"
        "Electrolyzer sizing follows from the co-product mass balance.\n"
        "Key tunable levers: j_mA_per_cm2, selectivity_main, selectivity_byproduct."
    )
    return _mk_template("electrochemical_oxidation",
                        sections, equipment, edges,
                        default_levers, default_meta, notes)


def _t_heterogeneous_hydrogenation() -> Dict[str, Any]:
    sections = [
        _SectionSpec("h2supply", "H₂ supply / compression",
                     "H₂ from electrolysis or SMR; compressed to reactor P",
                     "Pump / Compressor"),
        _SectionSpec("co2supply", "CO₂ / substrate compression",
                     "Substrate gas/liquid feed prep + compression",
                     "Pump / Compressor"),
        _SectionSpec("rxr", "Fixed-bed catalytic reactor",
                     "Hydrogenation over supported metal catalyst",
                     "Catalytic Reactor"),
        _SectionSpec("cooler", "Reactor effluent cooler",
                     "Quench to condense product",
                     "Heat Exchanger"),
        _SectionSpec("flash", "Flash separation",
                     "Gas/liquid split — unconverted reactants recycle",
                     "Gas-Liquid Sep"),
        _SectionSpec("purif", "Product purification",
                     "Distillation column for product grade",
                     "Distillation Column"),
        _SectionSpec("recycle", "Recycle compressor + purge",
                     "Recycle unconverted H₂ and CO₂",
                     "Recycle"),
        _SectionSpec("bop", "Balance of Plant",
                     "Pumps, HX, control", "Utility / BoP"),
    ]
    equipment = [
        _EquipmentSpec("h2supply",  "H2 compressor",         1_200_000),
        _EquipmentSpec("co2supply", "Feed compressor",         800_000),
        _EquipmentSpec("rxr",       "Fixed-bed reactor",     2_400_000),
        _EquipmentSpec("rxr",       "Catalyst inventory",      300_000, 1.0, 1.0, 5),
        _EquipmentSpec("cooler",    "Effluent cooler",         350_000),
        _EquipmentSpec("flash",     "Flash drum",              280_000),
        _EquipmentSpec("purif",     "Distillation column",   1_500_000),
        _EquipmentSpec("recycle",   "Recycle compressor",      900_000),
        _EquipmentSpec("bop",       "Pumps, HX, control",      800_000),
    ]
    edges = [
        ("in:H2",          "h2supply",  ""),
        ("in:CO2",         "co2supply", ""),
        ("in:substrate",   "co2supply", ""),
        ("h2supply",       "rxr",       "compressed H2"),
        ("co2supply",      "rxr",       "compressed feed"),
        ("rxr",            "cooler",    "hot effluent"),
        ("cooler",         "flash",     "cold effluent"),
        ("flash",          "purif",     "liquid product"),
        ("flash",          "recycle",   "unreacted gases"),
        ("recycle",        "rxr",       "recycled feed"),
        ("recycle",        "bop",       "purge"),
        ("purif",          "out:product", "purified product"),
        ("purif",          "bop",       "bottoms"),
    ]
    default_levers = {
        "conversion_per_pass":  0.30,
        "selectivity":          0.95,
        "recycle_ratio":        0.95,
        "h2_per_substrate":     3.0,        # mol H2 / mol substrate
        "catalyst_lifetime_y":  5.0,
    }
    default_meta = {
        "Reactor T (°C)":  240,
        "Reactor P (bar)": 50,
    }
    notes = (
        "Heterogeneous hydrogenation template (e.g. CO₂ + H₂ → MeOH).\n"
        "Key levers: conversion_per_pass, selectivity, recycle_ratio.\n"
        "Low single-pass conversion is OK if recycle is tight."
    )
    return _mk_template("heterogeneous_hydrogenation",
                        sections, equipment, edges,
                        default_levers, default_meta, notes)


def _t_catalytic_depolymerization() -> Dict[str, Any]:
    sections = [
        _SectionSpec("mech", "Mechanical pretreatment",
                     "Grind/wash/dry the polymer feed",
                     "Pretreatment"),
        _SectionSpec("feedprep", "Slurry preparation",
                     "Solvent + catalyst dosing",
                     "Mixer / Splitter"),
        _SectionSpec("rxr", "Depolymerization reactor",
                     "CSTR or PFR with catalyst (e.g. glycolysis, methanolysis)",
                     "Catalytic Reactor"),
        _SectionSpec("filt", "Solids filtration",
                     "Remove catalyst / unreacted polymer",
                     "Filter / Centrifuge"),
        _SectionSpec("cryst", "Monomer crystallization",
                     "Cooling crystallization of monomer",
                     "Crystallizer"),
        _SectionSpec("solvrec", "Solvent recovery (distillation)",
                     "Recover and recycle solvent",
                     "Distillation Column"),
        _SectionSpec("dry", "Final drying",
                     "Dry monomer crystals to spec",
                     "Dryer"),
        _SectionSpec("bop", "Balance of Plant",
                     "Pumps, HX, control", "Utility / BoP"),
    ]
    equipment = [
        _EquipmentSpec("mech",     "Shredder + washer + dryer",   1_500_000),
        _EquipmentSpec("feedprep", "Slurry tank + dosing",          280_000),
        _EquipmentSpec("rxr",      "Depolymerization reactor",    2_200_000),
        _EquipmentSpec("filt",     "Pressure filter / centrifuge",  680_000),
        _EquipmentSpec("cryst",    "Crystallizer + cooling",        720_000),
        _EquipmentSpec("solvrec",  "Solvent column + reboiler",   1_350_000),
        _EquipmentSpec("dry",      "Rotary or fluidized dryer",     480_000),
        _EquipmentSpec("bop",      "Pumps, HX, control",            780_000),
    ]
    edges = [
        ("in:polymer",   "mech",     "raw polymer"),
        ("in:solvent",   "feedprep", "depolymerization solvent"),
        ("in:catalyst",  "feedprep", "catalyst"),
        ("mech",         "feedprep", "clean flakes"),
        ("feedprep",     "rxr",      "slurry"),
        ("rxr",          "filt",     "depolymerised mix"),
        ("filt",         "cryst",    "filtrate"),
        ("filt",         "bop",      "residual solids"),
        ("cryst",        "solvrec",  "mother liquor"),
        ("cryst",        "dry",      "monomer crystals"),
        ("solvrec",      "feedprep", "recovered solvent"),
        ("dry",          "out:monomer", "dry monomer"),
    ]
    default_levers = {
        "conversion":            0.95,
        "selectivity":           0.92,
        "catalyst_loading_wt":   0.01,
        "solvent_recovery":      0.98,
        "catalyst_recovery":     0.95,
    }
    default_meta = {
        "Reactor T (°C)":  180,
        "Residence time (h)": 4,
    }
    notes = (
        "Catalytic depolymerization template (e.g. PET methanolysis, "
        "lignin solvolysis).\n"
        "Key levers: conversion, selectivity, catalyst_recovery, solvent_recovery."
    )
    return _mk_template("catalytic_depolymerization",
                        sections, equipment, edges,
                        default_levers, default_meta, notes)


def _t_fermentation() -> Dict[str, Any]:
    sections = [
        _SectionSpec("prep", "Substrate prep + sterilization",
                     "Sterile substrate broth", "Pretreatment"),
        _SectionSpec("ferm", "Fermenter",
                     "Aerobic/anaerobic batch or fed-batch fermentation",
                     "Bioreactor"),
        _SectionSpec("cellsep", "Cell separation",
                     "Centrifugation or filtration to remove biomass",
                     "Filter / Centrifuge"),
        _SectionSpec("dist", "Distillation",
                     "Beer column + rectifier to separate product",
                     "Distillation Column"),
        _SectionSpec("dehyd", "Molecular-sieve dehydration",
                     "Final water removal (for ethanol-class products)",
                     "Membrane / PSA"),
        _SectionSpec("ww", "Wastewater treatment",
                     "Stillage / cell mass handling",
                     "Wastewater Treatment"),
        _SectionSpec("bop", "Balance of Plant",
                     "Utilities, control", "Utility / BoP"),
    ]
    equipment = [
        _EquipmentSpec("prep",    "Sterilizer + mix tank",   620_000),
        _EquipmentSpec("ferm",    "Fermenter vessel",      3_200_000),
        _EquipmentSpec("ferm",    "Aeration + cooling",      980_000),
        _EquipmentSpec("cellsep", "Centrifuge / DSP",      1_100_000),
        _EquipmentSpec("dist",    "Beer column + rectifier", 1_800_000),
        _EquipmentSpec("dehyd",   "Molecular sieve unit",    720_000),
        _EquipmentSpec("ww",      "Wastewater treatment",  1_500_000),
        _EquipmentSpec("bop",     "Pumps, HX, control",      900_000),
    ]
    edges = [
        ("in:substrate", "prep",   "sugar / cellulosic feed"),
        ("in:nutrients", "prep",   "nutrients"),
        ("prep",         "ferm",   "sterile broth"),
        ("in:culture",   "ferm",   "inoculum"),
        ("ferm",         "cellsep", "fermentation broth"),
        ("cellsep",      "dist",   "clarified broth"),
        ("cellsep",      "ww",     "biomass"),
        ("dist",         "dehyd",  "crude product"),
        ("dist",         "ww",     "stillage"),
        ("dehyd",        "out:product", "anhydrous product"),
    ]
    default_levers = {
        "yield_g_per_g_substrate": 0.45,
        "fermentation_time_h":     48,
        "productivity_g_L_h":      1.5,
        "distillation_recovery":   0.99,
    }
    default_meta = {
        "Fermenter T (°C)":  32,
        "Fermenter pH":      5.0,
    }
    notes = (
        "Fermentation template (e.g. glucose → ethanol, sugar → succinate).\n"
        "Key levers: yield, productivity, fermentation_time.\n"
        "Note: WWT can be 10-20 % of plant cost for cellulosic processes."
    )
    return _mk_template("fermentation",
                        sections, equipment, edges,
                        default_levers, default_meta, notes)


def _t_biocatalytic_cascade() -> Dict[str, Any]:
    sections = [
        _SectionSpec("prep", "Substrate prep",
                     "pH/buffer adjustment", "Mixer / Splitter"),
        _SectionSpec("rxr1", "Bioreactor 1 (enzyme A)",
                     "First enzymatic step", "Bioreactor"),
        _SectionSpec("rxr2", "Bioreactor 2 (enzyme B)",
                     "Cascade second enzymatic step", "Bioreactor"),
        _SectionSpec("uf", "Ultrafiltration",
                     "Retain enzymes, pass small-mol product",
                     "Membrane / PSA"),
        _SectionSpec("conc", "Product concentration",
                     "Evaporation / nanofiltration",
                     "Membrane / PSA"),
        _SectionSpec("dry", "Spray dryer",
                     "Final product drying", "Dryer"),
        _SectionSpec("bop", "Balance of Plant",
                     "Utilities, control", "Utility / BoP"),
    ]
    equipment = [
        _EquipmentSpec("prep", "Buffer + dosing skid",      280_000),
        _EquipmentSpec("rxr1", "Bioreactor 1",            1_800_000),
        _EquipmentSpec("rxr1", "Enzyme A inventory",        180_000, 1.0, 1.0, 1),
        _EquipmentSpec("rxr2", "Bioreactor 2",            1_800_000),
        _EquipmentSpec("rxr2", "Enzyme B inventory",        220_000, 1.0, 1.0, 1),
        _EquipmentSpec("uf",   "UF skid + membranes",       620_000, 0.6, 1.0, 3),
        _EquipmentSpec("conc", "Evaporator / NF",           950_000),
        _EquipmentSpec("dry",  "Spray dryer",               780_000),
        _EquipmentSpec("bop",  "Pumps, HX, control",        700_000),
    ]
    edges = [
        ("in:substrate", "prep", ""),
        ("in:buffer",    "prep", ""),
        ("prep",         "rxr1", "buffered substrate"),
        ("in:enzymeA",   "rxr1", "enzyme A"),
        ("rxr1",         "rxr2", "intermediate"),
        ("in:enzymeB",   "rxr2", "enzyme B"),
        ("rxr2",         "uf",   "cascade product"),
        ("uf",           "conc", "small-mol product"),
        ("uf",           "rxr1", "enzyme recycle"),
        ("conc",         "dry",  "concentrate"),
        ("dry",          "out:product", "dried product"),
    ]
    default_levers = {
        "conversion_step1":      0.85,
        "conversion_step2":      0.80,
        "enzyme_recovery":       0.90,
        "uf_recovery":           0.95,
    }
    default_meta = {
        "Reactor T (°C)":  30,
        "Reactor pH":      7.0,
    }
    notes = (
        "Biocatalytic cascade template (e.g. enzymatic conversion of "
        "biomass-derived intermediates).\n"
        "Key levers: per-step conversions, enzyme recovery, UF recovery.\n"
        "Enzyme cost can be major OPEX — recovery is critical."
    )
    return _mk_template("biocatalytic_cascade",
                        sections, equipment, edges,
                        default_levers, default_meta, notes)


# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------

_TEMPLATES: Dict[str, Callable[[], Dict[str, Any]]] = {
    "electrochemical_oxidation":   _t_electrochemical_oxidation,
    "heterogeneous_hydrogenation": _t_heterogeneous_hydrogenation,
    "catalytic_depolymerization":  _t_catalytic_depolymerization,
    "fermentation":                _t_fermentation,
    "biocatalytic_cascade":        _t_biocatalytic_cascade,
}


def list_templates() -> List[str]:
    """Available reaction-class templates."""
    return sorted(_TEMPLATES)


def suggest_unit_ops(reaction_class: str,
                     substrate: Optional[str] = None,
                     products: Optional[List[str]] = None,
                     conditions: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return a template dict for the named reaction class.

    `substrate`, `products`, `conditions` are optional context that show up in
    the `notes` string and are used to label generic streams.
    """
    if reaction_class not in _TEMPLATES:
        raise ValueError(
            f"Unknown reaction class '{reaction_class}'. "
            f"Available: {list_templates()}"
        )
    tpl = _TEMPLATES[reaction_class]()
    tpl["substrate"] = substrate
    tpl["products"] = products or []
    tpl["conditions"] = conditions or {}
    # Augment notes
    extra = []
    if substrate:
        extra.append(f"Substrate: {substrate}")
    if products:
        extra.append(f"Products: {', '.join(products)}")
    if conditions:
        extra.append(f"Conditions: {conditions}")
    if extra:
        tpl["notes"] = tpl["notes"] + "\n\nUser context:\n  " + "\n  ".join(extra)
    return tpl


def whats_missing(template: Dict[str, Any],
                  user_sections: List[str]) -> List[str]:
    """Compare user's planned section list vs template, return missing ones.

    Use this for the "what's missing" checker: pass the template you'd
    recommend and the sections the user has in their draft, get back the
    list of sections they probably forgot.
    """
    tpl_keys = {s.key for s in template["sections"]}
    user_keys = set(user_sections)
    return sorted(tpl_keys - user_keys)


def materialize_template(template: Dict[str, Any],
                         substrate_name: str = "Substrate",
                         main_product_name: str = "Product",
                         scales_ton: Tuple[float, ...] = (1.0, 10.0, 100.0)
                         ) -> Tuple[Process, ComponentDB, TEAInputs]:
    """Convert a template dict into a runnable (process, db, inp) triple.

    Streams are stubbed with the substrate/product names; equipment uses the
    template's seed base_costs; meta is populated from default_meta +
    default_levers. The result is immediately runnable through `run_tea` and
    sweep/breakeven tools (which can then refine specific values).
    """
    db = ComponentDB.default()
    if substrate_name not in db:
        db.add(Component(substrate_name, mw=200.0, price_low=0.40,
                         role="input", price_ref="template default"))
    if main_product_name not in db:
        db.add(Component(main_product_name, mw=150.0, price_low=2.0,
                         role="output", price_ref="template default"))

    ss = StreamSet()
    ss.add_input(Stream(substrate_name, 10.0, recovery=0.0, category="feed"))
    ss.add_output(Stream(main_product_name, 1.0))

    sections = [ProcessSection(s.key, s.label, s.description, s.kind)
                for s in template["sections"]]

    eq = EquipmentList()
    for e in template["equipment"]:
        eq.add(Equipment(
            name=e.name, section=_section_label_lookup(sections, e.section),
            base_cost=e.base_cost,
            scaling_factor=e.scaling_factor,
            cap_ref=e.cap_ref,
            cepci_ref=2023,
            lifetime_years=e.lifetime_years,
        ))

    process = Process(
        name=f"Template: {template['name']}",
        description=template["notes"],
        streams=ss, equipment=eq, sections=sections,
        edges=list(template["edges"]),
        meta=dict(template["default_meta"]),
    )

    inp = TEAInputs(
        discount_rate=0.10, lifetime_years=20, capacity_factor=0.90,
        cepci_target_year=2023, osbl_fraction=0.25,
        maintenance_fraction=0.04, operation_fraction=0.05,
        batch_hours=1.0, msp_product=main_product_name,
        feedstock_for_economics=substrate_name,
        scales_ton=scales_ton,
    )
    return process, db, inp


def _section_label_lookup(sections: List[ProcessSection], key: str) -> str:
    for s in sections:
        if s.key == key:
            return s.label
    return key
