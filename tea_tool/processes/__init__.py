"""Process templates registry.

Each builder returns (Process, ComponentDB, TEAInputs) and the registry
auto-applies the YAML price database so component prices in `db` reflect
the latest values from `data/prices.yaml`.
"""
from tea_engine.prices import load_prices_into

from .pet_depolymerization      import build as _build_pet
from .water_electrolysis        import build as _build_h2
from .co2rr                     import build as _build_co2rr
from .biomass                   import build as _build_biomass
from .co2_to_ethylene           import build as _build_co2_c2h4
from .co2_electrolysis_lt       import build as _build_co2_hcooh
from .nitrate_to_nh2oh          import build as _build_nh2oh
from .co2rr_oor_coproduction    import build as _build_coprod
from .lignin_oxidation          import build as _build_lignin
from .h2o2_paired_pet           import build as _build_h2o2_pet
from .glucose_to_glucaric       import build as _build_glucaric
from .hmf_to_fdca               import build as _build_fdca
from .yim_2022_modular_flow_lignin import build as _build_yim_2022
from .spent_lfp_ballmill_li import build as _build_lfp_li



def _wrap(builder):
    """Builder wrapper that overlays the YAML price database onto the
    template's ComponentDB.  The PriceDB is attached as `db._pricedb`
    so the UI can read lookup URLs."""
    def _wrapped():
        process, db, inp = builder()
        try:
            pdb = load_prices_into(db)
            db._pricedb = pdb  # noqa: attribute used by Streamlit UI
        except FileNotFoundError:
            db._pricedb = None
        return process, db, inp
    return _wrapped


REGISTRY = {
    # Reference paper case — ground truth for validation
    "PET Depolymerization (PMA + Electrolysis) [paper-validated]": _wrap(_build_pet),

    # New paper-derived templates
    "CO2 Electrolysis → Ethylene (Bagemihl 2023)":              _wrap(_build_co2_c2h4),
    "Low-T CO2 Electrolysis → HCOOH (Shin 2021)":               _wrap(_build_co2_hcooh),
    "Nitrate → Hydroxylamine (Mosalpuri 2023)":                 _wrap(_build_nh2oh),
    "Paired CO2RR + OOR Coproduction (Na 2019)":                _wrap(_build_coprod),

    # Generic illustrative templates
    "Water Electrolysis (Green H2)":                            _wrap(_build_h2),
    "CO2 Electroreduction (CO2RR generic)":                     _wrap(_build_co2rr),
    "Biomass Fermentation (Glucose → Ethanol)":                 _wrap(_build_biomass),

    # Lignin valorisation (microwave + PMA + electrolytic H2)
    "Lignin Oxidation (Microwave + PMA + Electrolysis)":        _wrap(_build_lignin),

    # H2O2 + biomass paired-electrolysis (papers added 2026-05-27)
    "Paired H2O2 + PET upcycling (Qi 2023)":                    _wrap(_build_h2o2_pet),
    "Glucose -> Glucaric acid + H2 (Liu 2020)":                 _wrap(_build_glucaric),
    "HMF -> FDCA (Ni/NiOOH electrochemical)":                   _wrap(_build_fdca),

    # Yim/Oh 2022 — modular flow lignin + low-V H2 (paper-grade)
    "Modular Flow Lignin + Low-V H2 (Yim/Oh 2022)":             _wrap(_build_yim_2022),

    # Spent LFP Black Mass → Li2CO3
    "Spent LFP Black Mass → Li2CO3 (Mechanochemical, Li-only)": _wrap(_build_lfp_li),
}

# Backwards-compat aliases for existing imports
build_pet           = _wrap(_build_pet)
build_electrolysis  = _wrap(_build_h2)
build_co2rr         = _wrap(_build_co2rr)
build_biomass       = _wrap(_build_biomass)
build_lignin        = _wrap(_build_lignin)
