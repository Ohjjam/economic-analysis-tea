"""Build the Microwave-Lignin-Oxidation TEA — two scenarios.

A_lab        : water:lignin = 100:1 (lab procedure as-is, ~$32 M/y MW heating)
B_industrial : water:lignin = 10:1  (concentrated slurry, same MW kinetics, ~$8 M/y)

Run from the tea_tool root:
    py -3 generate_lignin_tea.py
"""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(__file__))

from processes.lignin_oxidation import build as build_lignin_raw
from processes import _wrap  # apply YAML prices
from tea_engine import run_tea, export_tea_xlsx


def _wrapped(scenario):
    """Build with YAML price overlay, like REGISTRY does."""
    builder = lambda: build_lignin_raw(scenario)
    return _wrap(builder)()


SENS = {
    # ---------------- Recovery / recycle scenarios ----------------
    "Lignin recycle fraction": {
        "param":  "Organosolv Lignin.recovery",
        "values": [0.0, 0.30, 0.50, 0.6868, 0.80, 0.90, 0.95, 0.99],
    },
    "PMA recycle fraction": {
        "param":  "PMA.recovery",
        "values": [0.90, 0.95, 0.98, 0.99, 0.999, 1.0],
    },
    "Chloroform recovery (distillation)": {
        "param":  "Chloroform.recovery",
        "values": [0.99, 0.995, 0.999, 0.9999, 0.99999],
    },
    "H2O recovery (recycle %)": {
        "param":  "H2O.recovery",
        "values": [0.0, 0.50, 0.80, 0.95, 0.99],
    },

    # ---------------- Product price scenarios ----------------
    "Vanillin price ($/kg) — synthetic vs. natural": {
        "param":  "Vanillin.output_price",
        "values": [5, 11, 25, 50, 100, 300, 700],
    },
    "Syringaldehyde price ($/kg)": {
        "param":  "Syringaldehyde.output_price",
        "values": [5, 20, 50, 100, 200, 400],
    },
    "Vanillic acid price ($/kg)": {
        "param":  "Vanillic acid.output_price",
        "values": [2, 10, 35, 60, 100, 150],
    },
    "Syringic acid price ($/kg)": {
        "param":  "Syringic acid.output_price",
        "values": [2, 5, 15, 30, 80, 150],
    },
    "H2 price ($/kg)": {
        "param":  "H2.output_price",
        "values": [2, 4, 6, 8, 10],
    },
    "Lignin feedstock price ($/kg)": {
        "param":  "Organosolv Lignin.price",
        "values": [0.20, 0.40, 0.60, 1.00, 1.50],
    },

    # ---------------- Process knobs ----------------
    "Microwave electricity coefficient ($/y per ton)": {
        "param":  "meta.Microwave Reaction Electricity_$_per_ton_per_y",
        "values": [2_000_000, 5_000_000, 8_000_000, 15_000_000, 32_000_000],
    },
    "Lignin conversion (single pass, %)": {
        "param":  "meta.Lignin conversion (single pass)",
        "values": [0.10, 0.20, 0.3132, 0.50, 0.70, 0.90],
    },
    "PMA reduction degree (electron loading)": {
        "param":  "meta.PMA reduction degree",
        "values": [0.10, 0.20, 0.302, 0.50, 0.80],
    },
}


def run_scenario(scenario, out_filename):
    process, db, inp = _wrapped(scenario)
    result = run_tea(process, db, inp)
    out_path = os.path.join(os.path.dirname(__file__), "output", out_filename)
    export_tea_xlsx(out_path, process, db, inp, result, sensitivity_specs=SENS)

    print("=" * 76)
    print(f"Scenario: {scenario}  →  {process.name}")
    print("=" * 76)
    print(f"  H2O / lignin (g/g)  : {process.meta.get('H2O / lignin (g/g)'):.1f}")
    print(f"  MW electricity coef.: ${process.meta['Microwave Reaction Electricity_$_per_ton_per_y']:,.0f}/y per ton")
    print()
    print(f"  {'Scale':<10s}{'CAPEX ($)':>18s}{'OPEX ($/y)':>18s}"
          f"{'Revenue ($/y)':>18s}{'MSP Vanillin':>16s}")
    for sc in inp.scales_ton:
        print(f"  {int(sc):>3d} ton   "
              f"{result.capex_total[sc]:>16,.0f}  "
              f"{result.opex_total[sc]:>16,.0f}  "
              f"{result.revenue_total[sc]:>16,.0f}  "
              f"{result.msp[sc]:>14,.2f}")
    print(f"\n  Wrote: {out_path}\n")
    return result


def main():
    print("\n>>> Generating two-scenario TEA: water:lignin = 100:1 vs 10:1\n")
    res_a = run_scenario("A_lab",        "Lignin_TEA_A_lab_100to1.xlsx")
    res_b = run_scenario("B_industrial", "Lignin_TEA_B_industrial_10to1.xlsx")

    print("=" * 76)
    print("SUMMARY — MSP Vanillin ($/kg) by scenario × scale")
    print("=" * 76)
    print(f"  {'Scale':<10s}{'A (lab 100:1)':>18s}{'B (industrial 10:1)':>22s}{'Δ ($/kg)':>14s}")
    for sc in res_a.inputs.scales_ton:
        delta = res_a.msp[sc] - res_b.msp[sc]
        print(f"  {int(sc):>3d} ton   "
              f"{res_a.msp[sc]:>16,.2f}  "
              f"{res_b.msp[sc]:>20,.2f}  "
              f"{delta:>12,.2f}")


if __name__ == "__main__":
    main()
