# Scale-up report — OER-ORR baseline (1.5V continuous) (auto first-cut)

## Stage-by-stage TEA

| Stage | ton/batch | CAPEX ($M) | Annualized CAPEX ($M/y) | OPEX ($M/y) | Revenue ($M/y) | Net profit ($M/y) | MSP ($/kg) | Annual product (t) | Batches/y | FTE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Lab | 0.001 | 0.04 | 0.00 | 0.01 | 0.00 | -0.01 | 944.03 | 0.01 | 4200 | 0.5 |
| Bench | 0.01 | 0.11 | 0.01 | 0.02 | 0.00 | -0.03 | 265.20 | 0.12 | 4200 | 1 |
| Pilot | 0.1 | 0.37 | 0.03 | 0.10 | 0.00 | -0.12 | 104.12 | 1.22 | 4200 | 3 |
| Demo | 1 | 1.44 | 0.12 | 0.50 | 0.02 | -0.60 | 50.90 | 12.18 | 4200 | 8 |
| Commercial | 10 | 5.68 | 0.46 | 3.29 | 0.18 | -3.57 | 30.81 | 121.81 | 4200 | 15 |

## Generic scale-up risks (reaction class)
- Electrode area scales linearly with current — capex of the cell stack dominates and does NOT follow the 6/10 rule.
- Gas management: H2/O2 evolution rates scale linearly; explosion-proof venting and gas-liquid disengagement become mandatory above pilot.
- Membrane lifetime (Nafion/PEM): expect 5-7 y replacement; build into OPEX as a periodic stream.
- Current distribution uniformity is hard above ~1 m² electrode — split into multiple cells in series rather than one giant cell.
- Electrolyte purification / makeup gets expensive at commercial scale; consider in-loop ion-exchange.

## Downstream scale-up risks
- Distillation: reflux ratio + tray count must be set from VLE data, not lab approximation; capex follows ~0.65 scaling.
- Extraction: solvent recovery loop is essential — virgin solvent OPEX kills the economics if recovery < 95%.
- Crystallisation: scale-up to >1 ton requires a defined cooling profile (PAT/seeding) to avoid agglomeration.
- Membrane separation: flux declines with feed concentration; fouling cleaning cycle = OPEX line.

## Recommendation
No stage is currently profitable. Tighten upstream yield, cheapen feed, or add a co-product revenue line before scale-up commitment.