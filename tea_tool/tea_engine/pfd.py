"""Process Flow Diagram - emit a graphviz DOT string from a Process.

Streamlit can render DOT directly via st.graphviz_chart so we don't need
a graphviz binary on the system.
"""
from __future__ import annotations
from typing import Iterable

from .process import Process

_PALETTE = {
    "input":   "#FFE0B2",   # warm orange
    "output":  "#C8E6C9",   # green
    "section": "#BBDEFB",   # blue
    "utility": "#F8BBD0",   # pink
}


def _esc(s: str) -> str:
    return s.replace('"', '\\"')


def _flow_badge(stream) -> str:
    """One-line badge describing a stream's time-resolved flow mode."""
    mode = getattr(stream, "flow_mode", "continuous")
    if mode == "one_time":
        kg = getattr(stream, "initial_charge_kg_per_ton", 0.0)
        return f"◆ initial only ({kg:g} kg/ton)"
    if mode == "periodic":
        months = getattr(stream, "replacement_interval_months", 0.0)
        years = months / 12.0
        unit = f"{years:g} y" if years >= 1 else f"{months:g} mo"
        return f"⏳ every {unit}"
    if getattr(stream, "recovery", 0.0) > 0:
        return f"♻ recycle {stream.recovery:.3g}"
    return ""


def build_pfd_dot(process: Process) -> str:
    """Return a DOT graph: feedstock → sections (in order) → products."""
    lines = [
        'digraph PFD {',
        '  rankdir=LR;',
        '  graph [bgcolor="white", fontname="Helvetica", fontsize=11, splines=ortho];',
        '  node  [fontname="Helvetica", fontsize=11, style="filled,rounded"];',
        '  edge  [fontname="Helvetica", fontsize=9, color="#555555"];',
        '',
        f'  label = "{_esc(process.name)}";',
        '  labelloc = "t";',
        '  fontsize = 14;',
        '',
    ]

    # Feedstock cluster (inputs)
    lines.append('  subgraph cluster_in {')
    lines.append('    label = "Feedstock & Reactants"; style="rounded,dashed"; color="#888";')
    for s in process.streams.inputs:
        nid = f"in_{s.component}"
        badge = _flow_badge(s)
        lab = f"{_esc(s.component)}\\n({s.mass_per_batch_g} g/batch)"
        if badge:
            lab += f"\\n{badge}"
        lines.append(f'    {nid} [shape=parallelogram, fillcolor="{_PALETTE["input"]}", label="{lab}"];')
    lines.append('  }')
    lines.append('')

    # Sections (process unit ops)
    lines.append('  subgraph cluster_proc {')
    lines.append('    label = "Process"; style="rounded"; color="#666";')
    for sec in process.sections:
        nid = f"sec_{sec.key}"
        lab = _esc(sec.label)
        lines.append(f'    {nid} [shape=box, fillcolor="{_PALETTE["section"]}", label="{lab}"];')
    lines.append('  }')
    lines.append('')

    # Outputs
    lines.append('  subgraph cluster_out {')
    lines.append('    label = "Products"; style="rounded,dashed"; color="#888";')
    for s in process.streams.outputs:
        nid = f"out_{s.component}"
        lab = f"{_esc(s.component)}\\n({s.mass_per_batch_g} g/batch)"
        lines.append(f'    {nid} [shape=parallelogram, fillcolor="{_PALETTE["output"]}", label="{lab}"];')
    lines.append('  }')
    lines.append('')

    # Edges declared by the process (between sections, and from inputs/to outputs)
    seen_section_link = False
    for src, dst, label in process.edges:
        # accept "in:<comp>", "out:<comp>", or "<section_key>"
        def to_node(token: str) -> str:
            if token.startswith("in:"):
                return f"in_{token[3:]}"
            if token.startswith("out:"):
                return f"out_{token[4:]}"
            return f"sec_{token}"
        a, b = to_node(src), to_node(dst)
        lab = f' [label="{_esc(label)}"]' if label else ''
        lines.append(f'  {a} -> {b}{lab};')
        seen_section_link = True

    # Fallback: if no edges given, chain inputs -> first section -> ... -> last section -> outputs
    if not seen_section_link and process.sections:
        first = f"sec_{process.sections[0].key}"
        last = f"sec_{process.sections[-1].key}"
        for s in process.streams.inputs:
            lines.append(f'  in_{s.component} -> {first};')
        for i in range(len(process.sections) - 1):
            a = f"sec_{process.sections[i].key}"
            b = f"sec_{process.sections[i+1].key}"
            lines.append(f'  {a} -> {b};')
        for s in process.streams.outputs:
            lines.append(f'  {last} -> out_{s.component};')

    lines.append('}')
    return "\n".join(lines)
