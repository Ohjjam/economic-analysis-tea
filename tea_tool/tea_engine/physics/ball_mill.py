"""Ball mill sizing — Python mirror of matlab/ball_mill_power.m.

Two physical models in series:

1. Bond's Third Law of Comminution  (intensive — kWh/t is scale-invariant)
   W_bond = 10 * Wi * (1/sqrt(P80) - 1/sqrt(F80))      [kWh / short ton]

2. Hogg & Fuerstenau (1972) mill power equation  (geometry READOUT only)
   P_net = 0.238 * D^2.5 * L * (1 - 0.937*J) * rho_b
           * (1 - 0.1/(2^(9 - 10*phi_c))) * phi_c       [kW]

What drives ECONOMICS vs. what is an informational READOUT
----------------------------------------------------------
* kWh_per_t_feed   → drives electricity OPEX. Bond comminution energy is
                     INTENSIVE (independent of throughput); the only scale
                     effect is drivetrain efficiency (see `drivetrain_eff`).
* motor_kW         → drives ball-mill CAPEX via base_cost_usd (mills are
                     sold by installed kW; cost ~ kW^0.6).
* cooling_water    → drives a small cooling-water OPEX line.
* mill_diameter/length/volume/ball_charge → INFORMATIONAL READOUT ONLY.
  They are back-solved from motor power through Hogg-Fuerstenau so an
  engineer can sanity-check vessel size. They do NOT feed any cost. The
  `mechanochem_intensity_factor` only rescales this readout geometry and
  has ZERO economic effect — it is a display-calibration knob, nothing more.

Honesty note: ~88% of the kWh/t number comes from `activation_mult` and the
efficiency terms, not from the Bond term itself (Bond contributes ~12%).
There is no first-principles model for mechanochemical activation energy in
the literature, so `activation_mult` is an explicit, tunable assumption —
not a derived quantity. Treat it as the dominant sensitivity lever.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional


@dataclass
class BallMillParams:
    Wi: float = 12.0                       # Bond work index (kWh/short ton)
    F80_um: float = 5000.0                 # feed 80%-passing size (um)
    P80_um: float = 75.0                   # product 80%-passing size (um)
    activation_mult: float = 6.0           # mechanochem overhead vs pure comminution (DOMINANT assumption)
    mill_eff: float = 0.70                 # comminution/process efficiency (intensive)
    J: float = 0.32                        # ball charge volume fraction (readout)
    phi_c: float = 0.75                    # fraction of critical speed (readout)
    rho_steel: float = 4650.0              # ball bulk density (kg/m^3) (readout)
    L_over_D: float = 1.5                  # mill L/D aspect ratio (readout)
    Cp_solid_kJ_kgK: float = 0.85          # solid Cp (reserved)
    water_price_usd_per_ton: float = 0.30  # cooling water $/ton
    capacity_factor: float = 0.85          # plant capacity factor
    # --- CAPEX correlation: mill cost ~ k_mill * motor_kW^0.6 -------------
    # Calibrated so the reference duty (default params, 1 ton/batch, 1 h ->
    # ~114.9 kW) reproduces the legacy $2.1M ball-mill quote. With this,
    # activation_mult / mill_eff / throughput now move CAPEX, not just OPEX.
    mill_capex_coeff: float = 121_950.0    # $ per kW^0.6  (≈ 2.1e6 / 114.9^0.6)
    mill_capex_exp: float = 0.60
    # --- Drivetrain (motor+gearbox) efficiency scale law -----------------
    # Bond specific energy is intensive, but real motor/gearbox efficiency
    # improves mildly with size (NEMA Premium curves: ~88% at <10 kW to
    # ~96% at >150 kW). We fold this in so kWh/t has a small, data-grounded
    # scale credit: combined_eff(thr) = mill_eff * (thr/thr_ref)^drivetrain_exp,
    # clamped. At thr_ref the credit is 1.0 (reference kWh/t preserved).
    drivetrain_exp: float = 0.030          # ~7% improvement per decade of throughput
    drivetrain_ref_t_per_h: float = 1.0    # reference throughput for the credit
    drivetrain_credit_min: float = 0.85    # clamp (small mills)
    drivetrain_credit_max: float = 1.18    # clamp (large mills)
    # --- Readout-only geometry calibration (NO economic effect) ----------
    mechanochem_intensity_factor: float = 50.0

    @classmethod
    def merged(cls, overrides: Optional[Dict] = None) -> "BallMillParams":
        if not overrides:
            return cls()
        base = asdict(cls())
        base.update({k: v for k, v in overrides.items() if k in base})
        return cls(**base)


def _hf_power(D: float, p: BallMillParams) -> float:
    """Hogg-Fuerstenau net power (kW) for mill of diameter D (m).

    READOUT ONLY — used to back-solve a plausible vessel diameter from the
    motor power. The `mechanochem_intensity_factor` rescales the 1972
    grinding-mill constant up to the forced-impact mechanochem regime so
    the reported D/V are physically plausible. Does not affect cost.
    """
    L = p.L_over_D * D
    speed_term = 1.0 - 0.1 / (2 ** (9 - 10 * p.phi_c))
    K = 0.238 * p.mechanochem_intensity_factor
    P_W = (K * D ** 2.5 * L * (1 - 0.937 * p.J)
           * p.rho_steel * speed_term * p.phi_c)
    return P_W / 1000.0  # W -> kW


def _bisect_for_diameter(P_target: float, p: BallMillParams) -> float:
    """Bisect on D such that _hf_power(D) == P_target (readout geometry)."""
    if P_target <= 0:
        return 0.1
    lo, hi = 0.05, 10.0
    P_hi = _hf_power(hi, p)
    while P_hi < P_target and hi < 50:
        hi *= 1.5
        P_hi = _hf_power(hi, p)
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if _hf_power(mid, p) < P_target:
            lo = mid
        else:
            hi = mid
        if abs(hi - lo) < 1e-5:
            break
    return 0.5 * (lo + hi)


def _drivetrain_credit(throughput_t_per_h: float, p: BallMillParams) -> float:
    """Efficiency credit (>1 = more efficient) vs the reference throughput.

    Returns combined-efficiency multiplier so that
        effective_eff = mill_eff * credit
    Larger throughput -> larger motor -> higher drivetrain efficiency.
    Clamped to keep the effect modest and bounded.
    """
    if throughput_t_per_h <= 0:
        return 1.0
    ratio = throughput_t_per_h / p.drivetrain_ref_t_per_h
    credit = ratio ** p.drivetrain_exp
    return max(p.drivetrain_credit_min, min(p.drivetrain_credit_max, credit))


def _specific_energy_kwh_per_t(throughput_t_per_h: float,
                               W_bond_metric: float,
                               p: BallMillParams) -> float:
    """kWh per metric tonne of feed at a given throughput.

    Bond term is intensive; drivetrain credit gives a small scale effect.
    """
    credit = _drivetrain_credit(throughput_t_per_h, p)
    effective_eff = p.mill_eff * credit
    return W_bond_metric * p.activation_mult / effective_eff


def ball_mill_power(throughput_ton_per_batch: float,
                    batch_hours: float,
                    params: Optional[Dict] = None,
                    batches_per_year: Optional[float] = None,
                    scales_ton: Optional[List[float]] = None) -> Dict:
    """Physics-based sizing of the mechanochemical ball mill.

    Parameters
    ----------
    throughput_ton_per_batch : float
        Plant batch size (ton LFP feed) at the design point.
    batch_hours : float
        Time per batch (h).
    params : dict, optional
        Overrides for `BallMillParams` fields.
    batches_per_year : float, optional
        For annualised cooling-water cost. Defaults to 8760*CF/batch_hours.
    scales_ton : list[float], optional
        If given, a `kWh_per_t_feed_by_scale` diagnostic table is computed
        showing how specific energy varies across scales (drivetrain effect).
    """
    p = BallMillParams.merged(params)

    # ---- 1. Bond energy for comminution (kWh / short ton) ---------------
    W_bond_short = 10.0 * p.Wi * (1.0 / math.sqrt(p.P80_um)
                                  - 1.0 / math.sqrt(p.F80_um))
    W_bond_metric = W_bond_short / 0.9072  # short ton -> metric ton

    # ---- 2. Specific energy at the design point (drivetrain-adjusted) ---
    throughput_t_per_h = throughput_ton_per_batch / batch_hours
    kWh_per_t_feed = _specific_energy_kwh_per_t(throughput_t_per_h,
                                                W_bond_metric, p)

    # ---- 3. Motor sizing for the duty -----------------------------------
    motor_kW = kWh_per_t_feed * throughput_t_per_h

    # ---- 4. Ball-mill CAPEX from installed motor power (ECONOMIC) --------
    base_cost_usd = p.mill_capex_coeff * motor_kW ** p.mill_capex_exp

    # ---- 5. Mill geometry from H-F equation (READOUT ONLY) --------------
    D = _bisect_for_diameter(motor_kW, p)
    L = p.L_over_D * D
    V_mill_m3 = math.pi / 4.0 * D ** 2 * L
    ball_charge_kg = p.J * V_mill_m3 * p.rho_steel
    specific_power_kW_per_m3 = motor_kW / V_mill_m3 if V_mill_m3 > 0 else 0.0
    n_critical = 42.3 / math.sqrt(D)
    n_op = p.phi_c * n_critical

    # ---- 6. Heat balance & cooling water (ECONOMIC, small) --------------
    Q_heat_kW = 0.9 * motor_kW
    dT_cw = 20.0
    Cp_water = 4.186
    m_cw_kg_per_s = Q_heat_kW / (Cp_water * dT_cw)
    m_cw_kg_per_h = m_cw_kg_per_s * 3600.0
    m_cw_kg_per_t = m_cw_kg_per_h / throughput_t_per_h if throughput_t_per_h > 0 else 0.0

    if batches_per_year is None:
        bpy = (8760.0 * p.capacity_factor / batch_hours) if batch_hours > 0 \
            else 8760.0 * p.capacity_factor
    else:
        bpy = batches_per_year
    water_usd_per_kg = p.water_price_usd_per_ton / 1000.0
    cw_kg_per_t_feed_per_y = m_cw_kg_per_t * bpy
    cw_usd_per_t_feed_per_y = cw_kg_per_t_feed_per_y * water_usd_per_kg

    # ---- 7. Diagnostic: specific energy across scales -------------------
    # List-of-objects so MATLAB jsonencode(struct array) and Python emit the
    # SAME JSON shape. Diagnostic only — not consumed by the TEA engine.
    by_scale = []
    if scales_ton:
        for s in scales_ton:
            t_per_h = s / batch_hours if batch_hours > 0 else s
            by_scale.append({
                "scale_ton": float(s),
                "kWh_per_t": _specific_energy_kwh_per_t(
                    t_per_h, W_bond_metric, p),
            })

    return {
        "kWh_per_t_feed":                    kWh_per_t_feed,
        "kWh_per_t_feed_by_scale":           by_scale,
        "specific_energy_is_intensive":      True,
        "drivetrain_credit_at_design":       _drivetrain_credit(throughput_t_per_h, p),
        "motor_kW_at_design_point":          motor_kW,
        "base_cost_usd":                     base_cost_usd,
        "bond_comminution_kWh_per_t":        W_bond_metric,
        "bond_fraction_of_total":            (W_bond_metric / kWh_per_t_feed
                                              if kWh_per_t_feed > 0 else 0.0),
        # --- informational geometry readout (NOT economic) ---
        "mill_diameter_m":                   D,
        "mill_length_m":                     L,
        "mill_volume_m3":                    V_mill_m3,
        "ball_charge_kg":                    ball_charge_kg,
        "specific_power_kW_per_m3":          specific_power_kW_per_m3,
        "critical_speed_rpm":                n_critical,
        "operating_speed_rpm":               n_op,
        "geometry_is_readout_only":          True,
        # --- parameters echoed for provenance ---
        "bond_work_index_kWh_per_t":         p.Wi,
        "feed_size_F80_um":                  p.F80_um,
        "product_size_P80_um":               p.P80_um,
        "activation_multiplier":             p.activation_mult,
        "mill_efficiency":                   p.mill_eff,
        "mechanochem_intensity_factor":      p.mechanochem_intensity_factor,
        # --- heat / cooling water (economic, small) ---
        "heat_load_kW_at_design_point":      Q_heat_kW,
        "cooling_water_kg_per_t_feed":       m_cw_kg_per_t,
        "cooling_water_usd_per_t_feed_per_y": cw_usd_per_t_feed_per_y,
    }
