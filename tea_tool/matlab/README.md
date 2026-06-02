# MATLAB Physics Sizing Layer

> Canonical physics models for unit-operation sizing.
> Outputs a JSON contract that the Python TEA engine consumes for CAPEX/OPEX scaling.

**Processes covered:**
- **LFP** (`spent_lfp_ballmill_li`): ball mill + leach + evaporator
  → `data/matlab_sizing.json` (driver `run_sizing.m` / `run_sizing.py`).
- **PET** (`pet_depolymerization`): electrolyzer + reactor heat
  → `data/matlab_sizing_pet.json` (driver `run_sizing_pet.m` / `run_sizing_pet.py`).
  The PET electrolyzer model **re-derives the reference paper's hand
  calculations** from Faraday's law (area 595.8 m², CAPEX $5.96M, 31.9 kWh/kg,
  electricity $0.567M/y) and reproduces the paper's MSP@1t = $1.5137/kg.

## Why this layer exists

The Python TEA tool was using single-point lab numbers (e.g. `ball_mill_energy_kwh_per_t = 150`)
that don't scale physically. That's fine at lab/bench, but loses fidelity at pilot → commercial
where the cost answer matters most.

This MATLAB layer replaces those flat assumptions with proper physics:

| Unit op             | Old (flat)           | New (physics-based)                            |
|---------------------|----------------------|------------------------------------------------|
| Ball mill energy    | 150 kWh/t flat       | Bond's law (intensive) × activation / efficiency, + NEMA drivetrain scale credit |
| Ball mill CAPEX     | $2.1M flat           | ∝ motor_kW^0.6 (calibrated to $2.1M at ref duty) |
| Leach tank          | $340k @ 1 ton flat   | first-order/SCM kinetics → τ → V → 0.6-power cost, referenced to volume at the baseline recovery (self-consistent) |
| Evaporator          | 0 (missing entirely) | Enthalpy balance → steam OPEX **and** area→CAPEX node (effects trade-off) |

> The "physics" sharpens the *form* and exposes sensitivities; several
> magnitudes (activation_multiplier, water load, LPS price, area $/m²) are
> still explicit assumptions. ~88 % of the ball-mill kWh/t comes from
> `activation_multiplier`, not the Bond term — see `ball_mill_power.m` header.

## File map

```
matlab/
├── README.md                  ← this file
│   # LFP process
├── sizing_schema.json         ← LFP JSON Schema (SINGLE SOURCE OF TRUTH)
├── ball_mill_power.m          ← Bond Wi + drivetrain credit; H-F geometry = readout
├── leach_kinetics_scm.m       ← closed-form first-order; ode45 only for scm_ash
├── evaporator_enthalpy.m      ← Q_evap = m·Cp·ΔT + m·ΔH_vap; + area→CAPEX
├── run_sizing.m               ← LFP driver → matlab_sizing.json (restoredefaultpath guard)
│   # PET process
├── sizing_schema_pet.json     ← PET JSON Schema (SINGLE SOURCE OF TRUTH)
├── electrolyzer_sizing.m      ← Faraday's law → area → CAPEX; V → kWh/kg → electricity OPEX
├── reactor_heat_duty.m        ← enthalpy balance Σm·Cp·ΔT × (1−recovery) → steam OPEX
├── run_sizing_pet.m           ← PET driver → matlab_sizing_pet.json
│   # shared
└── verify_against_python.m    ← auto-discovers unit blocks; LFP 51/51 & PET 21/21 PASS
```

## JSON contract — `data/matlab_sizing.json`

**Single source of truth: [`sizing_schema.json`](sizing_schema.json)** (JSON
Schema draft-07). The Python loader validates every payload against it before
use (best-effort: a structurally-invalid file is rejected and the tool falls
back to `LAB_DEFAULTS` rather than computing on bad data). Bump
`schema_version` on any breaking change and add it to `_SCHEMA_SUPPORTED` in
`processes/spent_lfp_ballmill_li.py`.

Top-level shape (v1.0): `schema_version`, `generated_at`, `generated_by`,
`process`, `design_point_ton_per_batch`, `target_recovery`, `batch_hours`,
`capacity_factor`, `batches_per_year`, `scales_ton`, and the three unit blocks
`ball_mill`, `leach_tank`, `evaporator`. See the schema file for every field.

### What is ECONOMIC vs what is a READOUT

Not every field feeds the TEA. Only these drive cost:

| Field | Feeds |
|---|---|
| `ball_mill.kWh_per_t_feed` | electricity OPEX (overrides `ball_mill_energy_kwh_per_t`) |
| `ball_mill.base_cost_usd` | "Mechanochemical Ball-mill" CAPEX (∝ motor_kW^0.6) |
| `ball_mill.cooling_water_usd_per_t_feed_per_y` | cooling-water OPEX meta key |
| `leach_tank.base_cost_usd` | "Water Leach" CAPEX (self-consistent — = orig at reference recovery) |
| `evaporator.base_cost_usd` | "Evaporator / Concentrator" CAPEX (added in physics mode) |
| `evaporator.lps_steam_usd_per_t_feed_per_y` | LPS-steam OPEX meta key |

Everything else (`mill_diameter_m`, `mill_volume_m3`, `ball_charge_kg`,
`critical_speed_rpm`, `mechanochem_intensity_factor`, the `kWh_per_t_feed_by_scale`
table, …) is an **informational readout** — useful for sanity-checking, but it
does **not** affect any number in the TEA. The regression suite asserts this
(changing `mechanochem_intensity_factor` must not move kWh/t or CAPEX).

## Run order

### From Python (default — no MATLAB licence needed):

```bash
python -m tea_engine.physics.run_sizing            # default single-effect
python -m tea_engine.physics.run_sizing --effects 3
```

Writes `data/matlab_sizing.json` with `generated_by = python_physics_fallback`.
Uses `scipy.solve_ivp` for the `scm_ash` ODE (the default `first_order` model
is solved in closed form — no solver needed).

### From MATLAB (canonical reference):

```matlab
>> cd matlab
>> run_sizing            % healthy MATLAB
```

On a **headless / broken-JVM install** (e.g. this machine, R2024a missing
`toolbox/local/classpath.txt`), run with `-nojvm`; `run_sizing.m` calls
`restoredefaultpath` automatically when it detects the minimal path, so
`ode45`/`jsonencode` load:

```bash
"/c/Program Files/MATLAB/R2024a/bin/matlab.exe" -nojvm -batch "cd('matlab'); run_sizing(1.0)"
```

### Verified equivalence

The two implementations are **proven numerically identical** — 51/51 scalar
fields at 0.000 % difference (including the `scm_ash`/`ode45` path):

```bash
"/c/Program Files/MATLAB/R2024a/bin/matlab.exe" -nojvm -batch "cd('matlab'); verify_against_python()"
# -> "PASS: MATLAB and Python sizing are numerically equivalent."
```

`verify_against_python.m` compares `matlab_sizing_matlab.json` (MATLAB) against
`matlab_sizing.json` (Python). Generate the MATLAB side first with
`run_sizing(1.0, '../data/matlab_sizing_matlab.json')`.

### From Python TEA driver:

`processes/spent_lfp_ballmill_li.build()` auto-detects the JSON file. If absent,
falls back to the original `LAB_DEFAULTS` (smoke tests stay green).

## Precedence rules in `build()`

```
user kwargs (overrides)        ← highest priority
    ↓
matlab_sizing.json (physics)   ← if file exists
    ↓
LAB_DEFAULTS                   ← fallback
```

So a user can always override any lever via kwargs; the JSON is *new defaults*, not a hard pin.

## Extending to other processes

To add a new process (e.g. PET depolymerization sizing):

1. Add new sub-models to `matlab/` (e.g. `reactor_sizing_pet.m`).
2. Extend `run_sizing.m` to call them and write under a new key in JSON
   (e.g. `process: "pet_depolymerization"` + relevant unit blocks).
3. Mirror in `tea_engine/physics/`.
4. In the corresponding `processes/*.py`, add a `_load_matlab_sizing()` helper.

Keep schema **versioned** — bump `schema_version` on any breaking change.
