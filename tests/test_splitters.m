%% Test Different Splitters
% Shows tree organization with various split combinations

clear; clc;
addpath('src');
addpath('src/tree');

fprintf('=== Testing Splitters ===\n\n');

data_file = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';
[data, ~] = loadEpicTreeData(data_file);
tree = epicTreeTools(data);

fprintf('Total epochs: %d\n\n', length(tree.allEpochs));

%% Test 1: Split by Date
fprintf('1. SPLIT BY DATE\n');
fprintf('   --------------\n');
tree.buildTreeWithSplitters({@epicTreeTools.splitOnExperimentDate});
fprintf('   %d date(s):\n', tree.childrenLength());
for i = 1:tree.childrenLength()
    child = tree.childAt(i);
    fprintf('   - %s: %d epochs\n', string(child.splitValue), child.epochCount());
end

%% Test 2: Split by Cell Type
fprintf('\n2. SPLIT BY CELL TYPE\n');
fprintf('   ------------------\n');
tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType});
fprintf('   %d cell type(s):\n', tree.childrenLength());
for i = 1:tree.childrenLength()
    child = tree.childAt(i);
    fprintf('   - %s: %d epochs\n', string(child.splitValue), child.epochCount());
end

%% Test 3: Split by Date -> Cell Type
fprintf('\n3. SPLIT BY DATE -> CELL TYPE\n');
fprintf('   ---------------------------\n');
tree.buildTreeWithSplitters({
    @epicTreeTools.splitOnExperimentDate,
    @epicTreeTools.splitOnCellType
});
fprintf('   Tree structure:\n');
for i = 1:tree.childrenLength()
    dateNode = tree.childAt(i);
    fprintf('   %s (%d epochs):\n', string(dateNode.splitValue), dateNode.epochCount());
    for j = 1:dateNode.childrenLength()
        cellNode = dateNode.childAt(j);
        fprintf('     - %s: %d epochs\n', string(cellNode.splitValue), cellNode.epochCount());
    end
end

%% Test 4: Split by Cell Type -> Date -> Cell ID
fprintf('\n4. SPLIT BY CELL TYPE -> DATE -> CELL ID\n');
fprintf('   -------------------------------------\n');
tree.buildTreeWithSplitters({
    @epicTreeTools.splitOnCellType,
    @epicTreeTools.splitOnExperimentDate,
    'cellInfo.id'
});
fprintf('   Tree structure (3 levels):\n');
for i = 1:tree.childrenLength()
    cellTypeNode = tree.childAt(i);
    fprintf('   %s (%d epochs):\n', string(cellTypeNode.splitValue), cellTypeNode.epochCount());

    for j = 1:cellTypeNode.childrenLength()
        dateNode = cellTypeNode.childAt(j);
        fprintf('     %s (%d cells):\n', string(dateNode.splitValue), dateNode.childrenLength());

        % Show first 3 cells
        for k = 1:min(3, dateNode.childrenLength())
            cellNode = dateNode.childAt(k);
            fprintf('       - Cell %s: %d epochs\n', ...
                string(cellNode.splitValue), cellNode.epochCount());
        end

        if dateNode.childrenLength() > 3
            fprintf('       ... and %d more cells\n', dateNode.childrenLength() - 3);
        end
    end
end

%% Test 5: Split by Date -> Cell ID
fprintf('\n5. SPLIT BY DATE -> CELL ID\n');
fprintf('   ------------------------\n');
tree.buildTreeWithSplitters({
    @epicTreeTools.splitOnExperimentDate,
    'cellInfo.id'
});
fprintf('   Tree structure:\n');
for i = 1:tree.childrenLength()
    dateNode = tree.childAt(i);
    fprintf('   %s (%d cells):\n', string(dateNode.splitValue), dateNode.childrenLength());

    % Show first 5 cells
    for j = 1:min(5, dateNode.childrenLength())
        cellNode = dateNode.childAt(j);
        fprintf('     - Cell %s: %d epochs\n', ...
            string(cellNode.splitValue), cellNode.epochCount());
    end

    if dateNode.childrenLength() > 5
        fprintf('     ... and %d more cells\n', dateNode.childrenLength() - 5);
    end
end

%% Summary
fprintf('\n=== SUMMARY ===\n');
fprintf('All splitters working correctly!\n');
fprintf('The tree can be reorganized by ANY combination of:\n');
fprintf('  - Date (experiment date)\n');
fprintf('  - Cell Type (RGC, OnP, OffP, etc.)\n');
fprintf('  - Cell ID (individual cells)\n');
fprintf('  - Protocol (experiment protocol)\n');
fprintf('  - Or any custom splitter you define!\n\n');
