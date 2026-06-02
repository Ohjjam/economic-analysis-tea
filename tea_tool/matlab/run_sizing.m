function run_sizing(design_point_ton, output_path, effects)
%RUN_SIZING  Master driver for physics-based unit-operation sizing.
%   Canonical MATLAB driver — mirrored by tea_engine/physics/run_sizing.py.
%
%   run_sizing()                          % 1.0 ton/batch -> ../data/matlab_sizing.json
%   run_sizing(design_point_ton)
%   run_sizing(design_point_ton, output_path)
%   run_sizing(design_point_ton, output_path, effects)
%
%   Calls the three physics models (ball mill, leach kinetics, evaporator)
%   and writes a single JSON file. Schema v1.0 — see matlab/sizing_schema.json.
%
%   Headless note: this install may launch with a minimal path under -nojvm
%   (toolbox path not initialised, so ode45 is missing). We call
%   `restoredefaultpath` ONLY when a core function is unavailable, so a
%   normal interactive MATLAB keeps the user's customised path untouched.

    % ---- ensure toolbox functions (ode45 etc.) are on the path ----------
    if isempty(which('ode45'))
        restoredefaultpath;
    end

    if nargin < 1 || isempty(design_point_ton), design_point_ton = 1.0; end
    if nargin < 2 || isempty(output_path)
        here = fileparts(mfilename('fullpath'));
        output_path = fullfile(here, '..', 'data', 'matlab_sizing.json');
    end
    if nargin < 3 || isempty(effects), effects = 1; end

    % ---- Process settings (match spent_lfp_ballmill_li.py TEAInputs) ----
    batch_hours      = 1.0;
    capacity_factor  = 0.85;
    batches_per_year = 365 * 24 * capacity_factor / batch_hours;  % 7446
    target_recovery  = 0.90;
    scales_ton       = [0.1, 1.0, 5.0];

    fprintf('=== run_sizing.m -- physics-based sizing ===\n');
    fprintf('Design point     : %.3f ton/batch\n', design_point_ton);
    fprintf('Batches per year : %.0f\n', batches_per_year);
    fprintf('Effects          : %d\n', effects);
    fprintf('Output path      : %s\n\n', output_path);

    % ---- 1. Ball mill ---------------------------------------------------
    bm = ball_mill_power(design_point_ton, batch_hours, struct(), ...
                         batches_per_year, scales_ton);
    fprintf('[ball mill ]  motor=%.2f kW  %.1f kWh/t  CAPEX=$%.0f  (Bond %.0f%%)\n', ...
        bm.motor_kW_at_design_point, bm.kWh_per_t_feed, bm.base_cost_usd, ...
        100*bm.bond_fraction_of_total);

    % ---- 2. Leach kinetics ---------------------------------------------
    lk = leach_kinetics_scm(design_point_ton, target_recovery, struct());
    fprintf('[leach     ]  tau=%.2f h  V=%.2f m^3  CAPEX=$%.0f\n', ...
        lk.residence_time_h, lk.reactor_volume_m3, lk.base_cost_usd);

    % ---- 3. Evaporator --------------------------------------------------
    ev = evaporator_enthalpy(design_point_ton, batches_per_year, ...
                             struct('effects', effects), batch_hours);
    fprintf('[evaporator]  area=%.1f m^2  CAPEX=$%.0f  steam OPEX=$%.0f/(t*y)\n\n', ...
        ev.heat_transfer_area_m2, ev.base_cost_usd, ev.lps_steam_usd_per_t_feed_per_y);

    % ---- Pack payload (top-level field order matches Python) -----------
    payload = struct();
    payload.schema_version             = '1.0';
    payload.generated_at               = datestr(now, 'yyyy-mm-ddTHH:MM:SS');
    payload.generated_by               = matlab_version_string();
    payload.process                    = 'spent_lfp_ballmill_li';
    payload.design_point_ton_per_batch = design_point_ton;
    payload.target_recovery            = target_recovery;
    payload.batch_hours                = batch_hours;
    payload.capacity_factor            = capacity_factor;
    payload.batches_per_year           = batches_per_year;
    payload.scales_ton                 = scales_ton;
    payload.ball_mill                  = bm;
    payload.leach_tank                 = lk;
    payload.evaporator                 = ev;

    % ---- Write JSON -----------------------------------------------------
    out_dir = fileparts(output_path);
    if ~isempty(out_dir) && ~exist(out_dir, 'dir'), mkdir(out_dir); end

    try
        json_str = jsonencode(payload, 'PrettyPrint', true);
    catch
        try
            json_str = jsonencode(payload);
        catch
            json_str = naive_jsonencode(payload);
        end
    end

    fid = fopen(output_path, 'w');
    if fid < 0, error('Could not open %s for write', output_path); end
    fprintf(fid, '%s\n', json_str);
    fclose(fid);

    fprintf('Wrote %s\n', output_path);
end


% ====================== local helpers ======================================

function s = matlab_version_string()
    try
        v = ver('MATLAB');
        s = sprintf('matlab_%s', strrep(strrep(v.Release, '(', ''), ')', ''));
    catch
        s = 'matlab';
    end
end

function s = naive_jsonencode(payload)
% Last-resort hand-rolled JSON for very old MATLAB (jsonencode absent).
    s = struct_to_json(payload, 0);
end

function s = struct_to_json(v, depth)
    indent = repmat('  ', 1, depth);
    sep = sprintf(',\n');               % FIX: real newline, not literal '\n'
    if isstruct(v) && numel(v) == 1
        fn = fieldnames(v);
        lines = cell(1, numel(fn));
        for i = 1:numel(fn)
            lines{i} = sprintf('%s"%s": %s', indent, fn{i}, ...
                               struct_to_json(v.(fn{i}), depth+1));
        end
        s = sprintf('{\n%s\n%s}', strjoin(lines, sep), indent);
    elseif isstruct(v)                  % struct array -> JSON array
        items = cell(1, numel(v));
        for i = 1:numel(v)
            items{i} = struct_to_json(v(i), depth+1);
        end
        s = sprintf('[\n%s\n%s]', strjoin(items, sep), indent);
    elseif ischar(v)
        s = sprintf('"%s"', v);
    elseif islogical(v)
        if v, s = 'true'; else, s = 'false'; end
    elseif isnumeric(v) && isscalar(v)
        s = sprintf('%g', v);
    elseif isnumeric(v)                 % numeric vector -> JSON array
        parts = arrayfun(@(x) sprintf('%g', x), v, 'UniformOutput', false);
        s = sprintf('[%s]', strjoin(parts, ', '));
    else
        s = '"<unsupported>"';
    end
end
