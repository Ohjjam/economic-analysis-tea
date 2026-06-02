# Scale-up report — Mosalpuri 2023 — Nitrate -> Hydroxylamine (auto first-cut)

## Stage-by-stage TEA

| Stage | ton/batch | CAPEX ($M) | Annualized CAPEX ($M/y) | OPEX ($M/y) | Revenue ($M/y) | Net profit ($M/y) | MSP ($/kg) | Annual product (t) | Batches/y | FTE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Lab | 0.001 | 0.09 | 0.01 | 0.02 | 0.00 | -0.03 | 19.34 | 1.52 | 3942 | 0.5 |
| Bench | 0.01 | 0.25 | 0.03 | 0.05 | 0.00 | -0.08 | 5.23 | 15.18 | 3942 | 1 |
| Pilot | 0.1 | 0.88 | 0.10 | 0.18 | 0.00 | -0.28 | 1.83 | 151.77 | 3942 | 3 |
| Demo | 1 | 3.38 | 0.40 | 0.70 | 0.04 | -1.06 | 0.70 | 1517.67 | 3942 | 8 |
| Commercial | 10 | 13.35 | 1.57 | 2.88 | 0.38 | -4.07 | 0.27 | 15176.70 | 3942 | 15 |

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
- Hydroxylamine: shock-sensitive at >50 wt%; thermal-runaway hazard; keep dilute in process.
- Caustic potash: high pH, hygroscopic; SS316 or HDPE wetted parts; thermal hazard on dilution.

## Recommendation
At an MSP target of **$5.37/kg**, the process first becomes viable at the **Bench** stage (0.01 ton/batch, MSP = $5.23/kg). Earlier stages are validation-only; CAPEX commitment should be staged with go/no-go gates after each.