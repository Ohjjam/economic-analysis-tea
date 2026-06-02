# Design Note — Lignin oxidation - microwave + PMA  (`lignin_pma_mw`)

> Generated from `experiments/lignin_pma_mw.yaml` on 2026-05-27.
> Edit freely. Claude Code uses this file as the running log of design
> decisions for `lignin_pma_mw`.

## 1. Experiment input summary

- Reaction type: **electrochemical**
- Primary feed: **Organosolv Lignin** (5.0 g/batch, Industrial organosolv lignin (oak))
- Reagents: PMA (1.0 g, rec=0.99), H2SO4 (1.2 g, rec=0.97), H2O (6.0 g, rec=0.99)
- Measured products (yield %): Vanillin 4.5%, Vanillic acid 2.1%, H2 0.55%
- Operating conditions: T=80 °C, P=1 bar, t=2.0 h
- Downstream steps: Extraction, Crystallisation

## 2. Process design options considered

| Option | Description | Pros | Cons | Decision |
|---|---|---|---|---|
| A | (default first-cut PFD: pretreatment → Electrochemical Cell → separation train) | Matches lab procedure 1:1; minimal assumptions | Capex defaults are rough; recovery factors are guesses | **Selected** for first-cut TEA |
| B | (alternative: integrated reactor-separation) | Lower capex, higher integration | Harder to operate; needs pilot data | Reject for first-cut |
| C | (alternative: ...) | ... | ... | ... |

*Edit this table when investigating alternatives.*

## 3. Key assumptions / sources

| Assumption | Value | Source / Justification |
|---|---|---|
| Electrolyzer cost | $ ... /m² | Bagemihl 2023, Mosalpuri 2023 |
| Membrane lifetime | ... y | Vendor data |
| Solvent recovery | ... % | Lab measurement / standard distillation correlation |
| Discount rate | 0.1 | TEA paper standard |
| Plant lifetime | 20 y | Industrial baseline |

## 4. Scale-up risks & mitigations

(populated by `scaleup.build_scaleup_report` — see Scale-up tab in the app)

## 5. Open questions for the experimentalist

- [ ] Membrane / electrode lifetime at lab cell — how many hours before
  performance loss?
- [ ] Recovery fraction of H2SO4 after extraction at >100 L scale?
- [ ] Are there minor by-products (>1 wt %) not in `results.yields`?

## 6. Next actions

- [ ] Refine `processes/from_experiment_lignin_pma_mw.py` with vendor-grade equipment costs.
- [ ] Run the full ladder via the **📈 Scale-up** tab and screenshot the result.
- [ ] If MSP fails: identify the single highest-leverage variable via sensitivity sweep.
