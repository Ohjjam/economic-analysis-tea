function out = reactor_heat_duty(feed_ton_per_batch, batches_per_year, params)
%REACTOR_HEAT_DUTY  Net reactor heat duty + steam OPEX for PET depolymerization.
%   Canonical MATLAB model — mirrored 1:1 by tea_engine/physics/reactor_heat.py.
%
%   Q_heating = sum_i m_i*Cp_i*(T_react - T_feed)    [kJ/batch]
%   Q_net     = Q_heating * (1 - heat_recovery_fraction)
%   steam$/t/y = Q_net[GJ] * batches/y * $/GJ / feed_ton
%
%   The bulk heating enthalpy is first-principles (stream masses x Cp x dT).
%   `heat_recovery_fraction` (the fraction offset by integrated cooling around
%   the 100/25/180C thermal cycle) is the ONE calibrated assumption; its
%   default (~0.667) reproduces the reference net duty (16.15 GJ/batch) and
%   steam OPEX ($0.27M/y at 1 ton). It is a design parameter, not a constant.
%
%   See also ELECTROLYZER_SIZING, RUN_SIZING_PET.

    if nargin < 3, params = struct(); end
    params = apply_defaults(params, default_params());

    dT = params.T_react_C - params.T_feed_C;

    % ---- 1. Bulk heating enthalpy (first principles) -------------------
    % solution: Nx2 matrix [mass_kg_per_t_feed, Cp_kJ_per_kgK]
    sol = params.solution;
    sigma_mCp_per_t = sum(sol(:,1) .* sol(:,2));    % kJ/K per ton feed
    Q_heating_kJ = sigma_mCp_per_t * feed_ton_per_batch * dT;
    Q_heating_GJ = Q_heating_kJ / 1e6;

    % ---- 2. Net duty after heat integration ----------------------------
    Q_net_GJ = Q_heating_GJ * (1.0 - params.heat_recovery_fraction);

    % ---- 3. Steam OPEX as $/(ton-feed * y) -----------------------------
    Q_net_GJ_per_y = Q_net_GJ * batches_per_year;
    steam_usd_per_y = Q_net_GJ_per_y * params.steam_price_usd_per_GJ;
    if feed_ton_per_batch > 0
        heat_usd_per_t_feed_per_y = steam_usd_per_y / feed_ton_per_batch;
    else
        heat_usd_per_t_feed_per_y = 0;
    end

    % ---- 4. Pack output (field order matches Python) -------------------
    out = struct();
    out.T_feed_C                  = params.T_feed_C;
    out.T_react_C                 = params.T_react_C;
    out.delta_T_K                 = dT;
    out.sigma_mCp_kJ_per_K_per_t  = sigma_mCp_per_t;
    out.heat_recovery_fraction    = params.heat_recovery_fraction;
    out.Q_heating_GJ_per_batch    = Q_heating_GJ;
    out.Q_net_GJ_per_batch        = Q_net_GJ;
    out.steam_price_usd_per_GJ    = params.steam_price_usd_per_GJ;
    out.heat_usd_per_t_feed_per_y = heat_usd_per_t_feed_per_y;
end


% ====================== local helpers ======================================

function p = default_params()
    % solution rows = [mass_kg_per_t_feed, Cp_kJ_per_kgK] for DMSO/H2O/H2SO4.
    % PMA (recycled solid catalyst) is excluded — matches reference ΣmCp.
    p = struct( ...
        'T_feed_C',               25.0, ...
        'T_react_C',              180.0, ...
        'heat_recovery_fraction', 0.6667, ...
        'steam_price_usd_per_GJ', 4.77, ...
        'solution',               [55000.0, 1.91; 48096.0, 4.18; 4904.0, 1.34] );
end

function s = apply_defaults(s, def)
    fn = fieldnames(def);
    for i = 1:numel(fn)
        if ~isfield(s, fn{i}), s.(fn{i}) = def.(fn{i}); end
    end
end
