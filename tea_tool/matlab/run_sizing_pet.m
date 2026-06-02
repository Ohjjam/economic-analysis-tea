function run_sizing_pet(design_point_ton, output_path)
%RUN_SIZING_PET  PET sizing driver — mirrored by tea_engine/physics/run_sizing_pet.py.
%
%   run_sizing_pet()                          % 1.0 ton -> ../data/matlab_sizing_pet.json
%   run_sizing_pet(design_point_ton)
%   run_sizing_pet(design_point_ton, output_path)
%
%   Calls the two PET physics models (electrolyzer, reactor heat) and writes
%   a single JSON file. Schema v1.0 — see matlab/sizing_schema_pet.json.
%
%   Headless note: identical guard to run_sizing.m — restoredefaultpath only
%   when a core path function is missing (broken-JVM -nojvm launch).

    if isempty(which('fileparts')), restoredefaultpath; end

    if nargin < 1 || isempty(design_point_ton), design_point_ton = 1.0; end
    if nargin < 2 || isempty(output_path)
        here = fileparts(mfilename('fullpath'));
        output_path = fullfile(here, '..', 'data', 'matlab_sizing_pet.json');
    end

    % ---- Process settings (match pet_depolymerization.py TEAInputs) -----
    batch_hours      = 2.0;
    capacity_factor  = 0.80;
    batches_per_year = 365 * 24 * capacity_factor / batch_hours;  % 3504
    h2_kg_per_batch_at_1t = 53.2224;   % reference workbook N15 (kg/2h)

    h2_kg_per_batch = h2_kg_per_batch_at_1t * design_point_ton;

    fprintf('=== run_sizing_pet.m -- PET physics sizing ===\n');
    fprintf('Design point     : %.3f ton PET/batch\n', design_point_ton);
    fprintf('Batches per year : %.0f\n\n', batches_per_year);

    % ---- 1. Electrolyzer (Faraday) -------------------------------------
    elec = electrolyzer_sizing(h2_kg_per_batch, batch_hours, batches_per_year, ...
                               design_point_ton, struct());
    fprintf('[electrolyzer] area=%.2f m^2  CAPEX=$%.0f  %.2f kWh/kg  elec OPEX=$%.0f/(t*y)\n', ...
        elec.required_area_m2, elec.base_cost_usd, ...
        elec.specific_energy_kWh_per_kg_H2, elec.electricity_usd_per_t_feed_per_y);

    % ---- 2. Reactor heat duty ------------------------------------------
    heat = reactor_heat_duty(design_point_ton, batches_per_year, struct());
    fprintf('[reactor heat] Q_net=%.2f GJ/batch  steam OPEX=$%.0f/(t*y)\n\n', ...
        heat.Q_net_GJ_per_batch, heat.heat_usd_per_t_feed_per_y);

    % ---- Pack payload (top-level field order matches Python) -----------
    payload = struct();
    payload.schema_version             = '1.0';
    payload.generated_at               = datestr(now, 'yyyy-mm-ddTHH:MM:SS');
    payload.generated_by               = matlab_version_string();
    payload.process                    = 'pet_depolymerization';
    payload.design_point_ton_per_batch = design_point_ton;
    payload.batch_hours                = batch_hours;
    payload.capacity_factor            = capacity_factor;
    payload.batches_per_year           = batches_per_year;
    payload.electrolyzer               = elec;
    payload.reactor_heat               = heat;

    % ---- Write JSON -----------------------------------------------------
    out_dir = fileparts(output_path);
    if ~isempty(out_dir) && ~exist(out_dir, 'dir'), mkdir(out_dir); end
    try
        json_str = jsonencode(payload, 'PrettyPrint', true);
    catch
        json_str = jsonencode(payload);
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
