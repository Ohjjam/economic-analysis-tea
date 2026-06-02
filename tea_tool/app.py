"""Streamlit UI for the TEA tool — interactive flow editor + TEA report.

Run:
    streamlit run app.py
"""
from __future__ import annotations
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from tea_engine import (
    build_pfd_dot, run_tea, export_tea_xlsx,
    load_experiment, list_experiments, save_experiment, summarize,
    build_process_from_experiment, render_design_note,
    build_scaleup_report,
)
from tea_engine.tea import sensitivity_one_param, TEAInputs
from tea_engine.equipment import CEPCI, Equipment
from tea_engine.streams import Stream
from tea_engine.process import ProcessSection, UNIT_TYPES
from processes import REGISTRY

EXPERIMENTS_DIR = Path(HERE) / "experiments"
DESIGN_NOTES_DIR = Path(HERE) / "design_notes"
EXPERIMENTS_DIR.mkdir(exist_ok=True)
DESIGN_NOTES_DIR.mkdir(exist_ok=True)

# Interactive ReactFlow-based diagram editor
from streamlit_flow import streamlit_flow
from streamlit_flow.elements import StreamlitFlowNode, StreamlitFlowEdge
from streamlit_flow.state import StreamlitFlowState
from streamlit_flow.layouts import LayeredLayout, ManualLayout


st.set_page_config(page_title="TEA Tool", layout="wide", page_icon="📊")

# Make the selected ReactFlow node visibly stand out, and pull edge labels
# off the line for readability.
st.markdown(
    """
    <style>
      /* Selected ReactFlow node: glowing blue outline that wraps the
         whole element regardless of streamlit-flow's inner DOM. */
      .react-flow__node.selected {
          outline: 4px solid rgba(33, 150, 243, 0.65) !important;
          outline-offset: 2px;
          border-radius: 4px;
          z-index: 10 !important;
      }
      .react-flow__node.selected > * {
          filter: drop-shadow(0 4px 10px rgba(33, 150, 243, 0.30));
          transition: filter 0.15s ease;
      }
      .react-flow__edge-text {
          font-size: 11px !important;
          font-weight: 500 !important;
          fill: #37474F !important;
      }
      .react-flow__edge-textbg {
          fill: #FFFFFF !important;
          fill-opacity: 0.9 !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================ Helpers
def _slug(s: str) -> str:
    return re.sub(r"\W+", "_", s.strip().lower()).strip("_") or "node"


def _flow_mode_badge(s) -> str:
    """Human-readable badge for an input stream's flow_mode."""
    mode = getattr(s, "flow_mode", "continuous")
    if mode == "one_time":
        kg = getattr(s, "initial_charge_kg_per_ton", 0.0)
        return f"◆ initial only ({kg:g} kg/ton)"
    if mode == "periodic":
        months = getattr(s, "replacement_interval_months", 0.0)
        years = months / 12.0
        return f"⏳ every {years:g} y" if years >= 1 else f"⏳ every {months:g} mo"
    if getattr(s, "recovery", 0.0) > 0:
        return f"♻ recycle {s.recovery:.3g}"
    return "♻ cont."


def _input_node(s, x: float, y: float) -> StreamlitFlowNode:
    """Asymmetric chevron, warm gradient — clearly an INPUT.

    Single-line label + g/batch + flow-mode badge.
    """
    badge = _flow_mode_badge(s)
    content = (f"▶ **{s.component}**\n\n"
               f"`{s.mass_per_batch_g:g} g/batch`\n\n"
               f"`{badge}`")
    return StreamlitFlowNode(
        id=f"in:{s.component}",
        pos=(x, y),
        data={"content": content},
        node_type="input",
        source_position="right",
        target_position="left",
        draggable=True, selectable=True, deletable=True, connectable=True, focusable=True,
        style={
            "background":   "linear-gradient(135deg, #FFE0B2 0%, #FFB74D 100%)",
            "border":       "2.5px solid #E65100",
            "borderRadius": "22px 4px 4px 22px",
            "width":        "150px",
            "minHeight":    "60px",
            "padding":      "8px 10px",
            "fontSize":     "12px",
            "lineHeight":   "1.25",
            "color":        "#3E2723",
            "boxShadow":    "0 2px 5px rgba(230, 81, 0, 0.25)",
        },
    )


def _output_node(s, x: float, y: float) -> StreamlitFlowNode:
    """Mirror chevron, cool green gradient — clearly an OUTPUT."""
    content = (f"**{s.component}** ▶\n\n"
               f"`{s.mass_per_batch_g:g} g/batch`")
    return StreamlitFlowNode(
        id=f"out:{s.component}",
        pos=(x, y),
        data={"content": content},
        node_type="output",
        source_position="right",
        target_position="left",
        draggable=True, selectable=True, deletable=True, connectable=True, focusable=True,
        style={
            "background":   "linear-gradient(135deg, #C8E6C9 0%, #66BB6A 100%)",
            "border":       "2.5px solid #1B5E20",
            "borderRadius": "4px 22px 22px 4px",
            "width":        "150px",
            "minHeight":    "60px",
            "padding":      "8px 10px",
            "fontSize":     "12px",
            "lineHeight":   "1.25",
            "color":        "#1B5E20",
            "boxShadow":    "0 2px 5px rgba(27, 94, 32, 0.25)",
        },
    )


def _section_node(sec, x: float, y: float) -> StreamlitFlowNode:
    """Process-step node — shape, colour & icon encode the unit type.

    Compact label (icon + name only) so content fits the styled box.
    Kind / description live in the click-to-edit form, not on the canvas.
    """
    ut = UNIT_TYPES.get(sec.kind, UNIT_TYPES["Generic"])
    content = f"{ut['icon']}  **{sec.label}**"
    # Distillation columns / absorbers are tall+narrow — need tighter line wrap
    is_tall = ut["h"] > ut["w"]
    if is_tall:
        content = f"{ut['icon']}\n\n**{sec.label}**"
    return StreamlitFlowNode(
        id=f"sec:{sec.key}",
        pos=(x, y),
        data={"content": content},
        node_type="default",
        source_position="right",
        target_position="left",
        draggable=True, selectable=True, deletable=True, connectable=True, focusable=True,
        style={
            "background":   ut["color"],
            "border":       f"2px solid {ut['border']}",
            "borderRadius": f"{ut['radius']}px",
            "width":        f"{ut['w']}px",
            "minHeight":    f"{ut['h']}px",
            "padding":      "8px",
            "fontSize":     "12px",
            "lineHeight":   "1.25",
            "color":        "#212121",
            "boxShadow":    "0 2px 4px rgba(0,0,0,0.12)",
            "textAlign":    "center",
            "display":      "flex",
            "alignItems":   "center",
            "justifyContent": "center",
        },
    )


def _edge_to_flow_id(token: str) -> str:
    """Map a process-edge token (in:X, out:X, sec_key) to a flow node id."""
    if token.startswith("in:") or token.startswith("out:"):
        return token
    return f"sec:{token}"


def _flow_id_to_token(node_id: str) -> str:
    if node_id.startswith("in:") or node_id.startswith("out:"):
        return node_id
    if node_id.startswith("sec:"):
        return node_id[4:]
    return node_id


def build_flow_state(process) -> StreamlitFlowState:
    """Construct a fresh StreamlitFlowState from a Process.

    Layout: inputs on the left, sections in the middle (laid out by edge order),
    outputs on the right.  After the first render we let the layout engine /
    user dragging take over.
    """
    nodes = []
    n_in  = len(process.streams.inputs)
    n_out = len(process.streams.outputs)
    n_sec = max(len(process.sections), 1)

    # vertical pitch: just enough to clear the 60-px-min input/output boxes
    in_pitch  = 95
    out_pitch = 95

    # Inputs left column
    for i, s in enumerate(process.streams.inputs):
        nodes.append(_input_node(s, x=0, y=in_pitch * i))

    # Sections in the vertical middle of the input range so edges don't snake
    section_y = max((in_pitch * (n_in - 1)) // 2 - 30, 0)
    section_x_start = 230
    section_x_step  = 250
    for i, sec in enumerate(process.sections):
        nodes.append(_section_node(sec,
                                   x=section_x_start + section_x_step * i,
                                   y=section_y))

    # Outputs right column, vertically centred near sections
    out_x = section_x_start + section_x_step * n_sec + 30
    out_y_offset = max(section_y - (out_pitch * (n_out - 1)) // 2, 0)
    for i, s in enumerate(process.streams.outputs):
        nodes.append(_output_node(s, x=out_x, y=out_y_offset + out_pitch * i))
    # edges
    edges = []
    for i, (src, dst, lab) in enumerate(process.edges):
        edges.append(StreamlitFlowEdge(
            id=f"e{i}",
            source=_edge_to_flow_id(src),
            target=_edge_to_flow_id(dst),
            label=lab or "",
            edge_type="smoothstep",
            animated=False, deletable=True, focusable=True,
            label_show_bg=True,
            label_bg_style={"fill": "#FFFFFF", "fillOpacity": 0.85},
        ))
    return StreamlitFlowState(nodes=nodes, edges=edges)


def sync_flow_to_process(state: StreamlitFlowState, process) -> None:
    """Apply user's changes from the canvas back into the Process model.

    - Topology (sections, edges) is fully driven by the canvas.
    - Stream nodes deleted on the canvas are removed from streams too.
    - Stream g values, equipment, prices stay edited via side forms.
    """
    flow_node_ids = {n.id for n in state.nodes}

    # Remove sections no longer present
    process.sections = [s for s in process.sections
                        if f"sec:{s.key}" in flow_node_ids]
    # Remove streams no longer present
    process.streams.inputs  = [s for s in process.streams.inputs
                               if f"in:{s.component}" in flow_node_ids]
    process.streams.outputs = [s for s in process.streams.outputs
                               if f"out:{s.component}" in flow_node_ids]

    # Rebuild edges from canvas
    new_edges = []
    for e in state.edges:
        new_edges.append((_flow_id_to_token(e.source),
                          _flow_id_to_token(e.target),
                          e.label or ""))
    process.edges = new_edges


def refresh_node_label(state: StreamlitFlowState, node_id: str, new_label_md: str) -> None:
    for n in state.nodes:
        if n.id == node_id:
            n.data["content"] = new_label_md
            return


# ============================================================ Header / sidebar
st.title("📊 Process TEA Tool")
st.caption("Drag, connect, click to edit a process flow diagram for "
           "Water Electrolysis / CO2RR / Plastic / Biomass; the TEA "
           "(CAPEX, OPEX, MSP, sensitivity) recalculates live and exports to xlsx.")


with st.sidebar:
    st.header("Process selection")
    source = st.radio(
        "Process source",
        ["Template", "🧪 From experiment YAML"],
        horizontal=False,
        help="Templates are the curated process catalog. Selecting an "
             "experiment YAML auto-generates a first-cut Process / TEA "
             "from `experiments/<slug>.yaml`.",
    )

    if source == "Template":
        proc_name = st.selectbox("Process template", list(REGISTRY.keys()))
        proc_key = f"tmpl::{proc_name}"
    else:
        exp_paths = list_experiments(EXPERIMENTS_DIR)
        if not exp_paths:
            st.warning("No YAML found in `experiments/`. Use the **🧪 Lab Data** tab "
                       "to create one, or copy `experiments/example_lignin_pma_mw.yaml` "
                       "as a starting point.")
            proc_name = list(REGISTRY.keys())[0]
            proc_key = f"tmpl::{proc_name}"
        else:
            labels = [p.stem for p in exp_paths]
            picked = st.selectbox("Experiment YAML", labels)
            proc_key = f"exp::{picked}"
            proc_name = picked  # used downstream for display only

    if "loaded_proc" not in st.session_state or st.session_state.loaded_proc != proc_key:
        if proc_key.startswith("tmpl::"):
            process, db, default_inp = REGISTRY[proc_name]()
        else:
            slug = proc_key[len("exp::"):]
            exp_obj = load_experiment(EXPERIMENTS_DIR / f"{slug}.yaml")
            process, db, default_inp = build_process_from_experiment(exp_obj)
            st.session_state.current_experiment = exp_obj
        st.session_state.process = process
        st.session_state.db = db
        st.session_state.inp = default_inp
        st.session_state.loaded_proc = proc_key
        st.session_state.flow_state = build_flow_state(process)
        st.session_state.canvas_rev = 0   # force-remount key

    process = st.session_state.process
    db = st.session_state.db
    inp: TEAInputs = st.session_state.inp

    output_names = [s.component for s in process.streams.outputs] or ["—"]
    inp.msp_product = st.selectbox(
        "MSP product", output_names,
        index=output_names.index(inp.msp_product) if inp.msp_product in output_names else 0,
        help="The product whose minimum-selling-price (MSP) is computed.",
    )

    with st.expander("⚙️ Economic assumptions", expanded=False):
        inp.discount_rate     = st.number_input("Discount rate", 0.0, 0.50, inp.discount_rate, 0.01, format="%.4f")
        inp.lifetime_years    = st.number_input("Plant lifetime (years)", 1, 60, inp.lifetime_years)
        inp.capacity_factor   = st.slider("Capacity factor", 0.1, 1.0, inp.capacity_factor, 0.01)
        inp.cepci_target_year = st.selectbox("CEPCI target year", sorted(CEPCI.keys()),
                                             index=sorted(CEPCI.keys()).index(inp.cepci_target_year))
        inp.osbl_fraction     = st.slider("OSBL (% of ISBL)", 0.0, 0.6, inp.osbl_fraction, 0.01)
        inp.maintenance_fraction = st.slider("Maintenance (% of CAPEX)", 0.0, 0.20, inp.maintenance_fraction, 0.01)
        inp.operation_fraction   = st.slider("Operation (% of CAPEX)",   0.0, 0.20, inp.operation_fraction, 0.01)
        inp.batch_hours       = st.number_input("Batch time (h)", 0.1, 240.0, inp.batch_hours, 0.5)

    with st.expander("📈 Production scales", expanded=False):
        # Pick a few representative anchor points from the ladder; the
        # auto-built ladder can have up to 5 stages — we expose the
        # smallest, middle, and largest so the existing TEA still works.
        scales_sorted = sorted(float(x) for x in inp.scales_ton)
        n = len(scales_sorted)
        defaults = (scales_sorted[0],
                    scales_sorted[n // 2] if n >= 2 else scales_sorted[0],
                    scales_sorted[-1])
        s1 = st.number_input("Scale A (ton feed/batch)", 1e-4, 1.0e4,
                             defaults[0], format="%.4f")
        s2 = st.number_input("Scale B (ton feed/batch)", 1e-4, 1.0e4,
                             defaults[1], format="%.4f")
        s3 = st.number_input("Scale C (ton feed/batch)", 1e-4, 1.0e4,
                             defaults[2], format="%.4f")
        inp.scales_ton = (s1, s2, s3)

    if st.button("🔄 Reset diagram to source default", use_container_width=True):
        if proc_key.startswith("tmpl::"):
            process2, _, _ = REGISTRY[proc_name]()
        else:
            slug = proc_key[len("exp::"):]
            process2, _, _ = build_process_from_experiment(
                load_experiment(EXPERIMENTS_DIR / f"{slug}.yaml"))
        st.session_state.process = process2
        st.session_state.flow_state = build_flow_state(process2)
        st.session_state.canvas_rev += 1
        st.rerun()


# ============================================================ Tabs
(tab_lab, tab_flow, tab_streams, tab_eq, tab_prices, tab_tea,
 tab_plots, tab_time, tab_sens, tab_scaleup, tab_export) = st.tabs([
    "🧪 Lab Data", "🧩 Flow Editor", "Streams", "Equipment", "💰 Prices",
    "TEA tables", "Plots", "📅 Time Profile", "Sensitivity",
    "📈 Scale-up", "Export"
])

# =================================================== Lab Data Input =====
with tab_lab:
    st.markdown("#### 🧪 Lab Data Input — feed an experiment into the AI design pipeline")
    st.caption(
        "Fill the form, save it as a YAML in `experiments/`, then either "
        "(a) select it from the sidebar **🧪 From experiment YAML** to see a "
        "first-cut TEA, or (b) ask Claude Code to refine the process design "
        "with the auto-generated instruction at the bottom of this tab."
    )

    lab_col_left, lab_col_right = st.columns([6, 4], gap="large")

    with lab_col_left:
        existing = list_experiments(EXPERIMENTS_DIR)
        existing_labels = ["<new>"] + [p.stem for p in existing]
        pick = st.selectbox("Load existing YAML (or `<new>` for blank form)", existing_labels)

        if pick != "<new>":
            try:
                loaded_raw = yaml.safe_load(
                    (EXPERIMENTS_DIR / f"{pick}.yaml").read_text(encoding="utf-8")
                ) or {}
            except Exception as exc:  # noqa: BLE001
                st.error(f"Failed to load: {exc}")
                loaded_raw = {}
        else:
            loaded_raw = {}

        meta = loaded_raw.get("meta", {}) or {}
        chem = loaded_raw.get("chemistry", {}) or {}
        feed = loaded_raw.get("feedstock", {}) or {}
        prim = feed.get("primary", {}) or {}
        reag = feed.get("reagents", []) or []
        op = loaded_raw.get("operating_conditions", {}) or {}
        ec = op.get("electrochem", {}) or {}
        res = loaded_raw.get("results", {}) or {}
        yields = res.get("yields", []) or []
        downstream = loaded_raw.get("downstream", []) or []
        cons = loaded_raw.get("constraints", {}) or {}
        sct = loaded_raw.get("scale_targets", {}) or {}

        st.markdown("**1) Metadata**")
        c1, c2 = st.columns(2)
        with c1:
            name_in = st.text_input("Experiment name *", meta.get("name", ""))
            slug_in = st.text_input("Slug (file-safe id) *", meta.get("slug", ""))
        with c2:
            date_in = st.text_input("Date (YYYY-MM-DD)", str(meta.get("date") or ""))
            who_in = st.text_input("Researcher", meta.get("researcher", ""))
        notes_in = st.text_area("Notes", meta.get("notes", ""), height=70)

        st.markdown("**2) Chemistry**")
        rtype_options = ["thermal", "catalytic", "electrochemical",
                         "photochemical", "biological", "hybrid", "unspecified"]
        rt_default = chem.get("reaction_type", "unspecified")
        rt_idx = rtype_options.index(rt_default) if rt_default in rtype_options else 6
        rtype_in = st.selectbox("Reaction type", rtype_options, index=rt_idx)
        chem_desc = st.text_area("Chemistry description",
                                 chem.get("description", ""), height=70)
        targets_in = st.text_input(
            "Target products (comma-separated)",
            ", ".join(chem.get("target_products") or []))

        st.markdown("**3) Primary feedstock**")
        c1, c2, c3 = st.columns(3)
        with c1:
            feed_name = st.text_input("Feed name *", prim.get("name", ""))
        with c2:
            feed_g = st.number_input("Mass per batch (g) *",
                                     min_value=0.0, value=float(prim.get("mass_per_batch_g", 1.0)))
        with c3:
            feed_price = st.number_input("Price ($/kg, optional)",
                                         min_value=0.0,
                                         value=float(prim.get("price_usd_per_kg") or 0.0),
                                         step=0.01, format="%.4f")
        feed_src = st.text_input("Source note", prim.get("source_note", ""))

        st.markdown("**4) Reagents** (editable table)")
        reag_df = pd.DataFrame(
            reag or [{"name": "", "mass_per_batch_g": 0.0,
                      "recovery_fraction": 0.0, "role": "input",
                      "price_usd_per_kg": 0.0}]
        )
        reag_edited = st.data_editor(
            reag_df, num_rows="dynamic",
            column_config={
                "role": st.column_config.SelectboxColumn(
                    options=["input", "catalyst", "solvent", "utility"]),
                "recovery_fraction": st.column_config.NumberColumn(
                    min_value=0.0, max_value=1.0, step=0.01),
                "mass_per_batch_g": st.column_config.NumberColumn(min_value=0.0),
                "price_usd_per_kg": st.column_config.NumberColumn(min_value=0.0, step=0.01),
            },
            key="lab_reagents_editor",
        )

        st.markdown("**5) Operating conditions**")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            T_in = st.number_input("Temperature (°C)", -200.0, 1500.0,
                                   float(op.get("temperature_C", 25.0)))
        with c2:
            P_in = st.number_input("Pressure (bar)", 0.01, 1000.0,
                                   float(op.get("pressure_bar", 1.0)))
        with c3:
            pH_in = st.number_input("pH", 0.0, 14.0, float(op.get("ph", 7.0)))
        with c4:
            t_in = st.number_input("Reaction time (h)", 0.01, 1000.0,
                                   float(op.get("reaction_time_h", 1.0)))

        with st.expander("⚡ Electrochemistry (optional)", expanded=bool(ec)):
            ec_voltage = st.number_input("Cell voltage (V)", 0.0, 20.0,
                                         float(ec.get("cell_voltage_V") or 0.0), 0.01)
            ec_j = st.number_input("Current density (mA/cm²)", 0.0, 5000.0,
                                   float(ec.get("current_density_mA_cm2") or 0.0))
            ec_fe = st.number_input("Faradaic efficiency (%)", 0.0, 100.0,
                                    float(ec.get("faradaic_efficiency_pct") or 0.0))
            ec_area = st.number_input("Electrode area (cm²)", 0.0, 1e5,
                                      float(ec.get("electrode_area_cm2") or 0.0))
            ec_electrolyte = st.text_input("Electrolyte", ec.get("electrolyte", ""))
            ec_membrane = st.text_input("Membrane", ec.get("membrane", ""))

        st.markdown("**6) Results — product yields**")
        y_df = pd.DataFrame(
            yields or [{"product": "", "yield_pct": 0.0, "selectivity_pct": 0.0}]
        )
        y_edited = st.data_editor(
            y_df, num_rows="dynamic",
            column_config={
                "yield_pct": st.column_config.NumberColumn(min_value=0.0),
                "selectivity_pct": st.column_config.NumberColumn(min_value=0.0),
            },
            key="lab_yields_editor",
        )
        c1, c2 = st.columns(2)
        with c1:
            conv_in = st.number_input("Conversion (%)", 0.0, 100.0,
                                      float(res.get("conversion_pct") or 0.0))
        with c2:
            mb_in = st.number_input("Mass balance closure (%)", 0.0, 100.0,
                                    float(res.get("mass_balance_closure_pct") or 0.0))

        st.markdown("**7) Downstream / separation** (editable table)")
        ds_df = pd.DataFrame(
            downstream or [{"step": "", "method": "", "solvent": "",
                            "solvent_loading_kg_per_kg_feed": 0.0,
                            "recovery_pct": 100.0, "target_purity_pct": 95.0}]
        )
        ds_edited = st.data_editor(
            ds_df, num_rows="dynamic",
            column_config={
                "solvent_loading_kg_per_kg_feed": st.column_config.NumberColumn(min_value=0.0),
                "recovery_pct": st.column_config.NumberColumn(min_value=0.0, max_value=100.0),
                "target_purity_pct": st.column_config.NumberColumn(min_value=0.0, max_value=100.0),
            },
            key="lab_downstream_editor",
        )

        st.markdown("**8) Constraints & scale-up targets**")
        c1, c2 = st.columns(2)
        with c1:
            msp_prod_in = st.text_input("Preferred MSP product",
                                        cons.get("preferred_msp_product", ""))
            haz_in = st.text_input("Hazardous materials (comma-sep)",
                                   ", ".join(cons.get("hazardous_materials") or []))
            prio_in = st.selectbox("Scale-up priority",
                                   ["balanced", "capex", "opex", "maximum_throughput"],
                                   index=["balanced", "capex", "opex", "maximum_throughput"]
                                   .index(cons.get("scale_up_priority", "balanced")))
        with c2:
            life_in = st.number_input("Plant lifetime (y)", 1, 60,
                                      int(cons.get("plant_lifetime_years", 20)))
            dr_in = st.number_input("Discount rate", 0.0, 0.5,
                                    float(cons.get("discount_rate", 0.10)), 0.01)
            scales_in = st.text_input(
                "Scale ladder (ton/batch, comma-sep)",
                ", ".join(str(x) for x in (sct.get("scales_ton_per_batch") or
                                           [0.01, 0.1, 1.0, 5.0, 10.0])))

        cap_in = st.slider("Capacity factor", 0.1, 1.0,
                           float(sct.get("capacity_factor", 0.8)), 0.01)
        bh_in = st.number_input("Batch hours", 0.1, 720.0,
                                float(sct.get("batch_hours", 2.0)))

        if st.button("💾 Save YAML to experiments/", type="primary"):
            if not name_in or not slug_in:
                st.error("Name and slug are required.")
            else:
                slug_safe = re.sub(r"[^a-zA-Z0-9_\-]+", "_", slug_in).strip("_")
                out = {
                    "meta": {
                        "name": name_in,
                        "slug": slug_safe,
                        "date": date_in or None,
                        "researcher": who_in,
                        "notes": notes_in,
                    },
                    "chemistry": {
                        "reaction_type": rtype_in,
                        "description": chem_desc,
                        "target_products": [t.strip() for t in targets_in.split(",") if t.strip()],
                    },
                    "feedstock": {
                        "primary": {
                            "name": feed_name, "mass_per_batch_g": feed_g,
                            "price_usd_per_kg": feed_price or None,
                            "source_note": feed_src,
                        },
                        "reagents": [
                            {k: (None if pd.isna(v) else v) for k, v in row.items()}
                            for row in reag_edited.fillna("").to_dict(orient="records")
                            if row.get("name")
                        ],
                    },
                    "operating_conditions": {
                        "temperature_C": T_in, "pressure_bar": P_in,
                        "ph": pH_in, "reaction_time_h": t_in,
                        "electrochem": ({
                            "cell_voltage_V": ec_voltage,
                            "current_density_mA_cm2": ec_j,
                            "faradaic_efficiency_pct": ec_fe,
                            "electrode_area_cm2": ec_area,
                            "electrolyte": ec_electrolyte,
                            "membrane": ec_membrane,
                        } if (ec_voltage or ec_j or ec_fe) else {}),
                    },
                    "results": {
                        "yields": [
                            row for row in y_edited.fillna(0).to_dict(orient="records")
                            if row.get("product")
                        ],
                        "conversion_pct": conv_in,
                        "mass_balance_closure_pct": mb_in,
                    },
                    "downstream": [
                        row for row in ds_edited.fillna("").to_dict(orient="records")
                        if row.get("step")
                    ],
                    "constraints": {
                        "preferred_msp_product": msp_prod_in,
                        "hazardous_materials": [h.strip() for h in haz_in.split(",") if h.strip()],
                        "scale_up_priority": prio_in,
                        "plant_lifetime_years": life_in,
                        "discount_rate": dr_in,
                    },
                    "scale_targets": {
                        "scales_ton_per_batch": [float(x.strip()) for x in scales_in.split(",") if x.strip()],
                        "capacity_factor": cap_in,
                        "batch_hours": bh_in,
                    },
                }
                target = EXPERIMENTS_DIR / f"{slug_safe}.yaml"
                save_experiment(out, target)
                st.success(f"Saved → {target.relative_to(Path(HERE))}")
                st.session_state["_just_saved_slug"] = slug_safe

    with lab_col_right:
        st.markdown("**Claude Code instruction**")
        st.caption("Copy-paste this into the Claude Code CLI to have the "
                   "agent refine the auto-generated process.")
        target_slug = (st.session_state.get("_just_saved_slug")
                       or (pick if pick != "<new>" else "<your-slug>"))
        instruction = f"""\
Read `experiments/{target_slug}.yaml`. Then:
1. Compare 2-3 process design options for this chemistry (reaction
   vessel choice, separation strategy, recycle topology) and pick one
   with a 1-paragraph justification.
2. Write `processes/from_experiment_{target_slug}.py` with vendor-grade
   equipment costs (cite each source in a comment), updated stream
   recoveries based on the downstream methods, and explicit
   `process.meta` entries for electricity / heating / cooling utilities.
3. Save a design note at `design_notes/{target_slug}.md` documenting
   the option comparison, key assumptions, and scale-up risks.
4. Run `py -3 -c "from processes.from_experiment_{target_slug} import build; \\
   from tea_engine import run_tea, export_tea_xlsx; \\
   p,d,i = build(); r = run_tea(p,d,i); \\
   export_tea_xlsx('output/{target_slug}_TEA.xlsx', p, d, i, r); \\
   print('MSP:', r.msp[max(i.scales_ton)])"`
5. Report MSP at lab / pilot / commercial and the dominant cost line.
"""
        st.code(instruction, language="markdown")

        st.markdown("**Quick auto first-cut**")
        st.caption("Runs `build_process_from_experiment` on the YAML and "
                   "writes a starter design note — no Claude Code involved.")
        run_target = st.text_input("YAML slug to bootstrap",
                                   st.session_state.get("_just_saved_slug", ""))
        if st.button("🚀 Bootstrap design note + xlsx"):
            try:
                ep = EXPERIMENTS_DIR / f"{run_target}.yaml"
                exp_obj = load_experiment(ep)
                p, d, i = build_process_from_experiment(exp_obj)
                r = run_tea(p, d, i)
                xlsx_out = Path(HERE) / "output" / f"{run_target}_auto_TEA.xlsx"
                export_tea_xlsx(str(xlsx_out), p, d, i, r)
                note_md = render_design_note(exp_obj)
                note_path = DESIGN_NOTES_DIR / f"{run_target}.md"
                note_path.write_text(note_md, encoding="utf-8")
                ton = max(i.scales_ton)
                st.success(
                    f"Done. MSP at {ton} ton/batch = "
                    f"${r.msp[ton]:.2f}/kg • CAPEX ${r.capex_total[ton]/1e6:.2f}M • "
                    f"OPEX ${r.opex_total[ton]/1e6:.2f}M/y"
                )
                st.markdown(f"- xlsx → `{xlsx_out.relative_to(Path(HERE))}`")
                st.markdown(f"- design note → `{note_path.relative_to(Path(HERE))}`")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Failed: {exc}")

        st.markdown("---")
        st.markdown("**Design note for current source**")
        if proc_key.startswith("exp::"):
            slug = proc_key[len("exp::"):]
            note_path = DESIGN_NOTES_DIR / f"{slug}.md"
            if note_path.exists():
                st.code(note_path.read_text(encoding="utf-8")[:4000],
                        language="markdown")
            else:
                st.info("No design note saved yet. Use 🚀 Bootstrap above "
                        "or have Claude Code generate one.")
        else:
            st.info("Switch the sidebar source to **🧪 From experiment YAML** "
                    "to view the corresponding design note.")

# =================================================== Flow Editor =====
with tab_flow:
    st.markdown("#### Interactive Process Flow Diagram")
    st.caption("Drag nodes • Drag handle-to-handle to connect • Right-click for menu • "
               "Click a node → edit panel appears on the right →")

    canvas_col, inspector_col = st.columns([7, 3], gap="small")

    # ============== CANVAS (left, 70%) ==============
    with canvas_col:
        canvas_key = f"pfd_canvas_{st.session_state.canvas_rev}"
        new_state = streamlit_flow(
            canvas_key,
            state=st.session_state.flow_state,
            height=620,
            fit_view=True,
            show_controls=True,
            show_minimap=False,           # was distracting at this size
            allow_new_edges=True,
            animate_new_edges=True,
            get_node_on_click=True,
            get_edge_on_click=True,
            enable_node_menu=True,
            enable_edge_menu=True,
            enable_pane_menu=False,
            hide_watermark=True,
            layout=ManualLayout(),
        )
        st.session_state.flow_state = new_state
        sync_flow_to_process(new_state, process)

    # ============== INSPECTOR (right, 30%) ==============
    # Selected-node highlight is handled by injected CSS (`.react-flow__node.selected`),
    # so the visual feedback appears immediately without a Streamlit rerun.
    selected_id = getattr(new_state, "selected_id", None)

    with inspector_col:
        st.markdown("##### 🛠️ Inspector")

        # ---- Selected-node editor ----
        # Clear visual cue at the top of the panel about which node is being edited.
        if selected_id and selected_id.startswith("in:"):
            comp = selected_id[3:]
            s = next((x for x in process.streams.inputs if x.component == comp), None)
            if s:
                st.markdown(
                    f"<div style='background:linear-gradient(90deg,#FFE0B2,#FFB74D);"
                    f"border-left:4px solid #E65100;padding:8px 12px;border-radius:4px;"
                    f"margin-bottom:8px;'><b>▶ Input · {comp}</b></div>",
                    unsafe_allow_html=True)
                new_g = st.number_input("g / batch", min_value=0.0,
                                        value=float(s.mass_per_batch_g),
                                        step=0.0001, format="%.6f",
                                        key=f"edit_g_{comp}")
                new_rec_pct = st.slider(
                    "Recovery (%)", 0.0, 100.0,
                    float(s.recovery * 100.0),
                    step=0.1, format="%.1f%%",
                    key=f"edit_rec_{comp}",
                    help="Fraction of this stream that is recycled (so only the make-up amount counts as feedstock OPEX)."
                )
                new_rec = new_rec_pct / 100.0
                cur_price = (db.components[comp].price_low if comp in db else 0.0) or 0.0
                new_pri = st.number_input("Price ($/kg)", 0.0, 1e6,
                                          value=float(cur_price), step=0.01,
                                          format="%.4f", key=f"edit_pri_{comp}")

                # ---- Flow-mode editor (continuous / one_time / periodic) ----
                modes = ("continuous", "one_time", "periodic")
                cur_mode = getattr(s, "flow_mode", "continuous") or "continuous"
                new_mode = st.selectbox(
                    "Flow mode", modes,
                    index=modes.index(cur_mode) if cur_mode in modes else 0,
                    key=f"edit_mode_{comp}",
                    help=("continuous = fed/consumed every batch.  "
                          "one_time = loaded once at t=0 (initial inventory).  "
                          "periodic = fully replaced every N months."),
                )
                new_init = float(getattr(s, "initial_charge_kg_per_ton", 0.0) or 0.0)
                new_int_m = float(getattr(s, "replacement_interval_months", 0.0) or 0.0)
                if new_mode in ("one_time", "periodic"):
                    new_init = st.number_input(
                        "Initial charge (kg / ton-feed)",
                        min_value=0.0, value=new_init, step=0.1, format="%.4f",
                        key=f"edit_init_{comp}",
                        help="Mass loaded at t=0 (per ton of limiting feed at scale).")
                if new_mode == "periodic":
                    new_int_m = st.number_input(
                        "Replacement interval (months)",
                        min_value=1.0, value=max(new_int_m, 12.0),
                        step=1.0, format="%.1f",
                        key=f"edit_int_{comp}",
                        help="How often the entire charge is replaced.")

                changed = (new_g != s.mass_per_batch_g or new_rec != s.recovery
                           or (comp in db and new_pri != (db.components[comp].price_low or 0.0))
                           or new_mode != cur_mode
                           or new_init != float(s.initial_charge_kg_per_ton or 0.0)
                           or new_int_m != float(s.replacement_interval_months or 0.0))
                if changed:
                    s.mass_per_batch_g = float(new_g)
                    s.recovery = float(new_rec)
                    s.flow_mode = new_mode
                    s.initial_charge_kg_per_ton = float(new_init)
                    s.replacement_interval_months = float(new_int_m)
                    if comp in db:
                        db.components[comp].price_low = float(new_pri)
                    badge = _flow_mode_badge(s)
                    refresh_node_label(
                        st.session_state.flow_state, selected_id,
                        f"▶ **{comp}**\n\n`{new_g:g} g/batch`\n\n`{badge}`"
                    )
                    st.session_state.canvas_rev += 1
                    st.rerun()

        elif selected_id and selected_id.startswith("out:"):
            comp = selected_id[4:]
            s = next((x for x in process.streams.outputs if x.component == comp), None)
            if s:
                st.markdown(
                    f"<div style='background:linear-gradient(90deg,#C8E6C9,#66BB6A);"
                    f"border-left:4px solid #1B5E20;padding:8px 12px;border-radius:4px;"
                    f"margin-bottom:8px;color:#1B5E20;'><b>◀ Output · {comp}</b></div>",
                    unsafe_allow_html=True)
                new_g = st.number_input("g / batch", min_value=0.0,
                                        value=float(s.mass_per_batch_g),
                                        step=0.0001, format="%.6f",
                                        key=f"edit_og_{comp}")
                cur_price = (db.components[comp].price_low if comp in db else 0.0) or 0.0
                new_pri = st.number_input("Price ($/kg)", 0.0, 1e6,
                                          value=float(cur_price), step=0.01,
                                          format="%.4f", key=f"edit_opri_{comp}")
                if (new_g != s.mass_per_batch_g
                        or (comp in db and new_pri != (db.components[comp].price_low or 0.0))):
                    s.mass_per_batch_g = float(new_g)
                    if comp in db:
                        db.components[comp].price_low = float(new_pri)
                    refresh_node_label(
                        st.session_state.flow_state, selected_id,
                        f"**{comp}** ▶\n\n`{new_g:g} g/batch`"
                    )
                    st.session_state.canvas_rev += 1
                    st.rerun()

        elif selected_id and selected_id.startswith("sec:"):
            key = selected_id[4:]
            sec = next((x for x in process.sections if x.key == key), None)
            if sec:
                ut = UNIT_TYPES.get(sec.kind, UNIT_TYPES["Generic"])
                st.markdown(
                    f"<div style='background:{ut['color']};"
                    f"border-left:4px solid {ut['border']};padding:8px 12px;border-radius:4px;"
                    f"margin-bottom:8px;'><b>{ut['icon']}  Step · {sec.label}</b></div>",
                    unsafe_allow_html=True)
                new_label = st.text_input("Step name", value=sec.label,
                                          key=f"edit_seclbl_{key}")
                kinds = list(UNIT_TYPES.keys())
                new_kind = st.selectbox(
                    "Unit type", kinds,
                    index=kinds.index(sec.kind) if sec.kind in kinds else 0,
                    key=f"edit_seckind_{key}",
                    format_func=lambda k: f"{UNIT_TYPES[k]['icon']}  {k}",
                )
                new_desc = st.text_area("Description", value=sec.description,
                                        key=f"edit_secdesc_{key}", height=80)
                if (new_label != sec.label or new_desc != sec.description
                        or new_kind != sec.kind):
                    for eq in process.equipment.items:
                        if eq.section == sec.label:
                            eq.section = new_label
                    sec.label = new_label
                    sec.description = new_desc
                    sec.kind = new_kind
                    new_node = _section_node(sec, x=0, y=0)
                    for n in st.session_state.flow_state.nodes:
                        if n.id == selected_id:
                            if hasattr(n, "position"):
                                new_node.position = n.position
                            idx = st.session_state.flow_state.nodes.index(n)
                            st.session_state.flow_state.nodes[idx] = new_node
                            break
                    st.session_state.canvas_rev += 1
                    st.rerun()

        else:
            st.info("👆 **Click a node** to edit it,\nor add a new one below.")

        # ---- Add-a-node panel (always visible, accordion-grouped) ----
        st.divider()
        st.markdown("##### ➕ Add a node")
        add_kind = st.radio(
            "Type", ["Process step", "Input stream", "Output stream"],
            horizontal=True, key="add_kind_picker", label_visibility="collapsed",
        )

        if add_kind == "Process step":
            new_sec_label = st.text_input("Step name", key="add_sec_name",
                                          placeholder="e.g. Pre-distillation")
            new_sec_kind  = st.selectbox(
                "Unit type", list(UNIT_TYPES.keys()),
                index=list(UNIT_TYPES.keys()).index("Generic"),
                key="add_sec_kind",
                format_func=lambda k: f"{UNIT_TYPES[k]['icon']}  {k}",
            )
            new_sec_desc  = st.text_input("Description (optional)", key="add_sec_desc")
            if st.button("Add step", key="add_sec_btn", use_container_width=True):
                if new_sec_label:
                    skey = _slug(new_sec_label)
                    base = skey
                    i = 2
                    while any(s.key == skey for s in process.sections):
                        skey = f"{base}_{i}"; i += 1
                    sec = ProcessSection(skey, new_sec_label,
                                         new_sec_desc or "", kind=new_sec_kind)
                    process.sections.append(sec)
                    n = _section_node(sec,
                                      x=230 + 250 * (len(process.sections) - 1),
                                      y=200)
                    st.session_state.flow_state.nodes.append(n)
                    process.equipment.add(Equipment(
                        name=f"{new_sec_label} - main unit",
                        section=new_sec_label,
                        base_cost=500_000.0, installation_factor=1.0,
                        cepci_ref=inp.cepci_target_year, cap_ref=1.0, scaling_factor=0.6,
                    ))
                    st.session_state.canvas_rev += 1
                    st.rerun()

        elif add_kind == "Input stream":
            new_in_name = st.text_input("Component", key="add_in_name",
                                        placeholder="e.g. CH3OH")
            new_in_g    = st.number_input("g / batch", min_value=0.0, value=1.0,
                                          key="add_in_g")
            new_in_rec_pct = st.slider("Recovery (%)", 0.0, 100.0, 0.0, 0.1,
                                       format="%.1f%%", key="add_in_rec_pct")
            new_in_pri  = st.number_input("Price ($/kg)", 0.0, 1e6, 1.0,
                                          key="add_in_pri")
            if st.button("Add input", key="add_in_btn", use_container_width=True):
                if new_in_name and not process.streams.has(new_in_name):
                    process.streams.add_input(Stream(new_in_name, float(new_in_g),
                                                     recovery=float(new_in_rec_pct/100)))
                    if new_in_name not in db.components:
                        from tea_engine.components import Component
                        db.add(Component(new_in_name, mw=0.0,
                                         price_low=float(new_in_pri), role="input"))
                    else:
                        db.components[new_in_name].price_low = float(new_in_pri)
                    n = _input_node(process.streams.inputs[-1], x=-50,
                                    y=95 * len(process.streams.inputs))
                    st.session_state.flow_state.nodes.append(n)
                    st.session_state.canvas_rev += 1
                    st.rerun()

        else:  # Output stream
            new_out_name = st.text_input("Component", key="add_out_name",
                                         placeholder="e.g. EtOH")
            new_out_g    = st.number_input("g / batch", min_value=0.0, value=1.0,
                                           key="add_out_g")
            new_out_pri  = st.number_input("Price ($/kg)", 0.0, 1e6, 1.0,
                                           key="add_out_pri")
            if st.button("Add output", key="add_out_btn", use_container_width=True):
                if new_out_name and not process.streams.has(new_out_name):
                    process.streams.add_output(Stream(new_out_name, float(new_out_g)))
                    if new_out_name not in db.components:
                        from tea_engine.components import Component
                        db.add(Component(new_out_name, mw=0.0,
                                         price_low=float(new_out_pri), role="output"))
                    else:
                        db.components[new_out_name].price_low = float(new_out_pri)
                    n = _output_node(process.streams.outputs[-1], x=900,
                                     y=95 * len(process.streams.outputs))
                    st.session_state.flow_state.nodes.append(n)
                    st.session_state.canvas_rev += 1
                    st.rerun()


# =================================================== Streams (table) =
with tab_streams:
    st.subheader("Streams (table view)")
    st.caption("Same data as the Flow Editor — handy for bulk editing.")

    col_in, col_out = st.columns(2)
    with col_in:
        st.markdown("**Inputs**")
        in_rows = [{"Component": s.component, "Mass/batch (g)": s.mass_per_batch_g,
                    "Recovery (0-1)": s.recovery,
                    "Flow mode": getattr(s, "flow_mode", "continuous"),
                    "Initial charge (kg/ton)": getattr(s, "initial_charge_kg_per_ton", 0.0),
                    "Replacement (months)": getattr(s, "replacement_interval_months", 0.0),
                    "Note": s.note}
                   for s in process.streams.inputs]
        in_df = st.data_editor(
            pd.DataFrame(in_rows), num_rows="dynamic",
            key="in_editor", use_container_width=True,
            column_config={
                "Flow mode": st.column_config.SelectboxColumn(
                    options=["continuous", "one_time", "periodic"],
                    help="continuous = every batch · one_time = t=0 only · periodic = every N months"),
                "Initial charge (kg/ton)": st.column_config.NumberColumn(
                    format="%.4f", help="Mass loaded at t=0 per ton-feed (one_time / periodic)"),
                "Replacement (months)": st.column_config.NumberColumn(
                    format="%.0f", help="Replacement interval in months (periodic only)"),
            },
        )
        process.streams.inputs.clear()
        for _, row in in_df.iterrows():
            if row.get("Component"):
                mode = str(row.get("Flow mode") or "continuous")
                if mode not in ("continuous", "one_time", "periodic"):
                    mode = "continuous"
                interval = float(row.get("Replacement (months)") or 0.0)
                if mode == "periodic" and interval <= 0:
                    interval = 12.0  # safe default to keep validator happy
                process.streams.inputs.append(Stream(
                    component=str(row["Component"]),
                    mass_per_batch_g=float(row["Mass/batch (g)"]),
                    recovery=float(row["Recovery (0-1)"]) if pd.notna(row["Recovery (0-1)"]) else 0.0,
                    role="input",
                    note=str(row["Note"]) if pd.notna(row["Note"]) else "",
                    flow_mode=mode,
                    initial_charge_kg_per_ton=float(row.get("Initial charge (kg/ton)") or 0.0),
                    replacement_interval_months=interval,
                ))

    with col_out:
        st.markdown("**Outputs**")
        out_rows = [{"Component": s.component, "Mass/batch (g)": s.mass_per_batch_g,
                     "Note": s.note} for s in process.streams.outputs]
        out_df = st.data_editor(pd.DataFrame(out_rows), num_rows="dynamic",
                                key="out_editor", use_container_width=True)
        process.streams.outputs.clear()
        for _, row in out_df.iterrows():
            if row.get("Component"):
                process.streams.outputs.append(Stream(
                    component=str(row["Component"]),
                    mass_per_batch_g=float(row["Mass/batch (g)"]),
                    role="output",
                    note=str(row["Note"]) if pd.notna(row["Note"]) else "",
                ))

    st.subheader("Component prices")
    price_rows = [{"Component": n, "$/kg": (c.price_low or 0.0), "Reference": c.price_ref or ""}
                  for n, c in db.components.items()
                  if any(s.component == n for s in process.streams.inputs + process.streams.outputs)]
    p_df = st.data_editor(pd.DataFrame(price_rows), key="price_editor",
                          use_container_width=True, num_rows="fixed")
    for _, row in p_df.iterrows():
        if row.get("Component") in db:
            db.components[row["Component"]].price_low = float(row["$/kg"])
            db.components[row["Component"]].price_ref = str(row["Reference"]) if pd.notna(row["Reference"]) else ""

    if st.button("Push table changes back to canvas"):
        st.session_state.flow_state = build_flow_state(process)
        st.session_state.canvas_rev += 1
        st.rerun()


# =================================================== Equipment ========
with tab_eq:
    st.subheader("Equipment list (installed cost basis)")
    st.caption("`Base cost` is the installed cost at the reference capacity "
               "(`Cap ref` ton/batch) in `CEPCI ref`.  Scaling to ton uses the "
               "power law with `Scaling exp.`.")
    eq_rows = [{
        "Section": e.section, "Equipment": e.name, "Base cost ($)": e.base_cost,
        "Install. factor": e.installation_factor, "CEPCI ref": e.cepci_ref,
        "Cap ref (ton)": e.cap_ref, "Scaling exp.": e.scaling_factor,
    } for e in process.equipment.items]
    eq_df = st.data_editor(pd.DataFrame(eq_rows), num_rows="dynamic",
                           key="eq_editor", use_container_width=True)
    process.equipment.items.clear()
    for _, row in eq_df.iterrows():
        if row.get("Equipment"):
            process.equipment.add(Equipment(
                name=str(row["Equipment"]),
                section=str(row["Section"]),
                base_cost=float(row["Base cost ($)"]),
                installation_factor=float(row["Install. factor"]),
                cepci_ref=int(row["CEPCI ref"]),
                cap_ref=float(row["Cap ref (ton)"]),
                scaling_factor=float(row["Scaling exp."]),
            ))


# =================================================== Prices ===========
with tab_prices:
    st.subheader("💰 Component prices & data sources")
    st.caption(
        "Prices are loaded from `data/prices.yaml` on every process load. "
        "Each component carries one or more **lookup links** to public price "
        "pages (ECHEMI / Made-in-China / Alibaba / EIA / IEA) — open the link, "
        "copy the latest $/kg, paste into the editor, and click **💾 Save** to "
        "persist back to YAML.  "
        "Paywalled feeds like ICIS / S&P Global aren't scraped automatically."
    )

    from tea_engine.prices import (
        PriceDB, save_prices_to_yaml, build_default_lookups,
        DEFAULT_PRICES_YAML,
    )

    # The PriceDB attached during process load — None on legacy templates
    pdb: PriceDB = getattr(db, "_pricedb", None)
    if pdb is None:
        pdb = PriceDB.load(DEFAULT_PRICES_YAML)
        db._pricedb = pdb

    # Show only components that the current process actually uses
    used = sorted({s.component for s in process.streams.inputs + process.streams.outputs})
    extras = [n for n in pdb.entries if n not in used]

    st.markdown("### Components in this process")
    rows = []
    for n in used:
        c = db.components.get(n)
        e = pdb.entries.get(n)
        rows.append({
            "Component": n,
            "$/kg":      (c.price_low if c else 0.0) or 0.0,
            "Tier":      (e.tier if e else "estimate"),
            "Source":    (c.price_ref if c else "") or (e.source if e else ""),
            "Role":      (c.role if c else "neutral"),
        })
    df = pd.DataFrame(rows)
    edited = st.data_editor(
        df, key="price_editor_used",
        num_rows="fixed", use_container_width=True,
        column_config={
            "$/kg":   st.column_config.NumberColumn(format="%.4f", min_value=0.0),
            "Tier":   st.column_config.SelectboxColumn(options=["paper", "market", "estimate"]),
            "Role":   st.column_config.SelectboxColumn(
                          options=["input", "output", "utility", "catalyst",
                                   "solvent", "electrolyte", "neutral"]),
        },
    )
    # Apply edits to ComponentDB and PriceDB
    for _, row in edited.iterrows():
        n = row["Component"]
        if n in db.components:
            db.components[n].price_low = float(row["$/kg"])
            db.components[n].price_ref = str(row["Source"]) if pd.notna(row["Source"]) else ""
            db.components[n].role = str(row["Role"]) if pd.notna(row["Role"]) else "neutral"
        if n in pdb.entries:
            pdb.entries[n].price_low = float(row["$/kg"])
            pdb.entries[n].source = str(row["Source"]) if pd.notna(row["Source"]) else ""
            pdb.entries[n].tier = str(row["Tier"]) if pd.notna(row["Tier"]) else "market"
            pdb.entries[n].role = str(row["Role"]) if pd.notna(row["Role"]) else "neutral"

    # ---- Auto-refresh from public price feeds ----
    st.markdown("### 🌐 Auto-refresh from public price feeds")
    st.caption(
        "Pulls **World Bank Pink Sheet** (monthly: oil, gas, coal, grains, "
        "fertilizers, urea, DAP, KCl, base metals) and **Trading Economics** "
        "(daily: methanol, polyethylene, polypropylene, PVC, styrene, urea, "
        "ethanol, propane, naphtha, …).  CNY → USD conversion via Frankfurter "
        "(ECB).  No API keys required.  Components flagged `tier: paper` are "
        "left untouched so paper-cited assumptions stay locked in."
    )

    cF1, cF2 = st.columns([2, 3])
    with cF1:
        respect_paper = st.checkbox("Lock paper-tier prices", value=True,
                                    help="If checked, components with tier=paper "
                                    "(authoritative TEA-paper numbers) are not "
                                    "overwritten by market feeds.")
        if st.button("🌐 Refresh prices from web", type="primary"):
            from tea_engine.fetchers import fetch_all, apply_records_to_db
            with st.spinner("Fetching from World Bank + Trading Economics + ECB FX…"):
                records, status = fetch_all()
                log = apply_records_to_db(records, db, pdb,
                                          respect_paper_tier=respect_paper)
            st.session_state.last_fetch_status = status
            st.session_state.last_fetch_log = log
            st.session_state.last_fetch_n = len(records)
            st.rerun()
    with cF2:
        if "last_fetch_status" in st.session_state:
            st.markdown(f"**Last fetch: {st.session_state.last_fetch_n} records**")
            for src, st_msg in st.session_state.last_fetch_status.items():
                icon = "✅" if st_msg.startswith("OK") else "❌"
                st.markdown(f"- {icon} **{src}** — {st_msg}")
            with st.expander("Per-component update log"):
                rows = [{"Component": k, "Outcome": v}
                        for k, v in st.session_state.last_fetch_log.items()]
                st.dataframe(pd.DataFrame(rows), use_container_width=True,
                             hide_index=True, height=240)

    st.divider()

    # Lookup-link buttons
    st.markdown("### 🔍 Manual lookup links")
    st.caption("For specialty chemicals not on the auto feeds (DMSO, PMA, etc.) — "
               "click to open the supplier's page, copy the latest $/kg, paste "
               "into the table above, and **💾 Save**.")
    for n in used:
        urls = pdb.lookup_urls(n)
        if not urls:
            urls = build_default_lookups(n)
        cols = st.columns([2] + [1] * min(len(urls), 4))
        cols[0].markdown(f"**{n}**")
        for i, u in enumerate(urls[:4]):
            host = u.split("/")[2] if "://" in u else u[:24]
            cols[i + 1].link_button(host, u)

    st.divider()
    st.markdown("### Persistence")
    cA, cB = st.columns(2)
    with cA:
        if st.button("💾 Save current prices → prices.yaml"):
            save_prices_to_yaml(db, pdb, DEFAULT_PRICES_YAML)
            st.success(f"Saved {len(pdb.entries)} entries to {DEFAULT_PRICES_YAML}")
    with cB:
        if st.button("🔄 Reload prices.yaml (discard edits)"):
            from tea_engine.prices import load_prices_into
            db._pricedb = load_prices_into(db, DEFAULT_PRICES_YAML)
            st.rerun()

    if extras:
        with st.expander(f"📚 Other components in price DB ({len(extras)} not used by this process)"):
            ex_rows = [{"Component": n,
                        "$/kg": pdb.entries[n].price_low,
                        "Tier": pdb.entries[n].tier,
                        "Source": pdb.entries[n].source}
                       for n in extras]
            st.dataframe(pd.DataFrame(ex_rows), use_container_width=True, hide_index=True)


# Compute TEA for the remaining tabs (only if there is at least one input + output)
if process.streams.inputs and process.streams.outputs:
    try:
        result = run_tea(process, db, inp)
    except Exception as e:
        st.error(f"TEA calculation failed: {e}")
        result = None
else:
    result = None


# =================================================== TEA tables ======
with tab_tea:
    if not result:
        st.warning("Add at least one input and one output stream to compute TEA.")
    else:
        scales = list(inp.scales_ton)
        cols = [f"{s:g} ton ($/y)" for s in scales]

        st.subheader("3. CAPEX summary")
        capex_rows = []
        sec_keys = list(result.capex_section[scales[0]].keys())
        for k in sec_keys:
            capex_rows.append([k] + [result.capex_section[s][k] for s in scales])
        capex_rows.append(["**Total Equipment CAPEX**"] + [result.capex_total[s] for s in scales])
        capex_rows.append(["**Total Annualized CAPEX**"] + [result.capex_annualized[s] for s in scales])
        st.dataframe(pd.DataFrame(capex_rows, columns=["Category"] + cols).style.format(
            {c: "${:,.0f}" for c in cols}), use_container_width=True)

        st.subheader("4. OPEX summary")
        opex_rows = []
        line_keys = [k for k in result.opex[scales[0]] if not k.startswith("__")]
        for k in line_keys:
            opex_rows.append([k] + [result.opex[s][k] for s in scales])
        for tk, lab in (("__Feedstock Total", "**Feedstock Total**"),
                        ("__Utility Total", "**Utility Total**"),
                        ("__Operation Total", "**Operation Total**"),
                        ("__OPEX Total", "**Total OPEX**")):
            opex_rows.append([lab] + [result.opex[s][tk] for s in scales])
        st.dataframe(pd.DataFrame(opex_rows, columns=["Category"] + cols).style.format(
            {c: "${:,.0f}" for c in cols}), use_container_width=True)

        st.subheader("5. Revenue & profitability")
        rev_rows = []
        for s_out in process.streams.outputs:
            rev_rows.append([s_out.component] + [result.revenue[s][s_out.component] for s in scales])
        rev_rows.append(["**Total Revenue**"] + [result.revenue_total[s] for s in scales])
        rev_rows.append(["**Total Annualized Cost**"]
                        + [result.capex_annualized[s] + result.opex_total[s] for s in scales])
        rev_rows.append(["**Net Profit**"] + [result.net_profit[s] for s in scales])
        st.dataframe(pd.DataFrame(rev_rows, columns=["Item"] + cols).style.format(
            {c: "${:,.0f}" for c in cols}), use_container_width=True)

        st.subheader(f"6. MSP ({inp.msp_product})")
        msp_df = pd.DataFrame({
            "Scale": [f"{s:g} ton feed" for s in scales],
            f"MSP ($/kg {inp.msp_product})": [result.msp[s] for s in scales],
        })
        st.dataframe(msp_df.style.format({f"MSP ($/kg {inp.msp_product})": "{:.4f}"}),
                     use_container_width=True)


# =================================================== Plots ============
with tab_plots:
    if not result:
        st.warning("Add at least one input and one output stream to compute TEA.")
    else:
        largest = max(inp.scales_ton)
        scales = list(inp.scales_ton)

        c1, c2 = st.columns(2)
        with c1:
            st.subheader(f"Cost breakdown ({largest:g} ton)")
            bd = {k: v for k, v in result.cost_breakdown.items() if k != "Total"}
            fig = go.Figure(data=[go.Pie(labels=list(bd.keys()), values=list(bd.values()),
                                          hole=0.4, textposition="inside",
                                          textinfo="percent+label")])
            fig.update_layout(height=420, margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.subheader(f"Revenue breakdown ({largest:g} ton)")
            rb = {k: v for k, v in result.revenue_breakdown.items() if k != "Total"}
            fig = go.Figure(data=[go.Pie(labels=list(rb.keys()), values=list(rb.values()),
                                          hole=0.4, textposition="inside",
                                          textinfo="percent+label")])
            fig.update_layout(height=420, margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig, use_container_width=True)

        st.subheader("CAPEX vs OPEX vs Revenue across scales")
        bar = go.Figure()
        bar.add_bar(name="Annualized CAPEX", x=scales, y=[result.capex_annualized[s] for s in scales])
        bar.add_bar(name="Annual OPEX",      x=scales, y=[result.opex_total[s] for s in scales])
        bar.add_bar(name="Annual Revenue",   x=scales, y=[result.revenue_total[s] for s in scales])
        bar.update_layout(barmode="group", xaxis_title="Scale (ton feed/batch)",
                          yaxis_title="$ / y", height=420)
        st.plotly_chart(bar, use_container_width=True)

        st.subheader(f"MSP {inp.msp_product} vs scale")
        msp_fig = go.Figure(data=[go.Scatter(x=scales, y=[result.msp[s] for s in scales],
                                              mode="lines+markers", line=dict(width=3))])
        msp_fig.update_layout(xaxis_title="Scale (ton feed/batch)",
                              yaxis_title=f"MSP ($/kg {inp.msp_product})", height=380)
        st.plotly_chart(msp_fig, use_container_width=True)


# =================================================== Time Profile ====
with tab_time:
    if not result:
        st.warning("Add at least one input and one output stream to compute TEA.")
    else:
        from tea_engine import (material_timeline, cashflow_timeline,
                                stream_events, equipment_events, to_yearly)

        st.subheader("📅 Time-resolved view of flows and cash")
        st.caption("Continuous lines flow every month; one-time charges load at t=0; "
                   "periodic items spike on their replacement schedule.")

        c1, c2, c3 = st.columns([2, 2, 3])
        with c1:
            scale_pick = st.selectbox(
                "Scale",
                list(inp.scales_ton),
                index=len(inp.scales_ton) - 1,
                format_func=lambda v: f"{v:g} ton/batch",
                key="time_scale",
            )
        with c2:
            granularity = st.radio("Granularity", ["Month", "Year"],
                                   horizontal=True, key="time_gran")
        with c3:
            show_inv = st.checkbox(
                "Show inventory line for one-time / periodic streams",
                value=True, key="time_show_inv")

        mt = material_timeline(process, db, scale_pick, inp)
        cf = cashflow_timeline(process, db, scale_pick, inp,
                               result.opex[scale_pick],
                               result.revenue[scale_pick],
                               result.capex_total[scale_pick])
        ev_streams = stream_events(process, db, scale_pick, inp)
        ev_equip = equipment_events(process, scale_pick, inp)

        # Stacked area: monthly $ spent on each input stream, colour-keyed by mode
        st.markdown("##### Material spending over time (inputs)")
        m_in = mt[mt["role"] == "input"].copy()
        if granularity == "Year":
            agg = (m_in.groupby([(m_in["month"] // 12).astype(int).rename("year"),
                                  "component", "flow_mode"])
                       .agg(usd=("usd_in_month", "sum"),
                            kg=("kg_consumed_in_month", "sum"))
                       .reset_index())
            x_col, x_title = "year", "Year"
        else:
            agg = m_in.rename(columns={"usd_in_month": "usd",
                                       "kg_consumed_in_month": "kg"})
            x_col, x_title = "month", "Month"

        fig_mat = go.Figure()
        mode_colour = {"continuous": "#1976D2", "one_time": "#E65100", "periodic": "#6A1B9A"}
        for comp_name in agg["component"].unique():
            sub = agg[agg["component"] == comp_name]
            mode = sub["flow_mode"].iloc[0]
            fig_mat.add_trace(go.Scatter(
                x=sub[x_col], y=sub["usd"],
                stackgroup="usd",
                name=f"{comp_name} ({mode})",
                line=dict(width=0.5, color=mode_colour.get(mode, "#888")),
                fillcolor=mode_colour.get(mode, "#888"),
                opacity=0.6 if mode == "continuous" else 0.85,
                hovertemplate=f"<b>{comp_name}</b> [{mode}]<br>{x_title} %{{x}}<br>$%{{y:,.0f}}<extra></extra>",
            ))
        fig_mat.update_layout(
            xaxis_title=x_title, yaxis_title="$ in period",
            height=380, margin=dict(t=10, b=10, l=10, r=10),
            hovermode="x unified",
        )
        st.plotly_chart(fig_mat, use_container_width=True)

        # Inventory step lines (only for one_time / periodic)
        if show_inv:
            inv = mt[(mt["role"] == "input") & (mt["flow_mode"] != "continuous")]
            if not inv.empty:
                st.markdown("##### On-site inventory (one-time / periodic streams)")
                fig_inv = go.Figure()
                for comp_name in inv["component"].unique():
                    sub = inv[inv["component"] == comp_name].sort_values("month")
                    mode = sub["flow_mode"].iloc[0]
                    fig_inv.add_trace(go.Scatter(
                        x=sub["month"] if granularity == "Month" else sub["month"] / 12,
                        y=sub["kg_inventory_eom"],
                        mode="lines", line=dict(shape="hv", width=2.5,
                                                color=mode_colour.get(mode, "#888")),
                        name=f"{comp_name} ({mode})",
                        hovertemplate=f"<b>{comp_name}</b> [{mode}]<br>%{{x}}<br>%{{y:,.1f}} kg<extra></extra>",
                    ))
                fig_inv.update_layout(
                    xaxis_title=x_title, yaxis_title="Inventory (kg)",
                    height=320, margin=dict(t=10, b=10, l=10, r=10),
                    hovermode="x unified",
                )
                st.plotly_chart(fig_inv, use_container_width=True)
            else:
                st.info("No one-time / periodic streams declared on this process.")

        # Cash flow with replacement event markers
        st.markdown("##### Cash flow and cumulative NPV (undiscounted)")
        if granularity == "Year":
            cf_agg = (cf.assign(year=(cf["month"] // 12).astype(int))
                        .groupby("year", as_index=False)
                        .agg(capex=("capex", "sum"), opex=("opex", "sum"),
                             revenue=("revenue", "sum"),
                             stream_event=("stream_event", "sum"),
                             equipment_event=("equipment_event", "sum"),
                             net=("net", "sum")))
            cf_agg["cumulative"] = cf_agg["net"].cumsum()
            x_cf = cf_agg["year"]
            cf_use = cf_agg
        else:
            x_cf = cf["month"]
            cf_use = cf

        fig_cf = go.Figure()
        fig_cf.add_bar(x=x_cf, y=cf_use["capex"], name="CAPEX (initial)",
                       marker_color="#37474F")
        fig_cf.add_bar(x=x_cf, y=cf_use["opex"], name="OPEX (continuous)",
                       marker_color="#90A4AE")
        fig_cf.add_bar(x=x_cf, y=cf_use["revenue"], name="Revenue",
                       marker_color="#43A047")
        fig_cf.add_bar(x=x_cf, y=cf_use["stream_event"],
                       name="Stream replacement", marker_color="#6A1B9A")
        fig_cf.add_bar(x=x_cf, y=cf_use["equipment_event"],
                       name="Equipment replacement", marker_color="#C62828")
        fig_cf.add_trace(go.Scatter(
            x=x_cf, y=cf_use["cumulative"], name="Cumulative",
            mode="lines", line=dict(color="#1A237E", width=3),
            yaxis="y2",
        ))
        fig_cf.update_layout(
            barmode="relative",
            xaxis_title=x_title,
            yaxis=dict(title="$ in period"),
            yaxis2=dict(title="Cumulative $", overlaying="y", side="right",
                        showgrid=False),
            height=440, margin=dict(t=10, b=10, l=10, r=10),
            hovermode="x unified",
            legend=dict(orientation="h", y=-0.18),
        )
        st.plotly_chart(fig_cf, use_container_width=True)

        # Event tables
        ec1, ec2 = st.columns(2)
        with ec1:
            st.markdown("##### Stream events")
            if ev_streams:
                ev_df = pd.DataFrame([{
                    "Month": e.month, "Year": round(e.month / 12, 2),
                    "Kind": e.kind.replace("_", " "),
                    "Component": e.component,
                    "$": e.amount_usd,
                } for e in sorted(ev_streams, key=lambda e: e.month)])
                st.dataframe(ev_df.style.format({"$": "${:,.0f}"}),
                             hide_index=True, use_container_width=True)
            else:
                st.caption("No one-time / periodic streams declared.")
        with ec2:
            st.markdown("##### Equipment replacement events")
            if ev_equip:
                eq_df = pd.DataFrame([{
                    "Month": e.month, "Year": round(e.month / 12, 2),
                    "Item": e.label.replace("Replace — ", ""),
                    "Section": e.section,
                    "$": e.amount_usd,
                } for e in sorted(ev_equip, key=lambda e: e.month)])
                st.dataframe(eq_df.style.format({"$": "${:,.0f}"}),
                             hide_index=True, use_container_width=True)
            else:
                st.caption("No equipment items have lifetime < plant lifetime.")

        with st.expander("📋 Raw monthly material table (debug)"):
            st.dataframe(mt, hide_index=True, use_container_width=True, height=300)


# =================================================== Sensitivity =====
with tab_sens:
    if not result:
        st.warning("Add at least one input and one output stream to compute TEA.")
    else:
        st.subheader("Single-parameter sensitivity sweeps")
        st.caption("Each row sweeps one parameter and recomputes the MSP at the largest scale.")

        output_names = [s.component for s in process.streams.outputs]
        input_names  = [s.component for s in process.streams.inputs]

        with st.expander("Add a sweep", expanded=True):
            which = st.radio("Sweep type",
                             ["Recovery (input)", "Output price ($/kg)", "Meta scalar"],
                             horizontal=True)
            if which == "Recovery (input)":
                comp = st.selectbox("Input", input_names)
                vals = st.text_input("Values (comma-separated)", "0.99999, 0.9999, 0.999, 0.99")
                param = f"{comp}.recovery"
            elif which == "Output price ($/kg)":
                comp = st.selectbox("Output", output_names)
                vals = st.text_input("Values (comma-separated)", "8, 6, 4, 2")
                param = f"{comp}.price"
            else:
                keys = list(process.meta.keys()) or [""]
                comp = st.selectbox("meta key", keys)
                vals = st.text_input("Values (comma-separated)", "1.0, 0.5, 0.1")
                param = f"meta.{comp}"

            if st.button("Run sweep"):
                try:
                    values = [float(v.strip()) for v in vals.split(",") if v.strip()]
                    data = sensitivity_one_param(process, db, inp, param, values)
                    df = pd.DataFrame(data, columns=[param, f"MSP ($/kg {inp.msp_product})"])
                    st.dataframe(df.style.format({df.columns[0]: "{:.6f}",
                                                  df.columns[1]: "{:.4f}"}),
                                 use_container_width=True)
                    fig = go.Figure(data=[go.Scatter(x=df[df.columns[0]], y=df[df.columns[1]],
                                                      mode="lines+markers", line=dict(width=3))])
                    fig.update_layout(xaxis_title=param,
                                      yaxis_title=f"MSP ($/kg {inp.msp_product})", height=380)
                    st.plotly_chart(fig, use_container_width=True)
                    st.session_state.last_sens = {param: data}
                except Exception as e:
                    st.error(f"Sweep failed: {e}")


# =================================================== Scale-up =========
with tab_scaleup:
    st.markdown("#### 📈 Scale-up scenario analysis")
    st.caption("Re-runs the TEA at five canonical stages (Lab → Bench → "
               "Pilot → Demo → Commercial) and adds reaction-class-aware "
               "risk and EHS commentary.")

    rt_options = ["thermal", "catalytic", "electrochemical",
                  "photochemical", "biological", "hybrid", "unspecified"]

    if proc_key.startswith("exp::") and "current_experiment" in st.session_state:
        eo = st.session_state.current_experiment
        default_rt = eo.reaction_type
        default_haz = ", ".join(eo.constraints.get("hazardous_materials") or [])
        default_ds = bool(eo.downstream)
    else:
        default_rt = "unspecified"
        default_haz = ""
        default_ds = any(
            "distill" in s.label.lower() or "extract" in s.label.lower()
            or "cryst" in s.label.lower() or "membrane" in s.label.lower()
            for s in process.sections
        )

    sc_c1, sc_c2, sc_c3 = st.columns([2, 3, 2])
    with sc_c1:
        rt_idx = rt_options.index(default_rt) if default_rt in rt_options else 6
        rt_pick = st.selectbox("Reaction type (for risk catalog)",
                               rt_options, index=rt_idx)
    with sc_c2:
        haz_pick = st.text_input("Hazardous materials (comma-sep)",
                                 default_haz)
    with sc_c3:
        has_ds = st.checkbox("Include downstream risks", value=default_ds)

    sc_c4, sc_c5 = st.columns(2)
    with sc_c4:
        msp_threshold = st.number_input(
            "Target MSP ($/kg) for recommendation block (0 = skip)",
            min_value=0.0, value=0.0, step=0.50,
        )
    with sc_c5:
        st.markdown("&nbsp;")
        if st.button("📈 Run scale-up scenarios", type="primary",
                     use_container_width=True):
            try:
                rep = build_scaleup_report(
                    process, db, inp,
                    reaction_type=rt_pick,
                    hazardous_materials=[h.strip() for h in haz_pick.split(",") if h.strip()],
                    has_downstream=has_ds,
                    recommendation_msp_threshold=msp_threshold if msp_threshold > 0 else None,
                )
                st.session_state.scaleup_report = rep
            except Exception as exc:  # noqa: BLE001
                st.error(f"Scale-up failed: {exc}")
                st.session_state.pop("scaleup_report", None)

    rep = st.session_state.get("scaleup_report")
    if rep:
        st.markdown("##### Stage-by-stage TEA")
        df = pd.DataFrame([
            {
                "Stage": s.stage.name,
                "ton/batch": s.stage.ton_per_batch,
                "CAPEX ($M)": s.capex_total_usd / 1e6,
                "Annualized CAPEX ($M/y)": s.capex_annualized_usd / 1e6,
                "OPEX ($M/y)": s.opex_total_usd / 1e6,
                "Revenue ($M/y)": s.revenue_total_usd / 1e6,
                "Net profit ($M/y)": s.net_profit_usd / 1e6,
                f"MSP ($/kg)": s.msp_usd_per_kg,
                "Annual product (t)": s.annual_product_kg / 1000,
                "Batches/y": s.batches_per_year,
                "FTE": s.fte_operators,
            }
            for s in rep.stages
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Visualise MSP vs scale + cost stack
        plot_c1, plot_c2 = st.columns(2)
        with plot_c1:
            fig_msp = go.Figure()
            fig_msp.add_trace(go.Scatter(
                x=[s.stage.ton_per_batch for s in rep.stages],
                y=[s.msp_usd_per_kg for s in rep.stages],
                mode="lines+markers+text",
                text=[s.stage.name for s in rep.stages],
                textposition="top center",
                line=dict(color="#1565C0", width=3),
                marker=dict(size=11, color="#1565C0"),
                name="MSP",
            ))
            if msp_threshold > 0:
                fig_msp.add_hline(y=msp_threshold, line_dash="dash",
                                  line_color="#C62828",
                                  annotation_text=f"Target ${msp_threshold:.2f}/kg",
                                  annotation_position="top right")
            fig_msp.update_layout(
                title="MSP vs scale", xaxis_type="log",
                xaxis_title="ton/batch (log)", yaxis_title="MSP ($/kg)",
                height=380, margin=dict(t=40, b=20),
            )
            st.plotly_chart(fig_msp, use_container_width=True)
        with plot_c2:
            fig_cost = go.Figure()
            stage_names = [s.stage.name for s in rep.stages]
            fig_cost.add_bar(name="Annualized CAPEX", x=stage_names,
                             y=[s.capex_annualized_usd / 1e6 for s in rep.stages],
                             marker_color="#37474F")
            fig_cost.add_bar(name="OPEX", x=stage_names,
                             y=[s.opex_total_usd / 1e6 for s in rep.stages],
                             marker_color="#90A4AE")
            fig_cost.add_bar(name="Revenue", x=stage_names,
                             y=[s.revenue_total_usd / 1e6 for s in rep.stages],
                             marker_color="#43A047")
            fig_cost.update_layout(
                title="Annual cost vs revenue", yaxis_title="$M/y",
                barmode="group", height=380, margin=dict(t=40, b=20),
            )
            st.plotly_chart(fig_cost, use_container_width=True)

        if rep.general_risks:
            with st.expander("Generic scale-up risks (reaction class)", expanded=True):
                for r in rep.general_risks:
                    st.markdown(f"- {r}")
        if rep.downstream_risks:
            with st.expander("Downstream scale-up risks"):
                for r in rep.downstream_risks:
                    st.markdown(f"- {r}")
        if rep.safety_risks:
            with st.expander("EHS / safety scale-up notes"):
                for r in rep.safety_risks:
                    st.markdown(f"- {r}")

        if rep.recommendation:
            st.markdown(f"##### Recommendation\n{rep.recommendation}")

        with st.expander("📄 Copy full markdown report"):
            st.code(rep.to_markdown(), language="markdown")
    else:
        st.info("Click **📈 Run scale-up scenarios** to generate the ladder.")


# =================================================== Export ===========
with tab_export:
    if not result:
        st.warning("Add at least one input and one output stream to compute TEA.")
    else:
        st.subheader("Export to xlsx")
        st.caption("Mirrors the layout of the reference paper TEA Summary so it can "
                   "be diffed cleanly.")
        fname = st.text_input(
            "Filename",
            f"TEA_{process.name.replace(' ', '_').replace('/', '-')}_{datetime.now():%Y%m%d}.xlsx"
        )
        include_sens = st.checkbox("Include last sensitivity sweep",
                                   value=("last_sens" in st.session_state))
        if st.button("Generate xlsx", type="primary"):
            out_dir = os.path.join(HERE, "output")
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, fname)
            sens_specs = None
            if include_sens and "last_sens" in st.session_state:
                sens_specs = {k: {"param": k, "values": [v for v, _ in vals]}
                              for k, vals in st.session_state.last_sens.items()}
            export_tea_xlsx(out_path, process, db, inp, result, sensitivity_specs=sens_specs)
            st.success(f"Saved: {out_path}")
            with open(out_path, "rb") as fh:
                st.download_button("Download xlsx", data=fh.read(), file_name=fname,
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
