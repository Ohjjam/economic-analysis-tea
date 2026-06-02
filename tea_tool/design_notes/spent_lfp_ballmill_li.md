# Design Note — Spent LFP Black Mass to Li2CO3 (`spent_lfp_ballmill_li`)

> Generated on 2026-05-29 for the hand-written process.
> Documents the option comparison, key assumptions, and economics of the mechanochemical extraction route.
> **Physics-based sizing layer is now active** — see Section 4.

## 1. Process Overview & Chemistry

This process models the selective extraction of Lithium (Li) from spent Lithium Iron Phosphate (LFP, $LiFePO_4$) batteries.
- **Feedstock:** LFP Black Mass (approx. 4 wt% Li, purchased at $1.50/kg).
- **Key Reaction (Ball Mill):**
  $$LiFePO_4 + NH_4Cl \rightarrow LiCl + NH_4FePO_4$$
- **Precipitation Reaction:**
  $$2 LiCl + Na_2CO_3 \rightarrow Li_2CO_3\downarrow + 2 NaCl$$
- **Product:** Battery-grade $Li_2CO_3$ (market price: $20.00/kg).
- **Byproduct/Waste Handling:** Iron and phosphate stay in the leach residue ($FePO_4$ + Carbon + Binder) and are treated as landfill waste ($0.15/kg disposal fee).

## 2. Process Design Options Considered

| Option | Description | Pros | Cons | Decision |
|---|---|---|---|---|
| **A (Mechanochemical)** | Ball-milling with $NH_4Cl$ + water leaching. | Highly selective for Li; low acid/base consumption; avoids toxic organic solvents. | High mechanical electricity requirement. | **Selected** for current implementation. |
| **B (Acid Leaching)** | Direct leaching with strong inorganic acids ($H_2SO_4$, $HCl$) or organic acids. | High recovery rates, fast reaction kinetics. | Low selectivity; digests Fe and P, requiring complex solvent extraction (SX) to separate. | Rejected. |
| **C (Pyrometallurgical)** | High-temperature reduction smelting. | High throughput, handles mixed feeds. | Extreme energy consumption; Li volatilization losses; high carbon footprint. | Rejected. |

## 3. Key Assumptions / Levers

| Assumption / Parameter | Lab Baseline | Commercial Target | Source / Justification |
|---|---|---|---|
| **Li Content in Feed** | 4.0 wt% | 4.0 wt% | Typical LFP battery chemistry limit. |
| **Li Recovery** | 90.0% | 98.0% | Lab activation limits vs. commercial optimization. |
| **Ball-mill Energy** | 150 kWh/t (lab flat) | physics-based (see §4) | Bond + activation overhead replaces flat assumption. |
| **$NH_4Cl$ Stoich Factor** | 1.50 (50% excess) | 1.10 (10% excess) | Reagent excess to drive solid-solid kinetics. |
| **$Na_2CO_3$ Stoich Factor** | 1.20 (20% excess) | 1.05 (5% excess) | Precipitation stoichiometry excess. |
| **Water Recovery** | 80.0% | 95.0% | Standard filtration and wastewater recycle rate. |
| **Feedstock Purchase Price** | $1.50/kg | $1.50/kg | Mid-2024 LFP black mass market baseline. |
| **$Li_2CO_3$ Selling Price** | $20.00/kg | $20.00/kg | Mid-2024 battery-grade market price. |
| **Fe-waste Landfill Cost** | $0.15/kg | $0.15/kg | Class I non-hazardous waste disposal fee. |

## 4. Physics-based Sizing (MATLAB canonical / Python mirror)

The previous flat-default version used a single lab number for ball-mill
energy (150 kWh/t) and ignored evaporation steam entirely. This rebuild
reads `data/matlab_sizing.json` and replaces those with physics-derived
values. **The MATLAB scripts and the Python mirror are verified numerically
identical** (51/51 fields at 0.000% — run `verify_against_python.m`).

| Unit op | Model | Physics output @ 1.0 t/batch | Drives |
|---|---|---|---|
| Ball mill | Bond's third law (intensive) | 114.9 kWh/t, motor 114.9 kW | electricity OPEX |
| Ball mill CAPEX | cost ∝ motor_kW^0.6 (calibrated) | $2,100,575 | mill CAPEX |
| Leach tank | first-order kinetics → τ → V → 6/10ths | τ = 1.00 h, V = 5.78 m³ → $340,000 | leach CAPEX |
| Evaporator | enthalpy balance $Q = m C_p\Delta T + m\Delta H_{vap}$ | Q = 11,175 MJ/batch, 5,375 kg-steam/batch | steam OPEX |
| Evaporator CAPEX | area = Q/(U·ΔT)·n_effects | 69 m² → $275,920 | evaporator CAPEX |

**Honesty note (read before quoting these numbers):** the Bond term is only
**12%** of the ball-mill kWh/t; the rest comes from
`activation_multiplier` and efficiency terms. There is no first-principles
model for mechanochemical activation energy, so `activation_multiplier` is an
explicit *tunable assumption*, not a derived truth — treat it as the dominant
sensitivity lever, not a fact. The mill diameter/volume/ball-charge figures
are an **informational readout** (back-solved from motor power via
Hogg-Fuerstenau); they do not feed any cost, and `mechanochem_intensity_factor`
only rescales that readout (zero economic effect — asserted in the test suite).

Two specific fixes vs. the first draft of this layer:
1. **Leach CAPEX is now self-consistent.** Cost is referenced to the volume
   at the reference recovery (90%), so at the baseline it
   equals the original $340,000 quote exactly and only grows when the
   recovery target is pushed higher (e.g. 98% → ~$467k). The earlier draft
   inflated it 2.6× via an arbitrary reference volume — removed.
2. **The evaporator now has CAPEX, not just steam OPEX.** A real
   Evaporator/Concentrator node ($275,920, 1-effect) is added to the
   flowsheet, paired with its steam cost. More effects → higher CAPEX, lower
   steam (the trade-off is now visible; sweep with `--effects 1|2|3`).

Provenance:
- `schema_version`: 1.0  (validated against `matlab/sizing_schema.json`)
- `generated_by`:   `python_physics_fallback`
- `generated_at`:   2026-05-29T03:13:52Z
- `design_point`:   1.0 ton/batch

Re-generate from either path (outputs are interchangeable):

```bash
# Python mirror (default — scipy.solve_ivp for the scm_ash ODE)
python -m tea_engine.physics.run_sizing

# MATLAB canonical (this machine: JVM broken, so run headless with path restore)
"/c/Program Files/MATLAB/R2024a/bin/matlab.exe" -nojvm -batch "cd('matlab'); run_sizing(1.0)"

# Cross-check the two agree (51/51 fields, <1%):
"/c/Program Files/MATLAB/R2024a/bin/matlab.exe" -nojvm -batch "cd('matlab'); verify_against_python()"
```

Override knobs (precedence: explicit kwarg > MATLAB JSON > LAB_DEFAULTS):

```python
build()                                    # MATLAB JSON if present
build(matlab_sizing=False)                 # force legacy LAB_DEFAULTS
build(ball_mill_energy_kwh_per_t=80.0)     # user kwarg wins over both
build(matlab_sizing="path/to/other.json")  # use a different JSON
```

## 5. Economic Performance — Legacy vs Physics-based

The physics layer adds previously-hidden costs that the flat-default model
missed — chiefly the LPS steam to concentrate the mother liquor before
crystallization, plus the matching evaporator CAPEX and a small ball-mill
cooling-water line. The leach-tank cost is now self-consistent (no longer
inflated). The net effect is a slightly higher, more honest MSP.

| Scale | MSP (legacy flat) | MSP (physics-based) | Δ |
|---|---:|---:|---:|
| 0.10 t/batch | $15.47 | $16.31 | +0.84 |
| 1.00 t/batch | $13.01 | $13.77 | +0.76 |
| 5.00 t/batch | $12.24 | $12.97 | +0.74 |

At $20/kg battery-grade Li₂CO₃, every modeled scale ≥ 0.1 ton/batch remains
profitable; the margin at 1.0 t/batch is $6.23/kg
(physics-based) vs $6.99/kg (legacy flat). The
~$0.76/kg increase is almost
entirely the single-effect evaporation steam — a real cost, now on the books.

## 6. Critical Issues & Scale-Up Risks

1. **Evaporation steam is the new swing cost.** Single-effect evaporation is
   ~$1.0M/(ton-feed·y) of LPS — the dominant new OPEX. A triple-effect unit
   roughly triples evaporator CAPEX but cuts the steam ~3× (re-run with
   `--effects 3`); this is the first investment to evaluate at scale.
2. **`activation_multiplier` is the dominant *assumption*, not a derived
   number.** It sets ~88% of the ball-mill energy and there is no
   first-principles mechanochem model behind it. Calibrate it against pilot
   energy data before trusting the electricity OPEX; sweep ±30% as a matter
   of course. (The mill geometry readout and `mechanochem_intensity_factor`
   have **no** economic effect — verified in the test suite.)
3. **Reagent consumption cost.** $NH_4Cl$ at 3.0 mol per mol LFP with 50% lab
   excess dominates chemical OPEX; $NH_3$ stripping recovery (already in the
   flow sheet) is essential at commercial scale.
4. **Solid-waste penalty.** Landfilling $FePO_4$ ($0.15/kg) costs ~$827k/y at
   1.0 t scale. A buyer for the $FePO_4$ residue (LFP cathode-precursor supply
   chain) flips this from cost to revenue — the single biggest upside lever.
5. **Specific energy is modeled as intensive (correct).** Bond's law makes
   kWh/t scale-invariant; the only scale credit is a mild NEMA drivetrain-
   efficiency term (115 kWh/t at the
   design point; see `kWh_per_t_feed_by_scale` for the ~7%/decade effect). The
   per-scale energy table is reported but not yet wired into per-scale OPEX —
   the engine consumes the design-point value (a known, documented limitation).
