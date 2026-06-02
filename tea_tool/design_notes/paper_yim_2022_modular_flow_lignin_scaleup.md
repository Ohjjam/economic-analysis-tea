# Scale-up report — Yim/Oh 2022 — Modular flow lignin -> aromatics + low-V H2 (auto first-cut)

## Stage-by-stage TEA

| Stage | ton/batch | CAPEX ($M) | Annualized CAPEX ($M/y) | OPEX ($M/y) | Revenue ($M/y) | Net profit ($M/y) | MSP ($/kg) | Annual product (t) | Batches/y | FTE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Lab | 0.001 | 0.14 | 0.02 | 0.04 | 0.00 | -0.06 | 8688.10 | 0.01 | 14875 | 0.5 |
| Bench | 0.01 | 0.30 | 0.04 | 0.18 | 0.00 | -0.21 | 3177.32 | 0.07 | 14875 | 1 |
| Pilot | 0.1 | 0.90 | 0.11 | 1.39 | 0.02 | -1.48 | 2196.14 | 0.68 | 14875 | 3 |
| Demo | 1 | 3.32 | 0.39 | 12.73 | 0.18 | -12.94 | 1926.80 | 6.77 | 14875 | 8 |
| Commercial | 10 | 12.93 | 1.52 | 123.29 | 1.85 | -122.96 | 1831.70 | 67.68 | 14875 | 15 |

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
- Chloroform is a suspected carcinogen — closed handling, vapor recovery, and exposure monitoring required at >100 L.
- Sulfuric acid: pH < 1 streams need Hastelloy/PTFE wetted parts; spill containment per OSHA HCS.
- H2 is highly flammable, LEL 4 vol-%; ventilation + leak monitoring + ATEX.

## Recommendation
No stage in the ladder hits the MSP target of $20.00/kg. Best-achieved MSP is $1831.70/kg at the Commercial stage. Recommend (a) raising yield/selectivity, (b) cheaper feedstock, or (c) co-product credit before committing to scale-up.