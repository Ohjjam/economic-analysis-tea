"""Scale-up scenario engine.

Generates a stage-by-stage scale-up report (lab → bench → pilot → demo →
commercial) for a given `Process` + `TEAInputs`, with:

- Per-stage TEA snapshot (CAPEX, OPEX, revenue, MSP)
- Throughput, batches/year, operator FTE estimates
- Equipment-list deltas (which units need duplication / extra storage / safety)
- A list of qualitative scale-up risks tied to each stage and reaction class
- Markdown-rendered narrative the Streamlit UI and the design notes can embed

This is deliberately rule-based — no LLM call — but the Process designer
(processes/from_experiment_*.py) is free to inject custom risks via
`Process.meta["scaleup_notes"]` to override per-stage commentary.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .components import ComponentDB
from .process import Process
from .tea import TEAInputs, TEAResult, run_tea


# ---------------------------------------------------------------- Stages
@dataclass(frozen=True)
class ScaleStage:
    name: str
    short: str                  # 3-char code
    ton_per_batch: float        # tonnes of primary feed per batch
    description: str
    expected_capex_usd: Optional[Tuple[float, float]] = None  # informational range


# Default 5-stage ladder. Builders can override via build_scaleup_report.
DEFAULT_STAGES: Tuple[ScaleStage, ...] = (
    ScaleStage(
        name="Lab",
        short="LAB",
        ton_per_batch=0.001,
        description="Bench-top glassware / single electrochemical cell. Manual sampling.",
        expected_capex_usd=(5_000, 50_000),
    ),
    ScaleStage(
        name="Bench",
        short="BEN",
        ton_per_batch=0.01,
        description="Small reactor (1-5 L), instrumented for T / I / pH logging. Manual feed.",
        expected_capex_usd=(50_000, 250_000),
    ),
    ScaleStage(
        name="Pilot",
        short="PIL",
        ton_per_batch=0.1,
        description="Pilot reactor (50-100 L) + first separation skid. Continuous data logging, partial automation.",
        expected_capex_usd=(500_000, 3_000_000),
    ),
    ScaleStage(
        name="Demo",
        short="DEM",
        ton_per_batch=1.0,
        description="Demonstration plant (~1-5 ton/batch). Full PFD with utilities, control DCS, ATEX zoning if applicable.",
        expected_capex_usd=(3_000_000, 25_000_000),
    ),
    ScaleStage(
        name="Commercial",
        short="COM",
        ton_per_batch=10.0,
        description="Full commercial plant. Multi-train if feed > single-unit capacity. Includes EHS, off-site logistics.",
        expected_capex_usd=(25_000_000, 250_000_000),
    ),
)


# Generic scale-up risk catalog keyed by reaction class.
_BASE_RISKS: Dict[str, List[str]] = {
    "electrochemical": [
        "Electrode area scales linearly with current — capex of the cell stack dominates and does NOT follow the 6/10 rule.",
        "Gas management: H2/O2 evolution rates scale linearly; explosion-proof venting and gas-liquid disengagement become mandatory above pilot.",
        "Membrane lifetime (Nafion/PEM): expect 5-7 y replacement; build into OPEX as a periodic stream.",
        "Current distribution uniformity is hard above ~1 m² electrode — split into multiple cells in series rather than one giant cell.",
        "Electrolyte purification / makeup gets expensive at commercial scale; consider in-loop ion-exchange.",
    ],
    "catalytic": [
        "Catalyst attrition increases with reactor size; account for higher annual makeup at demo/commercial scale.",
        "Heat removal in exothermic reactions scales with volume but heat transfer scales with surface area — multi-tube or recirculation reactor may be needed at >1 ton/batch.",
        "Diffusion limitations may appear when scaling beyond bench (smaller catalyst pellets vs pressure drop trade-off).",
    ],
    "thermal": [
        "Heat-transfer area / reactor volume ratio drops with scale; jacket heating fails above ~100 L — switch to coil or external HX.",
        "Microwave or RF heating does not scale linearly — alternative heating (steam, electric resistance, induction) usually needed above pilot.",
        "Energy integration (preheat trains) is mandatory at commercial scale to keep OPEX competitive.",
    ],
    "photochemical": [
        "Photon path-length problem: irradiance falls off with depth → thin-film or flow-cell geometry required at scale.",
        "LED capex scales linearly; treat the lighting array as a non-6/10 line item.",
        "Cooling required because most lamps dump >70% of input as heat.",
    ],
    "biological": [
        "Sterility costs grow non-linearly above 1 m³ — CIP/SIP system + biosafety design adds 15-25% to CAPEX.",
        "Oxygen mass transfer (kLa) drops with reactor diameter — sparger / impeller redesign needed.",
        "Downstream (cell separation, product recovery) often dominates commercial OPEX; pilot data on these unit ops is essential.",
    ],
    "hybrid": [
        "Multi-step processes accumulate yield losses — each unit operation's recovery becomes capex-OPEX critical.",
        "Buffer tanks between stages required for decoupling, adding capex.",
    ],
    "unspecified": [
        "Reaction class unspecified — fill chemistry.reaction_type for class-specific scale-up risks.",
    ],
}


_DOWNSTREAM_RISKS: List[str] = [
    "Distillation: reflux ratio + tray count must be set from VLE data, not lab approximation; capex follows ~0.65 scaling.",
    "Extraction: solvent recovery loop is essential — virgin solvent OPEX kills the economics if recovery < 95%.",
    "Crystallisation: scale-up to >1 ton requires a defined cooling profile (PAT/seeding) to avoid agglomeration.",
    "Membrane separation: flux declines with feed concentration; fouling cleaning cycle = OPEX line.",
]


_SAFETY_RISKS_BY_HAZARD: Dict[str, str] = {
    "chloroform":   "Chloroform is a suspected carcinogen — closed handling, vapor recovery, and exposure monitoring required at >100 L.",
    "methanol":     "Methanol is flammable + toxic; ATEX zoning + inerting at commercial scale.",
    "h2so4":        "Sulfuric acid: pH < 1 streams need Hastelloy/PTFE wetted parts; spill containment per OSHA HCS.",
    "naoh":         "Caustic: thermal hazard on dilution; CRZ on transfer lines.",
    "koh":          "Caustic potash: high pH, hygroscopic; SS316 or HDPE wetted parts; thermal hazard on dilution.",
    "hydrogen":     "H2 is highly flammable, LEL 4 vol-%; ventilation + leak monitoring + ATEX.",
    "h2":           "H2 is highly flammable, LEL 4 vol-%; ventilation + leak monitoring + ATEX.",
    "ammonia":      "NH3 is toxic + flammable; scrubber on vents + leak detection.",
    "co":           "CO is toxic (TLV 25 ppm) and flammable; CO monitors + double-block-and-bleed; never use as an indoor-vented anode feed.",
    "h2o2":         "H2O2 above 8 wt% is an oxidizer; passivated SS or aluminium vessels, ATEX-rated venting, and bunded storage required.",
    "ldg":          "Lignin depolymerization gas contains CO + light hydrocarbons; treat as a CO/LFG hazard (toxic + flammable).",
    "co2":          "CO2 above 5 vol-% causes asphyxiation; ventilated rooms + CO2 monitors; CO2 storage tanks rated for thermal expansion.",
    "ethylene":     "C2H4 is highly flammable, LEL 2.7 vol-%; ATEX classification mandatory at commercial scale.",
    "c2h4":         "C2H4 is highly flammable, LEL 2.7 vol-%; ATEX classification mandatory at commercial scale.",
    "hcooh":        "Formic acid: corrosive, can off-gas CO if heated; PFA-lined piping above 60 °C.",
    "hydroxylamine":"Hydroxylamine: shock-sensitive at >50 wt%; thermal-runaway hazard; keep dilute in process.",
    "nh2oh":        "Hydroxylamine: shock-sensitive at >50 wt%; thermal-runaway hazard; keep dilute in process.",
}


# ---------------------------------------------------------------- Results
@dataclass
class ScaleStageResult:
    stage: ScaleStage
    capex_total_usd: float
    capex_annualized_usd: float
    opex_total_usd: float
    revenue_total_usd: float
    net_profit_usd: float
    msp_usd_per_kg: float
    annual_product_kg: float
    batches_per_year: float
    fte_operators: float
    notes: List[str] = field(default_factory=list)


@dataclass
class ScaleupReport:
    process_name: str
    stages: List[ScaleStageResult] = field(default_factory=list)
    general_risks: List[str] = field(default_factory=list)
    safety_risks: List[str] = field(default_factory=list)
    downstream_risks: List[str] = field(default_factory=list)
    summary_table_markdown: str = ""
    recommendation: str = ""
    reported_msp_usd_per_kg: Optional[float] = None
    reported_source: str = ""

    def to_markdown(self) -> str:
        lines = [f"# Scale-up report — {self.process_name}", ""]
        if self.reported_msp_usd_per_kg is not None:
            lines.append(
                f"> 📖 **Paper-reported MSP:** ${self.reported_msp_usd_per_kg:.2f}/kg "
                f"(source: {self.reported_source or 'see YAML'})\n"
            )
        lines.append("## Stage-by-stage TEA")
        lines.append("")
        lines.append(self.summary_table_markdown)
        lines.append("")
        if self.general_risks:
            lines.append("## Generic scale-up risks (reaction class)")
            for r in self.general_risks:
                lines.append(f"- {r}")
            lines.append("")
        if self.downstream_risks:
            lines.append("## Downstream scale-up risks")
            for r in self.downstream_risks:
                lines.append(f"- {r}")
            lines.append("")
        if self.safety_risks:
            lines.append("## EHS / safety scale-up notes")
            for r in self.safety_risks:
                lines.append(f"- {r}")
            lines.append("")
        if self.recommendation:
            lines.append("## Recommendation")
            lines.append(self.recommendation)
        return "\n".join(lines)


# ---------------------------------------------------------------- Builder
def _fte_estimate(ton_per_batch: float) -> float:
    """Very crude FTE-operator estimate per ton/batch scale."""
    if ton_per_batch < 0.005:
        return 0.5
    if ton_per_batch < 0.05:
        return 1.0
    if ton_per_batch < 0.5:
        return 3.0
    if ton_per_batch < 5.0:
        return 8.0
    return 15.0


def build_scaleup_report(
    process: Process,
    db: ComponentDB,
    base_inputs: TEAInputs,
    *,
    stages: Tuple[ScaleStage, ...] = DEFAULT_STAGES,
    reaction_type: str = "unspecified",
    hazardous_materials: Optional[List[str]] = None,
    has_downstream: bool = False,
    recommendation_msp_threshold: Optional[float] = None,
    reported_msp_usd_per_kg: Optional[float] = None,
    reported_source: str = "",
) -> ScaleupReport:
    """Compute the per-stage TEA and assemble the narrative.

    Parameters
    ----------
    process, db, base_inputs : same as `run_tea`.
    stages : ladder of ScaleStages to evaluate.
    reaction_type : one of the keys in _BASE_RISKS — drives generic risks.
    hazardous_materials : list of lower-cased hazard keys (e.g. ["chloroform"]).
    has_downstream : enables downstream risk section.
    recommendation_msp_threshold : if given, the recommendation block flags
        the first stage where MSP falls below this $/kg cut-off (i.e. the
        stage that becomes economically viable).
    """
    report = ScaleupReport(
        process_name=process.name,
        reported_msp_usd_per_kg=reported_msp_usd_per_kg,
        reported_source=reported_source,
    )

    # Per-stage TEA — re-run with each stage's ton as the sole scale.
    for stage in stages:
        inp = TEAInputs(
            discount_rate=base_inputs.discount_rate,
            lifetime_years=base_inputs.lifetime_years,
            capacity_factor=base_inputs.capacity_factor,
            cepci_target_year=base_inputs.cepci_target_year,
            osbl_fraction=base_inputs.osbl_fraction,
            maintenance_fraction=base_inputs.maintenance_fraction,
            operation_fraction=base_inputs.operation_fraction,
            batch_hours=base_inputs.batch_hours,
            msp_product=base_inputs.msp_product,
            scales_ton=(stage.ton_per_batch,),
        )
        try:
            r = run_tea(process, db, inp)
        except Exception as exc:                            # noqa: BLE001
            report.stages.append(ScaleStageResult(
                stage=stage,
                capex_total_usd=float("nan"),
                capex_annualized_usd=float("nan"),
                opex_total_usd=float("nan"),
                revenue_total_usd=float("nan"),
                net_profit_usd=float("nan"),
                msp_usd_per_kg=float("nan"),
                annual_product_kg=0.0,
                batches_per_year=inp.batches_per_year,
                fte_operators=_fte_estimate(stage.ton_per_batch),
                notes=[f"TEA failed: {exc}"],
            ))
            continue

        ton = stage.ton_per_batch
        product_kg = r.flows_annual_kg[ton].get(inp.msp_product, 0.0)
        report.stages.append(ScaleStageResult(
            stage=stage,
            capex_total_usd=r.capex_total[ton],
            capex_annualized_usd=r.capex_annualized[ton],
            opex_total_usd=r.opex_total[ton],
            revenue_total_usd=r.revenue_total[ton],
            net_profit_usd=r.net_profit[ton],
            msp_usd_per_kg=r.msp[ton],
            annual_product_kg=product_kg,
            batches_per_year=inp.batches_per_year,
            fte_operators=_fte_estimate(ton),
        ))

    # Risk catalogs
    report.general_risks = list(_BASE_RISKS.get(reaction_type, _BASE_RISKS["unspecified"]))

    if has_downstream:
        report.downstream_risks = list(_DOWNSTREAM_RISKS)

    safety: List[str] = []
    for h in (hazardous_materials or []):
        key = h.lower().strip()
        if key in _SAFETY_RISKS_BY_HAZARD:
            safety.append(_SAFETY_RISKS_BY_HAZARD[key])
        else:
            safety.append(
                f"User-flagged hazardous material '{h}' — confirm storage class, "
                f"containment and ventilation per local regulation."
            )
    report.safety_risks = safety

    # Markdown summary table
    header = ("| Stage | ton/batch | CAPEX ($M) | Annualized CAPEX ($M/y) "
              "| OPEX ($M/y) | Revenue ($M/y) | Net profit ($M/y) | MSP ($/kg) "
              "| Annual product (t) | Batches/y | FTE |")
    sep = ("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    rows = [header, sep]
    for s in report.stages:
        rows.append(
            f"| {s.stage.name} | {s.stage.ton_per_batch:g} "
            f"| {s.capex_total_usd/1e6:.2f} "
            f"| {s.capex_annualized_usd/1e6:.2f} "
            f"| {s.opex_total_usd/1e6:.2f} "
            f"| {s.revenue_total_usd/1e6:.2f} "
            f"| {s.net_profit_usd/1e6:.2f} "
            f"| {s.msp_usd_per_kg:.2f} "
            f"| {s.annual_product_kg/1000:.2f} "
            f"| {s.batches_per_year:.0f} "
            f"| {s.fte_operators:g} |"
        )
    report.summary_table_markdown = "\n".join(rows)

    # Recommendation block
    if recommendation_msp_threshold is not None:
        viable = [s for s in report.stages if s.msp_usd_per_kg <= recommendation_msp_threshold]
        if viable:
            v = viable[0]
            report.recommendation = (
                f"At an MSP target of **${recommendation_msp_threshold:.2f}/kg**, the process "
                f"first becomes viable at the **{v.stage.name}** stage "
                f"({v.stage.ton_per_batch:g} ton/batch, MSP = ${v.msp_usd_per_kg:.2f}/kg). "
                f"Earlier stages are validation-only; CAPEX commitment should be staged "
                f"with go/no-go gates after each."
            )
        else:
            best = min(report.stages, key=lambda x: x.msp_usd_per_kg)
            report.recommendation = (
                f"No stage in the ladder hits the MSP target of ${recommendation_msp_threshold:.2f}/kg. "
                f"Best-achieved MSP is ${best.msp_usd_per_kg:.2f}/kg at the {best.stage.name} stage. "
                f"Recommend (a) raising yield/selectivity, (b) cheaper feedstock, or "
                f"(c) co-product credit before committing to scale-up."
            )
    else:
        # Pick the largest profitable stage.
        profitable = [s for s in report.stages if s.net_profit_usd > 0]
        if profitable:
            v = profitable[-1]
            report.recommendation = (
                f"Largest profitable stage: **{v.stage.name}** "
                f"({v.stage.ton_per_batch:g} ton/batch), net profit "
                f"${v.net_profit_usd/1e6:.2f} M/y, MSP ${v.msp_usd_per_kg:.2f}/kg. "
                f"Scale up with stage gates at each ladder rung."
            )
        else:
            report.recommendation = (
                "No stage is currently profitable. Tighten upstream yield, "
                "cheapen feed, or add a co-product revenue line before scale-up commitment."
            )

    return report
