# Paper TEA reproduction summary

## Auto-builder MSP vs. paper-reported MSP

| YAML | Paper id | Product | Auto MSP ($/kg) | Reported ($/kg) | Δ |
|---|---|---|---:|---:|---:|
| paper_bagemihl_2023_ethylene | Bagemihl 2023 | C2H4 | $0.13 | — | — |
| paper_glycerol_formic | Glycerol -> formic acid (industrial-level EO) | FA | $-0.22 | $0.85 | -126% |
| paper_hmf_to_fdca | HMF -> FDCA (Ni/NiOOH foam, electrochemical) | FDCA | $2.77 | $4.00 | -31% |
| paper_li_2025_h2o2_spillover | Li 2025 | H2O2 | $1.27 | $1.21 | +5% |
| paper_liu_2020_glucose_glucaric | Liu 2020 | Glucaric acid | $0.42 | $2.50 | -83% |
| paper_mosalpuri_2023_nh2oh | Mosalpuri 2023 | NH2OH | $1.57 | — | — |
| paper_na_2019_co2rr_oor | Na 2019 | FuroicAcid | $-0.16 | — | — |
| paper_nie_2025_h2o2_seawater | Nie 2025 | H2O2 | $1.37 | $0.95 | +44% |
| paper_oh_2026_pet_pma | Oh 2026 | TPA | $-0.30 | $0.81 | -137% |
| paper_qi_2023_h2o2_pet | Qi 2023 | H2O2 | $-0.20 | $0.51 | -140% |
| paper_shin_2021_hcooh | Shin 2021 | HCOOH | $-0.10 | — | — |
| paper_sun_2024_h2o2_eg | Sun 2024 | H2O2 | $-4.35 | $1.09 | -499% |
| paper_wang_2025_h2o2_gde | Wang 2025 | H2O2 | $1.46 | $0.85 | +72% |

## Paper-grade builders in REGISTRY

| Template | Product | MSP @10 ton/batch |
|---|---|---:|
| PET Depolymerization (PMA + Electrolysis) [paper-validated] | TPA | $0.81 |
| CO2 Electrolysis → Ethylene (Bagemihl 2023) | C2H4 | $0.59 |
| Low-T CO2 Electrolysis → HCOOH (Shin 2021) | HCOOH | $-0.01 |
| Nitrate → Hydroxylamine (Mosalpuri 2023) | NH2OH | $5.17 |
| Paired CO2RR + OOR Coproduction (Na 2019) | FuroicAcid | $0.11 |
| Water Electrolysis (Green H2) | H2 | $2.21 |
| CO2 Electroreduction (CO2RR generic) | HCOOH | $1.17 |
| Biomass Fermentation (Glucose → Ethanol) | Ethanol | $2.14 |
| Lignin Oxidation (Microwave + PMA + Electrolysis) | Vanillin | $20.83 |
| Paired H2O2 + PET upcycling (Qi 2023) | H2O2 | $-0.42 |
| Glucose -> Glucaric acid + H2 (Liu 2020) | Glucaric acid | $0.13 |
| HMF -> FDCA (Ni/NiOOH electrochemical) | FDCA | $1.20 |