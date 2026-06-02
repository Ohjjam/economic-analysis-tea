"""Physics-based sizing layer for the TEA engine.

Mirrors the canonical MATLAB scripts in `../matlab/`. Same equations, same
JSON output schema, no MATLAB licence required.

Modules (LFP — spent_lfp_ballmill_li):
    ball_mill        Bond's law + Hogg-Fuerstenau power & geometry sizing.
    leach_kinetics   Shrinking-core ODE (scipy.solve_ivp) for residence time.
    evaporator       Enthalpy balance -> LPS steam consumption.
    run_sizing       Master driver writing data/matlab_sizing.json.

Modules (PET — pet_depolymerization):
    electrolyzer     Faraday's law -> area -> CAPEX; voltage -> electricity OPEX.
    reactor_heat     Enthalpy balance -> net reactor heat duty -> steam OPEX.
    run_sizing_pet   PET driver writing data/matlab_sizing_pet.json.

CLI:
    python -m tea_engine.physics.run_sizing       # LFP -> data/matlab_sizing.json
    python -m tea_engine.physics.run_sizing_pet   # PET -> data/matlab_sizing_pet.json
"""
from .ball_mill import ball_mill_power
from .leach_kinetics import leach_kinetics_scm
from .evaporator import evaporator_enthalpy
from .electrolyzer import electrolyzer_sizing
from .reactor_heat import reactor_heat_duty

__all__ = [
    "ball_mill_power",
    "leach_kinetics_scm",
    "evaporator_enthalpy",
    "electrolyzer_sizing",
    "reactor_heat_duty",
]
