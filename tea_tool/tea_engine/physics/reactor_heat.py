"""Reactor heat duty — Python mirror of matlab/reactor_heat_duty.m.

Enthalpy balance for heating the depolymerization solution from feed to
reaction temperature, net of heat integration around the thermal cycle
(reactor 100 C ↔ electrolyzer 25 C ↔ vessel 180 C in the reference process).

    Q_heating = Σ m_i · Cp_i · (T_react − T_feed)        [kJ/batch]
    Q_net     = Q_heating · (1 − heat_recovery_fraction) [kJ/batch]
    steam$/t/y = Q_net[GJ] · batches/y · $/GJ / feed_ton

Honesty note (same spirit as the ball-mill `activation_mult`):
The bulk heating enthalpy is computed from first principles (stream masses ×
Cp × ΔT). The `heat_recovery_fraction` — how much of that heating is offset by
integrated cooling around the 3-temperature cycle — is the ONE calibrated
assumption. Its default (≈0.667) reproduces the reference paper's net duty
(16.15 GJ/batch) and the resulting steam OPEX ($0.27 M/y at 1 ton). It is a
heat-integration design parameter, not a derived constant — sweep it.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


def _default_solution() -> List[Dict]:
    # Masses are kg per ton of PET feed (== the 1-ton/batch scale-up flows in
    # the reference workbook); Cp in kJ/kg·K (= J/g·°C). PMA is the recycled
    # solid catalyst and is excluded from the liquid-heating duty (matches the
    # reference ΣmCp ≈ 3.13e5 kJ/K for DMSO+H2O+H2SO4).
    return [
        {"name": "DMSO",  "mass_kg_per_t_feed": 55000.0, "Cp_kJ_per_kgK": 1.91},
        {"name": "H2O",   "mass_kg_per_t_feed": 48096.0, "Cp_kJ_per_kgK": 4.18},
        {"name": "H2SO4", "mass_kg_per_t_feed":  4904.0, "Cp_kJ_per_kgK": 1.34},
    ]


@dataclass
class ReactorHeatParams:
    T_feed_C: float = 25.0
    T_react_C: float = 180.0                 # highest point of the thermal cycle
    heat_recovery_fraction: float = 0.6667   # net = heating × (1 − this); calibrated to paper
    steam_price_usd_per_GJ: float = 4.77     # medium-pressure steam (Turton 2018)
    solution: List[Dict] = field(default_factory=_default_solution)

    @classmethod
    def merged(cls, overrides: Optional[Dict] = None) -> "ReactorHeatParams":
        base = asdict(cls())
        if overrides:
            base.update({k: v for k, v in overrides.items() if k in base})
        return cls(**base)


def reactor_heat_duty(feed_ton_per_batch: float,
                      batches_per_year: float,
                      params: Optional[Dict] = None) -> Dict:
    """Net reactor heat duty and steam OPEX intensity."""
    p = ReactorHeatParams.merged(params)
    dT = p.T_react_C - p.T_feed_C

    # ---- 1. Bulk heating enthalpy (first principles) --------------------
    sigma_mCp_per_t = sum(c["mass_kg_per_t_feed"] * c["Cp_kJ_per_kgK"]
                          for c in p.solution)            # kJ/K per ton feed
    Q_heating_kJ = sigma_mCp_per_t * feed_ton_per_batch * dT
    Q_heating_GJ = Q_heating_kJ / 1e6

    # ---- 2. Net duty after heat integration -----------------------------
    Q_net_GJ = Q_heating_GJ * (1.0 - p.heat_recovery_fraction)

    # ---- 3. Steam OPEX as $/(ton-feed · y) ------------------------------
    Q_net_GJ_per_y = Q_net_GJ * batches_per_year
    steam_usd_per_y = Q_net_GJ_per_y * p.steam_price_usd_per_GJ
    if feed_ton_per_batch > 0:
        heat_usd_per_t_feed_per_y = steam_usd_per_y / feed_ton_per_batch
    else:
        heat_usd_per_t_feed_per_y = 0.0

    return {
        "T_feed_C":                     p.T_feed_C,
        "T_react_C":                    p.T_react_C,
        "delta_T_K":                    dT,
        "sigma_mCp_kJ_per_K_per_t":     sigma_mCp_per_t,
        "heat_recovery_fraction":       p.heat_recovery_fraction,
        "Q_heating_GJ_per_batch":       Q_heating_GJ,
        "Q_net_GJ_per_batch":           Q_net_GJ,
        "steam_price_usd_per_GJ":       p.steam_price_usd_per_GJ,
        "heat_usd_per_t_feed_per_y":    heat_usd_per_t_feed_per_y,
    }
