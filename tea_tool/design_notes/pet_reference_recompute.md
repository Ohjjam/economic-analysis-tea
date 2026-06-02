# PET → TPA + FA + H₂ — Tool Recomputation vs Reference Workbook

> Recomputed with the TEA tool (`processes.build_pet` → `run_tea`) on 2026-05-29.
> Source of truth (reference only): `Article/260402 TEA summary .xlsx`,
> sheet **"0.1g PET, 2H"** (0.1 g PET, 0.5 M PMA, 10 mL 1:1 H₂SO₄:DMSO, 2 h).
> Every tool number is computed fresh from the process model + engine, not copied.
> Reproduce: `python recompute_pet_vs_reference.py`.

## 1. Headline result — tool vs paper

| Metric | Scale | Reference (paper) | Tool | Δ |
|---|---|---:|---:|---:|
| **MSP of TPA** ($/kg) | 1 ton | **1.5137** | **1.5137** | 0.00% |
| | 5 ton | 0.9575 | 0.8437 | −11.9% |
| | 10 ton | 0.7506 | 0.6641 | −11.5% |
| CAPEX total ($) | 1/5/10 | 33.43M / 87.82M / 133.11M | identical | 0.00% |
| Annualized CAPEX ($/y) | 1/5/10 | 3.76M / 10.36M / 16.21M | identical | 0.00% |
| Revenue ($/y) | 1/5/10 | 5.53M / 27.65M / 55.30M | identical | 0.00% |
| OPEX ($/y) | 1 ton | 3.51M | 3.51M | 0.00% |
| | 5 ton | 17.55M | 15.83M | −9.8% |
| | 10 ton | 33.35M | 30.73M | −7.9% |

**The 1-ton column reproduces the paper to the dollar** — full validation of
CAPEX (every section), annualized CAPEX, OPEX, revenue, profit, and MSP.
CAPEX and revenue match at **all** scales. The only divergence is OPEX at
5/10 ton, and it decomposes into exactly two causes.

## 2. Divergence #1 — Maintenance + Operation scaling (modeling choice)

| | 1 ton | 5 ton | 10 ton |
|---|---:|---:|---:|
| Paper M+O (each) | $363,032 | $1,815,158 (×5) | $3,630,317 (×10) |
| Tool M+O (each, 0.6-power) | $363,032 | $953,513 (×2.63) | $1,445,255 (×3.98) |

The paper scales Maintenance and Operation **linearly with throughput**. The
tool scales them by the **0.6 power law, coupled to CAPEX** — the standard
Turton/Towler convention (maintenance is estimated as a fraction of fixed
capital, and capital itself scales at 0.6-power). This is the more defensible
choice and is why the tool's at-scale MSP is lower.

**Reconciliation:** forcing the tool to use the paper's linear M+O reproduces
the paper **exactly at 1 and 5 ton** (and isolates divergence #2 at 10 ton).

## 3. Divergence #2 — PET feedstock not scaled 5→10 ton (likely source error)

The reference sheet's PET feedstock OPEX line (row 60):

| | 1 ton | 5 ton | 10 ton |
|---|---:|---:|---:|
| Reference (`Z60/AA60/AB60`) | $350,400 | $1,752,000 (×5) | **$1,752,000 (×5)** |
| Correct ×10 | $350,400 | $1,752,000 | **$3,504,000** |

At 10 ton the workbook holds PET feedstock cost **flat** at the 5-ton value —
cell `AB60` equals `AA60` instead of `Z60 × 10`. The shortfall is exactly
**$1,752,000**, which is precisely the residual 10-ton OPEX gap that remains
after reconciling M+O. The tool scales PET feedstock correctly (×10), so it is
arithmetically right; the workbook cell appears to be a fill error (or an
undocumented fixed-supply cap). **Worth checking in the published sheet.**

## 4. Net effect at 10 ton

The two divergences push MSP in opposite directions:

- M+O (0.6-power vs linear): tool **saves** money → lower MSP
- PET feedstock (×10 vs ×5 cap): tool **spends** more → higher MSP

The M+O effect dominates, so the tool's 10-ton MSP ($0.66/kg) sits below the
paper's ($0.75/kg). If you adopt the paper's linear M+O but keep correct PET
scaling, MSP is $0.81/kg (the +$1.75M feedstock raises it above the paper).

## 5. What this says about the tool

- **Validation:** the engine reproduces a peer-reviewed, first-author TEA to
  the dollar at the design point — CAPEX build-up, CEPCI escalation, CRF,
  utility coefficients, revenue, and MSP all check out.
- **Improvement-with-use:** at scale it applies a more rigorous M+O scaling and
  surfaces a probable spreadsheet error — both are upgrades over the original
  static sheet, consistent with the "every analysis leaves the engine better"
  goal.
- **Note on prices:** revenue only matches when the YAML price DB
  (`data/prices.yaml`: TPA $0.94, FA $0.84, H₂ $8/kg) is overlaid via the
  package-level `build_pet`. The raw module defaults under-count revenue ~20%.
