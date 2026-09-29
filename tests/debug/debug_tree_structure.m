%% Debug Tree Structure
% Check what cell types are actually in the data

% Scientific recordings are local-only and never bundled.
if ~isfile(getenv('RIEKE_TEST_MAT'))
    warning('epicTreeGUI:SkippedLocalFixture', ...
        'Skipped: set RIEKE_TEST_MAT to a local recording export.');
    return;
end

clear; clc;
addpath('src');
addpath('src/tree');

fprintf('=== Debugging Tree Structure ===\n\n');

data_file = getenv('RIEKE_TEST_MAT');

% Load data
[data, ~] = loadEpicTreeData(data_file);

% Create tree
tree = epicTreeTools(data);
fprintf('Total epochs: %d\n\n', length(tree.allEpochs));

% Check what cell types exist in the data
fprintf('Checking cell type values in epochs:\n');
cellTypes = {};
for i = 1:min(10, length(tree.allEpochs))
    epoch = tree.allEpochs{i};

    % Check cellInfo.type
    if isfield(epoch, 'cellInfo') && isfield(epoch.cellInfo, 'type')
        ct = epoch.cellInfo.type;
        fprintf('  Epoch %d: cellInfo.type = "%s"\n', i, ct);
        cellTypes{end+1} = ct;
    else
        fprintf('  Epoch %d: NO cellInfo.type field\n', i);
    end
end

% Show unique cell types
if ~isempty(cellTypes)
    uniqueTypes = unique(cellTypes);
    fprintf('\nUnique cell types found: ');
    fprintf('%s, ', uniqueTypes{:});
    fprintf('\n\n');
end

% Build tree with cell type split
fprintf('Building tree with cellInfo.type split...\n');
tree.buildTree({'cellInfo.type'});

fprintf('Top-level children: %d\n', tree.childrenLength());
for i = 1:tree.childrenLength()
    child = tree.childAt(i);
    fprintf('  Child %d: splitValue="%s", epochs=%d\n', ...
        i, string(child.splitValue), child.epochCount());
end

fprintf('\n=== Tree Analysis ===\n');
fprintf('If you see only 1 cell type (e.g., "RGC"), the data may have:\n');
fprintf('1. All epochs from the same cell type, OR\n');
fprintf('2. Cell type stored in a different field\n\n');

% Check alternative fields
fprintf('Checking first epoch for alternative cell type fields:\n');
if ~isempty(tree.allEpochs)
    ep = tree.allEpochs{1};
    fprintf('  Available fields: ');
    fprintf('%s, ', fieldnames(ep){:});
    fprintf('\n\n');

    if isfield(ep, 'cellInfo')
        fprintf('  cellInfo fields: ');
        fprintf('%s, ', fieldnames(ep.cellInfo){:});
        fprintf('\n');
    end
end
