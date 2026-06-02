function out = ball_mill_power(throughput_ton_per_batch, batch_hours, params, batches_per_year, scales_ton)
%BALL_MILL_POWER  Physics-based sizing of the mechanochemical ball mill.
%   Canonical MATLAB model — mirrored 1:1 by tea_engine/physics/ball_mill.py.
%
%   out = ball_mill_power(throughput_ton_per_batch, batch_hours, params, ...
%                         batches_per_year, scales_ton)
%
%   Two models in series:
%     1) Bond's third law (INTENSIVE — kWh/t is scale-invariant):
%          W_bond = 10*Wi*(1/sqrt(P80) - 1/sqrt(F80))   [kWh/short ton]
%     2) Hogg-Fuerstenau geometry (READOUT ONLY — no economic effect):
%          P_net = 0.238*K*D^2.5*L*(1-0.937*J)*rho_b*speed_term*phi_c
%
%   What drives ECONOMICS vs what is a READOUT
%   ------------------------------------------
%     kWh_per_t_feed  -> electricity OPEX (Bond intensive + drivetrain credit)
%     motor_kW        -> ball-mill CAPEX via base_cost_usd (cost ~ kW^0.6)
%     cooling water   -> small cooling-water OPEX
%     D/L/V/ball_charge + mechanochem_intensity_factor -> READOUT ONLY.
%
%   HONESTY NOTE: ~88% of kWh/t comes from activation_mult and efficiency,
%   only ~12% from the Bond term. activation_mult is an explicit tunable
%   assumption (no first-principles mechanochem-activation model exists),
%   NOT a derived quantity. It is the dominant sensitivity lever.
%
%   See also LEACH_KINETICS_SCM, EVAPORATOR_ENTHALPY, RUN_SIZING.

    if nargin < 3, params = struct(); end
    params = apply_defaults(params, default_params());
    if nargin < 4 || isempty(batches_per_year)
        if batch_hours > 0
            batches_per_year = 8760 * params.capacity_factor / batch_hours;
        else
            batches_per_year = 8760 * params.capacity_factor;
        end
    end
    if nargin < 5 || isempty(scales_ton)
        scales_ton = [0.1, 1.0, 5.0];
    end

    % -------- 1. Bond energy for comminution (kWh / short ton) -----------
    W_bond_short = 10 * params.Wi * (1/sqrt(params.P80_um) ...
                                   - 1/sqrt(params.F80_um));
    W_bond_metric = W_bond_short / 0.9072;   % short ton -> metric ton

    % -------- 2. Specific energy at design point (drivetrain-adjusted) ---
    throughput_t_per_h = throughput_ton_per_batch / batch_hours;
    kWh_per_t_feed = specific_energy(throughput_t_per_h, W_bond_metric, params);

    % -------- 3. Motor sizing --------------------------------------------
    motor_kW = kWh_per_t_feed * throughput_t_per_h;

    % -------- 4. Ball-mill CAPEX from installed motor power (ECONOMIC) ---
    base_cost_usd = params.mill_capex_coeff * motor_kW ^ params.mill_capex_exp;

    % -------- 5. Mill geometry from H-F (READOUT ONLY) -------------------
    D = bisect_for_diameter(motor_kW, params);
    L = params.L_over_D * D;
    V_mill_m3 = pi/4 * D^2 * L;
    ball_charge_kg = params.J * V_mill_m3 * params.rho_steel;
    if V_mill_m3 > 0
        specific_power_kW_per_m3 = motor_kW / V_mill_m3;
    else
        specific_power_kW_per_m3 = 0;
    end
    n_critical = 42.3 / sqrt(D);
    n_op = params.phi_c * n_critical;

    % -------- 6. Heat balance & cooling water (ECONOMIC, small) ----------
    Q_heat_kW = 0.9 * motor_kW;
    dT_cw = 20.0; Cp_water = 4.186;
    m_cw_kg_per_s = Q_heat_kW / (Cp_water * dT_cw);
    m_cw_kg_per_h = m_cw_kg_per_s * 3600;
    if throughput_t_per_h > 0
        m_cw_kg_per_t = m_cw_kg_per_h / throughput_t_per_h;
    else
        m_cw_kg_per_t = 0;
    end
    water_usd_per_kg = params.water_price_usd_per_ton / 1000.0;
    cw_kg_per_t_feed_per_y = m_cw_kg_per_t * batches_per_year;
    cw_usd_per_t_feed_per_y = cw_kg_per_t_feed_per_y * water_usd_per_kg;

    % -------- 7. Diagnostic: specific energy across scales ---------------
    % Struct array -> jsonencode renders a JSON array of objects, matching
    % the Python list-of-dicts shape exactly. Diagnostic only.
    by_scale = struct('scale_ton', {}, 'kWh_per_t', {});
    for i = 1:numel(scales_ton)
        s = scales_ton(i);
        if batch_hours > 0, tph = s / batch_hours; else, tph = s; end
        by_scale(i).scale_ton = s;
        by_scale(i).kWh_per_t = specific_energy(tph, W_bond_metric, params);
    end

    if kWh_per_t_feed > 0
        bond_frac = W_bond_metric / kWh_per_t_feed;
    else
        bond_frac = 0;
    end

    % -------- 8. Pack output (field order matches Python) ----------------
    out = struct();
    out.kWh_per_t_feed                    = kWh_per_t_feed;
    out.kWh_per_t_feed_by_scale           = by_scale;
    out.specific_energy_is_intensive      = true;
    out.drivetrain_credit_at_design       = drivetrain_credit(throughput_t_per_h, params);
    out.motor_kW_at_design_point          = motor_kW;
    out.base_cost_usd                     = base_cost_usd;
    out.bond_comminution_kWh_per_t        = W_bond_metric;
    out.bond_fraction_of_total            = bond_frac;
    out.mill_diameter_m                   = D;
    out.mill_length_m                     = L;
    out.mill_volume_m3                    = V_mill_m3;
    out.ball_charge_kg                    = ball_charge_kg;
    out.specific_power_kW_per_m3          = specific_power_kW_per_m3;
    out.critical_speed_rpm                = n_critical;
    out.operating_speed_rpm               = n_op;
    out.geometry_is_readout_only          = true;
    out.bond_work_index_kWh_per_t         = params.Wi;
    out.feed_size_F80_um                  = params.F80_um;
    out.product_size_P80_um               = params.P80_um;
    out.activation_multiplier             = params.activation_mult;
    out.mill_efficiency                   = params.mill_eff;
    out.mechanochem_intensity_factor      = params.mechanochem_intensity_factor;
    out.heat_load_kW_at_design_point      = Q_heat_kW;
    out.cooling_water_kg_per_t_feed       = m_cw_kg_per_t;
    out.cooling_water_usd_per_t_feed_per_y = cw_usd_per_t_feed_per_y;
end


% ====================== local helpers ======================================

function E = specific_energy(throughput_t_per_h, W_bond_metric, p)
% kWh per metric tonne: Bond term (intensive) / (mill_eff * drivetrain credit)
    credit = drivetrain_credit(throughput_t_per_h, p);
    effective_eff = p.mill_eff * credit;
    E = W_bond_metric * p.activation_mult / effective_eff;
end

function c = drivetrain_credit(throughput_t_per_h, p)
% NEMA-style motor/gearbox efficiency credit vs reference throughput.
    if throughput_t_per_h <= 0, c = 1.0; return; end
    ratio = throughput_t_per_h / p.drivetrain_ref_t_per_h;
    c = ratio ^ p.drivetrain_exp;
    c = max(p.drivetrain_credit_min, min(p.drivetrain_credit_max, c));
end

function P = hf_power(D, params)
%HF_POWER  Hogg-Fuerstenau net power (kW) — READOUT geometry only.
    L = params.L_over_D * D;
    J = params.J; rho_b = params.rho_steel; phi_c = params.phi_c;
    speed_term = 1 - 0.1 / (2^(9 - 10*phi_c));
    K = 0.238 * params.mechanochem_intensity_factor;
    P = K * D^2.5 * L * (1 - 0.937*J) * rho_b * speed_term * phi_c / 1000.0;
end

function D_root = bisect_for_diameter(P_target, params)
    if P_target <= 0, D_root = 0.1; return; end
    lo = 0.05; hi = 10.0;
    Phi = hf_power(hi, params);
    while Phi < P_target && hi < 50
        hi = hi * 1.5; Phi = hf_power(hi, params);
    end
    for k = 1:80
        mid = 0.5 * (lo + hi);
        if hf_power(mid, params) < P_target, lo = mid; else, hi = mid; end
        if abs(hi - lo) < 1e-5, break; end
    end
    D_root = 0.5 * (lo + hi);
end

function p = default_params()
    p = struct( ...
        'Wi',                    12.0, ...
        'F80_um',                5000, ...
        'P80_um',                75, ...
        'activation_mult',       6.0, ...
        'mill_eff',              0.70, ...
        'J',                     0.32, ...
        'phi_c',                 0.75, ...
        'rho_steel',             4650, ...
        'L_over_D',              1.5, ...
        'Cp_solid_kJ_kgK',       0.85, ...
        'water_price_usd_per_ton', 0.30, ...
        'capacity_factor',       0.85, ...
        'mill_capex_coeff',      121950.0, ...
        'mill_capex_exp',        0.60, ...
        'drivetrain_exp',        0.030, ...
        'drivetrain_ref_t_per_h', 1.0, ...
        'drivetrain_credit_min', 0.85, ...
        'drivetrain_credit_max', 1.18, ...
        'mechanochem_intensity_factor', 50.0 );
end

function s = apply_defaults(s, def)
    fn = fieldnames(def);
    for i = 1:numel(fn)
        if ~isfield(s, fn{i}), s.(fn{i}) = def.(fn{i}); end
    end
end
