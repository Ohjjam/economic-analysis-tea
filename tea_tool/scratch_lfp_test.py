import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from processes.spent_lfp_ballmill_li import build
from tea_engine.tea import run_tea

# Build process with defaults
process, db, inp = build()

# Run TEA
result = run_tea(process, db, inp)

print("=" * 80)
print(f"PROCESS: {process.name}")
print(f"DESCRIPTION: {process.description}")
print("=" * 80)
print(f"CRF: {inp.crf:.6f}")
print(f"Batches per year: {inp.batches_per_year:.1f}")
print()
print("SCALES (ton/batch):")
for scale in inp.scales_ton:
    print(f"\n--- SCALE: {scale} ton/batch ---")
    print(f"  CAPEX Total:               ${result.capex_total[scale]:,.2f}")
    print(f"  CAPEX Annualized:          ${result.capex_annualized[scale]:,.2f}")
    print(f"  OPEX Total:                ${result.opex_total[scale]:,.2f}/y")
    print(f"    - Feedstock Total:       ${result.opex[scale]['__Feedstock Total']:,.2f}/y")
    print(f"    - Utility Total:         ${result.opex[scale]['__Utility Total']:,.2f}/y")
    print(f"    - Operation Total:       ${result.opex[scale]['__Operation Total']:,.2f}/y")
    print(f"  Revenue Total:             ${result.revenue_total[scale]:,.2f}/y")
    for prod, rev in result.revenue[scale].items():
        print(f"    - {prod} revenue:        ${rev:,.2f}/y")
    print(f"  Net Profit:                ${result.net_profit[scale]:,.2f}/y")
    print(f"  MSP of Li2CO3:             ${result.msp[scale]:.4f}/kg")
    if scale in result.net_per_kg_feedstock:
        print(f"  Net Profit per kg feed:    ${result.net_per_kg_feedstock[scale]:.4f}/kg")
    
    print("\n  Material Flows (kg/batch):")
    for comp, flow in result.flows_per_batch_kg[scale].items():
        print(f"    - {comp:20s}: {flow:,.2f} kg/batch")
    
    print("\n  Material Flows (Annual kg/y):")
    for comp, flow in result.flows_annual_kg[scale].items():
        print(f"    - {comp:20s}: {flow:,.2f} kg/y")

print("=" * 80)
