function out = leach_kinetics_scm(throughput_ton_per_batch, target_recovery, params)
%LEACH_KINETICS_SCM  Leach-tank residence time + volume + self-consistent cost.
%   Canonical MATLAB model — mirrored 1:1 by tea_engine/physics/leach_kinetics.py.
%
%   out = leach_kinetics_scm(throughput_ton_per_batch, target_recovery, params)
%
%   Kinetic models:
%     first_order  dX/dt = k(1-X)  -> CLOSED FORM  t = -ln(1-X)/k
%                  (no solver: an ODE integrator would only re-derive the
%                   exact exponential. This is the LFP default.)
%     scm_ash      ash-layer shrinking core (nonlinear) -> ode45.
%
%   Cost self-consistency (the key fix)
%   -----------------------------------
%   Cost is referenced to the volume required at a REFERENCE recovery
%   (reference_recovery, default 0.90), at the same throughput:
%       base_cost = cost_ref_usd * (V(target)/V(reference_recovery))^0.6
%   So at the default recovery the override == the original $340k quote
%   exactly (no spurious inflation). It deviates only when the recovery
%   TARGET differs (e.g. 0.90 -> 0.98 needs a bigger tank). The previous
%   arbitrary V_ref=1.15 m^3 (which inflated cost 2.6x) is removed.
%
%   See also BALL_MILL_POWER, EVAPORATOR_ENTHALPY, RUN_SIZING.

    if nargin < 3, params = struct(); end
    params = apply_defaults(params, default_params());

    % Residence time + volume at TARGET recovery
    [t_target, k_eff] = residence_time(target_recovery, params);
    V_target = leach_volume(throughput_ton_per_batch, t_target, params);

    % Residence time + volume at REFERENCE recovery (same throughput)
    [t_ref, ~] = residence_time(params.reference_recovery, params);
    V_ref = leach_volume(throughput_ton_per_batch, t_ref, params);

    % Self-consistent cost
    if V_ref > 0
        base_cost = params.cost_ref_usd * (V_target / V_ref) ^ params.cost_scaling;
    else
        base_cost = params.cost_ref_usd;
    end

    out = struct();
    out.target_recovery       = target_recovery;
    out.reference_recovery    = params.reference_recovery;
    out.kinetic_model         = params.model;
    out.rate_constant         = k_eff;
    out.residence_time_h      = t_target;
    out.residence_time_ref_h  = t_ref;
    out.reactor_volume_m3     = V_target;
    out.reactor_volume_ref_m3 = V_ref;
    out.safety_factor         = params.safety_factor;
    out.base_cost_usd         = base_cost;
    out.base_cost_usd_orig    = params.cost_ref_usd;
    out.cost_scaling_factor   = params.cost_scaling;
end


% ====================== local helpers ======================================

function [t_h, k_eff] = residence_time(X_target, p)
    switch lower(p.model)
        case 'first_order'
            X = min(max(X_target, 0.0), 1 - 1e-12);
            t_h = -log(1 - X) / p.k_per_h;
            k_eff = p.k_per_h;
        case 'scm_ash'
            [t_h, k_eff] = scm_time(X_target, p);
        otherwise
            error('Unknown kinetic model "%s". Use first_order or scm_ash.', p.model);
    end
end

function [t_h, k_eff] = scm_time(X_target, p)
    R = p.R0_um * 1e-6;
    tau_s = (p.rho_B_mol_per_m3 * R^2) ...
          / (6 * p.b_stoich * p.D_e_m2_per_s * p.C_A_mol_per_m3);
    tau_h = tau_s / 3600.0;
    k_eff = 1.0 / tau_h;

    odefun = @(t, X) (1.0 / tau_h) / max((1 - min(max(X,1e-9),1-1e-9))^(-1/3) - 1, 1e-9);
    opts = odeset('Events', @(t, X) hit_target(t, X, X_target), ...
                  'RelTol', 1e-7, 'AbsTol', 1e-9);
    sol = ode45(odefun, [0, 1000*tau_h], 1e-4, opts);
    if ~isempty(sol.xe)
        t_h = sol.xe(end);
    else
        Xt = X_target;
        t_h = tau_h * (1 - 3*(1-Xt)^(2/3) + 2*(1-Xt));
    end
end

function V = leach_volume(throughput_ton_per_batch, t_h, p)
    slurry_mass_t = throughput_ton_per_batch / p.solids_mass_frac;
    slurry_m3_per_batch = slurry_mass_t * 1000.0 / p.slurry_density;
    F_vol_m3_per_h = slurry_m3_per_batch / p.batch_hours;
    V = F_vol_m3_per_h * t_h * p.safety_factor;
end

function [value, isterminal, direction] = hit_target(~, X, Xt)
    value = X - Xt; isterminal = 1; direction = 1;
end

function p = default_params()
    p = struct( ...
        'model',              'first_order', ...
        'k_per_h',            2.30, ...
        'reference_recovery', 0.90, ...
        'R0_um',              30, ...
        'rho_B_mol_per_m3',   22800, ...
        'b_stoich',           1.0, ...
        'D_e_m2_per_s',       1.0e-9, ...
        'C_A_mol_per_m3',     7000, ...
        'slurry_density',     1300, ...
        'solids_mass_frac',   0.20, ...
        'safety_factor',      1.50, ...
        'batch_hours',        1.0, ...
        'cost_ref_usd',       340000, ...
        'cost_scaling',       0.60 );
end

function s = apply_defaults(s, def)
    fn = fieldnames(def);
    for i = 1:numel(fn)
        if ~isfield(s, fn{i}), s.(fn{i}) = def.(fn{i}); end
    end
end
