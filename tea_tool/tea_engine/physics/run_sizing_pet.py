"""PET sizing driver — Python mirror of matlab/run_sizing_pet.m.

CLI:
    python -m tea_engine.physics.run_sizing_pet
        Writes data/matlab_sizing_pet.json at the 1.0 ton-PET/batch design point.

Schema in sync with matlab/run_sizing_pet.m — see matlab/sizing_schema_pet.json.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone

from .electrolyzer import electrolyzer_sizing
from .reactor_heat import reactor_heat_duty

SCHEMA_VERSION = "1.0"
PROCESS_NAME = "pet_depolymerization"

# Design-point H2 production at 1 ton PET/batch (reference workbook N15: kg/2h).
H2_KG_PER_BATCH_AT_1T = 53.2224


def build_payload(design_point_ton: float = 1.0,
                  batch_hours: float = 2.0,
                  capacity_factor: float = 0.80,
                  h2_kg_per_batch_at_1t: float = H2_KG_PER_BATCH_AT_1T,
                  electrolyzer_overrides: dict | None = None,
                  reactor_heat_overrides: dict | None = None) -> dict:
    batches_per_year = 365 * 24 * capacity_factor / batch_hours  # 3504 at 2h/0.8

    # H2 scales linearly with PET feed.
    h2_kg_per_batch = h2_kg_per_batch_at_1t * design_point_ton

    elec = electrolyzer_sizing(h2_kg_per_batch, batch_hours, batches_per_year,
                               feed_ton_per_batch=design_point_ton,
                               params=electrolyzer_overrides)
    heat = reactor_heat_duty(design_point_ton, batches_per_year,
                             params=reactor_heat_overrides)

    return {
        "schema_version":             SCHEMA_VERSION,
        "generated_at":               datetime.now(timezone.utc)
                                              .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by":               "python_physics_fallback",
        "process":                    PROCESS_NAME,
        "design_point_ton_per_batch": design_point_ton,
        "batch_hours":                batch_hours,
        "capacity_factor":            capacity_factor,
        "batches_per_year":           batches_per_year,
        "electrolyzer":               elec,
        "reactor_heat":               heat,
    }


def _default_output_path() -> str:
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(here, "data", "matlab_sizing_pet.json")


def write_payload(payload: dict, output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate physics-based sizing JSON for the PET TEA template.")
    ap.add_argument("--design-point", type=float, default=1.0,
                    help="Design-point PET throughput in ton/batch (default 1.0).")
    ap.add_argument("--batch-hours", type=float, default=2.0)
    ap.add_argument("--capacity-factor", type=float, default=0.80)
    ap.add_argument("--output", type=str, default=_default_output_path())
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    payload = build_payload(design_point_ton=args.design_point,
                            batch_hours=args.batch_hours,
                            capacity_factor=args.capacity_factor)
    write_payload(payload, args.output)

    if not args.quiet:
        e = payload["electrolyzer"]
        h = payload["reactor_heat"]
        print("=" * 66)
        print(f"Python physics sizing -- {PROCESS_NAME}")
        print("=" * 66)
        print(f"Design point   : {args.design_point} ton PET/batch")
        print()
        print(f"[electrolyzer] area = {e['required_area_m2']:8.2f} m^2   "
              f"I = {e['required_current_A']:,.0f} A")
        print(f"               CAPEX = ${e['base_cost_usd']:13,.0f}   "
              f"(area x ${e['area_cost_usd_per_m2']:,.0f}/m^2)")
        print(f"               energy = {e['specific_energy_kWh_per_kg_H2']:.2f} kWh/kg H2   "
              f"electricity OPEX = ${e['electricity_usd_per_t_feed_per_y']:,.0f}/(t*y)")
        print(f"[reactor heat] Q_heating = {h['Q_heating_GJ_per_batch']:6.2f} GJ/batch  "
              f"recovery = {h['heat_recovery_fraction']*100:.1f}%")
        print(f"               Q_net = {h['Q_net_GJ_per_batch']:6.2f} GJ/batch   "
              f"steam OPEX = ${h['heat_usd_per_t_feed_per_y']:,.0f}/(t*y)")
        print()
        print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
