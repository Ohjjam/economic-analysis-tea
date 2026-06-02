"""Time-resolved view of process flows and cash outlays.

Builds month-by-month dataframes that drive the "Time Profile" tab:

  * `material_timeline(...)`  - per-stream monthly consumption + inventory
  * `cashflow_timeline(...)`  - per-line monthly $ outflow / inflow
  * `equipment_events(...)`   - lifetime-driven equipment replacement events
  * `stream_events(...)`      - one_time / periodic stream events

The same data structures power the Plotly area / step / spike views and the
NPV bar overlay.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from .components import ComponentDB
from .equipment import CEPCI
from .process import Process
from .tea import TEAInputs, _scale_factor


# ---------------------------------------------------------------------------- #
# Events
# ---------------------------------------------------------------------------- #
@dataclass
class TimelineEvent:
    month: int
    kind: str                # "stream_initial" | "stream_replace" | "equipment_replace" | "capex"
    label: str
    amount_usd: float = 0.0
    component: str = ""      # for stream events
    section: str = ""        # for equipment events


def stream_events(process: Process, db: ComponentDB, ton: float,
                  inp: TEAInputs) -> List[TimelineEvent]:
    """Initial-charge + every replacement event for one_time / periodic inputs.

    Notes:
      - one_time events fire once at month 0.
      - periodic events fire at month 0 (initial fill) and every
        `replacement_interval_months` thereafter, up to plant lifetime.
    """
    horizon_months = int(inp.lifetime_years * 12)
    out: List[TimelineEvent] = []
    for s in process.streams.inputs:
        if s.flow_mode == "continuous":
            continue
        comp = db.get(s.component)
        price = comp.price_low or 0.0
        kg = s.initial_charge_kg_per_ton * ton
        if kg <= 0:
            continue
        cost = kg * price
        out.append(TimelineEvent(
            month=0, kind="stream_initial",
            label=f"Initial charge — {s.component}",
            amount_usd=cost, component=s.component,
        ))
        if s.flow_mode == "periodic" and s.replacement_interval_months > 0:
            interval = int(round(s.replacement_interval_months))
            t = interval
            while t <= horizon_months:
                out.append(TimelineEvent(
                    month=t, kind="stream_replace",
                    label=f"Replace — {s.component}",
                    amount_usd=cost, component=s.component,
                ))
                t += interval
    return out


def equipment_events(process: Process, ton: float,
                     inp: TEAInputs) -> List[TimelineEvent]:
    """Equipment-replacement events for items with lifetime < plant lifetime.

    The original CAPEX outlay (month 0) is *not* emitted here — it lives on the
    cash-flow series as a single CAPEX bar; this list only contains the
    *recurring* replacements.
    """
    horizon_months = int(inp.lifetime_years * 12)
    cepci_target = CEPCI[inp.cepci_target_year]
    out: List[TimelineEvent] = []
    for eq in process.equipment.items:
        rep_y = eq.replacement_years()
        if rep_y is None or rep_y <= 0 or rep_y >= inp.lifetime_years:
            continue
        cost = eq.installed_cost(cepci_target, ton, process.meta)
        interval = int(round(rep_y * 12))
        t = interval
        while t <= horizon_months:
            out.append(TimelineEvent(
                month=t, kind="equipment_replace",
                label=f"Replace — {eq.name}",
                amount_usd=cost, section=eq.section,
            ))
            t += interval
    return out


# ---------------------------------------------------------------------------- #
# Material timeline (per-stream monthly consumption + inventory)
# ---------------------------------------------------------------------------- #
def material_timeline(process: Process, db: ComponentDB, ton: float,
                      inp: TEAInputs) -> pd.DataFrame:
    """One row per (month, stream).

    Columns:
        month, year, component, role, flow_mode,
        kg_consumed_in_month   - mass actually consumed *in* that month
        kg_inventory_eom       - on-site inventory at end of month
        usd_in_month           - $ spent on this stream in that month (one_time
                                 spike, periodic spike, or continuous makeup)
    """
    horizon_months = int(inp.lifetime_years * 12)
    bpy = inp.batches_per_year
    base_g = process.streams.inputs[0].mass_per_batch_g
    sf = _scale_factor(ton, base_g)

    rows: List[Dict] = []

    # ---- inputs ----
    for s in process.streams.inputs:
        comp = db.get(s.component)
        price = comp.price_low or 0.0
        per_batch_kg = s.mass_per_batch_g * sf / 1000.0
        net_per_batch_kg = per_batch_kg * (1 - s.recovery)
        annual_makeup_kg = net_per_batch_kg * bpy
        monthly_makeup_kg = annual_makeup_kg / 12.0
        monthly_makeup_usd = monthly_makeup_kg * price

        if s.flow_mode == "continuous":
            for m in range(horizon_months + 1):
                rows.append({
                    "month": m, "year": m / 12.0,
                    "component": s.component, "role": "input",
                    "flow_mode": "continuous",
                    "kg_consumed_in_month": monthly_makeup_kg,
                    "kg_inventory_eom": 0.0,
                    "usd_in_month": monthly_makeup_usd,
                })
            continue

        # one_time / periodic: track inventory explicitly
        initial_kg = s.initial_charge_kg_per_ton * ton
        initial_usd = initial_kg * price
        # consumption per month (only the makeup-equivalent fraction)
        consumed_per_month = monthly_makeup_kg
        inventory = 0.0
        for m in range(horizon_months + 1):
            spike_usd = 0.0
            spike_kg = 0.0
            if m == 0:
                inventory = initial_kg
                spike_usd = initial_usd
                spike_kg = initial_kg
            elif (s.flow_mode == "periodic"
                  and s.replacement_interval_months > 0
                  and m % int(round(s.replacement_interval_months)) == 0):
                inventory = initial_kg
                spike_usd = initial_usd
                spike_kg = initial_kg
            # consume during month
            consumed = min(inventory, consumed_per_month)
            inventory -= consumed
            rows.append({
                "month": m, "year": m / 12.0,
                "component": s.component, "role": "input",
                "flow_mode": s.flow_mode,
                "kg_consumed_in_month": consumed,
                "kg_inventory_eom": inventory,
                # spike $ on replacement / initial-charge months,
                # tiny continuous makeup $ otherwise (only if the stream also
                # has mass_per_batch_g > 0 representing replenishment loss)
                "usd_in_month": spike_usd if spike_usd > 0 else (consumed * price),
            })

    # ---- outputs (revenue side) ----
    for s in process.streams.outputs:
        comp = db.get(s.component)
        price = comp.price_low or 0.0
        per_batch_kg = s.mass_per_batch_g * sf / 1000.0
        annual_kg = per_batch_kg * bpy
        monthly_kg = annual_kg / 12.0
        monthly_usd = monthly_kg * price
        for m in range(horizon_months + 1):
            rows.append({
                "month": m, "year": m / 12.0,
                "component": s.component, "role": "output",
                "flow_mode": "continuous",
                "kg_consumed_in_month": monthly_kg,   # = produced
                "kg_inventory_eom": 0.0,
                "usd_in_month": monthly_usd,
            })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------- #
# Cash-flow timeline (monthly $ in / out)
# ---------------------------------------------------------------------------- #
def cashflow_timeline(process: Process, db: ComponentDB, ton: float,
                      inp: TEAInputs, opex: Dict[str, float],
                      revenue: Dict[str, float],
                      capex_total: float) -> pd.DataFrame:
    """Monthly cash flow at scale `ton`.

    Combines:
      - month-0 CAPEX outlay (-capex_total)
      - flat monthly OPEX  (-opex_annual / 12)   [continuous lines only]
      - flat monthly revenue (+revenue_annual / 12)
      - lumpy stream + equipment replacement events at their event months
    """
    horizon_months = int(inp.lifetime_years * 12)

    # OPEX split: subtract the periodic / equipment-replace lines so we don't
    # double-count when we add their event-month spikes.
    flat_opex_ann = 0.0
    lumpy_lines = 0.0
    for k, v in opex.items():
        if k.startswith("__"):
            continue
        if k.lstrip().startswith(("Periodic replacement", "Equipment replacement")):
            lumpy_lines += v
            continue
        flat_opex_ann += v
    monthly_opex = flat_opex_ann / 12.0
    monthly_rev = sum(revenue.values()) / 12.0

    rows: List[Dict] = []
    for m in range(horizon_months + 1):
        capex = -capex_total if m == 0 else 0.0
        rows.append({
            "month": m, "year": m / 12.0,
            "capex": capex,
            "opex": -monthly_opex if m > 0 else 0.0,
            "revenue": monthly_rev if m > 0 else 0.0,
            "stream_event": 0.0,
            "equipment_event": 0.0,
        })
    df = pd.DataFrame(rows)

    # add lumpy events as negative outflows on their month
    for ev in stream_events(process, db, ton, inp):
        if ev.month == 0:
            # initial charge already inside CAPEX-extra annualized
            # (we surface it at month 0 explicitly so the visual lines up)
            df.loc[df["month"] == ev.month, "stream_event"] -= ev.amount_usd
        else:
            df.loc[df["month"] == ev.month, "stream_event"] -= ev.amount_usd
    for ev in equipment_events(process, ton, inp):
        df.loc[df["month"] == ev.month, "equipment_event"] -= ev.amount_usd

    df["net"] = df["capex"] + df["opex"] + df["revenue"] + df["stream_event"] + df["equipment_event"]
    df["cumulative"] = df["net"].cumsum()
    return df


# ---------------------------------------------------------------------------- #
# Convenience: month → year aggregation
# ---------------------------------------------------------------------------- #
def to_yearly(df: pd.DataFrame, value_cols: Optional[List[str]] = None,
              group_extra: Optional[List[str]] = None) -> pd.DataFrame:
    """Aggregate monthly dataframe to yearly buckets.

    Sums the columns in `value_cols` (auto-detected if None: any numeric column
    other than month/year). `group_extra` lets caller preserve grouping keys
    like 'component'.
    """
    df = df.copy()
    df["year_int"] = (df["month"] // 12).astype(int)
    keys = ["year_int"] + (group_extra or [])
    if value_cols is None:
        value_cols = [c for c in df.select_dtypes(include="number").columns
                      if c not in ("month", "year", "year_int", "kg_inventory_eom")]
    agg = {c: "sum" for c in value_cols}
    if "kg_inventory_eom" in df.columns:
        agg["kg_inventory_eom"] = "last"
    out = df.groupby(keys, as_index=False).agg(agg)
    out = out.rename(columns={"year_int": "year"})
    return out
