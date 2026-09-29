caise the%% Test Robust Splits with Your Data
% Organizes by: Cell Type -> Date -> Cell ID

clear; clc;
addpath('src');
addpath('src/tree');

fprintf('=== Testing Robust Splits ===\n\n');

[data, ~] = loadEpicTreeData('/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat');
tree = epicTreeTools(data);

fprintf('Total epochs: %d\n\n', length(tree.allEpochs));

% Check what fields are available in first epoch
if ~isempty(tree.allEpochs)
    fprintf('Checking first epoch structure:\n');
    ep = tree.allEpochs{1};

    fprintf('  cellInfo fields: ');
    if isfield(ep, 'cellInfo')
        fprintf('%s, ', fieldnames(ep.cellInfo){:});
    end
    fprintf('\n');

    fprintf('  expInfo fields: ');
    if isfield(ep, 'expInfo')
        fprintf('%s, ', fieldnames(ep.expInfo){:});
    end
    fprintf('\n');

    fprintf('  parameters fields: ');
    if isfield(ep, 'parameters')
        pfields = fieldnames(ep.parameters);
        if length(pfields) > 10
            fprintf('%s, ', pfields{1:10});
            fprintf('... (%d total)', length(pfields));
        else
            fprintf('%s, ', pfields{:});
        end
    else
        fprintf('(no parameters field)');
    end
    fprintf('\n\n');
end

% Try Cell Type split
fprintf('1. Split by CELL TYPE:\n');
try
    tree.buildTree({'cellInfo.type'});
    fprintf('   ✓ Success! %d cell types:\n', tree.childrenLength());
    for i = 1:tree.childrenLength()
        child = tree.childAt(i);
        fprintf('     - %s: %d epochs\n', string(child.splitValue), child.epochCount());
    end
catch ME
    fprintf('   ✗ Failed: %s\n', ME.message);
end

% Try Cell Type -> Cell ID split
fprintf('\n2. Split by CELL TYPE -> CELL ID:\n');
try
    tree.buildTree({'cellInfo.type', 'cellInfo.id'});
    fprintf('   ✓ Success!\n');
    for i = 1:tree.childrenLength()
        cellTypeNode = tree.childAt(i);
        fprintf('   %s: %d cells\n', string(cellTypeNode.splitValue), ...
            cellTypeNode.childrenLength());
        for j = 1:min(3, cellTypeNode.childrenLength())
            cellIdNode = cellTypeNode.childAt(j);
            fprintf('     - Cell ID %s: %d epochs\n', ...
                string(cellIdNode.splitValue), cellIdNode.epochCount());
        end
        if cellTypeNode.childrenLength() > 3
            fprintf('     ... and %d more cells\n', cellTypeNode.childrenLength() - 3);
        end
    end
catch ME
    fprintf('   ✗ Failed: %s\n', ME.message);
end

% Try Cell Type -> Date -> Cell ID split (3 levels)
fprintf('\n3. Split by CELL TYPE -> DATE -> CELL ID:\n');
try
    tree.buildTreeWithSplitters({
        @epicTreeTools.splitOnCellType,
        @epicTreeTools.splitOnExperimentDate,
        'cellInfo.id'
    });
    fprintf('   ✓ Success! 3-level hierarchy:\n');
    for i = 1:tree.childrenLength()
        cellTypeNode = tree.childAt(i);
        fprintf('   %s:\n', string(cellTypeNode.splitValue));
        for j = 1:cellTypeNode.childrenLength()
            dateNode = cellTypeNode.childAt(j);
            fprintf('     Date %s: %d cells\n', ...
                string(dateNode.splitValue), dateNode.childrenLength());
            for k = 1:min(2, dateNode.childrenLength())
                cellNode = dateNode.childAt(k);
                fprintf('       - Cell %s: %d epochs\n', ...
                    string(cellNode.splitValue), cellNode.epochCount());
            end
        end
    end
catch ME
    fprintf('   ✗ Failed: %s\n', ME.message);
end

fprintf('\n=== Recommendation ===\n');
fprintf('Based on the results above, use one of the successful splits.\n');
fprintf('The tree will show expandable nodes at each level.\n\n');
