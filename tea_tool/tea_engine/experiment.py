"""Experiment-data loader.

Reads YAMLs that conform to `experiments/SCHEMA.md`. The data classes here
are deliberately permissive (every block is optional except the few minimum
fields) so Claude Code can still produce a first-cut design even when the
user only filled the essentials.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


# ---------------------------------------------------------------- Dataclasses
@dataclass
class FeedstockReagent:
    name: str
    mass_per_batch_g: float
    recovery_fraction: float = 0.0
    role: str = "input"
    price_usd_per_kg: Optional[float] = None


@dataclass
class FeedstockPrimary:
    name: str
    mass_per_batch_g: float
    purity_pct: Optional[float] = None
    price_usd_per_kg: Optional[float] = None
    source_note: str = ""


@dataclass
class ResultYield:
    product: str
    yield_pct: float
    selectivity_pct: Optional[float] = None


@dataclass
class DownstreamStep:
    step: str
    method: str
    solvent: Optional[str] = None
    solvent_loading_kg_per_kg_feed: float = 0.0
    recovery_pct: float = 100.0
    target_purity_pct: Optional[float] = None


@dataclass
class Reference:
    """A first-class citation (schema v2). Other fields cite it by `id`."""
    id: str
    citation: str
    type: str = "literature"   # literature | market | vendor | assumption | internal
    url: Optional[str] = None
    doi: Optional[str] = None
    note: str = ""

    def label(self) -> str:
        bits = [self.citation]
        if self.doi:
            bits.append(f"doi:{self.doi}")
        elif self.url:
            bits.append(self.url)
        return "  ".join(bits)


@dataclass
class Assumption:
    """A standalone modeling assumption with its source (schema v2)."""
    key: str
    value: Any
    ref: Optional[str] = None        # references[].id
    unit: str = ""
    note: str = ""


@dataclass
class ExperimentMeta:
    name: str
    slug: str
    date: Optional[str] = None
    researcher: str = ""
    lab: str = ""
    notes: str = ""


@dataclass
class Experiment:
    meta: ExperimentMeta
    chemistry: Dict[str, Any] = field(default_factory=dict)
    feedstock_primary: Optional[FeedstockPrimary] = None
    feedstock_reagents: List[FeedstockReagent] = field(default_factory=list)
    operating_conditions: Dict[str, Any] = field(default_factory=dict)
    results_yields: List[ResultYield] = field(default_factory=list)
    results_extra: Dict[str, Any] = field(default_factory=dict)
    downstream: List[DownstreamStep] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    scale_targets: Dict[str, Any] = field(default_factory=dict)
    # Optional `reported:` block — paper's own TEA numbers for sanity-check.
    reported: Dict[str, Any] = field(default_factory=dict)
    # ---- schema v2 additions (backward compatible; empty for v1 files) ----
    schema_version: int = 1
    references: List[Reference] = field(default_factory=list)
    assumptions: List[Assumption] = field(default_factory=list)
    pfd: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    # ---- scenario config (schema v2, optional) ----------------------------
    @property
    def scenarios(self) -> Dict[str, Any]:
        return self.raw.get("scenarios") or {}

    # ---- reference helpers (schema v2) ------------------------------------
    def reference_ids(self) -> List[str]:
        return [r.id for r in self.references]

    def find_reference(self, ref_id: str) -> Optional[Reference]:
        for r in self.references:
            if r.id == ref_id:
                return r
        return None

    @property
    def reported_msp(self) -> Optional[float]:
        v = self.reported.get("msp_usd_per_kg")
        return float(v) if v is not None else None

    @property
    def reported_source(self) -> str:
        return str(self.reported.get("source") or "")

    # ---- convenience accessors --------------------------------------------
    @property
    def target_products(self) -> List[str]:
        return list(self.chemistry.get("target_products") or [])

    @property
    def reaction_type(self) -> str:
        return str(self.chemistry.get("reaction_type") or "unspecified")

    @property
    def electrochem_stoichiometry(self) -> Dict[str, Dict[str, float]]:
        """User-supplied per-product electron/MW for Faraday-law sizing.

        Schema: ``chemistry.electrochem_stoichiometry: {product: {z, MW_g_mol}}``
        ``z`` = electrons transferred per molecule of product.
        ``MW_g_mol`` = molar mass (g/mol).

        Empty dict means the builder falls back to its internal lookup +
        rough default (2e⁻, MW ≈ 30 g/mol).
        """
        block = self.chemistry.get("electrochem_stoichiometry") or {}
        out: Dict[str, Dict[str, float]] = {}
        for k, v in block.items():
            if isinstance(v, dict) and "z" in v and "MW_g_mol" in v:
                out[str(k).lower()] = {
                    "z": float(v["z"]),
                    "MW_g_mol": float(v["MW_g_mol"]),
                }
        return out

    @property
    def stages(self) -> List[Dict[str, Any]]:
        """Return chemistry.stages if defined, else synthesize a single
        stage from `reaction_type` + `operating_conditions`."""
        s = self.chemistry.get("stages")
        if s:
            return list(s)
        # Fallback: single stage built from the legacy fields
        op = self.operating_conditions or {}
        return [{
            "name": "Reaction",
            "type": self.reaction_type,
            "T_C": op.get("temperature_C"),
            "P_bar": op.get("pressure_bar"),
            "residence_h": op.get("reaction_time_h"),
            "V": (op.get("electrochem") or {}).get("cell_voltage_V"),
            "j_mA_cm2": (op.get("electrochem") or {}).get("current_density_mA_cm2"),
            "FE_pct": (op.get("electrochem") or {}).get("faradaic_efficiency_pct"),
            "heating_method": (op.get("thermal") or {}).get("heating_method"),
        }]

    @property
    def preferred_msp_product(self) -> str:
        prod = self.constraints.get("preferred_msp_product")
        if prod:
            return str(prod)
        # default: first listed target
        return self.target_products[0] if self.target_products else ""

    @property
    def scales_ton(self) -> List[float]:
        s = self.scale_targets.get("scales_ton_per_batch") or [1.0, 5.0, 10.0]
        return [float(x) for x in s]

    @property
    def batch_hours(self) -> float:
        return float(self.scale_targets.get("batch_hours", 2.0))

    @property
    def capacity_factor(self) -> float:
        return float(self.scale_targets.get("capacity_factor", 0.8))

    @property
    def discount_rate(self) -> float:
        return float(self.constraints.get("discount_rate", 0.10))

    @property
    def plant_lifetime_years(self) -> int:
        return int(self.constraints.get("plant_lifetime_years", 20))


# ---------------------------------------------------------------- Loader / writer
def load_experiment(path: str | Path) -> Experiment:
    """Parse a YAML at `path` into an Experiment object."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    meta_raw = raw.get("meta", {}) or {}
    if not meta_raw.get("name") or not meta_raw.get("slug"):
        raise ValueError(
            f"{p}: meta.name and meta.slug are required."
        )
    meta = ExperimentMeta(
        name=str(meta_raw["name"]),
        slug=str(meta_raw["slug"]),
        date=str(meta_raw.get("date") or "") or None,
        researcher=str(meta_raw.get("researcher") or ""),
        lab=str(meta_raw.get("lab") or ""),
        notes=str(meta_raw.get("notes") or ""),
    )

    chem = raw.get("chemistry") or {}

    feed_block = raw.get("feedstock") or {}
    fp_raw = feed_block.get("primary") or {}
    fp = None
    if fp_raw:
        fp = FeedstockPrimary(
            name=str(fp_raw.get("name", "Feedstock")),
            mass_per_batch_g=float(fp_raw.get("mass_per_batch_g", 1.0)),
            purity_pct=fp_raw.get("purity_pct"),
            price_usd_per_kg=fp_raw.get("price_usd_per_kg"),
            source_note=str(fp_raw.get("source_note") or ""),
        )
    reagents_raw = feed_block.get("reagents") or []
    reagents = [
        FeedstockReagent(
            name=str(r.get("name", "")),
            mass_per_batch_g=float(r.get("mass_per_batch_g", 0.0)),
            recovery_fraction=float(r.get("recovery_fraction", 0.0)),
            role=str(r.get("role", "input")),
            price_usd_per_kg=r.get("price_usd_per_kg"),
        )
        for r in reagents_raw
        if r.get("name")
    ]

    op = raw.get("operating_conditions") or {}

    res = raw.get("results") or {}
    yields_raw = res.get("yields") or []
    yields = [
        ResultYield(
            product=str(y.get("product", "")),
            yield_pct=float(y.get("yield_pct", 0.0)),
            selectivity_pct=y.get("selectivity_pct"),
        )
        for y in yields_raw
        if y.get("product")
    ]
    res_extra = {k: v for k, v in res.items() if k != "yields"}

    downstream_raw = raw.get("downstream") or []
    downstream = [
        DownstreamStep(
            step=str(d.get("step", "")),
            method=str(d.get("method", "")),
            solvent=d.get("solvent"),
            solvent_loading_kg_per_kg_feed=float(d.get("solvent_loading_kg_per_kg_feed", 0.0)),
            recovery_pct=float(d.get("recovery_pct", 100.0)),
            target_purity_pct=d.get("target_purity_pct"),
        )
        for d in downstream_raw
    ]

    cons = raw.get("constraints") or {}
    scale = raw.get("scale_targets") or {}
    reported = raw.get("reported") or {}

    # ---- schema v2 blocks (optional; absent → v1 behaviour) --------------
    schema_version = int(raw.get("schema_version", 1) or 1)
    references = [
        Reference(
            id=str(r.get("id", "")),
            citation=str(r.get("citation", "")),
            type=str(r.get("type", "literature")),
            url=r.get("url"),
            doi=r.get("doi"),
            note=str(r.get("note") or ""),
        )
        for r in (raw.get("references") or [])
        if r.get("id")
    ]
    assumptions = [
        Assumption(
            key=str(a.get("key", "")),
            value=a.get("value"),
            ref=a.get("ref"),
            unit=str(a.get("unit") or ""),
            note=str(a.get("note") or ""),
        )
        for a in (raw.get("assumptions") or [])
        if a.get("key")
    ]
    pfd = raw.get("pfd") or {}

    if fp is None:
        raise ValueError(f"{p}: feedstock.primary block is required.")
    if not yields:
        raise ValueError(f"{p}: results.yields must contain at least one entry.")

    return Experiment(
        meta=meta,
        chemistry=chem,
        feedstock_primary=fp,
        feedstock_reagents=reagents,
        operating_conditions=op,
        results_yields=yields,
        results_extra=res_extra,
        downstream=downstream,
        constraints=cons,
        scale_targets=scale,
        reported=reported,
        schema_version=schema_version,
        references=references,
        assumptions=assumptions,
        pfd=pfd,
        raw=raw,
    )


def save_experiment(exp_dict: Dict[str, Any], path: str | Path) -> Path:
    """Dump an experiment dict to YAML at `path`. Returns the resolved Path."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump(exp_dict, f, allow_unicode=True, sort_keys=False, indent=2)
    return p


def list_experiments(directory: str | Path) -> List[Path]:
    """Return YAML experiment files under `directory` (sorted)."""
    d = Path(directory)
    if not d.exists():
        return []
    return sorted(p for p in d.glob("*.yaml") if p.is_file())


def summarize(exp: Experiment) -> str:
    """Compact textual summary, used in the Streamlit Lab Data tab and the
    Claude Code instruction snippet."""
    lines = [f"# {exp.meta.name}  ({exp.meta.slug})",
             f"- Reaction: {exp.reaction_type}",
             f"- Researcher: {exp.meta.researcher or '-'}"]
    if exp.feedstock_primary:
        fp = exp.feedstock_primary
        lines.append(f"- Primary feed: {fp.name} ({fp.mass_per_batch_g} g/batch)")
    lines.append(f"- Reagents: " + ", ".join(
        f"{r.name} ({r.mass_per_batch_g}g, rec={r.recovery_fraction})"
        for r in exp.feedstock_reagents) or "  none")
    lines.append(f"- Products: " + ", ".join(
        f"{y.product} {y.yield_pct}%" for y in exp.results_yields))
    lines.append(f"- MSP product: {exp.preferred_msp_product}")
    lines.append(f"- Scales (ton/batch): {exp.scales_ton}")
    return "\n".join(lines)
