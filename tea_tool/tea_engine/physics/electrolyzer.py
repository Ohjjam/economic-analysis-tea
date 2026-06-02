"""Electrolyzer sizing — Python mirror of matlab/electrolyzer_sizing.m.

Sizes the PMA re-oxidation / H2-evolution electrolyzer from first principles
(Faraday's law), reproducing the hand calculation in the reference PET TEA.

Faraday's law
-------------
    I = n · F · ṅ_H2 / FE              [A]      (n = 2 e- per H2)
    A = I / j                          [m^2]    (j in A/m^2)
    base_cost = A · area_cost          [$]      ($/m^2 of cell)

Specific electrolysis energy (thermodynamic, from cell voltage)
    E = V_cell · n · F / MW_H2 / 3.6e6 [kWh/kg H2]

These are exactly the relations the reference workbook used; with the paper's
inputs (125 mA/cm^2, 1.2 V, 95% FE) this returns area = 595.8 m^2, CAPEX =
$5.96 M, energy = 31.9 kWh/kg H2, electricity OPEX = $0.567 M/y at 1 ton — i.e.
the tool now DERIVES what the paper computed by hand.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict, Optional

FARADAY = 96485.33212      # C/mol
MW_H2_KG = 2.016e-3        # kg/mol


@dataclass
class ElectrolyzerParams:
    current_density_mA_cm2: float = 125.0   # j
    cell_voltage_V: float = 1.2             # V_cell
    faradaic_efficiency: float = 0.95       # FE
    electrons_per_h2: int = 2               # n
    area_cost_usd_per_m2: float = 10000.0   # installed $/m^2 of electrolyzer
    electricity_price_usd_per_kWh: float = 0.0953
    capacity_factor: float = 0.80           # PET plant CF (matches TEAInputs)

    @classmethod
    def merged(cls, overrides: Optional[Dict] = None) -> "ElectrolyzerParams":
        if not overrides:
            return cls()
        base = asdict(cls())
        base.update({k: v for k, v in overrides.items() if k in base})
        return cls(**base)


def electrolyzer_sizing(h2_kg_per_batch: float,
                        batch_hours: float,
                        batches_per_year: float,
                        feed_ton_per_batch: float = 1.0,
                        params: Optional[Dict] = None) -> Dict:
    """Size the electrolyzer and return CAPEX + electricity OPEX intensity.

    Parameters
    ----------
    h2_kg_per_batch : float
        H2 produced per batch at the design point.
    batch_hours : float
        Batch duration (h) — sets the instantaneous H2 rate / current.
    batches_per_year : float
        For the annual electricity OPEX.
    feed_ton_per_batch : float
        Feed (PET) tons per batch at the design point — used to express the
        electricity cost as a $/(ton-feed·y) intensity for the TEA meta key.
    params : dict, optional
        Overrides for `ElectrolyzerParams`.
    """
    p = ElectrolyzerParams.merged(params)

    # ---- 1. Faraday's law: current & area -------------------------------
    h2_kg_per_h = h2_kg_per_batch / batch_hours
    mol_per_s = (h2_kg_per_h / MW_H2_KG) / 3600.0
    current_A = p.electrons_per_h2 * FARADAY * mol_per_s / p.faradaic_efficiency
    j_A_per_m2 = p.current_density_mA_cm2 * 10.0   # mA/cm^2 -> A/m^2
    area_m2 = current_A / j_A_per_m2 if j_A_per_m2 > 0 else 0.0

    # ---- 2. CAPEX from area --------------------------------------------
    base_cost_usd = area_m2 * p.area_cost_usd_per_m2

    # ---- 3. Specific energy from cell voltage --------------------------
    specific_energy_kWh_per_kg = (p.cell_voltage_V * p.electrons_per_h2
                                  * FARADAY / MW_H2_KG / 3.6e6)

    # ---- 4. Electricity OPEX as $/(ton-feed · y) -----------------------
    h2_kg_per_y = h2_kg_per_batch * batches_per_year
    electricity_usd_per_y = (specific_energy_kWh_per_kg * h2_kg_per_y
                             * p.electricity_price_usd_per_kWh)
    if feed_ton_per_batch > 0:
        electricity_usd_per_t_feed_per_y = electricity_usd_per_y / feed_ton_per_batch
    else:
        electricity_usd_per_t_feed_per_y = 0.0

    return {
        "h2_production_kg_per_batch":        h2_kg_per_batch,
        "current_density_mA_cm2":            p.current_density_mA_cm2,
        "cell_voltage_V":                    p.cell_voltage_V,
        "faradaic_efficiency":               p.faradaic_efficiency,
        "electrons_per_h2":                  p.electrons_per_h2,
        "required_current_A":                current_A,
        "required_area_m2":                  area_m2,
        "area_cost_usd_per_m2":              p.area_cost_usd_per_m2,
        "base_cost_usd":                     base_cost_usd,
        "specific_energy_kWh_per_kg_H2":     specific_energy_kWh_per_kg,
        "electricity_price_usd_per_kWh":     p.electricity_price_usd_per_kWh,
        "electricity_usd_per_t_feed_per_y":  electricity_usd_per_t_feed_per_y,
    }
