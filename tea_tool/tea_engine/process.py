"""Process model - groups streams, equipment, sections, and PFD topology."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple, Union

from .streams import StreamSet
from .equipment import EquipmentList


# ============================================================================
# Unit-operation catalog — drives PFD node shape / colour / icon.
#
# Inspired by Aspen / standard chemical-engineering PFD conventions:
#   - Towers (distillation, absorber, stripper) → tall narrow rectangles
#   - Reactors (CSTR, PFR, electrochem) → square-ish rectangles
#   - Separators → wider rectangles with rounded corners
#   - Pumps / compressors → circles
#   - Tanks → tall rounded vessels
#
# `w`/`h` are pixels (the streamlit-flow component honors style.width /
# style.height); `radius` is the CSS borderRadius.
# ============================================================================
UNIT_TYPES: Dict[str, Dict] = {
    "Generic":              {"icon": "▭",  "color": "#BBDEFB", "border": "#1976D2", "w": 170, "h": 90,  "radius": 8},
    "Pretreatment":         {"icon": "✂️", "color": "#FFCCBC", "border": "#D84315", "w": 170, "h": 90,  "radius": 8},
    "Thermal Reactor":      {"icon": "🔥", "color": "#FFCDD2", "border": "#C62828", "w": 180, "h": 100, "radius": 8},
    "Electrochemical Cell": {"icon": "⚡", "color": "#E1BEE7", "border": "#6A1B9A", "w": 190, "h": 100, "radius": 8},
    "Catalytic Reactor":    {"icon": "🧪", "color": "#F8BBD0", "border": "#AD1457", "w": 180, "h": 100, "radius": 8},
    "Bioreactor":           {"icon": "🦠", "color": "#C5E1A5", "border": "#558B2F", "w": 180, "h": 100, "radius": 8},
    "Distillation Column":  {"icon": "⫼",  "color": "#B2DFDB", "border": "#00695C", "w":  90, "h": 170, "radius": 4},
    "Absorber / Stripper":  {"icon": "▌",  "color": "#80DEEA", "border": "#00838F", "w":  90, "h": 170, "radius": 4},
    "Liquid-Liquid Sep":    {"icon": "💧", "color": "#B3E5FC", "border": "#0277BD", "w": 160, "h": 90,  "radius": 14},
    "Gas-Liquid Sep":       {"icon": "💨", "color": "#BBDEFB", "border": "#1565C0", "w": 160, "h": 90,  "radius": 14},
    "Crystallizer":         {"icon": "❄️", "color": "#E0F2F1", "border": "#00838F", "w": 160, "h": 100, "radius": 8},
    "Filter / Centrifuge":  {"icon": "🔎", "color": "#ECEFF1", "border": "#455A64", "w": 160, "h": 90,  "radius": 8},
    "Heat Exchanger":       {"icon": "🌡️", "color": "#FFE0B2", "border": "#EF6C00", "w": 160, "h": 80,  "radius": 4},
    "Pump / Compressor":    {"icon": "⚙️", "color": "#FFF59D", "border": "#F57F17", "w":  95, "h": 95,  "radius": 50},
    "Storage Tank":         {"icon": "🛢️", "color": "#FFF8E1", "border": "#F9A825", "w": 100, "h": 140, "radius": 28},
    "Mixer / Splitter":     {"icon": "🔀", "color": "#DCEDC8", "border": "#558B2F", "w": 130, "h": 80,  "radius": 8},
    "Membrane / PSA":       {"icon": "▦",  "color": "#D1C4E9", "border": "#4527A0", "w": 170, "h": 95,  "radius": 8},
    "Electrodialysis":      {"icon": "⇌",  "color": "#CE93D8", "border": "#7B1FA2", "w": 170, "h": 95,  "radius": 8},
    "Dryer":                {"icon": "🌬️", "color": "#FFE0B2", "border": "#E65100", "w": 160, "h": 90,  "radius": 8},
    "Utility / BoP":        {"icon": "🔧", "color": "#CFD8DC", "border": "#37474F", "w": 150, "h": 80,  "radius": 8},
    "Recycle":              {"icon": "♻️", "color": "#FFF9C4", "border": "#9E9D24", "w": 140, "h": 80,  "radius": 8},
    "CO2 Capture":          {"icon": "🌫️", "color": "#B0BEC5", "border": "#37474F", "w": 170, "h": 95,  "radius": 8},
    "Wastewater Treatment": {"icon": "🚰", "color": "#B2EBF2", "border": "#006064", "w": 170, "h": 95,  "radius": 8},
}


@dataclass
class ProcessSection:
    """Logical block in the PFD (e.g. Feedstock Pretreatment)."""
    key: str                       # short id for graph nodes
    label: str                     # display name
    description: str = ""
    kind: str = "Generic"          # one of UNIT_TYPES keys


@dataclass
class Process:
    name: str
    description: str
    streams: StreamSet
    equipment: EquipmentList
    sections: List[ProcessSection] = field(default_factory=list)
    edges: List[Tuple[str, str, str]] = field(default_factory=list)  # (from_key, to_key, label)
    # process-level metadata (electrolyzer area, voltage, current density, ...)
    meta: Dict[str, float] = field(default_factory=dict)
    # extra annual costs not captured by equipment (e.g. distillation OPEX, mechanical crushing)
    extra_opex: Dict[str, Union[float, Dict[str, Any]]] = field(default_factory=dict)
    # extra annualized capex line items (e.g. initial feedstock, distillation column capex)
    extra_capex_annualized: Dict[str, Union[float, Dict[str, Any]]] = field(default_factory=dict)

    def section_keys(self) -> List[str]:
        return [s.key for s in self.sections]

    def section_label(self, key: str) -> str:
        for s in self.sections:
            if s.key == key:
                return s.label
        return key
