function out = evaporator_enthalpy(throughput_ton_per_batch, batches_per_year, params, batch_hours)
%EVAPORATOR_ENTHALPY  Enthalpy balance -> steam OPEX + evaporator CAPEX.
%   Canonical MATLAB model — mirrored 1:1 by tea_engine/physics/evaporator.py.
%
%   out = evaporator_enthalpy(throughput_ton_per_batch, batches_per_year, ...
%                             params, batch_hours)
%
%   Q_evap = m_feed*Cp*(T_boil - T_feed) + m_evap*dH_vap
%
%   Multi-effect trade-off (made explicit):
%     steam economy:  Q_LPS  ~ Q_evap / n_effects   (steam falls ~1/n)
%     heat-transfer area: A_total ~ n * A_single     (CAPEX rises ~n)
%   So adding effects cuts steam OPEX but raises evaporator CAPEX. Both are
%   returned, and the LFP flowsheet now gets a real evaporator CAPEX row to
%   match the steam OPEX (fixes "OPEX for a unit that doesn't exist").
%
%   See also BALL_MILL_POWER, LEACH_KINETICS_SCM, RUN_SIZING.

    if nargin < 3, params = struct(); end
    params = apply_defaults(params, default_params());
    if nargin < 4 || isempty(batch_hours), batch_hours = 1.0; end

    % -------- 1. Feed water mass per batch ------------------------------
    m_feed_kg_per_batch = throughput_ton_per_batch * params.water_per_t_feed_kg;

    % -------- 2. Heat duty ----------------------------------------------
    Q_sens_kJ = m_feed_kg_per_batch * params.Cp_kJ_per_kgK ...
              * (params.T_boil_C - params.T_feed_C);
    m_evap_kg = m_feed_kg_per_batch * params.evaporation_target_frac;
    Q_latent_kJ = m_evap_kg * params.deltaH_vap_kJ_per_kg;
    Q_total_kJ = Q_sens_kJ + Q_latent_kJ;
    Q_after_effects_kJ = Q_total_kJ / max(params.effects, 1);

    % -------- 3. Steam mass (OPEX side, falls with effects) -------------
    m_steam_per_batch_kg = Q_after_effects_kJ ...
                         / (params.deltaH_vap_kJ_per_kg * params.boiler_efficiency);

    % -------- 4. Per-ton-feed-per-YEAR normalisation --------------------
    if throughput_ton_per_batch <= 0
        steam_kg_per_t = 0;
    else
        steam_kg_per_t = m_steam_per_batch_kg / throughput_ton_per_batch;
    end
    steam_kg_per_t_per_y = steam_kg_per_t * batches_per_year;
    steam_usd_per_t_per_y = steam_kg_per_t_per_y / 1000.0 * params.lps_price_usd_per_ton;

    % -------- 5. Heat-transfer area + CAPEX (rises with effects) --------
    batch_s = max(batch_hours, 1e-9) * 3600.0;
    Q_rate_W = (Q_total_kJ * 1000.0) / batch_s;
    A_single_m2 = Q_rate_W / (params.U_W_per_m2K * params.deltaT_total_K);
    A_total_m2 = A_single_m2 * max(params.effects, 1);
    base_cost_usd = params.area_cost_usd_per_m2 * A_total_m2;

    % -------- 6. Pack output (field order matches Python) ---------------
    out = struct();
    out.feed_water_kg_per_batch         = m_feed_kg_per_batch;
    out.evaporation_target_fraction     = params.evaporation_target_frac;
    out.effects                         = params.effects;
    out.Q_evap_MJ_per_batch             = Q_total_kJ / 1000.0;
    out.lps_steam_kg_per_batch          = m_steam_per_batch_kg;
    out.lps_steam_kg_per_t_feed_per_y   = steam_kg_per_t_per_y;
    out.lps_steam_usd_per_t_feed_per_y  = steam_usd_per_t_per_y;
    out.lps_price_usd_per_ton           = params.lps_price_usd_per_ton;
    out.heat_transfer_area_m2           = A_total_m2;
    out.single_effect_area_m2           = A_single_m2;
    out.U_W_per_m2K                     = params.U_W_per_m2K;
    out.deltaT_total_K                  = params.deltaT_total_K;
    out.area_cost_usd_per_m2            = params.area_cost_usd_per_m2;
    out.base_cost_usd                   = base_cost_usd;
    out.boiler_feed_T_C                 = params.T_feed_C;
    out.boil_T_C                        = params.T_boil_C;
    out.specific_heat_water_kJ_per_kg_K = params.Cp_kJ_per_kgK;
    out.latent_heat_vap_kJ_per_kg       = params.deltaH_vap_kJ_per_kg;
end


% ====================== local helpers ======================================

function p = default_params()
    p = struct( ...
        'water_per_t_feed_kg',     5000, ...
        'evaporation_target_frac', 0.85, ...
        'effects',                 1, ...
        'Cp_kJ_per_kgK',           4.186, ...
        'deltaH_vap_kJ_per_kg',    2260, ...
        'T_feed_C',                25, ...
        'T_boil_C',                100, ...
        'lps_price_usd_per_ton',   25, ...
        'boiler_efficiency',       0.92, ...
        'U_W_per_m2K',             1500, ...
        'deltaT_total_K',          30, ...
        'area_cost_usd_per_m2',    4000 );
end

function s = apply_defaults(s, def)
    fn = fieldnames(def);
    for i = 1:numel(fn)
        if ~isfield(s, fn{i}), s.(fn{i}) = def.(fn{i}); end
    end
end
