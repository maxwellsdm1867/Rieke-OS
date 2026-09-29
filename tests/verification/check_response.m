% Check response fields in exported mat file
% Scientific recordings are local-only and never bundled.
if ~isfile(getenv('RIEKE_TEST_MAT'))
    warning('epicTreeGUI:SkippedLocalFixture', ...
        'Skipped: set RIEKE_TEST_MAT to a local recording export.');
    return;
end

data = load(getenv('RIEKE_TEST_MAT'));
exp = data.experiments{1};
cell1 = exp.cells{1};
eg = cell1.epoch_groups{1};
eb = eg.epoch_blocks{1};
ep = eb.epochs{1};

disp('=== Response Fields ===');
responses = ep.responses;
if iscell(responses)
    r1 = responses{1};
else
    r1 = responses(1);
end

fn = fieldnames(r1);
for i = 1:length(fn)
    val = r1.(fn{i});
    if ischar(val) || isstring(val)
        fprintf('%s: "%s"\n', fn{i}, val);
    elseif isnumeric(val)
        fprintf('%s: size=[%d x %d]\n', fn{i}, size(val,1), size(val,2));
    else
        fprintf('%s: %s\n', fn{i}, class(val));
    end
end

% Check for H5 paths
disp('');
disp('=== H5 Path Check ===');
if isfield(r1, 'h5_file')
    fprintf('h5_file: %s\n', r1.h5_file);
else
    disp('h5_file: NOT PRESENT');
end
if isfield(r1, 'h5_path')
    fprintf('h5_path: %s\n', r1.h5_path);
else
    disp('h5_path: NOT PRESENT');
end
