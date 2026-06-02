# COOR-ORR systems comparison (auto first-cut)

Source: `Article/260506 COOR-ORR TEA.xlsx`, 4 paired-electrolysis systems
for electrochemical H2O2 synthesis. All numbers below come from running
the auto-builder (`build_process_from_experiment`) on the corresponding
YAML in `experiments/`, evaluated at 10 ton/batch of the limiting feed.

## 1. Headline TEA comparison (10 ton/batch)

| System | Feedstock | CAPEX ($M) | OPEX ($M/y) | Revenue ($M/y) | Net profit ($M/y) | MSP H2O2 ($/kg) |
|---|---|---:|---:|---:|---:|---:|
| 1 — LDG, 1V pulse  | LDG (free CO surrogate) | 11.90 | 3.09  | 7.78  |  3.73 |  **-1.24** |
| 2 — OER, 1.5V      | O2                      |  5.68 | 3.29  | 0.18  | -3.57 | **30.81**  |
| 3 — LDG galvanic 0V | LDG + air              |  8.79 | 1.76  | 0.07  | -2.40 | **213.43** |
| 4 — pure CO, 1V    | CO ($5.68/kg)           |  8.55 | 19.22 | 7.78  | -12.13 | **10.40**  |

### Key qualitative findings

- **System 1 wins by a landslide.** With LDG as a zero-cost CO source and
  K2CO3 captured as a sellable byproduct ($0.89/kg), the H2O2 break-even
  price is *negative* — the K2CO3 credit alone pays for the plant.
- **System 2 (OER) is the worst-case baseline.** No CO feed → no K2CO3
  credit → MSP rises ~30× higher than System 1.
- **System 3 (galvanic, 0V)** saves electricity entirely but its
  current density of ~7 mA/cm² makes the capex-per-kg crippling. Only
  attractive at micro-scale (off-grid demonstrators).
- **System 4 (pure CO)** shows the LDG advantage: paying $5.68/kg for
  procured CO crashes the economics, even with the same chemistry.

## 2. Sensitivity — K2CO3 byproduct credit (System 1)

The K2CO3 anolyte byproduct is the single biggest lever for H2O2 MSP.

| K2CO3 ($/kg) | MSP H2O2 ($/kg) |
|---:|---:|
| 0.00 |   2.97 |
| 0.50 |   0.61 |
| 0.89 (base) |  -1.24 |
| 1.50 |  -4.12 |
| 3.00 | -11.20 |

> A $0 K2CO3 credit (e.g. inability to find a buyer) flips the
> result: H2O2 MSP becomes a positive $2.97/kg.

## 3. Sensitivity — CO feed price (System 4)

System 4 is identical to System 1 except for the CO procurement cost.
Each $1/kg of priced CO adds roughly $20/kg to the H2O2 MSP — the
process is only viable when the CO source costs less than ~$0.10/kg
(only achievable from LDG / waste-gas).

| Feed ($/kg) | MSP H2O2 ($/kg) |
|---:|---:|
|  0.00 |  -1.92 |
|  1.00 |  18.61 |
|  2.57 (Echemi 2023) |  50.85 |
|  5.68 (Echemi 2025) | 114.71 |
| 10.00 | 203.41 |

## 4. Sensitivity — Electricity price (System 1)

Electricity is a much weaker lever than feedstock/byproduct credit.
Even at $250k / ton-feed / y (≈ 4× the workbook default), MSP only
moves from -$1.24 to +$0.60 / kg.

| Electricity ($/ton-feed/y) | MSP H2O2 ($/kg) |
|---:|---:|
|       0 | -1.24 |
|  10,000 | -1.16 |
|  50,000 | -0.87 |
| 100,000 | -0.50 |
| 250,000 |  0.60 |

## 5. Recommended scale-up gating

1. **Validate LDG composition and yield** at pilot (System 1) — the
   conclusion above hinges on LDG being CO-rich and free.
2. **Secure a K2CO3 off-taker** before committing to demo CAPEX — the
   $0.89/kg credit is the load-bearing assumption.
3. Avoid System 4 (priced CO) and System 3 (galvanic) for >100 t/y
   targets unless the CO procurement cost drops below $0.10/kg.
4. Keep System 2 (OER) only as a benchmark; it cannot reach $1.5/kg
   H2O2 without a major capex/utility breakthrough.

## 6. Caveats (auto-builder limits)

- Reactor CAPEX uses the workbook's $10,000/m² + $963.5/m² (electrode)
  + $180/m² (Nafion) values, scaled linearly with cell area. Real demo
  plants will sit ±30 % around this.
- Pulse duty cycle is folded into `batch_hours`; the energy-OPEX
  calculation assumes the workbook's effective on-time.
- K2CO3 evaporative crystallisation OPEX uses the workbook's LPS
  factor (1.177 kg LPS / kg evaporated water).
- Cross-validation against the workbook's reported numbers will require
  Claude Code to write a paper-grade `processes/from_experiment_coor_orr_sys*.py`
  using vendor quotes (see the **🧪 Lab Data** tab instruction block).
