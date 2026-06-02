# Scale-up report — Bagemihl 2023 — CO2 -> Ethylene (Cu-GDE) (auto first-cut)

## Stage-by-stage TEA

| Stage | ton/batch | CAPEX ($M) | Annualized CAPEX ($M/y) | OPEX ($M/y) | Revenue ($M/y) | Net profit ($M/y) | MSP ($/kg) | Annual product (t) | Batches/y | FTE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Lab | 0.001 | 0.04 | 0.01 | 0.01 | 0.01 | -0.01 | 3.16 | 4.57 | 8410 | 0.5 |
| Bench | 0.01 | 0.12 | 0.01 | 0.03 | 0.05 | 0.01 | 0.90 | 45.66 | 8410 | 1 |
| Pilot | 0.1 | 0.41 | 0.05 | 0.15 | 0.53 | 0.33 | 0.37 | 456.64 | 8410 | 3 |
| Demo | 1 | 1.56 | 0.18 | 0.99 | 5.28 | 4.11 | 0.20 | 4566.41 | 8410 | 8 |
| Commercial | 10 | 6.16 | 0.72 | 7.96 | 52.84 | 44.15 | 0.13 | 45664.13 | 8410 | 15 |

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
- CO2 above 5 vol-% causes asphyxiation; ventilated rooms + CO2 monitors; CO2 storage tanks rated for thermal expansion.
- C2H4 is highly flammable, LEL 2.7 vol-%; ATEX classification mandatory at commercial scale.

## Recommendation
At an MSP target of **$1.30/kg**, the process first becomes viable at the **Bench** stage (0.01 ton/batch, MSP = $0.90/kg). Earlier stages are validation-only; CAPEX commitment should be staged with go/no-go gates after each.