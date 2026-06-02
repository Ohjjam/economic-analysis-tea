function verify_against_python(p_matlab, p_python, tol)
%VERIFY_AGAINST_PYTHON  Compare MATLAB sizing output vs the Python mirror.
%   Both must agree within tolerance — the Python mirror is a 1:1
%   reimplementation of the canonical MATLAB scripts.
%
%   verify_against_python()                       % default paths + tol 1%
%   verify_against_python(p_matlab, p_python, tol)
%
%   Defaults:
%     p_matlab = ../data/matlab_sizing_matlab.json   (from run_sizing.m)
%     p_python = ../data/matlab_sizing.json          (from python -m
%                                                      tea_engine.physics.run_sizing)
%
%   Reports the worst relative difference per numeric field; PASS if all
%   numeric fields agree within `tol` (default 0.01 = 1%).

    % `fileparts` is a path function (absent under the broken headless
    % -nojvm launch); restore the toolbox path only when it's missing.
    if isempty(which('fileparts')), restoredefaultpath; end

    here = fileparts(mfilename('fullpath'));
    if nargin < 1 || isempty(p_matlab)
        p_matlab = fullfile(here, '..', 'data', 'matlab_sizing_matlab.json');
    end
    if nargin < 2 || isempty(p_python)
        p_python = fullfile(here, '..', 'data', 'matlab_sizing.json');
    end
    if nargin < 3 || isempty(tol), tol = 0.01; end

    if ~exist(p_matlab, 'file')
        error('MATLAB output not found: %s. Run run_sizing first.', p_matlab);
    end
    if ~exist(p_python, 'file')
        error(['Python output not found: %s. Run ' ...
               '`python -m tea_engine.physics.run_sizing` first.'], p_python);
    end

    A = jsondecode(fileread(p_matlab));
    B = jsondecode(fileread(p_python));

    fprintf('=== MATLAB vs Python physics sizing -- tolerance %.2f%% ===\n', tol*100);
    fprintf('  MATLAB: %s (%s)\n', p_matlab, A.generated_by);
    fprintf('  Python: %s (%s)\n', p_python, B.generated_by);

    % Auto-discover unit blocks: any top-level field that is itself a struct
    % (works for both LFP ball_mill/leach_tank/evaporator and PET
    % electrolyzer/reactor_heat without editing this file).
    topf = fieldnames(A);
    blocks = {};
    for i = 1:numel(topf)
        if isstruct(A.(topf{i})) && isfield(B, topf{i})
            blocks{end+1} = topf{i}; %#ok<AGROW>
        end
    end

    fail = 0; nchecked = 0;
    for block = blocks
        b = block{1};
        fa = fieldnames(A.(b));
        fprintf('\n[%s]\n', b);
        for i = 1:numel(fa)
            f = fa{i};
            if ~isfield(B.(b), f), continue; end
            va = A.(b).(f); vb = B.(b).(f);
            if ~isnumeric(va) || ~isnumeric(vb) || ~isscalar(va) || ~isscalar(vb)
                continue;
            end
            nchecked = nchecked + 1;
            denom = max(abs(va), 1e-12);
            rel = abs(va - vb) / denom;
            status = '   OK';
            if rel > tol, status = '** FAIL'; fail = fail + 1; end
            fprintf('   %-40s  matlab=%-13.5g python=%-13.5g  d=%6.3f%%  %s\n', ...
                    f, va, vb, rel*100, status);
        end
    end
    fprintf('\n%d scalar field(s) checked, %d failed tolerance.\n', nchecked, fail);
    if fail == 0
        fprintf('PASS: MATLAB and Python sizing are numerically equivalent.\n');
    else
        error('verify_against_python: %d field(s) exceeded tolerance.', fail);
    end
end
