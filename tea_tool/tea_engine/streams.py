"""Material streams - per-batch / per-year flow tracking, with time-resolved
flow modes for the temporal cash-flow / inventory view.

flow_mode encodes how a stream is replenished over plant lifetime:

- "continuous"  — the historical default.  Stream is consumed every batch and
                  fed every batch.  `mass_per_batch_g` × batches/year drives
                  feedstock OPEX; `recovery` reduces makeup.
- "one_time"    — Stream is loaded once at t=0 (initial inventory).  Cost is
                  annualized via plant-CRF and shows up in CAPEX-extra.
                  `initial_charge_kg_per_ton` is the loaded mass per ton-feed
                  capacity.  `mass_per_batch_g` is IGNORED for OPEX accounting
                  to keep the cost pathway single-source (the Feedstock line
                  in tea._opex_lines skips this mode).  If you need ongoing
                  makeup, model the stream as "continuous" plus a separate
                  one_time inventory stream of the same component.
- "periodic"    — Stream is fully replaced every `replacement_interval_months`
                  months (e.g. catalyst regeneration, ion-exchange resin).
                  Cost-per-replacement = `initial_charge_kg_per_ton * ton * $/kg`,
                  annualized as cost / (interval_months / 12).
                  `mass_per_batch_g` is IGNORED for OPEX accounting (same
                  rationale as one_time).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List


VALID_FLOW_MODES = ("continuous", "one_time", "periodic")


@dataclass
class Stream:
    """A material stream tied to one component.

    `mass_per_batch_g` is what the user typically writes (lab scale).
    Scale-up uses the chosen `target_batch_kg` of the limiting feed.
    """
    component: str
    mass_per_batch_g: float
    role: str = "input"           # input | output | recycle | utility
    recovery: float = 0.0         # 0..1, fraction recovered & looped (for makeup calc)
    note: str = ""

    # ----- Time-resolved flow metadata (default keeps legacy behaviour) -----
    flow_mode: str = "continuous"
    initial_charge_kg_per_ton: float = 0.0   # one_time / periodic loadings
    replacement_interval_months: float = 0.0  # periodic only
    lifetime_months: float = 0.0              # informational; 0 = unbounded

    # ----- Topology hint (informs the PFD builder where the stream feeds in) -----
    # One of: "feed" (primary feedstock, enters at first section),
    #         "catalyst" (enters at reactor, recycled from EC / regen step),
    #         "acid" / "base" (electrolyte; enters at reactor, recycled),
    #         "solvent_extraction" (enters at extraction step, recycled from distillation),
    #         "solvent_reaction" (co-solvent in reaction phase),
    #         "utility" (water, energy; minor visual weight),
    #         "membrane" / "consumable" (periodic replacement only).
    category: str = "feed"

    def __post_init__(self):
        if self.flow_mode not in VALID_FLOW_MODES:
            raise ValueError(
                f"Stream {self.component}: flow_mode={self.flow_mode!r} "
                f"not in {VALID_FLOW_MODES}"
            )
        if self.flow_mode == "periodic" and self.replacement_interval_months <= 0:
            raise ValueError(
                f"Stream {self.component}: flow_mode='periodic' requires "
                f"replacement_interval_months > 0"
            )

    def per_batch_kg(self, scale_factor: float) -> float:
        return self.mass_per_batch_g * scale_factor / 1000.0

    def annual_kg(self, scale_factor: float, batches_per_year: float) -> float:
        # makeup-only for recycled streams
        net = self.mass_per_batch_g * (1 - self.recovery) if self.role in ("input", "utility") else self.mass_per_batch_g
        return net * scale_factor * batches_per_year / 1000.0


@dataclass
class StreamSet:
    inputs: List[Stream] = field(default_factory=list)
    outputs: List[Stream] = field(default_factory=list)

    def add_input(self, s: Stream) -> None:
        s.role = "input"
        self.inputs.append(s)

    def add_output(self, s: Stream) -> None:
        s.role = "output"
        self.outputs.append(s)

    def by_component(self) -> Dict[str, Stream]:
        return {s.component: s for s in (self.inputs + self.outputs)}

    def remove_input(self, component: str) -> None:
        self.inputs = [s for s in self.inputs if s.component != component]

    def remove_output(self, component: str) -> None:
        self.outputs = [s for s in self.outputs if s.component != component]

    def has(self, component: str) -> bool:
        return any(s.component == component for s in self.inputs + self.outputs)
