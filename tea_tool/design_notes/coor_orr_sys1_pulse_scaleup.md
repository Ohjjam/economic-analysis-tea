# Scale-up report — COOR-ORR paired electrolysis (1V pulse, LDG feed) (auto first-cut)

## Stage-by-stage TEA

| Stage | ton/batch | CAPEX ($M) | Annualized CAPEX ($M/y) | OPEX ($M/y) | Revenue ($M/y) | Net profit ($M/y) | MSP ($/kg) | Annual product (t) | Batches/y | FTE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Lab | 0.001 | 0.07 | 0.01 | 0.01 | 0.00 | -0.02 | 136.86 | 0.14 | 2800 | 0.5 |
| Bench | 0.01 | 0.21 | 0.02 | 0.04 | 0.01 | -0.05 | 39.38 | 1.36 | 2800 | 1 |
| Pilot | 0.1 | 0.77 | 0.06 | 0.16 | 0.08 | -0.15 | 12.17 | 13.64 | 2800 | 3 |
| Demo | 1 | 3.00 | 0.24 | 0.67 | 0.78 | -0.14 | 2.50 | 136.37 | 2800 | 8 |
| Commercial | 10 | 11.90 | 0.96 | 3.09 | 7.78 | 3.73 | -1.24 | 1363.74 | 2800 | 15 |

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

## EHS / safety scale-up notes
- H2 is highly flammable, LEL 4 vol-%; ventilation + leak monitoring + ATEX.
- Caustic: thermal hazard on dilution; CRZ on transfer lines.

## Recommendation
Largest profitable stage: **Commercial** (10 ton/batch), net profit $3.73 M/y, MSP $-1.24/kg. Scale up with stage gates at each ladder rung.