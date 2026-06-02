"""Leach-tank sizing — Python mirror of matlab/leach_kinetics_scm.m.

Finds the residence time to hit a target Li recovery, sizes the reactor
volume, and costs it via Williams' six-tenths rule.

Two kinetic models:
  * first_order  dX/dt = k(1-X)   -> CLOSED FORM  t = -ln(1-X)/k
                 (no numerical solver — it would just re-derive the exact
                  exponential. The default LFP leach uses this.)
  * scm_ash      ash-layer shrinking-core, genuinely nonlinear -> integrated
                 numerically with scipy.solve_ivp (only when selected).

Cost self-consistency (the key fix)
-----------------------------------
The cost is referenced to the volume required at a REFERENCE recovery
(`reference_recovery`, default 0.90 = the lab/commercial baseline), at the
same throughput:

    base_cost = cost_ref_usd * (V(target) / V(reference_recovery))^0.6

So at the default recovery the override equals the original $340k quote
exactly (no spurious inflation). It only deviates — correctly — when the
recovery TARGET differs (e.g. pushing 90% -> 98% needs a bigger tank). The
previous version hard-coded an arbitrary V_ref=1.15 m^3 that inflated the
cost 2.6x for no physical reason; that bug is removed.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, asdict
from typing import Dict, Optional, Tuple

from scipy.integrate import solve_ivp


@dataclass
class LeachParams:
    model: str = "first_order"          # "first_order" or "scm_ash"
    k_per_h: float = 2.30               # rate constant (1/h) — X=0.90 at 1 h
    reference_recovery: float = 0.90    # recovery at which cost_ref_usd applies
    R0_um: float = 30.0                 # initial particle radius (um)
    rho_B_mol_per_m3: float = 22800.0   # molar density of LFP core
    b_stoich: float = 1.0               # mol-A per mol-B
    D_e_m2_per_s: float = 1.0e-9        # effective diffusivity
    C_A_mol_per_m3: float = 7000.0      # bulk concentration of A
    slurry_density: float = 1300.0      # kg/m^3
    solids_mass_frac: float = 0.20      # mass-fraction solids
    safety_factor: float = 1.50         # reactor over-sizing
    batch_hours: float = 1.0            # process time per batch
    cost_ref_usd: float = 340000.0      # reference equipment cost at reference_recovery
    cost_scaling: float = 0.60          # 6/10ths rule exponent

    @classmethod
    def merged(cls, overrides: Optional[Dict] = None) -> "LeachParams":
        if not overrides:
            return cls()
        base = asdict(cls())
        base.update({k: v for k, v in overrides.items() if k in base})
        return cls(**base)


def _first_order_time(X_target: float, k_per_h: float) -> float:
    """Exact residence time for dX/dt = k(1-X):  t = -ln(1-X)/k."""
    X = min(max(X_target, 0.0), 1 - 1e-12)
    return -math.log(1.0 - X) / k_per_h


def _scm_time(X_target: float, p: LeachParams) -> Tuple[float, float]:
    """Ash-layer SCM residence time via numerical integration.

    dX/dt = (1/tau) / [(1-X)^(-1/3) - 1],   tau = rho_B R^2 / (6 b D_e C_A).
    Uses solve_ivp because this ODE is genuinely nonlinear (no clean closed
    form in t); falls back to the Yagi-Kunii inverse if the event is missed.
    """
    R = p.R0_um * 1e-6
    tau_s = (p.rho_B_mol_per_m3 * R ** 2) / (
        6.0 * p.b_stoich * p.D_e_m2_per_s * p.C_A_mol_per_m3)
    tau_h = tau_s / 3600.0

    def rhs(t, X):
        x = min(max(X[0], 1e-9), 1 - 1e-9)
        denom = (1 - x) ** (-1.0 / 3.0) - 1.0
        return [(1.0 / tau_h) / max(denom, 1e-9)]

    def event_target(t, X):
        return X[0] - X_target
    event_target.terminal = True
    event_target.direction = 1

    sol = solve_ivp(rhs, (0.0, 1000.0 * tau_h), [1e-4],
                    events=event_target, rtol=1e-7, atol=1e-9,
                    max_step=0.05 * tau_h if tau_h > 0 else 0.01)
    if sol.t_events and len(sol.t_events[0]) > 0:
        return float(sol.t_events[0][-1]), tau_h
    Xt = X_target
    t_h = tau_h * (1.0 - 3.0 * (1.0 - Xt) ** (2.0 / 3.0) + 2.0 * (1.0 - Xt))
    return t_h, tau_h


def _residence_time(X_target: float, p: LeachParams) -> Tuple[float, float]:
    """Return (residence_time_h, rate_metric) for the configured model."""
    if p.model == "first_order":
        return _first_order_time(X_target, p.k_per_h), p.k_per_h
    elif p.model == "scm_ash":
        t_h, tau_h = _scm_time(X_target, p)
        return t_h, (1.0 / tau_h if tau_h > 0 else float("inf"))
    raise ValueError(f"Unknown kinetic model '{p.model}'. "
                     "Use 'first_order' or 'scm_ash'.")


def _volume(throughput_ton_per_batch: float, t_h: float, p: LeachParams) -> float:
    """Reactor volume (m^3) for a given residence time."""
    slurry_mass_t = throughput_ton_per_batch / p.solids_mass_frac
    slurry_m3_per_batch = slurry_mass_t * 1000.0 / p.slurry_density
    F_vol_m3_per_h = slurry_m3_per_batch / p.batch_hours
    return F_vol_m3_per_h * t_h * p.safety_factor


def leach_kinetics_scm(throughput_ton_per_batch: float,
                       target_recovery: float,
                       params: Optional[Dict] = None) -> Dict:
    """Size the leach tank to deliver `target_recovery` of Li.

    base_cost_usd equals cost_ref_usd when target_recovery ==
    reference_recovery, and scales by (V_target / V_ref)^0.6 otherwise.
    """
    p = LeachParams.merged(params)

    # Residence time + volume at the TARGET recovery
    t_target, k_eff = _residence_time(target_recovery, p)
    V_target = _volume(throughput_ton_per_batch, t_target, p)

    # Residence time + volume at the REFERENCE recovery (same throughput)
    t_ref, _ = _residence_time(p.reference_recovery, p)
    V_ref = _volume(throughput_ton_per_batch, t_ref, p)

    # Self-consistent cost: equals cost_ref_usd at reference recovery
    if V_ref > 0:
        base_cost = p.cost_ref_usd * (V_target / V_ref) ** p.cost_scaling
    else:
        base_cost = p.cost_ref_usd

    return {
        "target_recovery":       target_recovery,
        "reference_recovery":    p.reference_recovery,
        "kinetic_model":         p.model,
        "rate_constant":         k_eff,
        "residence_time_h":      t_target,
        "residence_time_ref_h":  t_ref,
        "reactor_volume_m3":     V_target,
        "reactor_volume_ref_m3": V_ref,
        "safety_factor":         p.safety_factor,
        "base_cost_usd":         base_cost,
        "base_cost_usd_orig":    p.cost_ref_usd,
        "cost_scaling_factor":   p.cost_scaling,
    }
