% Verify selection filtering works correctly
[data, ~] = loadEpicTreeData('/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat');
tree = epicTreeTools(data);
tree.buildTree({'cellInfo.type'});

% Verify source_file was captured
assert(~isempty(tree.sourceFile), 'sourceFile should be set from loadEpicTreeData');
assert(contains(tree.sourceFile, '2025-12-02_F.mat'), 'sourceFile should contain the filename');

% Get a leaf node
leaves = tree.leafNodes();
leaf = leaves{1};

% Count total
totalBefore = leaf.epochCount();

% Deselect using setSelected (correct method)
leaf.setSelected(false, true);

% Verify getAllEpochs(true) returns 0
selectedAfter = leaf.getAllEpochs(true);
assert(isempty(selectedAfter), 'getAllEpochs(true) should return empty after deselecting all');

% Re-select
leaf.setSelected(true, true);
selectedAll = leaf.getAllEpochs(true);
assert(length(selectedAll) == totalBefore, 'getAllEpochs(true) should return all after re-selecting');

% Verify sourceFile property exists
assert(isprop(tree, 'sourceFile'), 'sourceFile property should exist');

disp('Task 1 verification PASSED');
