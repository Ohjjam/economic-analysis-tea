"""TEA (Techno-Economic Analysis) engine.

Modules:
    components  - chemical component database
    streams     - material/utility stream containers
    equipment   - equipment list with installed-cost scaling (CEPCI + 6/10 rule)
    process     - process model: feed -> equipment -> products
    tea         - CAPEX / OPEX / Revenue / MSP / sensitivity
    excel_export - xlsx writer matching the reference TEA Summary layout
    pfd         - process flow diagram (graphviz)
"""
from .components import Component, ComponentDB, PriceSource
from .streams import Stream, StreamSet
from .equipment import Equipment, EquipmentList, CEPCI, CapexSource
from .process import Process, ProcessSection
from .tea import TEAInputs, TEAResult, run_tea
from .excel_export import export_tea_xlsx
from .pfd import build_pfd_dot
from .timeline import (
    TimelineEvent,
    material_timeline,
    cashflow_timeline,
    stream_events,
    equipment_events,
    to_yearly,
)
from .experiment import (
    Experiment,
    ExperimentMeta,
    FeedstockPrimary,
    FeedstockReagent,
    ResultYield,
    DownstreamStep,
    Reference,
    Assumption,
    load_experiment,
    save_experiment,
    list_experiments,
    summarize,
)
from .schema_validate import validate_experiment, ValidationReport
from .scenarios import compute_scenarios, render_scenarios_html
from .scaleup import (
    ScaleStage,
    ScaleupReport,
    build_scaleup_report,
    DEFAULT_STAGES,
)
from .auto_builder import (
    build_process_from_experiment,
    render_design_note,
)
from .viewer import (
    render_html_viewer,
    render_comparison_html,
    auto_pfd_mermaid,
    pfd_mermaid_from_spec,
)

__all__ = [
    "Component", "ComponentDB", "PriceSource",
    "Stream", "StreamSet",
    "Equipment", "EquipmentList", "CEPCI", "CapexSource",
    "Process", "ProcessSection",
    "TEAInputs", "TEAResult", "run_tea",
    "export_tea_xlsx",
    "build_pfd_dot",
    "TimelineEvent", "material_timeline", "cashflow_timeline",
    "stream_events", "equipment_events", "to_yearly",
    "Experiment", "ExperimentMeta", "FeedstockPrimary", "FeedstockReagent",
    "ResultYield", "DownstreamStep", "Reference", "Assumption",
    "load_experiment", "save_experiment", "list_experiments", "summarize",
    "validate_experiment", "ValidationReport",
    "compute_scenarios", "render_scenarios_html",
    "ScaleStage", "ScaleupReport", "build_scaleup_report", "DEFAULT_STAGES",
    "build_process_from_experiment", "render_design_note",
    "render_html_viewer", "render_comparison_html", "auto_pfd_mermaid",
    "pfd_mermaid_from_spec",
]
