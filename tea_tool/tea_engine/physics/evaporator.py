"""Evaporator enthalpy balance — Python mirror of matlab/evaporator_enthalpy.m.

    Q_evap = m_feed * Cp * (T_boil - T_feed) + m_evap * dH_vap

Multi-effect (MEE) trade-off, made explicit
--------------------------------------------
  * Steam economy:  Q_LPS  ≈ Q_evap / n_effects   (steam falls ~1/n)
  * Heat-transfer area: total area ≈ n * A_single  (CAPEX rises ~n)
    (classic MEE result: each effect runs at ΔT_total/n and ~Q/n duty, so
     each needs ≈ the single-effect area; n effects ⇒ ≈ n× total area.)

So adding effects cuts the steam OPEX but raises the evaporator CAPEX —
the model now exposes BOTH sides so the trade-off is visible, and the LFP
flowsheet gets a real Evaporator CAPEX row to match the steam OPEX (no more
"OPEX for a unit that doesn't exist").
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict, Optional


@dataclass
class EvaporatorParams:
    water_per_t_feed_kg: float = 5000.0       # filtrate water mass per ton feed
    evaporation_target_frac: float = 0.85     # fraction of water evaporated
    effects: int = 1                          # 1=single, 2=double, 3=triple
    Cp_kJ_per_kgK: float = 4.186              # liquid-water specific heat
    deltaH_vap_kJ_per_kg: float = 2260.0      # latent heat at 100 C
    T_feed_C: float = 25.0                    # feed temperature
    T_boil_C: float = 100.0                   # boiling temperature
    lps_price_usd_per_ton: float = 25.0       # LPS market price
    boiler_efficiency: float = 0.92           # useful Q per kJ steam delivered
    # --- heat-transfer area + CAPEX correlation --------------------------
    U_W_per_m2K: float = 1500.0               # overall HT coeff (falling film)
    deltaT_total_K: float = 30.0              # available driving ΔT (all effects)
    area_cost_usd_per_m2: float = 4000.0      # installed $/m^2 (SS evaporator)

    @classmethod
    def merged(cls, overrides: Optional[Dict] = None) -> "EvaporatorParams":
        if not overrides:
            return cls()
        base = asdict(cls())
        base.update({k: v for k, v in overrides.items() if k in base})
        return cls(**base)


def evaporator_enthalpy(throughput_ton_per_batch: float,
                        batches_per_year: float,
                        params: Optional[Dict] = None,
                        batch_hours: float = 1.0) -> Dict:
    """Enthalpy balance returning steam OPEX intensity AND evaporator CAPEX.

    `lps_steam_usd_per_t_feed_per_y` plugs into a `<name>_$_per_ton_per_y`
    meta key. `base_cost_usd` feeds the new Evaporator equipment row.
    """
    p = EvaporatorParams.merged(params)

    # ---- 1. Feed water mass per batch -----------------------------------
    m_feed_kg_per_batch = throughput_ton_per_batch * p.water_per_t_feed_kg

    # ---- 2. Heat duty ---------------------------------------------------
    Q_sens_kJ = (m_feed_kg_per_batch * p.Cp_kJ_per_kgK
                 * (p.T_boil_C - p.T_feed_C))
    m_evap_kg = m_feed_kg_per_batch * p.evaporation_target_frac
    Q_latent_kJ = m_evap_kg * p.deltaH_vap_kJ_per_kg
    Q_total_kJ = Q_sens_kJ + Q_latent_kJ
    Q_after_effects_kJ = Q_total_kJ / max(p.effects, 1)

    # ---- 3. Steam mass (OPEX side, falls with effects) ------------------
    m_steam_per_batch_kg = (Q_after_effects_kJ
                            / (p.deltaH_vap_kJ_per_kg * p.boiler_efficiency))

    # ---- 4. Per-ton-feed-per-YEAR normalisation -------------------------
    # Engine treats meta key "X_$_per_ton_per_y" as: annual cost = X * ton.
    # So X must be annualised intensity -> multiply per-batch by bpy.
    if throughput_ton_per_batch > 0:
        steam_kg_per_t = m_steam_per_batch_kg / throughput_ton_per_batch
    else:
        steam_kg_per_t = 0.0
    steam_kg_per_t_per_y = steam_kg_per_t * batches_per_year
    steam_usd_per_t_per_y = steam_kg_per_t_per_y / 1000.0 * p.lps_price_usd_per_ton

    # ---- 5. Heat-transfer area + CAPEX (rises with effects) -------------
    # Duty rate that must be transferred (W) at the design point:
    batch_s = max(batch_hours, 1e-9) * 3600.0
    Q_rate_W = (Q_total_kJ * 1000.0) / batch_s          # kJ/batch -> W
    A_single_m2 = Q_rate_W / (p.U_W_per_m2K * p.deltaT_total_K)
    A_total_m2 = A_single_m2 * max(p.effects, 1)        # MEE: ~n × single
    base_cost_usd = p.area_cost_usd_per_m2 * A_total_m2

    return {
        "feed_water_kg_per_batch":          m_feed_kg_per_batch,
        "evaporation_target_fraction":      p.evaporation_target_frac,
        "effects":                          p.effects,
        "Q_evap_MJ_per_batch":              Q_total_kJ / 1000.0,
        "lps_steam_kg_per_batch":           m_steam_per_batch_kg,
        "lps_steam_kg_per_t_feed_per_y":    steam_kg_per_t_per_y,
        "lps_steam_usd_per_t_feed_per_y":   steam_usd_per_t_per_y,
        "lps_price_usd_per_ton":            p.lps_price_usd_per_ton,
        # --- evaporator CAPEX (now matches the steam OPEX) ---
        "heat_transfer_area_m2":            A_total_m2,
        "single_effect_area_m2":            A_single_m2,
        "U_W_per_m2K":                      p.U_W_per_m2K,
        "deltaT_total_K":                   p.deltaT_total_K,
        "area_cost_usd_per_m2":             p.area_cost_usd_per_m2,
        "base_cost_usd":                    base_cost_usd,
        # --- echoed params ---
        "boiler_feed_T_C":                  p.T_feed_C,
        "boil_T_C":                         p.T_boil_C,
        "specific_heat_water_kJ_per_kg_K":  p.Cp_kJ_per_kgK,
        "latent_heat_vap_kJ_per_kg":        p.deltaH_vap_kJ_per_kg,
    }
