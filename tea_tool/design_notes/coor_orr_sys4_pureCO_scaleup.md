# Scale-up report — COOR-ORR with pure CO feed (1V pulse) (auto first-cut)

## Stage-by-stage TEA

| Stage | ton/batch | CAPEX ($M) | Annualized CAPEX ($M/y) | OPEX ($M/y) | Revenue ($M/y) | Net profit ($M/y) | MSP ($/kg) | Annual product (t) | Batches/y | FTE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Lab | 0.001 | 0.05 | 0.00 | 0.01 | 0.00 | -0.02 | 121.76 | 0.14 | 2800 | 0.5 |
| Bench | 0.01 | 0.16 | 0.01 | 0.05 | 0.01 | -0.05 | 40.79 | 1.36 | 2800 | 1 |
| Pilot | 0.1 | 0.56 | 0.05 | 0.29 | 0.08 | -0.25 | 20.15 | 13.64 | 2800 | 3 |
| Demo | 1 | 2.16 | 0.17 | 2.18 | 0.78 | -1.58 | 13.09 | 136.37 | 2800 | 8 |
| Commercial | 10 | 8.55 | 0.69 | 19.22 | 7.78 | -12.13 | 10.40 | 1363.74 | 2800 | 15 |

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
- CO is toxic (TLV 25 ppm) and flammable; CO monitors + double-block-and-bleed; never use as an indoor-vented anode feed.

## Recommendation
No stage is currently profitable. Tighten upstream yield, cheapen feed, or add a co-product revenue line before scale-up commitment.