# Experiment Data Schema (v2)

This document defines the YAML format used to feed lab experimental data into
the AI-assisted process design pipeline.

Workflow:

1. The user fills the **🧪 Lab Data Input** tab in the Streamlit app (or
   writes a YAML directly), saving it as
   `experiments/<slug>.yaml`.
2. The user asks Claude Code (in this CLI) to "design a process and run TEA
   for `experiments/<slug>.yaml`".
3. Claude Code reads the YAML, decides on a process topology, generates a
   process builder under `processes/from_experiment_<slug>.py`, writes a
   design note in `design_notes/<slug>.md` (including option comparison
   and scale-up reasoning), runs the TEA, and exports an xlsx.

## What's new in v2 (and why)

v2 makes two things **first-class and checkable**, because in v1 they were
silently optional and so they often went missing:

1. **`references:`** — a citation registry. Every price and every modeling
   assumption must point to a reference id (`*_ref:`). No more un-sourced
   numbers slipping through.
2. **`pfd:`** — an explicit process-flow-diagram spec: units with operating
   conditions (T, P, V, j, residence, stages), streams classed as
   feed / intermediate / recycle / product, and an explicit **initial-vs-makeup**
   charge list. A PFD can now always be drawn, correctly.

**Backward compatible:** files without `schema_version: 2` are treated as v1
and keep working unchanged. Set `schema_version: 2` to opt into strict
validation (missing references / PFD become errors instead of warnings).

**Validate any file (prints a completeness report):**

```bash
python -m tea_engine.validate_cli experiments/paper_oh_2026_pet_pma.yaml
python -m tea_engine.validate_cli experiments/          # whole folder
```

A clean v2 file reports e.g.
`schema v2 — OK | refs 5/5 priced inputs sourced | 10 refs defined | PFD yes (6 units, 13 streams)`.

**Worked example:** `experiments/paper_oh_2026_pet_pma.yaml` is the canonical
v2 exemplar — copy its `references:`, `assumptions:`, and `pfd:` blocks.

### v2 block: `references`

```yaml
schema_version: 2
references:
  - id: icis2024                       # short id, cited elsewhere as *_ref
    citation: "ICIS Chemical Business — PET contract price, 2024"
    type: market                       # market | literature | vendor | assumption | internal
    url: "https://..."                 # url OR doi (optional but recommended)
  - id: natcomm2021
    citation: "Na et al., Nat. Commun. 12, 4679 (2021)"
    type: literature
    doi: "10.1038/s41467-021-25214-1"
```

### v2 convention: `*_ref` on every price

```yaml
feedstock:
  primary:
    name: PET
    price_usd_per_kg: 0.10
    price_ref: recycling_market_2024   # ← must match a references[].id
  reagents:
    - name: DMSO
      price_usd_per_kg: 1.50
      price_ref: echemi
```

### v2 block: `assumptions` (standalone sourced numbers)

```yaml
assumptions:
  - key: "electrolyzer_cost_usd_per_m2"
    value: 10000
    unit: "$/m^2"
    ref: natcomm2021
  - key: "steam_price_usd_per_GJ"
    value: 4.77
    unit: "$/GJ"
    ref: turton2018
```

### v2 block: `pfd` (process flow diagram spec)

```yaml
pfd:
  units:                               # each carries operating conditions
    - key: depoly
      label: "PET Depolymerization"
      kind: "Catalytic Reactor"        # one of process.UNIT_TYPES
      conditions: {T_C: 100, P_bar: 1, residence_h: 2.0, stages: 7}
    - key: elec
      label: "Electrolysis"
      kind: "Electrochemical Cell"
      conditions: {V_cell: 1.2, j_mA_cm2: 125, FE_pct: 95}
  streams:                             # classed; endpoints are unit keys or in:/out:
    - {from: "in:PET", to: depoly, label: "shredded PET", kind: feed}
    - {from: elec,     to: depoly, label: "regen PMA",    kind: recycle}
    - {from: depoly,   to: "out:TPA", label: "TPA",       kind: product}
  charges:                             # initial vs makeup distinction
    - {stream: PMA,  kind: initial, note: "one-time catalyst inventory"}
    - {stream: DMSO, kind: makeup,  note: "99% recovered; buy only the loss"}
```

`kind` for streams: `feed | intermediate | recycle | product`.
`kind` for charges: `initial | makeup | continuous | periodic`.

### v2 block: `scenarios` (optional — product-strategy comparison)

If a process makes co-products, declare them here and the dossier auto-builds a
cumulative-recovery comparison + a per-co-product "is it worth recovering?"
marginal table (revenue vs. separation cost) + feasibility notes. Generic — no
per-paper code. See `tea_engine/scenarios.py` and the PET exemplar.

```yaml
scenarios:
  basis_scale_ton: 10.0
  primary_product: "TPA"          # product whose MSP is reported
  base_coproducts: ["H2"]         # always sold (part of the base case)
  base_opex_excludes_usd_per_ton: 1225309.96   # OPEX a variable co-product already
                                                # contributes in the builder (avoid double-count)
  variable_coproducts:
    - key: "EG"
      name: "Ethylene glycol"
      kg_per_kg_feed: 0.20
      amount_basis: "[stoich/est] ..."          # flag estimates honestly
      price_usd_kg: 0.60
      price_ref: echemi                          # references[].id
      sep_capex_usd_per_kg: 0.0884               # IECR-2021 distillation correlation
      sep_opex_usd_per_kg: 0.8633
      sep_difficulty: 1.3                         # cost multiplier for hard separations
      sep_ref: iecr2021
      feasibility: "Feasible but energy-heavy: EG bp 197 C ..."
```

## Bring a paper to "dossier standard" (repeatable checklist)

Everything below produces the same quality of dossier (correct PFD, numbered
inline references, itemized CAPEX/OPEX with sources, per-scale net profit,
energy basis, optional scenario comparison) for ANY paper — the machinery is
generic; each paper is mostly data entry.

1. **Copy the template:** `experiments/_TEMPLATE_v2.yaml` → `experiments/<slug>.yaml`.
2. **Fill `references` + `*_ref` on every price, and `assumptions` (each with `ref`).**
   Run `python -m tea_engine.validate_cli experiments/<slug>.yaml` until it reports
   `schema v2 — OK` with full reference coverage.
3. **Fill the `pfd` block** — units with operating conditions (T/P/V/j), classed
   streams (feed/intermediate/recycle/product), and the initial-vs-makeup `charges`.
   This is what the dossier draws; getting it right fixes the diagram.
4. **(Optional but recommended) add a validated builder.** The auto-builder is a
   shallow first cut (it under-sizes electrolysis and omits reactor heat duty). For
   a paper-grade dossier, write `processes/<slug>.py` (or reuse a hand-built one),
   register it, and map the slug in `generate_dossiers.PREFERRED_BUILDER`. The
   dossier then shows validated economics (heat + electricity, correct MSP).
5. **(Optional) add a `scenarios` block** for product-strategy comparison.
6. **Generate:** `python generate_dossiers.py` (or double-click `TEA_보고서_생성.bat`).
   The new paper appears in `dossier/index.html` with its full dossier and, if
   present, its scenarios page — automatically.

## YAML structure

```yaml
# ---- 1. Metadata ----
meta:
  name: "Lignin oxidation - microwave + PMA"   # required, short title
  slug: "lignin_pma_mw"                        # required, file-safe id
  date: 2026-05-27                              # ISO date
  researcher: "오현명"
  lab: "UNIST Energy & Chemical Engineering"
  notes: "Free-form context about the experiment."

# ---- 2. Reaction / chemistry ----
chemistry:
  reaction_type: "electrochemical"             # one of:
                                               #   thermal | catalytic |
                                               #   electrochemical | photochemical |
                                               #   biological | hybrid
  description: |
    Microwave-assisted oxidation of organosolv lignin with PMA catalyst,
    followed by H2 generation at the cathode.
  reactions:                                   # optional structured form
    - lhs: "Lignin + PMA(ox)"
      rhs: "Vanillin + Vanillic acid + PMA(red)"
      role: "main"
    - lhs: "PMA(red) -> PMA(ox)"
      rhs: "anodic"
      role: "regeneration"
    - lhs: "2 H+ + 2 e-"
      rhs: "H2"
      role: "cathode"
  target_products:                             # list, ordered by priority
    - "Vanillin"
    - "Vanillic acid"
    - "H2"

# ---- 3. Feedstock & inputs ----
feedstock:
  primary:
    name: "Organosolv Lignin"
    mass_per_batch_g: 5.0                      # lab scale
    purity_pct: 95
    price_usd_per_kg: 0.4                      # null = unknown, AI will estimate
    source_note: "Industrial organosolv (oak)"
  reagents:                                    # list, all consumed/recovered
    - name: "PMA"
      mass_per_batch_g: 1.0
      recovery_fraction: 0.99                  # 0..1
      role: "catalyst"
      price_usd_per_kg: 0.01
    - name: "H2SO4"
      mass_per_batch_g: 1.2
      recovery_fraction: 0.97
      role: "solvent"
      price_usd_per_kg: 0.037
    - name: "H2O"
      mass_per_batch_g: 6.0
      recovery_fraction: 0.99
      role: "utility"
      price_usd_per_kg: 0.00022

# ---- 4. Operating conditions ----
operating_conditions:
  temperature_C: 80
  pressure_bar: 1
  ph: 1.5
  reaction_time_h: 2.0
  batch_volume_ml: 50
  # electrochemistry-specific (optional)
  electrochem:
    cell_voltage_V: 0.95
    current_density_mA_cm2: 100
    faradaic_efficiency_pct: 92               # for the target product
    electrode_area_cm2: 5.0
    electrolyte: "0.5 M H2SO4"
    membrane: "Nafion 117"
  # thermal/catalytic-specific (optional)
  thermal:
    heating_method: "microwave"
    power_W: 300

# ---- 5. Results / measured performance ----
results:
  yields:                                      # mass-yield (kg product / kg feed)
    - product: "Vanillin"
      yield_pct: 4.5                           # % w/w on dry-lignin basis
      selectivity_pct: 32
    - product: "Vanillic acid"
      yield_pct: 2.1
      selectivity_pct: 15
    - product: "H2"
      yield_pct: 0.55                          # by Faraday's law, optional
  conversion_pct: 28
  mass_balance_closure_pct: 91                 # how well the inputs add up to outputs
  energy_consumption_kWh_per_kg_product: null  # optional measured
  notes: "GC-FID for monomers; HPLC for acids; gas chromatography for H2."

# ---- 6. Separation / downstream (optional but recommended) ----
downstream:
  - step: "Extraction"
    method: "Liquid-liquid (chloroform)"
    solvent: "Chloroform"
    solvent_loading_kg_per_kg_feed: 5.0
    recovery_pct: 95
  - step: "Crystallisation"
    method: "Cooling crystallization"
    target_purity_pct: 98
    recovery_pct: 80

# ---- 7. Known constraints / design preferences ----
constraints:
  must_have_unit_operations: []                # e.g. ["distillation", "electrolysis"]
  avoid_unit_operations: []                    # e.g. ["chromatography"]
  preferred_msp_product: "Vanillin"
  hazardous_materials: ["chloroform"]
  scale_up_priority: "balanced"                # capex | opex | balanced | maximum_throughput
  plant_lifetime_years: 20
  discount_rate: 0.10

# ---- 8. Scale targets ----
scale_targets:
  scales_ton_per_batch: [0.01, 0.1, 1.0, 5.0, 10.0]   # lab → bench → pilot → demo → commercial
  capacity_factor: 0.8                                # uptime
  batch_hours: 2.0
```

## Required vs optional

The absolute minimum the AI needs to produce a usable first-cut design and
TEA is:

- `meta.name`, `meta.slug`
- `chemistry.reaction_type`, `chemistry.target_products`
- `feedstock.primary.{name, mass_per_batch_g}`
- At least one entry in `results.yields`

Everything else is optional but improves the AI's design and lowers the
amount of guessing in the design note.
