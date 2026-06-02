# Scale-up report — Na 2019 — CO2RR-OOR (CO + 2-furoic acid) (auto first-cut)

## Stage-by-stage TEA

| Stage | ton/batch | CAPEX ($M) | Annualized CAPEX ($M/y) | OPEX ($M/y) | Revenue ($M/y) | Net profit ($M/y) | MSP ($/kg) | Annual product (t) | Batches/y | FTE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Lab | 0.001 | 0.06 | 0.01 | 0.01 | 0.00 | -0.02 | 2.05 | 8.66 | 7446 | 0.5 |
| Bench | 0.01 | 0.21 | 0.03 | 0.05 | 0.03 | -0.05 | 0.58 | 86.60 | 7446 | 1 |
| Pilot | 0.1 | 0.79 | 0.10 | 0.26 | 0.28 | -0.08 | 0.09 | 865.97 | 7446 | 3 |
| Demo | 1 | 3.11 | 0.41 | 1.64 | 2.85 | 0.80 | -0.09 | 8659.70 | 7446 | 8 |
| Commercial | 10 | 12.37 | 1.63 | 12.61 | 28.46 | 14.23 | -0.16 | 86596.98 | 7446 | 15 |

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
- CO2 above 5 vol-% causes asphyxiation; ventilated rooms + CO2 monitors; CO2 storage tanks rated for thermal expansion.

## Recommendation
At an MSP target of **$1.73/kg**, the process first becomes viable at the **Bench** stage (0.01 ton/batch, MSP = $0.58/kg). Earlier stages are validation-only; CAPEX commitment should be staged with go/no-go gates after each.