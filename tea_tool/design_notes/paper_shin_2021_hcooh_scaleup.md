# Scale-up report — Shin 2021 — CO2 -> HCOOH (BPM MEA) (auto first-cut)

## Stage-by-stage TEA

| Stage | ton/batch | CAPEX ($M) | Annualized CAPEX ($M/y) | OPEX ($M/y) | Revenue ($M/y) | Net profit ($M/y) | MSP ($/kg) | Annual product (t) | Batches/y | FTE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Lab | 0.001 | 0.06 | 0.01 | 0.01 | 0.01 | -0.01 | 2.26 | 8.01 | 8410 | 0.5 |
| Bench | 0.01 | 0.19 | 0.02 | 0.04 | 0.08 | 0.02 | 0.60 | 80.06 | 8410 | 1 |
| Pilot | 0.1 | 0.71 | 0.07 | 0.18 | 0.81 | 0.56 | 0.14 | 800.59 | 8410 | 3 |
| Demo | 1 | 2.76 | 0.28 | 0.97 | 8.13 | 6.88 | -0.02 | 8005.94 | 8410 | 8 |
| Commercial | 10 | 10.94 | 1.11 | 6.41 | 81.31 | 73.79 | -0.08 | 80059.39 | 8410 | 15 |

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
- Formic acid: corrosive, can off-gas CO if heated; PFA-lined piping above 60 °C.

## Recommendation
At an MSP target of **$0.59/kg**, the process first becomes viable at the **Pilot** stage (0.1 ton/batch, MSP = $0.14/kg). Earlier stages are validation-only; CAPEX commitment should be staged with go/no-go gates after each.