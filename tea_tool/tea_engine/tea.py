"""TEA calculations: CAPEX, OPEX, Revenue, MSP, profitability, sensitivity.

Numerical layout follows the reference TEA xlsx so an exported sheet can be
diffed cleanly against the paper's spreadsheet.

Conventions
-----------
- Lab scale uses `mass_per_batch_g` for the limiting feed.
- Scale-up tons:  ``ton`` ∈ ``inputs.scales_ton`` is "tons of limiting feed
  per batch".  Annual flow = batch flow × batches_per_year.
- Equipment installed cost at scale ``ton`` follows
      cost(ton) = base_cost × (ton / cap_ref) ** scaling_factor
                              × (CEPCI_target / CEPCI_ref)
                              × installation_factor
  Set ``cap_ref=1.0`` and supply ``base_cost`` already at the target year if
  you want a flat 1-ton baseline.
- Utility lines come from ``process.meta`` keys ending in
  ``_$_per_ton_per_y``  (linear in ton).
- Extra OPEX lines come from ``process.extra_opex``. Each value is either a
  scalar ($ per ton per y, linear scale-up) or a dict
  ``{"value_at_ref": ..., "scaling_factor": 0.6, "cap_ref": 1.0}`` for
  CAPEX-coupled lines (e.g. Maintenance, Operation) that should follow the
  0.6 power-law instead of throughput.
- Extra annualized CAPEX from ``process.extra_capex_annualized``
  ($ per ton per y, e.g. initial feedstock charge or distillation column).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .components import ComponentDB
from .equipment import EquipmentList, CEPCI
from .process import Process


@dataclass
class TEAInputs:
    discount_rate: float = 0.10
    lifetime_years: int = 30
    capacity_factor: float = 0.8
    cepci_target_year: int = 2023
    osbl_fraction: float = 0.25
    maintenance_fraction: float = 0.10
    operation_fraction: float = 0.10
    batch_hours: float = 2.0
    msp_product: str = "TPA"
    scales_ton: Tuple[float, ...] = (1.0, 5.0, 10.0)
    # Forward-economics metric. When set to an input/feedstock component name,
    # the engine computes net_profit / feedstock_annual_kg and exposes it as
    # `net_per_kg_feedstock` on TEAResult. Useful when the question is "how
    # much profit/loss per kg of feedstock processed at current market prices"
    # rather than the backwards-solved MSP. Both can coexist.
    feedstock_for_economics: Optional[str] = None

    @property
    def crf(self) -> float:
        i = self.discount_rate
        n = self.lifetime_years
        if i == 0:
            return 1.0 / n
        return i * (1 + i) ** n / ((1 + i) ** n - 1)

    @property
    def batches_per_year(self) -> float:
        return 365 * 24 * self.capacity_factor / self.batch_hours


@dataclass
class TEAResult:
    inputs: TEAInputs
    capex_section: Dict[float, Dict[str, float]] = field(default_factory=dict)
    capex_total: Dict[float, float] = field(default_factory=dict)
    capex_annualized: Dict[float, float] = field(default_factory=dict)
    capex_extra_annualized: Dict[float, Dict[str, float]] = field(default_factory=dict)
    opex: Dict[float, Dict[str, float]] = field(default_factory=dict)
    opex_total: Dict[float, float] = field(default_factory=dict)
    revenue: Dict[float, Dict[str, float]] = field(default_factory=dict)
    revenue_total: Dict[float, float] = field(default_factory=dict)
    net_profit: Dict[float, float] = field(default_factory=dict)
    msp: Dict[float, float] = field(default_factory=dict)
    # Forward-economics metric, $/kg of the feedstock named in
    # `TEAInputs.feedstock_for_economics`. Positive = profit/kg-feed; negative
    # = loss/kg-feed at the market prices currently in the component DB.
    net_per_kg_feedstock: Dict[float, float] = field(default_factory=dict)
    feedstock_basis_label: str = ""
    flows_per_batch_kg: Dict[float, Dict[str, float]] = field(default_factory=dict)
    flows_annual_kg: Dict[float, Dict[str, float]] = field(default_factory=dict)
    cost_breakdown: Dict[str, float] = field(default_factory=dict)
    revenue_breakdown: Dict[str, float] = field(default_factory=dict)
    sensitivity: Dict[str, List[Tuple[float, float]]] = field(default_factory=dict)


def _scale_factor(ton: float, base_lab_g: float) -> float:
    """grams-of-lab → kilograms-of-process multiplier."""
    return ton * 1e6 / base_lab_g  # ton * 1000 kg/ton * 1000 g/kg / lab_g


def _flows(process: Process, ton: float, bpy: float) -> Tuple[Dict[str, float], Dict[str, float]]:
    base = process.streams.inputs[0].mass_per_batch_g
    sf = _scale_factor(ton, base)
    pb: Dict[str, float] = {}
    ann: Dict[str, float] = {}
    for s in process.streams.inputs + process.streams.outputs:
        kg_batch = s.mass_per_batch_g * sf / 1000.0  # kg per batch
        pb[s.component] = kg_batch
        if s.role == "input" and s.recovery > 0:
            net = kg_batch * (1 - s.recovery)
        else:
            net = kg_batch
        # one_time / periodic streams contribute their own annualized cost via
        # capex_extra_annualized / extra_opex pathways; their *flow* line is
        # only the (typically zero) makeup component above. This keeps the
        # historical "continuous"-only behaviour byte-identical.
        ann[s.component] = net * bpy
    return pb, ann


def _crf_at(rate: float, years: float) -> float:
    if years <= 0:
        return 0.0
    if rate == 0:
        return 1.0 / years
    return rate * (1 + rate) ** years / ((1 + rate) ** years - 1)


def _periodic_opex_from_streams(process: Process, db: ComponentDB,
                                ton: float) -> Dict[str, float]:
    """Annualized cost of every `periodic` input stream.

    cost_per_replacement = initial_charge_kg_per_ton * ton * $/kg
    annual              = cost_per_replacement / (interval_months / 12)
    """
    out: Dict[str, float] = {}
    for s in process.streams.inputs:
        if s.flow_mode != "periodic":
            continue
        comp = db.get(s.component)
        price = comp.price_low or 0.0
        kg_per_replacement = s.initial_charge_kg_per_ton * ton
        years = s.replacement_interval_months / 12.0
        if years <= 0:
            continue
        annual = kg_per_replacement * price / years
        out[f"Periodic replacement - {s.component} (every {years:g} y)"] = annual
    return out


def _one_time_capex_from_streams(process: Process, db: ComponentDB,
                                 ton: float, crf: float) -> Dict[str, float]:
    """Annualized initial inventory of every `one_time` input stream.

    cost = initial_charge_kg_per_ton * ton * $/kg
    annual = cost * CRF
    """
    out: Dict[str, float] = {}
    for s in process.streams.inputs:
        if s.flow_mode != "one_time":
            continue
        comp = db.get(s.component)
        price = comp.price_low or 0.0
        kg = s.initial_charge_kg_per_ton * ton
        if kg <= 0:
            continue
        cost = kg * price
        out[f"Initial inventory - {s.component}"] = cost * crf
    return out


def _opex_lines(process: Process, db: ComponentDB, ton: float, bpy: float,
                capex_total: float, inp: TEAInputs) -> Dict[str, float]:
    out: Dict[str, float] = {}
    base = process.streams.inputs[0].mass_per_batch_g
    sf = _scale_factor(ton, base)

    # Feedstock makeup
    # Cost accounting per flow_mode (no double-counting across pathways):
    #   continuous  → mass_per_batch_g × (1 - recovery) × bpy × price  (this line)
    #   one_time    → full inventory annualized in _one_time_capex_from_streams
    #                 (CRF on initial_charge_kg_per_ton). This line is SKIPPED.
    #   periodic    → `initial_charge_kg_per_ton × ton × price / years` in
    #                 _periodic_opex_from_streams. This line is SKIPPED.
    feed_total = 0.0
    for s in process.streams.inputs:
        if getattr(s, "flow_mode", "continuous") != "continuous":
            continue
        comp = db.get(s.component)
        kg_batch = s.mass_per_batch_g * sf / 1000.0
        annual_makeup_kg = kg_batch * (1 - s.recovery) * bpy
        cost = annual_makeup_kg * (comp.price_low or 0.0)
        label = f"  Feedstock - {s.component}" + (" makeup" if s.recovery > 0 else "")
        out[label] = cost
        feed_total += cost
    out["__Feedstock Total"] = feed_total

    # Utility lines: declared per ton feedstock per year
    util_total = 0.0
    util_keys = [k for k in process.meta if k.endswith("_$_per_ton_per_y")]
    for k in util_keys:
        label_core = k.replace("_$_per_ton_per_y", "").replace("_", " ")
        label = f"  Utility - {label_core.title()}"
        v = process.meta[k] * ton
        out[label] = v
        util_total += v
    out["__Utility Total"] = util_total

    # Extra OPEX. Each entry is either:
    #   scalar value  → legacy linear: cost = value × ton  ($/ton/y)
    #   dict          → cost = value_at_ref × (ton / cap_ref) ** scaling_factor
    #                   Use when the line tracks CAPEX-coupled spend (e.g. M+O)
    #                   so it follows the 0.6 power-law instead of throughput.
    op_extras = 0.0
    for name, spec in process.extra_opex.items():
        if isinstance(spec, dict):
            v_ref = float(spec["value_at_ref"])
            sf_pow = float(spec.get("scaling_factor", 1.0))
            cap_ref = float(spec.get("cap_ref", 1.0))
            cost = v_ref * (ton / cap_ref) ** sf_pow
        else:
            cost = float(spec) * ton
        out[f"  {name}"] = cost
        op_extras += cost

    # Periodic-replacement streams (catalyst, resin, ...) — recurring cash
    # outlays land in OPEX. Equipment with a short lifetime is *not* added
    # here; it's handled inside CAPEX-annualization with its own per-item CRF
    # in `run_tea` (otherwise we'd double-count the plant-CRF amortization).
    periodic_stream_lines = _periodic_opex_from_streams(process, db, ton)
    for name, val in periodic_stream_lines.items():
        out[f"  {name}"] = val
        op_extras += val

    # Maintenance + Operation
    maint = capex_total * inp.maintenance_fraction
    oper = capex_total * inp.operation_fraction
    out["  Maintenance (% of CAPEX)"] = maint
    out["  Operation (% of CAPEX)"] = oper
    out["__Operation Total"] = op_extras + maint + oper

    out["__OPEX Total"] = (out["__Feedstock Total"] + out["__Utility Total"]
                          + out["__Operation Total"])
    return out


def run_tea(process: Process, db: ComponentDB, inputs: TEAInputs) -> TEAResult:
    res = TEAResult(inputs=inputs)
    cepci_target = CEPCI[inputs.cepci_target_year]
    bpy = inputs.batches_per_year
    largest = max(inputs.scales_ton)

    for ton in inputs.scales_ton:
        # --- CAPEX ---
        sec_costs: Dict[str, float] = {}
        for sec in process.sections:
            sec_costs[sec.label] = process.equipment.section_cost(
                sec.label, cepci_target, ton, process.meta
            )
        isbl = sum(sec_costs.values())
        osbl = isbl * inputs.osbl_fraction
        sec_costs[f"OSBL ({int(inputs.osbl_fraction * 100)}% of ISBL)"] = osbl
        total_eq_capex = isbl + osbl

        # Annualize: items with lifetime_years < plant life use their own CRF
        # (cleanly captures the recurring replacement cash flow); everything
        # else uses the plant-level CRF.
        plant_life_capex = osbl  # OSBL always rides on plant life
        short_life_annual = 0.0
        for eq in process.equipment.items:
            cost = eq.installed_cost(cepci_target, ton, process.meta)
            life = eq.lifetime_years
            if (life is not None and 0 < life < inputs.lifetime_years):
                short_life_annual += cost * _crf_at(inputs.discount_rate, life)
            else:
                plant_life_capex += cost
        annualized_eq = plant_life_capex * inputs.crf + short_life_annual

        extra_ann = {k: v * ton for k, v in process.extra_capex_annualized.items()}
        # `one_time` input streams contribute their initial-inventory cost
        # × CRF as additional annualized CAPEX.
        for k, v in _one_time_capex_from_streams(process, db, ton, inputs.crf).items():
            extra_ann[k] = extra_ann.get(k, 0.0) + v
        annualized_total = annualized_eq + sum(extra_ann.values())

        res.capex_section[ton] = sec_costs
        res.capex_total[ton] = total_eq_capex
        res.capex_annualized[ton] = annualized_total
        res.capex_extra_annualized[ton] = {"Annualized Equipment CAPEX": annualized_eq, **extra_ann}

        # --- Flows ---
        pb, ann = _flows(process, ton, bpy)
        res.flows_per_batch_kg[ton] = pb
        res.flows_annual_kg[ton] = ann

        # --- OPEX ---
        opex = _opex_lines(process, db, ton, bpy, total_eq_capex, inputs)
        res.opex[ton] = opex
        res.opex_total[ton] = opex["__OPEX Total"]

        # --- Revenue ---
        rev: Dict[str, float] = {}
        for s in process.streams.outputs:
            comp = db.get(s.component)
            rev[s.component] = ann[s.component] * (comp.price_low or 0.0)
        res.revenue[ton] = rev
        res.revenue_total[ton] = sum(rev.values())

        res.net_profit[ton] = res.revenue_total[ton] - (annualized_total + res.opex_total[ton])

        # --- MSP for chosen product ---
        msp_kg = ann.get(inputs.msp_product, 0.0)
        other_rev = sum(v for k, v in rev.items() if k != inputs.msp_product)
        if msp_kg > 0:
            res.msp[ton] = (annualized_total + res.opex_total[ton] - other_rev) / msp_kg
        else:
            res.msp[ton] = float("nan")

        # --- Forward economics: $/kg-feedstock at current market prices ---
        if inputs.feedstock_for_economics:
            feed_kg = ann.get(inputs.feedstock_for_economics, 0.0)
            if feed_kg > 0:
                res.net_per_kg_feedstock[ton] = res.net_profit[ton] / feed_kg
            else:
                res.net_per_kg_feedstock[ton] = float("nan")

    bd = {
        "CAPEX (Annualized)": res.capex_annualized[largest],
        "Feedstock Cost": res.opex[largest]["__Feedstock Total"],
        "Utility Cost": res.opex[largest]["__Utility Total"],
        "Operation (Maint. + Oper. + extras)": res.opex[largest]["__Operation Total"],
    }
    bd["Total"] = sum(bd.values())
    res.cost_breakdown = bd

    rb = dict(res.revenue[largest])
    rb["Total"] = sum(rb.values())
    res.revenue_breakdown = rb
    res.feedstock_basis_label = inputs.feedstock_for_economics or ""
    return res


def sensitivity_one_param(process: Process, db: ComponentDB, inputs: TEAInputs,
                          param_name: str, values: List[float]) -> List[Tuple[float, float]]:
    """Recompute MSP at the largest scale, sweeping one parameter.

    Supported param_name values:
        "<component>.recovery"       – set Stream.recovery for an input
        "<component>.price"          – override price ($/kg)
        "meta.<key>"                 – set process.meta[key]
        "<component>.output_price"   – override output price (other product)
    """
    largest = max(inputs.scales_ton)
    out: List[Tuple[float, float]] = []
    # snapshot
    orig_recoveries = {s.component: s.recovery for s in process.streams.inputs}
    orig_prices = {n: c.price_low for n, c in db.components.items()}
    orig_meta = dict(process.meta)
    try:
        for v in values:
            if param_name.endswith(".recovery"):
                comp = param_name.split(".")[0]
                for s in process.streams.inputs:
                    if s.component == comp:
                        s.recovery = v
            elif param_name.endswith(".price") or param_name.endswith(".output_price"):
                comp = param_name.split(".")[0]
                db.components[comp].price_low = v
            elif param_name.startswith("meta."):
                key = param_name.split(".", 1)[1]
                process.meta[key] = v
            r = run_tea(process, db, inputs)
            out.append((v, r.msp[largest]))
    finally:
        for s in process.streams.inputs:
            s.recovery = orig_recoveries.get(s.component, s.recovery)
        for n, p in orig_prices.items():
            db.components[n].price_low = p
        process.meta.clear()
        process.meta.update(orig_meta)
    return out
