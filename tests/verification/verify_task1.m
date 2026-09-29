% Verify selection filtering works correctly
% Scientific recordings are local-only and never bundled.
if ~isfile(getenv('RIEKE_TEST_MAT'))
    warning('epicTreeGUI:SkippedLocalFixture', ...
        'Skipped: set RIEKE_TEST_MAT to a local recording export.');
    return;
end

[data, ~] = loadEpicTreeData(getenv('RIEKE_TEST_MAT'));
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
