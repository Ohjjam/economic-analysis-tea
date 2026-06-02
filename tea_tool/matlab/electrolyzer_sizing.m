function out = electrolyzer_sizing(h2_kg_per_batch, batch_hours, batches_per_year, feed_ton_per_batch, params)
%ELECTROLYZER_SIZING  Faraday-law sizing of the PMA re-oxidation / H2 electrolyzer.
%   Canonical MATLAB model — mirrored 1:1 by tea_engine/physics/electrolyzer.py.
%
%   Faraday's law:
%     I = n*F*ndot_H2/FE        [A]   (n = 2 e- per H2)
%     A = I / j                 [m^2] (j in A/m^2)
%     base_cost = A * area_cost [$]
%   Specific energy (from cell voltage):
%     E = V_cell*n*F/MW_H2/3.6e6  [kWh/kg H2]
%
%   With the reference PET inputs (125 mA/cm^2, 1.2 V, 95% FE) this returns
%   area = 595.8 m^2, CAPEX = $5.96M, 31.9 kWh/kg, electricity $0.567M/y at
%   1 ton — i.e. it DERIVES the paper's hand-calculated electrolyzer sizing.
%
%   See also REACTOR_HEAT_DUTY, RUN_SIZING_PET.

    F = 96485.33212;   % C/mol
    MW_H2 = 2.016e-3;  % kg/mol

    if nargin < 5, params = struct(); end
    params = apply_defaults(params, default_params());
    if nargin < 4 || isempty(feed_ton_per_batch), feed_ton_per_batch = 1.0; end

    % ---- 1. Faraday's law: current & area ------------------------------
    h2_kg_per_h = h2_kg_per_batch / batch_hours;
    mol_per_s = (h2_kg_per_h / MW_H2) / 3600.0;
    current_A = params.electrons_per_h2 * F * mol_per_s / params.faradaic_efficiency;
    j_A_per_m2 = params.current_density_mA_cm2 * 10.0;   % mA/cm^2 -> A/m^2
    if j_A_per_m2 > 0
        area_m2 = current_A / j_A_per_m2;
    else
        area_m2 = 0;
    end

    % ---- 2. CAPEX from area --------------------------------------------
    base_cost_usd = area_m2 * params.area_cost_usd_per_m2;

    % ---- 3. Specific energy from cell voltage --------------------------
    specific_energy = params.cell_voltage_V * params.electrons_per_h2 * F / MW_H2 / 3.6e6;

    % ---- 4. Electricity OPEX as $/(ton-feed * y) -----------------------
    h2_kg_per_y = h2_kg_per_batch * batches_per_year;
    electricity_usd_per_y = specific_energy * h2_kg_per_y * params.electricity_price_usd_per_kWh;
    if feed_ton_per_batch > 0
        electricity_usd_per_t_feed_per_y = electricity_usd_per_y / feed_ton_per_batch;
    else
        electricity_usd_per_t_feed_per_y = 0;
    end

    % ---- 5. Pack output (field order matches Python) -------------------
    out = struct();
    out.h2_production_kg_per_batch       = h2_kg_per_batch;
    out.current_density_mA_cm2           = params.current_density_mA_cm2;
    out.cell_voltage_V                   = params.cell_voltage_V;
    out.faradaic_efficiency              = params.faradaic_efficiency;
    out.electrons_per_h2                 = params.electrons_per_h2;
    out.required_current_A               = current_A;
    out.required_area_m2                 = area_m2;
    out.area_cost_usd_per_m2             = params.area_cost_usd_per_m2;
    out.base_cost_usd                    = base_cost_usd;
    out.specific_energy_kWh_per_kg_H2    = specific_energy;
    out.electricity_price_usd_per_kWh    = params.electricity_price_usd_per_kWh;
    out.electricity_usd_per_t_feed_per_y = electricity_usd_per_t_feed_per_y;
end


% ====================== local helpers ======================================

function p = default_params()
    p = struct( ...
        'current_density_mA_cm2',        125.0, ...
        'cell_voltage_V',                1.2, ...
        'faradaic_efficiency',           0.95, ...
        'electrons_per_h2',              2, ...
        'area_cost_usd_per_m2',          10000.0, ...
        'electricity_price_usd_per_kWh', 0.0953, ...
        'capacity_factor',               0.80 );
end

function s = apply_defaults(s, def)
    fn = fieldnames(def);
    for i = 1:numel(fn)
        if ~isfield(s, fn{i}), s.(fn{i}) = def.(fn{i}); end
    end
end
