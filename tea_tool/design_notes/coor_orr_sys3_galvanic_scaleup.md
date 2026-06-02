# Scale-up report — Galvanic COOR-ORR (0V, LDG + air) (auto first-cut)

## Stage-by-stage TEA

| Stage | ton/batch | CAPEX ($M) | Annualized CAPEX ($M/y) | OPEX ($M/y) | Revenue ($M/y) | Net profit ($M/y) | MSP ($/kg) | Annual product (t) | Batches/y | FTE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Lab | 0.001 | 0.29 | 0.03 | 0.06 | 0.00 | -0.08 | 74241.37 | 0.00 | 420 | 0.5 |
| Bench | 0.01 | 0.39 | 0.03 | 0.08 | 0.00 | -0.11 | 9925.91 | 0.01 | 420 | 1 |
| Pilot | 0.1 | 0.79 | 0.07 | 0.16 | 0.00 | -0.23 | 1986.25 | 0.11 | 420 | 3 |
| Demo | 1 | 2.40 | 0.20 | 0.48 | 0.01 | -0.67 | 591.89 | 1.13 | 420 | 8 |
| Commercial | 10 | 8.79 | 0.71 | 1.76 | 0.07 | -2.40 | 213.43 | 11.34 | 420 | 15 |

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