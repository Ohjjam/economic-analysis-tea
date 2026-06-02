"""Equipment library with installed-cost scaling.

Each Equipment carries a base equipment cost in a reference year (CEPCI_ref)
for a reference capacity (capacity_ref).  Scaling uses:

    Cost(year, cap) = Cost_ref * (cap / cap_ref)^scaling_factor
                                * (CEPCI_year / CEPCI_ref)
                                * installation_factor

Equipment whose cost truly scales linearly with area (electrolyzer) sets
`linear_with` to a key that pulls a value from process-level metadata.

Each Equipment also accepts `cost_sources: List[CapexSource]` so the user
can see (and toggle between) multiple curated vendor / paper quotes.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class CapexSource:
    """One curated equipment-cost data point with full provenance."""
    value_usd: float                 # base installed cost at cap_ref
    source: str                      # vendor, paper, in-house quote, ...
    cap_ref: float = 1.0             # ton/batch or other unit
    cepci_ref: int = 2023
    scaling_factor: float = 0.6
    year: Optional[int] = None
    note: Optional[str] = None
    url: Optional[str] = None

    def label(self) -> str:
        bits = [self.source]
        if self.year:
            bits.append(str(self.year))
        return " ".join(bits)


# CEPCI reference table - extend as needed
CEPCI: Dict[int, float] = {
    2016: 541.7,
    2018: 603.1,
    2020: 596.2,
    2021: 708.0,
    2022: 816.0,
    2023: 800.8,
    2024: 800.0,
}


@dataclass
class Equipment:
    name: str
    section: str                           # e.g. "Feedstock Pretreatment"
    base_cost: float                       # equipment cost in CEPCI_ref$ at cap_ref
    installation_factor: float = 1.0
    cepci_ref: int = 2016
    cap_ref: float = 1.0                   # ref capacity (e.g. 6.25 ton PET / batch)
    scaling_factor: float = 0.6
    linear_with: Optional[str] = None      # if set, ignores power-law -> linear w/ that key
    note: str = ""
    source: Optional[str] = None           # short ref tag for the active base_cost
    # ----- Time-resolved equipment lifetime metadata -----
    lifetime_years: Optional[float] = None
    replacement_interval_years: Optional[float] = None
    # ----- Multi-source CAPEX provenance -----
    cost_sources: List["CapexSource"] = field(default_factory=list)
    active_source_index: int = 0

    def active_label(self) -> str:
        if self.cost_sources:
            i = max(0, min(self.active_source_index, len(self.cost_sources) - 1))
            return self.cost_sources[i].label()
        return self.source or "default"

    def set_active_source(self, source_label: str) -> bool:
        """Activate a cost source by its `.label()` — also updates the
        equipment's effective base_cost / scaling_factor / cap_ref / cepci_ref."""
        for i, s in enumerate(self.cost_sources):
            if s.label() == source_label:
                self.active_source_index = i
                self.base_cost = s.value_usd
                self.cap_ref = s.cap_ref
                self.cepci_ref = s.cepci_ref
                self.scaling_factor = s.scaling_factor
                return True
        return False

    def installed_cost(self, cepci_target: float, capacity: float, meta: Dict[str, float]) -> float:
        if self.linear_with is not None:
            # cost = base_cost * meta[key]   (already in $/unit at the right year)
            unit = meta.get(self.linear_with, 0.0)
            cost = self.base_cost * unit
        else:
            ratio = (capacity / self.cap_ref) ** self.scaling_factor if self.cap_ref > 0 else 1.0
            cost = self.base_cost * ratio * (cepci_target / CEPCI[self.cepci_ref]) * self.installation_factor
        return cost

    def replacement_years(self) -> Optional[float]:
        """Years between full equipment replacements, if shorter than plant life."""
        if self.replacement_interval_years is not None:
            return self.replacement_interval_years
        return self.lifetime_years


@dataclass
class EquipmentList:
    items: List[Equipment] = field(default_factory=list)

    def add(self, eq: Equipment) -> None:
        self.items.append(eq)

    def by_section(self) -> Dict[str, List[Equipment]]:
        out: Dict[str, List[Equipment]] = {}
        for e in self.items:
            out.setdefault(e.section, []).append(e)
        return out

    def section_cost(self, section: str, cepci_target: float, capacity: float, meta: Dict[str, float]) -> float:
        return sum(e.installed_cost(cepci_target, capacity, meta) for e in self.items if e.section == section)

    def total_cost(self, cepci_target: float, capacity: float, meta: Dict[str, float]) -> float:
        return sum(e.installed_cost(cepci_target, capacity, meta) for e in self.items)
