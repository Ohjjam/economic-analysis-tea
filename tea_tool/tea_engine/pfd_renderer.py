"""Render BFD / PFD / P&ID diagrams for a Process as PNGs.

Three diagram tiers (chemical-engineering convention):
  - BFD  (Block Flow Diagram):  collapsed sections, single flow line.
                                Use for executive summary / quick orientation.
  - PFD  (Process Flow Diagram): every section as a box with input/output
                                streams + recycle lines + stream labels.
                                Standard engineering communication level.
  - P&ID (Piping & Instrumentation Diagram): PFD + pumps + control valves +
                                ISA instrument symbols (TI/PI/FI/LI) added
                                heuristically. Schematic only — real P&IDs
                                require detailed piping/safety data not in
                                the process model.

Public API:
    from tea_engine.pfd_renderer import render_bfd, render_pfd, render_pid
    render_bfd(process, "out/bfd.png")
    render_pfd(process, "out/pfd.png")
    render_pid(process, "out/pid.png")

Each returns the path written.
"""
from __future__ import annotations
import os
from typing import Dict, List, Set, Tuple

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import (FancyBboxPatch, FancyArrowPatch, Circle,
                                    Polygon, Rectangle)
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False

from .process import UNIT_TYPES, Process


# ----------------------------------------------------------------------------
# Common helpers
# ----------------------------------------------------------------------------

def _ensure_dir(path: str) -> None:
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def _classify_nodes(process: Process):
    """Return (inputs, outputs, sections) lists of (key, label, kind)."""
    sections = [(s.key, s.label, s.kind) for s in process.sections]
    inputs, outputs = set(), set()
    for src, dst, _ in process.edges:
        if src.startswith("in:"):
            inputs.add(src)
        if dst.startswith("out:"):
            outputs.add(dst)
    inputs = sorted(inputs)
    outputs = sorted(outputs)
    return inputs, outputs, sections


def _detect_recycle_edges(process: Process) -> Set[Tuple[str, str]]:
    """Identify recycle edges (back-edges in declared section order)."""
    sec_order = {s.key: i for i, s in enumerate(process.sections)}
    back = set()
    for src, dst, _ in process.edges:
        if src in sec_order and dst in sec_order:
            if sec_order[dst] <= sec_order[src]:
                back.add((src, dst))
    return back


def _rect_edge(cx, cy, w, h, tx, ty):
    """Return (x, y) where ray from (cx,cy) toward (tx,ty) intersects the
    boundary of a (w × h) rectangle centred at (cx,cy)."""
    dx = tx - cx
    dy = ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    # Half-extents
    hw = w / 2.0
    hh = h / 2.0
    # How far along the ray (in normalised units) to hit each side
    if dx == 0:
        return cx, cy + (hh if dy > 0 else -hh)
    if dy == 0:
        return cx + (hw if dx > 0 else -hw), cy
    t = min(hw / abs(dx), hh / abs(dy))
    return cx + t * dx, cy + t * dy


def _draw_arrow(ax, x1, y1, x2, y2,
                color="#1976D2", linewidth=2.0, linestyle="-",
                curve=0.10, label=None, label_color=None,
                src_box=None, dst_box=None):
    """Draw a visible arrow between two points (or between two boxes).

    If src_box=(w,h) and dst_box=(w,h) are given, the arrow starts/ends at the
    box EDGE rather than the centre — so the arrowhead is always visible.
    """
    # Adjust endpoints to box edges if box sizes provided
    if src_box is not None:
        x1, y1 = _rect_edge(x1, y1, src_box[0], src_box[1], x2, y2)
    if dst_box is not None:
        x2, y2 = _rect_edge(x2, y2, dst_box[0], dst_box[1], x1, y1)

    arrow = FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle="-|>,head_length=0.5,head_width=0.35",
        mutation_scale=18,
        color=color, linewidth=linewidth, linestyle=linestyle,
        connectionstyle=f"arc3,rad={curve}",
        shrinkA=0, shrinkB=0, zorder=2,
    )
    ax.add_patch(arrow)
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2 + 0.18
        ax.text(mx, my, label, fontsize=7, color=label_color or color,
                ha="center", va="bottom", zorder=3,
                bbox=dict(boxstyle="round,pad=0.18",
                          facecolor="white", edgecolor="none", alpha=0.9))


def _draw_box(ax, x, y, w, h, label, color, border,
              fontsize=8, fontweight="bold", zorder=3):
    box = FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h,
        boxstyle="round,pad=0.05",
        edgecolor=border, facecolor=color, linewidth=1.7, zorder=zorder,
    )
    ax.add_patch(box)
    ax.text(x, y, label, ha="center", va="center",
            fontsize=fontsize, wrap=True, zorder=zorder + 1,
            fontweight=fontweight)


# ============================================================================
# BFD — Block Flow Diagram
# ============================================================================

def render_bfd(process: Process, output_path: str,
               width: float = 16.0, height: float = 4.5) -> str:
    """Render a Block Flow Diagram: collapsed sections in one row.

    Inputs grouped into one block on left, outputs grouped on right.
    No recycle detail, no stream labels — just the main flow direction.
    """
    if not _HAS_MPL:
        raise RuntimeError("matplotlib required")
    _ensure_dir(output_path)

    inputs, outputs, sections = _classify_nodes(process)

    fig, ax = plt.subplots(figsize=(width, height))
    n_sec = len(sections)
    # Determine block layout: 1 row for ≤6 sections, 2 rows otherwise
    if n_sec <= 6:
        cols = n_sec
        rows = 1
    else:
        cols = (n_sec + 1) // 2
        rows = 2
    dx = 2.6
    dy = 2.0

    # Position blocks
    sec_pos = {}
    for i, (key, label, kind) in enumerate(sections):
        col = i % cols
        row = i // cols
        x = col * dx
        y = -row * dy
        sec_pos[key] = (x, y)

    # Feeds block on left, Products block on right
    feeds_x = -dx * 1.4
    feeds_y = -(rows - 1) * dy / 2
    products_x = (cols - 1) * dx + dx * 1.4
    products_y = feeds_y

    ax.set_xlim(feeds_x - 2.0, products_x + 2.0)
    ax.set_ylim(-rows * dy - 0.8, 1.5)
    ax.set_aspect("equal", adjustable="datalim")
    ax.axis("off")

    # Draw feed block
    feed_labels = "\n".join(["FEEDS:"] + ["• " + n[3:] for n in inputs])
    _draw_box(ax, feeds_x, feeds_y, 2.0, max(1.2, 0.35 * (len(inputs) + 1)),
              feed_labels, "#E8F5E9", "#2E7D32",
              fontsize=8, fontweight="normal")

    # Draw products block
    prod_labels = "\n".join(["PRODUCTS:"] + ["• " + n[4:] for n in outputs])
    _draw_box(ax, products_x, products_y, 2.0, max(1.2, 0.35 * (len(outputs) + 1)),
              prod_labels, "#FFF3E0", "#E65100",
              fontsize=8, fontweight="normal")

    # Draw section blocks
    for i, (key, label, kind) in enumerate(sections):
        x, y = sec_pos[key]
        ut = UNIT_TYPES.get(kind, UNIT_TYPES["Generic"])
        # Number the blocks for clarity
        label_with_num = f"{i+1}. {label}"
        _draw_box(ax, x, y, dx * 0.85, dy * 0.55, label_with_num,
                  ut["color"], ut["border"], fontsize=8)

    # Draw arrows: Feeds → first section
    first_key = sections[0][0]
    fx, fy = sec_pos[first_key]
    _draw_arrow(ax, feeds_x + 1.0, feeds_y, fx - dx * 0.5, fy,
                color="#444", linewidth=2.0, curve=0)

    # Linear arrows between sections (just main flow)
    for i in range(len(sections) - 1):
        k1 = sections[i][0]
        k2 = sections[i + 1][0]
        x1, y1 = sec_pos[k1]
        x2, y2 = sec_pos[k2]
        # If same row, simple right arrow; if wrapping, downward then back
        if abs(y1 - y2) < 0.1:
            _draw_arrow(ax, x1 + dx * 0.45, y1, x2 - dx * 0.45, y2,
                        color="#444", linewidth=2.0, curve=0)
        else:
            # Vertical drop
            _draw_arrow(ax, x1, y1 - dy * 0.3, x2, y2 + dy * 0.3,
                        color="#444", linewidth=2.0, curve=0.3)

    # Last section → Products
    last_key = sections[-1][0]
    lx, ly = sec_pos[last_key]
    _draw_arrow(ax, lx + dx * 0.5, ly, products_x - 1.0, products_y,
                color="#444", linewidth=2.0, curve=0)

    ax.set_title("BFD — Block Flow Diagram (simplified main flow)",
                 fontsize=11, pad=8)
    ax.text(feeds_x - 1.8, -rows * dy - 0.4,
            "BFD shows the high-level sequence of unit operations. "
            "Recycle loops and stream details are abstracted away — see PFD for those.",
            fontsize=7, color="#555", va="bottom")

    fig.tight_layout()
    fig.savefig(output_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return output_path


# ============================================================================
# PFD — Process Flow Diagram
# ============================================================================

def _layered_positions_pfd(process: Process):
    """Position sections in LTR rows, inputs on left, outputs on right."""
    inputs, outputs, sections = _classify_nodes(process)
    n_sec = len(sections)
    cols = max(3, min(5, (n_sec + 1) // 2))
    rows = (n_sec + cols - 1) // cols

    dx = 3.8
    dy = 2.5
    pos = {}
    for i, (key, _, _) in enumerate(sections):
        col = i % cols
        row = i // cols
        pos[key] = (col * dx, -row * dy)

    in_x = -dx * 1.1
    span = max((rows - 1) * dy, dy * 2)
    in_n = max(len(inputs), 1)
    for j, k in enumerate(inputs):
        y = -j * (span / in_n) + (in_n - 1) * (span / in_n) / 2
        pos[k] = (in_x, y)

    out_x = (cols - 1) * dx + dx * 1.1
    out_n = max(len(outputs), 1)
    for j, k in enumerate(outputs):
        y = -j * (span / out_n) + (out_n - 1) * (span / out_n) / 2
        pos[k] = (out_x, y)
    return pos, rows, cols, dx, dy


def render_pfd(process: Process, output_path: str,
               width: float = 18.0, height: float = 10.0,
               title: str = None) -> str:
    """Render Process Flow Diagram with visible arrows and recycle loops."""
    if not _HAS_MPL:
        raise RuntimeError("matplotlib required")
    _ensure_dir(output_path)

    inputs, outputs, sections = _classify_nodes(process)
    back = _detect_recycle_edges(process)
    pos, rows, cols, dx, dy = _layered_positions_pfd(process)

    xs = [x for x, _ in pos.values()]
    ys = [y for _, y in pos.values()]
    fig, ax = plt.subplots(figsize=(width, height))
    ax.set_xlim(min(xs) - 2.5, max(xs) + 2.5)
    ax.set_ylim(min(ys) - 2.0, max(ys) + 2.0)
    ax.set_aspect("equal", adjustable="datalim")
    ax.axis("off")

    # Box sizes
    SEC_BOX = (2.8, 1.3)
    IO_BOX = (1.8, 0.7)

    def _box_for(k):
        if k.startswith("in:") or k.startswith("out:"):
            return IO_BOX
        return SEC_BOX

    # Draw NON-recycle edges first (under), then recycle on top
    for (src, dst, label) in process.edges:
        if src not in pos or dst not in pos:
            continue
        if (src, dst) in back:
            continue
        x1, y1 = pos[src]; x2, y2 = pos[dst]
        same_layer = abs(y1 - y2) < 0.5
        curve = 0.05 if same_layer else 0.20
        _draw_arrow(ax, x1, y1, x2, y2,
                    color="#1565C0", linewidth=2.0, curve=curve,
                    label=label, label_color="#1565C0",
                    src_box=_box_for(src), dst_box=_box_for(dst))

    # Recycle edges on top
    for (src, dst, label) in process.edges:
        if src not in pos or dst not in pos:
            continue
        if (src, dst) not in back:
            continue
        x1, y1 = pos[src]; x2, y2 = pos[dst]
        _draw_arrow(ax, x1, y1, x2, y2,
                    color="#D32F2F", linewidth=2.4, linestyle="--",
                    curve=0.55,
                    label=(label + " [recycle]") if label else "recycle",
                    label_color="#D32F2F",
                    src_box=_box_for(src), dst_box=_box_for(dst))

    # Draw nodes
    for k, (x, y) in pos.items():
        if k.startswith("in:"):
            label = "IN\n" + k[3:]
            _draw_box(ax, x, y, 1.8, 0.7, label, "#E8F5E9", "#2E7D32",
                      fontsize=8, fontweight="normal")
        elif k.startswith("out:"):
            label = "OUT\n" + k[4:]
            _draw_box(ax, x, y, 1.8, 0.7, label, "#FFF3E0", "#E65100",
                      fontsize=8, fontweight="normal")
        else:
            # Section
            sec = next((s for s in process.sections if s.key == k), None)
            label = sec.label if sec else k
            ut = UNIT_TYPES.get(sec.kind if sec else "Generic", UNIT_TYPES["Generic"])
            _draw_box(ax, x, y, 2.8, 1.3, label, ut["color"], ut["border"],
                      fontsize=9)

    ax.set_title(title or "PFD — " + process.name, fontsize=12, pad=10)
    ax.text(min(xs) - 2.3, min(ys) - 1.5,
            "BLUE solid = main flow.   RED dashed = recycle loop.\n"
            "Section box color encodes unit type (see Process_structure sheet).",
            fontsize=8, color="#333", va="bottom")

    fig.tight_layout()
    fig.savefig(output_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return output_path


# ============================================================================
# P&ID — Piping & Instrumentation Diagram (schematic)
# ============================================================================

# Standard ISA instrument tag families — which to add per unit kind
_INSTRUMENT_RULES = {
    "Pretreatment":         ["FI"],
    "Mixer / Splitter":     ["FI", "LI"],
    "Thermal Reactor":      ["TI", "PI", "TC"],
    "Catalytic Reactor":    ["TI", "PI", "FI"],
    "Bioreactor":           ["TI", "pH", "LI"],
    "Electrochemical Cell": ["VI", "AI"],   # V/A instead of T/P
    "Distillation Column":  ["TI", "PI", "LI"],
    "Absorber / Stripper":  ["TI", "PI"],
    "Liquid-Liquid Sep":    ["LI"],
    "Gas-Liquid Sep":       ["PI", "LI"],
    "Crystallizer":         ["TI", "LI"],
    "Filter / Centrifuge":  ["FI"],
    "Heat Exchanger":       ["TI"],
    "Membrane / PSA":       ["PI", "FI"],
    "Dryer":                ["TI"],
    "Wastewater Treatment": ["pH", "FI"],
    "Storage Tank":         ["LI"],
    "Recycle":              ["FI"],
    "Utility / BoP":        [],
    "Pump / Compressor":    ["PI"],
}


def _draw_pump(ax, x, y, r=0.18, color="#FFF59D", border="#F57F17"):
    """Pump symbol — circle with diagonal line."""
    circ = Circle((x, y), r, facecolor=color, edgecolor=border,
                  linewidth=1.3, zorder=4)
    ax.add_patch(circ)
    ax.plot([x - r * 0.6, x + r * 0.6], [y - r * 0.6, y + r * 0.6],
            color=border, linewidth=1.0, zorder=5)
    ax.text(x, y - r - 0.10, "P", fontsize=7, ha="center", va="top",
            color=border, fontweight="bold", zorder=5)


def _draw_control_valve(ax, x, y, size=0.16, color="#FFE082", border="#E65100"):
    """Control valve — bowtie shape."""
    pts = [(x - size, y - size), (x + size, y + size),
           (x + size, y - size), (x - size, y + size)]
    poly = Polygon(pts, closed=True, facecolor=color, edgecolor=border,
                   linewidth=1.3, zorder=4)
    ax.add_patch(poly)
    # Stem with controller bubble on top
    ax.plot([x, x], [y + size, y + size + 0.18],
            color=border, linewidth=1.0, zorder=5)
    circ = Circle((x, y + size + 0.28), 0.10,
                  facecolor="white", edgecolor=border,
                  linewidth=1.0, zorder=5)
    ax.add_patch(circ)
    ax.text(x, y + size + 0.28, "FC", fontsize=5, ha="center", va="center",
            color=border, zorder=6)


def _draw_instrument(ax, x, y, tag, r=0.14, color="white", border="#1A237E"):
    """ISA instrument balloon — circle with letters (e.g. TI, PI, FI, LI)."""
    circ = Circle((x, y), r, facecolor=color, edgecolor=border,
                  linewidth=1.0, zorder=4)
    ax.add_patch(circ)
    ax.text(x, y, tag, fontsize=6, ha="center", va="center",
            color=border, fontweight="bold", zorder=5)


def render_pid(process: Process, output_path: str,
               width: float = 20.0, height: float = 11.5) -> str:
    """Render a schematic P&ID: PFD + pumps + control valves + instruments.

    NOT a real engineering P&ID — instruments are added heuristically based on
    section kind. Treat this as a starting point / illustration only.
    """
    if not _HAS_MPL:
        raise RuntimeError("matplotlib required")
    _ensure_dir(output_path)

    inputs, outputs, sections = _classify_nodes(process)
    back = _detect_recycle_edges(process)
    pos, rows, cols, dx, dy = _layered_positions_pfd(process)

    xs = [x for x, _ in pos.values()]
    ys = [y for _, y in pos.values()]
    fig, ax = plt.subplots(figsize=(width, height))
    ax.set_xlim(min(xs) - 2.8, max(xs) + 2.8)
    ax.set_ylim(min(ys) - 2.5, max(ys) + 2.0)
    ax.set_aspect("equal", adjustable="datalim")
    ax.axis("off")

    SEC_BOX = (2.8, 1.3)
    IO_BOX = (1.7, 0.65)

    def _box_for(k):
        if k.startswith("in:") or k.startswith("out:"):
            return IO_BOX
        return SEC_BOX

    # Draw main-flow edges + insert PUMP on each connection between sections
    for (src, dst, label) in process.edges:
        if src not in pos or dst not in pos:
            continue
        is_recycle = (src, dst) in back
        x1, y1 = pos[src]; x2, y2 = pos[dst]
        if is_recycle:
            _draw_arrow(ax, x1, y1, x2, y2,
                        color="#D32F2F", linewidth=2.4, linestyle="--",
                        curve=0.55,
                        label=(label + " [recycle]") if label else "recycle",
                        label_color="#D32F2F",
                        src_box=_box_for(src), dst_box=_box_for(dst))
        else:
            _draw_arrow(ax, x1, y1, x2, y2,
                        color="#1565C0", linewidth=1.8, curve=0.10,
                        label=label, label_color="#1565C0",
                        src_box=_box_for(src), dst_box=_box_for(dst))
            # Pump on inter-section lines (skip in/out connections)
            if (not src.startswith("in:")) and (not dst.startswith("out:")):
                mx, my = (x1 + x2) / 2, (y1 + y2) / 2
                _draw_pump(ax, mx, my)

    # Add control valve on every OUT-going line (to product / waste)
    for (src, dst, _) in process.edges:
        if dst.startswith("out:") and src in pos and dst in pos:
            x1, y1 = pos[src]; x2, y2 = pos[dst]
            cx = x1 + (x2 - x1) * 0.7
            cy = y1 + (y2 - y1) * 0.7
            _draw_control_valve(ax, cx, cy)

    # Draw nodes + instruments
    for k, (x, y) in pos.items():
        if k.startswith("in:"):
            label = "IN\n" + k[3:]
            _draw_box(ax, x, y, 1.7, 0.65, label, "#E8F5E9", "#2E7D32",
                      fontsize=7, fontweight="normal")
            _draw_instrument(ax, x + 0.95, y + 0.2, "FI")
        elif k.startswith("out:"):
            label = "OUT\n" + k[4:]
            _draw_box(ax, x, y, 1.7, 0.65, label, "#FFF3E0", "#E65100",
                      fontsize=7, fontweight="normal")
        else:
            sec = next((s for s in process.sections if s.key == k), None)
            label = sec.label if sec else k
            ut = UNIT_TYPES.get(sec.kind if sec else "Generic", UNIT_TYPES["Generic"])
            _draw_box(ax, x, y, 2.8, 1.3, label, ut["color"], ut["border"],
                      fontsize=8)
            # Instrument balloons clustered above the box
            tags = _INSTRUMENT_RULES.get(sec.kind if sec else "Generic", ["TI"])
            for i, tag in enumerate(tags):
                tx = x - (len(tags) - 1) * 0.18 + i * 0.36
                ty = y + 0.85
                _draw_instrument(ax, tx, ty, tag)

    # Legend block
    legend_x = min(xs) - 2.5
    legend_y = min(ys) - 1.5
    ax.text(legend_x, legend_y + 0.6,
            "P&ID symbol legend:", fontsize=9, fontweight="bold")
    _draw_pump(ax, legend_x + 0.4, legend_y); ax.text(legend_x + 0.85, legend_y,
                                                       "Pump", fontsize=8, va="center")
    _draw_control_valve(ax, legend_x + 1.8, legend_y); ax.text(legend_x + 2.25, legend_y,
                                                                "Control valve (with FC controller)",
                                                                fontsize=8, va="center")
    _draw_instrument(ax, legend_x + 4.2, legend_y, "TI")
    ax.text(legend_x + 4.5, legend_y,
            "Instrument: T=Temp, P=Pressure, F=Flow, L=Level, V=Voltage, A=Current, pH",
            fontsize=8, va="center")
    ax.text(legend_x, legend_y - 0.5,
            "BLUE solid = main flow.   RED dashed = recycle loop. "
            "Instruments added heuristically per unit kind — treat this P&ID as illustrative, not engineering-grade.",
            fontsize=8, color="#333")

    ax.set_title("P&ID — " + process.name + " (schematic)",
                 fontsize=12, pad=10)
    fig.tight_layout()
    fig.savefig(output_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return output_path
