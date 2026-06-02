"""Master driver — Python mirror of matlab/run_sizing.m.

CLI:
    python -m tea_engine.physics.run_sizing
        Writes data/matlab_sizing.json at default 1.0 ton/batch.

    python -m tea_engine.physics.run_sizing --design-point 5.0
        Anchors physics at 5 ton/batch.

    python -m tea_engine.physics.run_sizing --output data/python_sizing.json
        Write to a different path (used by verify_against_python.m).

The schema must remain in sync with `matlab/run_sizing.m` so the Python
artifact is interchangeable with the MATLAB artifact downstream.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone

from .ball_mill import ball_mill_power
from .leach_kinetics import leach_kinetics_scm
from .evaporator import evaporator_enthalpy

SCHEMA_VERSION = "1.0"
PROCESS_NAME = "spent_lfp_ballmill_li"


def build_payload(design_point_ton: float = 1.0,
                  target_recovery: float = 0.90,
                  batch_hours: float = 1.0,
                  capacity_factor: float = 0.85,
                  scales_ton: list | None = None,
                  ball_mill_overrides: dict | None = None,
                  leach_overrides: dict | None = None,
                  evaporator_overrides: dict | None = None) -> dict:
    """Compute the full sizing payload and return as a dict ready for JSON."""
    batches_per_year = 365 * 24 * capacity_factor / batch_hours
    if scales_ton is None:
        scales_ton = [0.1, 1.0, 5.0]

    bm = ball_mill_power(design_point_ton, batch_hours, ball_mill_overrides,
                         batches_per_year=batches_per_year,
                         scales_ton=scales_ton)
    lk = leach_kinetics_scm(design_point_ton, target_recovery, leach_overrides)
    ev = evaporator_enthalpy(design_point_ton, batches_per_year,
                             evaporator_overrides, batch_hours=batch_hours)

    return {
        "schema_version":             SCHEMA_VERSION,
        "generated_at":               datetime.now(timezone.utc)
                                              .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by":               "python_physics_fallback",
        "process":                    PROCESS_NAME,
        "design_point_ton_per_batch": design_point_ton,
        "target_recovery":            target_recovery,
        "batch_hours":                batch_hours,
        "capacity_factor":            capacity_factor,
        "batches_per_year":           batches_per_year,
        "scales_ton":                 scales_ton,
        "ball_mill":                  bm,
        "leach_tank":                 lk,
        "evaporator":                 ev,
    }


def _default_output_path() -> str:
    here = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    return os.path.join(here, "data", "matlab_sizing.json")


def write_payload(payload: dict, output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate physics-based sizing JSON for the LFP TEA tool.")
    ap.add_argument("--design-point", type=float, default=1.0,
                    help="Design-point throughput in ton/batch (default 1.0).")
    ap.add_argument("--target-recovery", type=float, default=0.90,
                    help="Target Li recovery (default 0.90).")
    ap.add_argument("--batch-hours", type=float, default=1.0,
                    help="Batch duration in hours (default 1.0).")
    ap.add_argument("--capacity-factor", type=float, default=0.85,
                    help="Plant capacity factor (default 0.85).")
    ap.add_argument("--effects", type=int, default=1,
                    help="Evaporator effects: 1 single, 2 double, 3 triple "
                         "(default 1).")
    ap.add_argument("--output", type=str, default=_default_output_path(),
                    help="Output JSON path "
                         "(default data/matlab_sizing.json).")
    ap.add_argument("--quiet", action="store_true",
                    help="Suppress informational stdout.")
    args = ap.parse_args(argv)

    payload = build_payload(
        design_point_ton=args.design_point,
        target_recovery=args.target_recovery,
        batch_hours=args.batch_hours,
        capacity_factor=args.capacity_factor,
        evaporator_overrides={"effects": args.effects},
    )
    write_payload(payload, args.output)

    if not args.quiet:
        bm = payload["ball_mill"]
        lk = payload["leach_tank"]
        ev = payload["evaporator"]
        print("=" * 66)
        print(f"Python physics sizing -- {PROCESS_NAME}")
        print("=" * 66)
        print(f"Design point   : {args.design_point} ton/batch")
        print(f"Target recovery: {args.target_recovery * 100:.1f}%")
        print(f"Effects        : {args.effects}")
        print()
        print(f"[ball mill ]  motor = {bm['motor_kW_at_design_point']:7.2f} kW   "
              f"{bm['kWh_per_t_feed']:6.1f} kWh/t   "
              f"(Bond {100*bm['bond_fraction_of_total']:.0f}% of total)")
        print(f"              CAPEX = ${bm['base_cost_usd']:11,.0f}   "
              f"[readout: D={bm['mill_diameter_m']:.2f} m, "
              f"{bm['ball_charge_kg']:,.0f} kg balls]")
        if bm.get("kWh_per_t_feed_by_scale"):
            tbl = "  ".join(f"{r['scale_ton']:g}t:{r['kWh_per_t']:.0f}"
                            for r in bm["kWh_per_t_feed_by_scale"])
            print(f"              kWh/t by scale (drivetrain): {tbl}")
        print(f"[leach     ]  tau   = {lk['residence_time_h']:5.2f} h    "
              f"V = {lk['reactor_volume_m3']:6.2f} m^3   "
              f"CAPEX = ${lk['base_cost_usd']:11,.0f}")
        print(f"              (= ref ${lk['base_cost_usd_orig']:,.0f} at "
              f"{lk['reference_recovery']*100:.0f}% recovery; "
              f"now {100*(lk['base_cost_usd']/lk['base_cost_usd_orig']-1):+.1f}% "
              f"at {lk['target_recovery']*100:.0f}%)")
        print(f"[evaporator]  Q     = {ev['Q_evap_MJ_per_batch']:7.1f} MJ/batch  "
              f"steam = {ev['lps_steam_kg_per_batch']:7.1f} kg/batch  "
              f"({ev['effects']}-effect)")
        print(f"              area  = {ev['heat_transfer_area_m2']:6.1f} m^2   "
              f"CAPEX = ${ev['base_cost_usd']:11,.0f}   "
              f"steam OPEX = ${ev['lps_steam_usd_per_t_feed_per_y']:,.0f}/(t*y)")
        print()
        print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
