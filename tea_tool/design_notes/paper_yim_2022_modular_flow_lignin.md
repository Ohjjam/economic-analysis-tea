# Design Note — Yim/Oh 2022 — Modular flow lignin -> aromatics + low-V H2  (`paper_yim_2022_modular_flow_lignin`)

> Generated from `experiments/paper_yim_2022_modular_flow_lignin.yaml` on 2022-09-01.
> Edit freely. Claude Code uses this file as the running log of design
> decisions for `paper_yim_2022_modular_flow_lignin`.



## 1. Experiment input summary

- Reaction type: **electrochemical**
- Primary feed: **Organosolv Lignin** (1.1 g/batch, Kraft lignin (industrial 2024 market))
- Reagents: PMA (11.0 g, rec=0.99), H2SO4 (1.18 g, rec=0.97), H2O (12.0 g, rec=0.95), Chloroform (6.0 g, rec=0.95)
- Measured products (yield %): Vanillin 0.0455%, Acetovanillone 0.0155%, H2 0.07%
- Operating conditions: T=80 °C, P=35 bar, t=0.53 h
- Downstream steps: Chloroform extraction, Density-based phase separation, Chloroform recovery, Vanillin crystallisation, Electrolyzer (PMA reactivation + HER)

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

- [ ] Refine `processes/from_experiment_paper_yim_2022_modular_flow_lignin.py` with vendor-grade equipment costs.
- [ ] Run the full ladder via the **📈 Scale-up** tab and screenshot the result.
- [ ] If MSP fails: identify the single highest-leverage variable via sensitivity sweep.
