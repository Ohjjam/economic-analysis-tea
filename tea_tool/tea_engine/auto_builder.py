"""Auto-builder: turn an `Experiment` YAML into a runnable Process / TEA.

This produces a sensible *first-cut* topology with three sections:

    Pretreatment  →  Reaction  →  Separation

It picks unit-operation kinds from the experiment's `reaction_type` and the
downstream methods listed, sizes a single placeholder equipment item per
section using rough capex correlations, and registers all components in
a fresh ComponentDB (merging with the project default DB).

The goal is to let the user click **"Run TEA from experiment"** in the
Streamlit app and immediately see a CAPEX/OPEX/MSP table — Claude Code can
then refine the process by writing `processes/from_experiment_<slug>.py`
with hand-tuned equipment costs and stream recovery.
"""
from __future__ import annotations
from typing import Dict, List, Tuple

from .components import Component, ComponentDB
from .equipment import Equipment, EquipmentList
from .experiment import Experiment
from .process import Process, ProcessSection
from .streams import Stream, StreamSet
from .tea import TEAInputs


# ---------------------------------------------------------------- Mapping rules
_REACTION_TO_UNIT: Dict[str, Tuple[str, str]] = {
    # reaction_type -> (section label, UNIT_TYPES key)
    "thermal":          ("Thermal Reaction",        "Thermal Reactor"),
    "catalytic":        ("Catalytic Reaction",      "Catalytic Reactor"),
    "electrochemical":  ("Electrochemical Cell",    "Electrochemical Cell"),
    "photochemical":    ("Photochemical Reaction",  "Catalytic Reactor"),
    "biological":       ("Bioreactor",              "Bioreactor"),
    "hybrid":           ("Reaction (Hybrid)",       "Generic"),
    "unspecified":      ("Reaction",                "Generic"),
}

# Per-reaction-type CAPEX defaults at cap_ref = 1 ton/batch, CEPCI 2016 $.
# These are intentionally rough — refine in processes/from_experiment_*.py.
_REACTION_CAPEX: Dict[str, float] = {
    "thermal":          250_000,
    "catalytic":        400_000,
    "electrochemical":  1_500_000,
    "photochemical":    800_000,
    "biological":       900_000,
    "hybrid":           600_000,
    "unspecified":      400_000,
}


_DOWNSTREAM_UNIT_MAP: Dict[str, Tuple[str, float]] = {
    # method-keyword -> (UNIT_TYPES key, base capex $ at 1 ton/batch)
    "distillation":         ("Distillation Column",   500_000),
    "extraction":           ("Liquid-Liquid Sep",     250_000),
    "crystallisation":      ("Crystallizer",          300_000),
    "crystallization":      ("Crystallizer",          300_000),
    "filtration":           ("Filter / Centrifuge",   100_000),
    "filter":               ("Filter / Centrifuge",   100_000),
    "centrifuge":           ("Filter / Centrifuge",   150_000),
    "membrane":             ("Membrane / PSA",        350_000),
    "psa":                  ("Membrane / PSA",        450_000),
    "absorption":           ("Absorber / Stripper",   200_000),
    "stripping":            ("Absorber / Stripper",   200_000),
    "drying":               ("Dryer",                 150_000),
    "electrodialysis":      ("Electrodialysis",       600_000),
}


def _kind_for_downstream(method: str) -> Tuple[str, float]:
    m = method.lower()
    for key, val in _DOWNSTREAM_UNIT_MAP.items():
        if key in m:
            return val
    return ("Filter / Centrifuge", 100_000)


# ---------------------------------------------------------------- Builder core
def _ensure_component(db: ComponentDB, name: str, role: str, price: float | None) -> None:
    """Insert a placeholder Component if `name` is unknown to the DB."""
    if name in db:
        if price is not None and db.get(name).price_low in (None, 0.0):
            db.components[name].price_low = float(price)
        return
    db.add(Component(
        name=name,
        mw=1.0,                  # unknown — irrelevant for TEA (mass basis only)
        price_low=float(price) if price is not None else 0.0,
        price_ref="from experiment YAML",
        role=role,
    ))


def _classify_reagent(r) -> str:
    """Return a topology category for a feedstock reagent."""
    role = (r.role or "").lower()
    name = (r.name or "").lower()
    # Name-based wins over role — H2SO4 is acid even if YAML says role=solvent.
    if any(a in name for a in ("h2so4", "sulfuric", "naoh", "koh", "hno3",
                               "h3po4", "hcl", "h2so")):
        return "acid_or_base"
    if "membrane" in name or "nafion" in name or "mea" in name or "gde" in name:
        return "consumable"
    # Extraction solvents matched by name regardless of declared role.
    extraction_solvents = ("chloroform", "2-meth", "methf", "ethyl acetate",
                           "mtbe", "toluene", "hexane", "dichloromethane", "dcm",
                           "ionic liquid", "ionic_liquid")
    if any(s in name for s in extraction_solvents):
        return "solvent_extraction"
    if role == "solvent":
        return "solvent_reaction"
    if role == "catalyst":
        return "catalyst"
    if role == "utility":
        return "utility"
    return "feed"


def _classify_downstream(d) -> str:
    """Categorize a downstream step into one of:
    extraction / phase_split / solvent_recovery / product_recovery /
    electrolyzer / gas_separation / generic.
    Used by the topology builder to wire branches and recycles correctly.
    """
    s = ((d.step or "") + " " + (d.method or "")).lower()
    if any(k in s for k in ("electrolyz", "reactivat", "regen pma", "pma reactivation",
                            "her")):
        return "electrolyzer"
    if any(k in s for k in ("density", "phase separat", "decanter", "dpt")):
        return "phase_split"
    if any(k in s for k in ("extract", "liquid-liquid", "ll extraction", "ll sep")):
        return "extraction"
    if any(k in s for k in ("distillation", "distill", "solvent recovery",
                            "solvent rec")):
        return "solvent_recovery"
    if any(k in s for k in ("psa", "membrane sep", "pressure swing")):
        return "gas_separation"
    if any(k in s for k in ("crystall", "crystalliz", "filtration", "filter",
                            "centrifuge", "polish", "drying", "dryer")):
        return "product_recovery"
    return "generic"


def _section_keys_by_cat(downstream) -> Dict[str, List[str]]:
    """Map downstream-step category → list of section keys (sepN)."""
    out: Dict[str, List[str]] = {}
    for i, d in enumerate(downstream, start=1):
        cat = _classify_downstream(d)
        out.setdefault(cat, []).append(f"sep{i}")
    return out


def _find_extraction_section_key(downstream) -> Optional[str]:
    keys = _section_keys_by_cat(downstream).get("extraction", [])
    return keys[0] if keys else None


def _find_solvent_recovery_section_key(downstream) -> Optional[str]:
    keys = _section_keys_by_cat(downstream).get("solvent_recovery", [])
    return keys[0] if keys else None


def _find_electrolyzer_section_key(downstream, default_rxn_key="rxn") -> str:
    keys = _section_keys_by_cat(downstream).get("electrolyzer", [])
    return keys[0] if keys else default_rxn_key


def _match_output_to_section(product: str, sec_map: Dict[str, List[str]],
                             rxn_key: str, last_key: str) -> str:
    """Pick the most semantically appropriate section for an output stream."""
    p = product.lower()
    # Gas products → electrolyzer or gas separator
    if p in ("h2", "co", "o2", "c2h4", "h2o2"):
        if "electrolyzer" in sec_map and sec_map["electrolyzer"]:
            return sec_map["electrolyzer"][0]
        if "gas_separation" in sec_map and sec_map["gas_separation"]:
            return sec_map["gas_separation"][0]
    # Solid / liquid organic products → crystallization / product recovery
    if "product_recovery" in sec_map and sec_map["product_recovery"]:
        return sec_map["product_recovery"][-1]
    # Solvent recovery as fallback for crude product output
    if "solvent_recovery" in sec_map and sec_map["solvent_recovery"]:
        return sec_map["solvent_recovery"][0]
    return last_key


def build_process_from_experiment(exp: Experiment) -> Tuple[Process, ComponentDB, TEAInputs]:
    """Construct a first-cut Process + ComponentDB + TEAInputs from `exp`."""
    db = ComponentDB.default()

    # ---- Components from the experiment --------------------------------
    fp = exp.feedstock_primary
    assert fp is not None
    _ensure_component(db, fp.name, "input", fp.price_usd_per_kg)
    for r in exp.feedstock_reagents:
        role = r.role if r.role in ("catalyst", "solvent", "utility") else "input"
        _ensure_component(db, r.name, role, r.price_usd_per_kg)

    # Yield-derived output streams
    feed_g = fp.mass_per_batch_g
    output_streams: List[Stream] = []
    for y in exp.results_yields:
        _ensure_component(db, y.product, "output", None)
        prod_g = feed_g * (y.yield_pct / 100.0)
        output_streams.append(Stream(y.product, prod_g, role="output"))

    # ---- Streams (with topology categories) ----------------------------
    streams = StreamSet()
    streams.add_input(Stream(fp.name, fp.mass_per_batch_g,
                             role="input", recovery=0.0, category="feed"))
    reagent_categories: Dict[str, str] = {}
    for r in exp.feedstock_reagents:
        cat = _classify_reagent(r)
        reagent_categories[r.name] = cat
        streams.add_input(Stream(r.name, r.mass_per_batch_g,
                                 role="input", recovery=r.recovery_fraction,
                                 category=cat))
    for o in output_streams:
        streams.add_output(o)

    # ---- Sections (Pretreatment → Reaction stages → Separation chain) ----
    sections: List[ProcessSection] = [
        ProcessSection("pretreat", "Feedstock Pretreatment",
                       "Dissolution / mixing of feed with catalyst & acid.",
                       kind="Mixer / Splitter"),
    ]

    # Multi-stage reaction support. Each stage gets its own ProcessSection
    # with the operating conditions baked into the label.
    stage_keys: List[str] = []
    for idx, st in enumerate(exp.stages):
        key = f"rxn{idx+1}" if len(exp.stages) > 1 else "rxn"
        stage_type = (st.get("type") or exp.reaction_type or "unspecified").lower()
        st_label_base, kind_key = _REACTION_TO_UNIT.get(stage_type,
                                                        _REACTION_TO_UNIT["unspecified"])
        # Build a descriptive label with operating conditions
        conds = []
        if st.get("T_C") is not None:
            conds.append(f"{st['T_C']:g} °C")
        if st.get("P_bar") is not None and st.get("P_bar") not in (1, 1.0):
            conds.append(f"{st['P_bar']:g} bar")
        if st.get("residence_h") is not None:
            rh = st["residence_h"]
            if rh < 1:
                conds.append(f"{rh*60:g} min")
            else:
                conds.append(f"{rh:g} h")
        if st.get("V") is not None:
            conds.append(f"{st['V']:g} V")
        if st.get("j_mA_cm2") is not None:
            conds.append(f"{st['j_mA_cm2']:g} mA/cm²")
        if st.get("FE_pct") is not None:
            conds.append(f"FE {st['FE_pct']:g}%")
        if st.get("heating_method"):
            conds.append(str(st["heating_method"]))
        st_name = st.get("name") or st_label_base
        cond_str = " · ".join(conds)
        full_label = f"{st_name}\n{cond_str}" if cond_str else st_name
        desc = st.get("description") or exp.chemistry.get("description", "")
        sections.append(ProcessSection(key, full_label, desc, kind=kind_key))
        stage_keys.append(key)

    # Chain stages in series
    for a, b in zip(stage_keys, stage_keys[1:]):
        edges_stage_chain = (a, b, "intermediate")
    # (collected in `edges` below; placeholder)
    last_reaction_key = stage_keys[-1]
    # The "rxn" key downstream code references — keep for legacy
    rxn_alias = stage_keys[0]
    # Last stage's UNIT_TYPE keys for the equipment block downstream
    last_stage_type = (exp.stages[-1].get("type") or exp.reaction_type or "unspecified").lower()
    sec_label, kind_key = _REACTION_TO_UNIT.get(last_stage_type,
                                                _REACTION_TO_UNIT["unspecified"])

    # Downstream chain — branch-aware topology
    edges: List[Tuple[str, str, str]] = []
    sec_map = _section_keys_by_cat(exp.downstream)
    last_key = last_reaction_key

    # Stage-to-stage edges (multi-stage reactions)
    for a, b in zip(stage_keys, stage_keys[1:]):
        edges.append((a, b, "intermediate"))
    # Pretreat feeds the first reaction stage
    edges.append(("pretreat", rxn_alias, "feed slurry"))

    if exp.downstream:
        # First, create all section nodes
        for i, d in enumerate(exp.downstream, start=1):
            key = f"sep{i}"
            ds_kind, _ = _kind_for_downstream(d.method)
            sections.append(ProcessSection(key, d.step, d.method, kind=ds_kind))

        # Now wire edges based on category. The canonical paired-electrolysis
        # flow is:
        #   rxn → extraction → phase_split
        #      ├─ (organic phase) → solvent_recovery → product_recovery
        #      │                        ├─ recycle solvent → extraction
        #      │                        └─ → product outputs
        #      └─ (aqueous phase) → electrolyzer
        #                              ├─ → H2 / gas outputs
        #                              ├─ recycle catalyst → pretreat
        #                              └─ gas_separation (if present)
        ext_key   = sec_map.get("extraction",       [None])[0]
        split_key = sec_map.get("phase_split",      [None])[0]
        rec_keys  = sec_map.get("solvent_recovery", [])
        rec_key   = rec_keys[0] if rec_keys else None
        ec_key    = sec_map.get("electrolyzer",     [None])[0]
        psa_key   = sec_map.get("gas_separation",   [None])[0]
        prod_keys = sec_map.get("product_recovery", [])
        # last reaction stage → first downstream section
        first_after_rxn = ext_key or split_key or ec_key or (prod_keys[0] if prod_keys else None) or rec_key
        if first_after_rxn:
            edges.append((last_reaction_key, first_after_rxn, "crude product"))

        # Extraction → phase split (or directly to solvent recovery)
        if ext_key:
            next_after_ext = split_key or rec_key or (prod_keys[0] if prod_keys else None)
            if next_after_ext:
                edges.append((ext_key, next_after_ext, "biphasic mixture"))

        # Phase split → solvent_recovery (organic) and electrolyzer (aqueous)
        if split_key:
            if rec_key:
                edges.append((split_key, rec_key, "organic phase"))
            if ec_key:
                edges.append((split_key, ec_key, "aqueous phase"))
            # if no electrolyzer but a product recovery — feed organic into that
            if not ec_key and prod_keys and not rec_key:
                edges.append((split_key, prod_keys[0], "organic phase"))

        # Solvent recovery → product recovery + recycle to extraction
        if rec_key:
            if prod_keys:
                edges.append((rec_key, prod_keys[0], "concentrated product"))
            if ext_key:
                edges.append((rec_key, ext_key, "recycle solvent"))

        # Electrolyzer → gas separation (if present) and recycle catalyst to pretreat
        if ec_key:
            edges.append((ec_key, "pretreat", "recycle catalyst / electrolyte"))
            if psa_key:
                edges.append((ec_key, psa_key, "wet gas"))

        # Chain any remaining product_recovery steps (cryst → filter → dryer)
        for a, b in zip(prod_keys, prod_keys[1:]):
            edges.append((a, b, "stream"))

        # Determine "last" key for fallback output routing
        last_key = (prod_keys[-1] if prod_keys
                    else (rec_key or ec_key or split_key or ext_key)
                    or last_key)
    else:
        sections.append(ProcessSection("sep", "Product Separation",
                                       "Recovery + polishing.",
                                       kind="Liquid-Liquid Sep"))
        edges.append((last_reaction_key, "sep", "crude product"))
        last_key = "sep"

    # ---- Topology-aware input edges ------------------------------------
    # feed + utility + acid + catalyst → pretreat → rxn
    # extraction-solvent → extraction step (if found), else last separator
    # consumable (membrane) → electrolyzer step (if found), else rxn
    ext_key = _find_extraction_section_key(exp.downstream)
    rec_key = _find_solvent_recovery_section_key(exp.downstream)
    ec_key = _find_electrolyzer_section_key(exp.downstream, default_rxn_key="rxn")

    edges.insert(0, (f"in:{fp.name}", "pretreat", ""))
    for r in exp.feedstock_reagents:
        cat = reagent_categories[r.name]
        is_recycled = r.recovery_fraction >= 0.95
        if cat in ("catalyst", "acid_or_base", "utility", "solvent_reaction"):
            target = "pretreat"
            base_lab = cat.replace("_", " ")
        elif cat == "solvent_extraction" and ext_key is not None:
            target = ext_key
            base_lab = "extraction solvent"
        elif cat == "consumable":
            target = ec_key
            base_lab = "membrane/GDE"
        else:
            target = "pretreat"
            base_lab = ""
        if is_recycled and cat != "consumable":
            # Two arrows: bold initial charge + dashed makeup
            edges.append((f"in:{r.name}", target, f"{base_lab} (initial charge)"))
            edges.append((f"in:{r.name}", target, f"{base_lab} makeup ({(1-r.recovery_fraction)*100:.1f}% drag-out)"))
        else:
            edges.append((f"in:{r.name}", target, base_lab))

    # ---- Recycle loops (rendered as dashed edges by viewer) ------------
    # Origin section is chosen by category:
    #   catalyst / acid / utility live in the aqueous loop → exit at EC
    #     (paired electrolysis) or last separator → back to pretreat
    #   extraction solvent → solvent recovery (distillation) → back to extraction
    aqueous_exit = ec_key if ec_key and ec_key != "rxn" else last_key
    for r in exp.feedstock_reagents:
        cat = reagent_categories[r.name]
        if r.recovery_fraction >= 0.5:
            if cat in ("catalyst", "acid_or_base", "solvent_reaction", "utility"):
                edges.append((aqueous_exit, "pretreat",
                              f"recycle {r.name} ({r.recovery_fraction*100:.0f}%)"))
            elif cat == "solvent_extraction" and rec_key is not None and ext_key is not None:
                edges.append((rec_key, ext_key,
                              f"recycle {r.name} ({r.recovery_fraction*100:.0f}%)"))

    # ---- Output edges: route each output to its semantic source section ---
    for o in output_streams:
        target = _match_output_to_section(o.component, sec_map, "rxn", last_key)
        edges.append((target, f"out:{o.component}", ""))

    # ---- Dedupe + merge edges -----------------------------------------
    # Strategy:
    # 1. Drop exact-duplicate (src, dst, label) triples.
    # 2. Same (src, dst) with MULTIPLE recycle labels → merge into one
    #    edge with a combined label ("recycle PMA, H2SO4, H2O").
    # 3. Same (src, dst) where one label is empty/generic and the other
    #    is informative → keep the informative one (single arrow).
    # 4. initial-charge vs makeup (different semantics) → keep both arrows.
    triples_seen: set = set()
    pair_buckets: Dict[Tuple[str, str], List[str]] = {}
    pair_order: List[Tuple[str, str]] = []
    for src, dst, lab in edges:
        t = (src, dst, lab)
        if t in triples_seen:
            continue
        triples_seen.add(t)
        key = (src, dst)
        if key not in pair_buckets:
            pair_buckets[key] = []
            pair_order.append(key)
        pair_buckets[key].append(lab)

    def _merge_labels(labels: List[str]) -> List[str]:
        """Return the simplified label list for one (src, dst) pair."""
        # Separate by kind
        recycles = [l for l in labels if "recycle" in l.lower()]
        makeups  = [l for l in labels if "makeup" in l.lower()]
        initials = [l for l in labels if "initial charge" in l.lower()]
        others   = [l for l in labels
                    if l and l not in recycles + makeups + initials]
        result = []
        # Collapse recycles into one line: "recycle X (95%), Y (99%), ..."
        if recycles:
            items = []
            for r in recycles:
                # Strip the leading "recycle " or "recycle: " then dedupe
                token = r
                lo = r.lower()
                if lo.startswith("recycle "):
                    token = r[len("recycle "):]
                elif lo.startswith("recycle: "):
                    token = r[len("recycle: "):]
                items.append(token.strip())
            # Dedupe while preserving order
            seen = set()
            unique = [x for x in items if not (x in seen or seen.add(x))]
            if len(unique) == 1:
                result.append(f"recycle {unique[0]}")
            else:
                result.append("recycle " + ", ".join(unique))
        # initial charge + makeup stay as two distinct arrows (semantically
        # different — solid vs dashed)
        for x in initials:
            result.append(x)
        for x in makeups:
            result.append(x)
        # Other generic labels — keep the most informative one
        if others:
            non_empty = [x for x in others if x and x != "stream"]
            if non_empty:
                # If there's "concentrated product" and "biphasic mixture" etc,
                # keep them all but only if they're all distinct meanings
                seen2 = set()
                for x in non_empty:
                    if x not in seen2:
                        result.append(x)
                        seen2.add(x)
            elif not result:
                result.append("")
        if not result:
            result.append("")
        return result

    deduped: List[Tuple[str, str, str]] = []
    for key in pair_order:
        src, dst = key
        for lab in _merge_labels(pair_buckets[key]):
            deduped.append((src, dst, lab))
    edges = deduped

    # ---- Equipment -----------------------------------------------------
    eqs = EquipmentList()
    eqs.add(Equipment(
        name="Pretreatment Mill / Mixer",
        section="Feedstock Pretreatment",
        base_cost=120_000, cepci_ref=2016, cap_ref=1.0, scaling_factor=0.6,
        note="Auto-generated placeholder; refine for actual feed handling.",
    ))

    op = exp.operating_conditions or {}
    ec = op.get("electrochem") or {}

    # Equipment per stage. Each stage uses the matching ProcessSection's
    # display-label as the equipment section (so the EquipmentList groups
    # by stage, not by raw reaction type).
    for idx, st in enumerate(exp.stages):
        stage_key = stage_keys[idx]
        # Find the matching ProcessSection's label for grouping
        stage_section_label = next(
            (s.label for s in sections if s.key == stage_key), stage_key)
        stage_type = (st.get("type") or exp.reaction_type or "unspecified").lower()

        if stage_type == "electrochemical":
            eqs.add(Equipment(
                name="Electrolyzer cell housing",
                section=stage_section_label,
                base_cost=10_000, cepci_ref=2023, cap_ref=1.0,
                scaling_factor=1.0, linear_with="cell_area_m2",
                installation_factor=1.2,
                note="$10,000/m² cell housing, 30-y life (workbook default).",
                source="260506 COOR-ORR TEA workbook",
                lifetime_years=30,
            ))
            eqs.add(Equipment(
                name="Electrode pair",
                section=stage_section_label,
                base_cost=963.54, cepci_ref=2023, cap_ref=1.0,
                scaling_factor=1.0, linear_with="electrode_area_m2",
                installation_factor=1.0,
                note="$963.54/m² electrode pair, 5-y life.",
                source="260506 COOR-ORR TEA workbook",
                lifetime_years=5,
            ))
            eqs.add(Equipment(
                name="Nafion 117 membrane",
                section=stage_section_label,
                base_cost=180.0, cepci_ref=2023, cap_ref=1.0,
                scaling_factor=1.0, linear_with="membrane_area_m2",
                installation_factor=1.0,
                note="$180/m² Nafion 117, 5-y life.",
                source="Chemours catalog",
                lifetime_years=5,
            ))
            eqs.add(Equipment(
                name="Balance of plant (BoP)",
                section=stage_section_label,
                base_cost=3_500, cepci_ref=2023, cap_ref=1.0,
                scaling_factor=1.0, linear_with="cell_area_m2",
                installation_factor=1.0,
                note="BoP at 35 % of cell housing.",
                source="industry standard 35% factor",
                lifetime_years=30,
            ))
        elif stage_type == "thermal":
            # Jacketed flow reactor + heat-exchanger train
            eqs.add(Equipment(
                name="Flow reactor (FRP / jacketed)",
                section=stage_section_label,
                base_cost=350_000, cepci_ref=2023, cap_ref=1.0, scaling_factor=0.6,
                installation_factor=1.4,
                note="Continuous flow reactor with jacketed heat duty.",
                source="vendor-quote ballpark",
            ))
            eqs.add(Equipment(
                name="Heat exchanger train",
                section=stage_section_label,
                base_cost=180_000, cepci_ref=2023, cap_ref=1.0, scaling_factor=0.6,
                installation_factor=1.3,
                source="Aspen ICARUS factor",
            ))
        elif stage_type in ("catalytic", "photochemical", "biological"):
            base_capex = _REACTION_CAPEX.get(stage_type, _REACTION_CAPEX["unspecified"])
            eqs.add(Equipment(
                name=f"{st.get('name', stage_section_label)} reactor",
                section=stage_section_label,
                base_cost=base_capex, cepci_ref=2016, cap_ref=1.0, scaling_factor=0.6,
                installation_factor=1.4,
                source=f"default {stage_type} reactor capex",
            ))
        else:
            base_capex = _REACTION_CAPEX.get(stage_type, _REACTION_CAPEX["unspecified"])
            eqs.add(Equipment(
                name=f"{stage_section_label} reactor",
                section=stage_section_label,
                base_cost=base_capex, cepci_ref=2016, cap_ref=1.0, scaling_factor=0.6,
                installation_factor=1.4,
                source="default placeholder",
            ))

    if exp.downstream:
        for i, d in enumerate(exp.downstream, start=1):
            _, capex = _kind_for_downstream(d.method)
            eqs.add(Equipment(
                name=f"{d.step} unit ({d.method})",
                section=d.step,
                base_cost=capex, cepci_ref=2016, cap_ref=1.0, scaling_factor=0.6,
                installation_factor=1.3,
                note="Auto-generated; tune base_cost from vendor quotes.",
            ))
    else:
        eqs.add(Equipment(
            name="Product Separation",
            section="Product Separation",
            base_cost=200_000, cepci_ref=2016, cap_ref=1.0, scaling_factor=0.6,
            installation_factor=1.3,
        ))

    # ---- meta: electrolyzer area + utility OPEX --------------------------
    meta: Dict[str, float] = {}
    if ec:
        j = float(ec.get("current_density_mA_cm2") or 100.0)
        v = float(ec.get("cell_voltage_V") or 1.5)
        fe = max(float(ec.get("faradaic_efficiency_pct") or 100.0) / 100.0, 0.05)

        # Cell area scales linearly with current; assume 100 mA/cm² ≡ 1 m²
        # of cell housing per ton/y of primary feed at typical electron load.
        # The TEA workbook used 1 cm² lab area for ~3 mg/hr H2O2 — we expose
        # area-per-ton as a tunable in meta.
        area_per_ton_m2 = max(1.0 / (j / 100.0), 0.1)  # m²/ton primary feed
        meta["cell_area_m2"] = area_per_ton_m2
        meta["electrode_area_m2"] = area_per_ton_m2
        meta["membrane_area_m2"] = area_per_ton_m2 * 4.0   # Nafion ≈ 4× electrode

        # Pulse duty cycle (if the user filled on/off times somewhere).
        # Default duty = 1.0 (continuous). For paired-pulse cases the user
        # encodes total on-time in batch_hours, so duty = 1.0 here.
        duty = 1.0

        # Faraday-law electricity OPEX, per ton primary feed per year:
        #   energy(kWh) = V * I * t = V * j[A/m²] * area[m²] * t[h] / 1000
        # We collapse it into the standard $/ton/y meta key.
        F = 96485.0
        
        # Product-specific stoichiometry: (z_e_transferred, MW_kg_mol)
        _EC_STOICHIOMETRY = {
            "h2":            (2, 0.002016),
            "hcooh":         (2, 0.04603),
            "co":            (2, 0.02801),
            "c2h4":          (12, 0.028055),
            "ethylene":      (12, 0.028055),
            "h2o2":          (2, 0.03401),
            "nh2oh":         (6, 0.03303),
            "hydroxylamine": (6, 0.03303),
            "glucaric":      (4, 0.21014),
            "fdca":          (6, 0.15610),
        }
        
        target_product_name = exp.preferred_msp_product or (
            exp.target_products[0] if exp.target_products else ""
        )
        target_yield_pct = 100.0
        for y in exp.results_yields:
            if y.product.lower() == target_product_name.lower():
                target_yield_pct = y.yield_pct
                break
                
        prod_key = target_product_name.lower().strip()
        # Stoichiometry source priority:
        #   1. chemistry.electrochem_stoichiometry in the experiment YAML
        #      (lets a paper-specific override travel with the data)
        #   2. Internal _EC_STOICHIOMETRY lookup for common products
        #   3. Rough fallback: 2 e⁻ per molecule, MW ≈ 30 g/mol
        user_stoich = exp.electrochem_stoichiometry
        if prod_key in user_stoich:
            z = user_stoich[prod_key]["z"]
            mw_kg = user_stoich[prod_key]["MW_g_mol"] / 1000.0
            stoich_source = "yaml"
        elif prod_key in _EC_STOICHIOMETRY:
            z, mw_kg = _EC_STOICHIOMETRY[prod_key]
            stoich_source = "lookup"
        else:
            z, mw_kg = 2.0, 0.030
            stoich_source = "fallback"

        # Energy per kg of product: V · z · F / (1000 · MW_kg · 3600) → kWh/kg
        kWh_per_kg_prod = v * (z * F) / (1000.0 * mw_kg * 3600.0)
        # Per-kg-feed conversion via mass-yield (kg product / kg feed).
        # This is an approximation that becomes exact when yield_pct is the
        # mass-basis product:feed ratio. For molar yields the user should
        # specify a per-product `yield_pct` whose semantics match the feed
        # mass basis (consistent with the rest of the engine).
        kWh_per_kg_feed = kWh_per_kg_prod * (target_yield_pct / 100.0)
        meta["electron_stoich_source"] = stoich_source
        meta["electron_stoich_z"] = float(z)
        meta["electron_stoich_MW_g_mol"] = float(mw_kg * 1000.0)

        kWh_per_ton_per_y = kWh_per_kg_feed * 1000.0 * 8400.0 / 8760.0 * duty / fe
        elec_price = 0.116  # $/kWh — workbook default
        if v > 0:
            meta["Electricity_$_per_ton_per_y"] = kWh_per_ton_per_y * elec_price
        else:
            # galvanic — no external electricity
            meta["Electricity_$_per_ton_per_y"] = 0.0

        # Low-pressure steam OPEX for K2CO3 evaporative crystallisation.
        # LPS_req = 1.177 kg LPS / kg evaporated water (workbook).
        # Coarse assumption: evaporative duty = 1× feed mass at large scale.
        if any("crystall" in (d.step + d.method).lower() for d in exp.downstream):
            meta["LPS_steam_$_per_ton_per_y"] = (
                1.177 * 1000.0 * 0.00416457987574889 * 8400.0 / 8760.0
            )

    # ---- TEAInputs -----------------------------------------------------
    msp_product = exp.preferred_msp_product or (
        exp.target_products[0] if exp.target_products else ""
    )
    scales = tuple(exp.scales_ton) if exp.scales_ton else (1.0, 5.0, 10.0)

    tea_inputs = TEAInputs(
        discount_rate=exp.discount_rate,
        lifetime_years=exp.plant_lifetime_years,
        capacity_factor=exp.capacity_factor,
        cepci_target_year=2023,
        msp_product=msp_product,
        scales_ton=scales,
        batch_hours=exp.batch_hours,
    )

    process = Process(
        name=f"{exp.meta.name} (auto first-cut)",
        description=(exp.chemistry.get("description", "")
                     or f"Auto-generated process for {exp.meta.name}."),
        streams=streams,
        equipment=eqs,
        sections=sections,
        edges=edges,
        meta=meta,
    )
    # Attach DB reference so downstream tools (HTML viewer, sensitivity sweeps)
    # can introspect price-source provenance.
    process._component_db_ref = db
    return process, db, tea_inputs


# ---------------------------------------------------------------- Design note
DESIGN_NOTE_TEMPLATE = """# Design Note — {name}  (`{slug}`)

> Generated from `experiments/{slug}.yaml` on {date_iso}.
> Edit freely. Claude Code uses this file as the running log of design
> decisions for `{slug}`.

{reported_block}

## 1. Experiment input summary

- Reaction type: **{reaction_type}**
- Primary feed: **{feed_name}** ({feed_g_per_batch} g/batch{feed_note})
- Reagents: {reagents}
- Measured products (yield %): {products}
- Operating conditions: T={T_C} °C, P={P_bar} bar, t={time_h} h
- Downstream steps: {downstream_steps}

## 2. Process design options considered

| Option | Description | Pros | Cons | Decision |
|---|---|---|---|---|
| A | (default first-cut PFD: pretreatment → {reaction_unit} → separation train) | Matches lab procedure 1:1; minimal assumptions | Capex defaults are rough; recovery factors are guesses | **Selected** for first-cut TEA |
| B | (alternative: integrated reactor-separation) | Lower capex, higher integration | Harder to operate; needs pilot data | Reject for first-cut |
| C | (alternative: ...) | ... | ... | ... |

*Edit this table when investigating alternatives.*

## 3. Key assumptions / sources

| Assumption | Value | Source / Justification |
|---|---|---|
| Electrolyzer cost | $ ... /m² | Bagemihl 2023, Mosalpuri 2023 |
| Membrane lifetime | ... y | Vendor data |
| Solvent recovery | ... % | Lab measurement / standard distillation correlation |
| Discount rate | {discount_rate} | TEA paper standard |
| Plant lifetime | {plant_life} y | Industrial baseline |

## 4. Scale-up risks & mitigations

(populated by `scaleup.build_scaleup_report` — see Scale-up tab in the app)

## 5. Open questions for the experimentalist

- [ ] Membrane / electrode lifetime at lab cell — how many hours before
  performance loss?
- [ ] Recovery fraction of {first_solvent} after extraction at >100 L scale?
- [ ] Are there minor by-products (>1 wt %) not in `results.yields`?

## 6. Next actions

- [ ] Refine `processes/from_experiment_{slug}.py` with vendor-grade equipment costs.
- [ ] Run the full ladder via the **📈 Scale-up** tab and screenshot the result.
- [ ] If MSP fails: identify the single highest-leverage variable via sensitivity sweep.
"""


def render_design_note(exp: Experiment, auto_msp: float | None = None) -> str:
    """Fill the design-note template with experiment values. Pure string template.

    If `auto_msp` is supplied, the report also shows a side-by-side
    "auto vs paper" comparison block when the YAML carries a `reported:`
    section.
    """
    fp = exp.feedstock_primary
    reagents = (", ".join(f"{r.name} ({r.mass_per_batch_g} g, rec={r.recovery_fraction:g})"
                          for r in exp.feedstock_reagents) or "none")
    products = (", ".join(f"{y.product} {y.yield_pct:g}%" for y in exp.results_yields)
                or "none")
    downstream = (", ".join(d.step for d in exp.downstream) or "none")
    op = exp.operating_conditions or {}
    sec_label, _ = _REACTION_TO_UNIT.get(exp.reaction_type,
                                         _REACTION_TO_UNIT["unspecified"])
    first_solvent = next((r.name for r in exp.feedstock_reagents
                          if r.role == "solvent"), "<solvent>")

    reported_block = ""
    if exp.reported_msp is not None:
        rmsp = exp.reported_msp
        msp_compare = ""
        if auto_msp is not None:
            delta_pct = ((auto_msp - rmsp) / rmsp * 100.0) if rmsp != 0 else float("nan")
            msp_compare = (
                f"\n> **Auto vs paper:** auto MSP = ${auto_msp:.2f}/kg, "
                f"paper reported = ${rmsp:.2f}/kg, "
                f"Δ = {delta_pct:+.1f} %."
            )
        reported_block = (
            f"\n> 📖 **Paper-reported TEA:** MSP = **${rmsp:.2f}/kg** "
            f"(source: {exp.reported_source or 'see YAML'})."
            f"{msp_compare}\n"
        )

    return DESIGN_NOTE_TEMPLATE.format(
        name=exp.meta.name,
        slug=exp.meta.slug,
        date_iso=str(exp.meta.date or ""),
        reaction_type=exp.reaction_type,
        feed_name=fp.name if fp else "?",
        feed_g_per_batch=fp.mass_per_batch_g if fp else "?",
        feed_note=(f", {fp.source_note}" if fp and fp.source_note else ""),
        reagents=reagents,
        products=products,
        T_C=op.get("temperature_C", "?"),
        P_bar=op.get("pressure_bar", "?"),
        time_h=op.get("reaction_time_h", "?"),
        downstream_steps=downstream,
        reaction_unit=sec_label,
        discount_rate=exp.discount_rate,
        plant_life=exp.plant_lifetime_years,
        first_solvent=first_solvent,
        reported_block=reported_block,
    )
