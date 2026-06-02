"""Schema validation + completeness report for experiment YAMLs.

The point of this module is to make the two things the user complained about —
missing process diagrams and un-sourced numbers — *visible* rather than silent.

`validate_experiment(raw)` returns a `ValidationReport` with:
  • errors    — block usage (missing required fields; for schema_version>=2,
                also: undefined reference ids, no PFD, prices without a ref)
  • warnings  — things that should be fixed but don't block (v1 files surface
                these as warnings instead of errors)
  • coverage  — reference coverage %, PFD presence, condition completeness

Policy:
  • schema_version >= 2  → STRICT: the "should be sourced / should have a PFD"
                           rules are ERRORS.
  • schema_version  < 2  → LENIENT: same rules are WARNINGS (so the 23 legacy
                           v1 files keep loading and the smoke test stays green),
                           but the coverage numbers still print so gaps show.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


# Numeric input fields that SHOULD carry a sibling "<name>_ref" citation id.
# (field path for reporting, dict to read, value key, ref key)
def _price_targets(raw: Dict[str, Any]) -> List[Tuple[str, Dict, str, str]]:
    out: List[Tuple[str, Dict, str, str]] = []
    feed = raw.get("feedstock") or {}
    prim = feed.get("primary") or {}
    if prim.get("price_usd_per_kg") is not None:
        out.append((f"feedstock.primary.{prim.get('name','?')}",
                    prim, "price_usd_per_kg", "price_ref"))
    for r in (feed.get("reagents") or []):
        if r.get("price_usd_per_kg") is not None:
            out.append((f"feedstock.reagent.{r.get('name','?')}",
                        r, "price_usd_per_kg", "price_ref"))
    return out


@dataclass
class ValidationReport:
    slug: str
    schema_version: int
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    coverage: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_text(self) -> str:
        lines = [f"[{self.slug}] schema v{self.schema_version} — "
                 f"{'OK' if self.ok else 'ERRORS'}"]
        cov = self.coverage
        if cov:
            lines.append(
                f"   refs {cov.get('priced_with_ref',0)}/{cov.get('priced_total',0)} priced inputs sourced"
                f" | {cov.get('n_references',0)} refs defined"
                f" | PFD {'yes' if cov.get('pfd') else 'NO'}"
                f" ({cov.get('pfd_units',0)} units, {cov.get('pfd_streams',0)} streams)")
        for e in self.errors:
            lines.append(f"   ERROR: {e}")
        for w in self.warnings:
            lines.append(f"   warn:  {w}")
        return "\n".join(lines)


def validate_experiment(raw: Dict[str, Any]) -> ValidationReport:
    """Validate a raw experiment dict (as loaded from YAML)."""
    meta = raw.get("meta") or {}
    slug = str(meta.get("slug") or meta.get("name") or "?")
    ver = int(raw.get("schema_version", 1) or 1)
    rep = ValidationReport(slug=slug, schema_version=ver)
    strict = ver >= 2

    def fail(msg: str):
        (rep.errors if strict else rep.warnings).append(msg)

    # ---- hard minimums (always errors) ----------------------------------
    if not meta.get("name") or not meta.get("slug"):
        rep.errors.append("meta.name and meta.slug are required.")
    feed = raw.get("feedstock") or {}
    if not (feed.get("primary") or {}).get("name"):
        rep.errors.append("feedstock.primary.name is required.")
    if not ((raw.get("results") or {}).get("yields")):
        rep.errors.append("results.yields needs at least one entry.")

    # ---- references registry --------------------------------------------
    refs = raw.get("references") or []
    ref_ids = {str(r.get("id")) for r in refs if r.get("id")}
    for r in refs:
        if not r.get("id"):
            rep.errors.append("a references[] entry is missing 'id'.")
        elif not r.get("citation"):
            fail(f"reference '{r.get('id')}' has no citation text.")

    # ---- price sourcing -------------------------------------------------
    targets = _price_targets(raw)
    priced_total = len(targets)
    priced_with_ref = 0
    for path, d, vkey, rkey in targets:
        rid = d.get(rkey)
        if not rid:
            fail(f"{path}.{vkey} has no '{rkey}' citation.")
        else:
            priced_with_ref += 1
            if ref_ids and str(rid) not in ref_ids:
                rep.errors.append(f"{path}.{rkey} = '{rid}' is not defined in references[].")

    # ---- standalone assumptions sourcing --------------------------------
    for a in (raw.get("assumptions") or []):
        if not a.get("ref"):
            fail(f"assumption '{a.get('key','?')}' has no 'ref'.")
        elif ref_ids and str(a.get("ref")) not in ref_ids:
            rep.errors.append(f"assumption '{a.get('key','?')}'.ref "
                              f"'{a.get('ref')}' is not defined in references[].")

    # ---- PFD ------------------------------------------------------------
    pfd = raw.get("pfd") or {}
    units = pfd.get("units") or []
    streams = pfd.get("streams") or []
    if not units:
        fail("no pfd.units — a process flow diagram cannot be drawn.")
    else:
        for u in units:
            if not u.get("key") or not u.get("label"):
                rep.errors.append("a pfd.units entry needs both 'key' and 'label'.")
            if not (u.get("conditions") or {}):
                fail(f"pfd unit '{u.get('key','?')}' has no operating conditions "
                     f"(T/P/V/j/residence).")
        # stream endpoints must reference unit keys or in:/out: terminals
        unit_keys = {u.get("key") for u in units}
        for s in streams:
            for end in ("from", "to"):
                v = str(s.get(end, ""))
                if v and not (v in unit_keys or v.startswith(("in:", "out:",
                                                              "feed", "out_"))):
                    rep.warnings.append(f"pfd stream {end}='{v}' is not a known unit key.")

    # ---- coverage block -------------------------------------------------
    rep.coverage = {
        "n_references": len(ref_ids),
        "priced_total": priced_total,
        "priced_with_ref": priced_with_ref,
        "ref_coverage_pct": round(100.0 * priced_with_ref / priced_total, 1) if priced_total else None,
        "pfd": bool(units),
        "pfd_units": len(units),
        "pfd_streams": len(streams),
    }
    return rep
