"""Breakeven solver for forward-design mode.

Given a parametric build_fn, find the lever value that hits a target metric
(typically $/kg-feedstock = 0). Uses bisection on a bracket — robust even when
the metric is not monotonic everywhere, as long as you pick a sane bracket.

Typical use:
    from processes.yim_2022_modular_flow_lignin import build
    from tea_engine.solver import breakeven

    j_star = breakeven(build, parameter="j_mA_per_cm2",
                       target=0.0, bracket=(20, 5000))
    # "Need j >= 1820 mA/cm² to break even at current other lever values"

Also exposes `breakeven_multi` for finding the indifference curve of two levers.
"""
from __future__ import annotations
from typing import Callable, Dict, List, Optional, Tuple

from .tea import run_tea


def breakeven(
    build_fn: Callable,
    parameter: str,
    target: float = 0.0,
    metric: str = "net_per_kg_feedstock",
    bracket: Tuple[float, float] = None,
    scale_ton: Optional[float] = None,
    other_overrides: Optional[Dict[str, float]] = None,
    tol: float = 1e-4,
    max_iter: int = 60,
    verbose: bool = False,
) -> Optional[float]:
    """Find the lever value at which `metric` crosses `target`.

    Args:
        build_fn: parametric process builder
        parameter: lever name to solve for
        target: desired metric value (default 0 = breakeven)
        metric: TEAResult field to drive
        bracket: (lo, hi) — must contain a sign change of (metric - target).
                 Required.
        scale_ton: which scale point's metric to use (default: largest)
        other_overrides: extra build_fn overrides held constant during solve
        tol: convergence tolerance on lever value
        max_iter: bisection iterations

    Returns:
        Lever value that hits target, or None if bracket doesn't contain
        a sign change.
    """
    if bracket is None:
        raise ValueError("bracket=(lo, hi) is required")

    other = dict(other_overrides or {})

    def f(x: float) -> float:
        p, db, inp = build_fn(**{parameter: x, **other})
        r = run_tea(p, db, inp)
        scale = scale_ton if scale_ton is not None else max(inp.scales_ton)
        m = getattr(r, metric).get(scale, float("nan"))
        return m - target

    lo, hi = bracket
    flo, fhi = f(lo), f(hi)

    if verbose:
        print(f"  bracket f({lo})={flo:+.4f}, f({hi})={fhi:+.4f}")

    if flo * fhi > 0:
        # No sign change → no root in bracket
        return None

    # Bisection
    for it in range(max_iter):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if verbose and (it < 5 or it % 10 == 0):
            print(f"  iter {it}: mid={mid:.4f}, f={fm:+.4f}, bracket=[{lo:.4f},{hi:.4f}]")
        if abs(fm) < tol or (hi - lo) < tol:
            return mid
        if flo * fm < 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm

    return 0.5 * (lo + hi)


def breakeven_multi(
    build_fn: Callable,
    parameter_a: str,
    parameter_b: str,
    values_a: List[float],
    bracket_b: Tuple[float, float],
    target: float = 0.0,
    metric: str = "net_per_kg_feedstock",
    scale_ton: Optional[float] = None,
    other_overrides: Optional[Dict[str, float]] = None,
) -> Dict[float, Optional[float]]:
    """For each value of parameter_a, solve for the parameter_b that hits target.

    Returns {a_value: b_at_breakeven}. Useful for drawing the indifference
    curve "for j=X, need vanillin_sel ≥ Y".
    """
    out = {}
    for a in values_a:
        other = dict(other_overrides or {})
        other[parameter_a] = a
        b_star = breakeven(
            build_fn, parameter=parameter_b, target=target,
            metric=metric, bracket=bracket_b, scale_ton=scale_ton,
            other_overrides=other,
        )
        out[a] = b_star
    return out


def breakeven_report(
    build_fn: Callable,
    parameter: str,
    bracket: Tuple[float, float],
    lab_value: Optional[float] = None,
    commercial_target: Optional[float] = None,
    target: float = 0.0,
    metric: str = "net_per_kg_feedstock",
    scale_ton: Optional[float] = None,
) -> str:
    """Human-readable breakeven report for a single lever.

    Returns a multi-line string explaining:
      - lab value (if given)
      - commercial target (if given)
      - solved breakeven value
      - implied gap
    """
    b_star = breakeven(build_fn, parameter, target=target, metric=metric,
                       bracket=bracket, scale_ton=scale_ton)
    lines = [f"Lever: {parameter}"]
    if lab_value is not None:
        lines.append(f"  Lab value:           {lab_value}")
    if commercial_target is not None:
        lines.append(f"  Commercial target:   {commercial_target}")
    if b_star is None:
        lines.append(f"  Breakeven:           NOT REACHABLE in bracket {bracket}")
        lines.append(f"  → Adjust other levers; this one alone cannot reach {metric}={target}")
    else:
        lines.append(f"  Breakeven value:     {b_star:.4f}  (for {metric}={target})")
        if lab_value is not None:
            gap = b_star / lab_value
            lines.append(f"  Gap vs lab:          {gap:.1f}× the lab value needed")
        if commercial_target is not None:
            if b_star <= commercial_target:
                lines.append(f"  Commercial target is SUFFICIENT (target ≥ breakeven)")
            else:
                ratio = b_star / commercial_target
                lines.append(f"  Commercial target FALLS SHORT ({ratio:.1f}× more needed)")
    return "\n".join(lines)
