%% Test tree selection, navigation, and data extraction (automated)
% No GUI or user interaction needed.
% Tests building trees, navigating, selecting, and extracting real H5 data.

close all; clear; clc;

fprintf('=== Test Selection and Navigation (Automated) ===\n\n');

% Setup paths
baseDir = fileparts(mfilename('fullpath'));
projectDir = fileparts(baseDir);
addpath(fullfile(projectDir, 'src'));
addpath(fullfile(projectDir, 'src', 'tree'));

% Configure H5 directory
h5Dir = '/Users/maxwellsdm/Documents/epicTreeTest/h5';
epicTreeConfig('h5_dir', h5Dir);
fprintf('H5 directory: %s\n', h5Dir);

% Load data
dataFile = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';
[data, ~] = loadEpicTreeData(dataFile);

% Build tree: Cell Type -> Protocol
tree = epicTreeTools(data, 'LoadUserMetadata', 'none');
tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType, @epicTreeTools.splitOnProtocol});

assert(tree.childrenLength() > 0, 'Tree should have children');
assert(tree.epochCount() == 1915, sprintf('Expected 1915 epochs, got %d', tree.epochCount()));
fprintf('\n--- Test 1: Build tree ---\n');
fprintf('  Root: %d children, %d epochs [PASS]\n', tree.childrenLength(), tree.epochCount());

% Navigate down - enumerate all cell types and protocols
fprintf('\n--- Test 2: Navigate hierarchy ---\n');
for i = 1:tree.childrenLength()
    cellNode = tree.childAt(i);
    assert(~isempty(cellNode.splitValue), 'Cell type should not be empty');
    fprintf('  %s (%d epochs, %d protocols)\n', ...
        string(cellNode.splitValue), cellNode.epochCount(), cellNode.childrenLength());
    for j = 1:cellNode.childrenLength()
        protNode = cellNode.childAt(j);
        assert(~isempty(protNode.splitValue), 'Protocol should not be empty');
        assert(strcmp(string(protNode.parent.splitValue), string(cellNode.splitValue)), ...
            'Parent mismatch');
        fprintf('    %s: %d epochs\n', string(protNode.splitValue), protNode.epochCount());
    end
end
fprintf('  [PASS]\n');

% Find SingleSpot by split value
fprintf('\n--- Test 3: childBySplitValue ---\n');
firstCell = tree.childAt(1);
ssNode = firstCell.childBySplitValue('SingleSpot');
assert(~isempty(ssNode), 'Should find SingleSpot');
fprintf('  Found SingleSpot: %d epochs [PASS]\n', ssNode.epochCount());

% Selection: deselect and re-select
fprintf('\n--- Test 4: Selection management ---\n');
allCount = tree.epochCount();
selBefore = length(tree.getAllEpochs(true));
assert(selBefore == allCount, 'All should start selected');

ssNode.setSelected(false, true);
selAfter = length(tree.getAllEpochs(true));
assert(selAfter == allCount - ssNode.epochCount(), 'Deselect mismatch');
fprintf('  Deselected SingleSpot: %d -> %d selected\n', selBefore, selAfter);

ssNode.setSelected(true, true);
selFinal = length(tree.getAllEpochs(true));
assert(selFinal == allCount, 'Re-select failed');
fprintf('  Re-selected: %d/%d [PASS]\n', selFinal, allCount);

% Extract waveform data from SingleSpot
fprintf('\n--- Test 5: Extract SingleSpot waveforms ---\n');
[respData, epochs, fs] = epicTreeTools.getSelectedData(ssNode, 'Amp1');
assert(~isempty(respData), 'Should get response data');
assert(fs == 10000, sprintf('Expected fs=10000, got %g', fs));
assert(size(respData,1) == ssNode.epochCount(), 'Trace count mismatch');
fprintf('  %d traces x %d samples, fs=%g Hz, peak=%.1f pA [PASS]\n', ...
    size(respData,1), size(respData,2), fs, max(abs(respData(:))));

% Extract from every leaf node
fprintf('\n--- Test 6: Extract from all leaves ---\n');
leaves = tree.leafNodes();
nExtracted = 0;
totalTraces = 0;
for i = 1:length(leaves)
    leaf = leaves{i};
    [leafData, ~, ~] = epicTreeTools.getSelectedData(leaf, 'Amp1');
    if ~isempty(leafData)
        nExtracted = nExtracted + 1;
        totalTraces = totalTraces + size(leafData, 1);
        assert(size(leafData,1) == leaf.epochCount(), ...
            sprintf('Leaf %d: trace count mismatch', i));
        assert(any(leafData(:) ~= 0), sprintf('Leaf %d: all zeros', i));

        node = leaf;
        path = char(string(leaf.splitValue));
        while ~isempty(node.parent) && ~isempty(node.parent.splitValue)
            node = node.parent;
            path = [char(string(node.splitValue)), ' / ', path];
        end
        fprintf('  %s: %d x %d [OK]\n', path, size(leafData,1), size(leafData,2));
    end
end
assert(totalTraces == 1915, sprintf('Expected 1915 total traces, got %d', totalTraces));
fprintf('  %d/%d leaves, %d traces [PASS]\n', nExtracted, length(leaves), totalTraces);

% Rebuild tree with different splitters and extract again
fprintf('\n--- Test 7: Rebuild + re-extract ---\n');
tree.buildTreeWithSplitters({'cellInfo.label', 'parameters.stimTime'});
assert(tree.epochCount() == 1915, 'Epoch count changed after rebuild');

leaves2 = tree.leafNodes();
for i = 1:length(leaves2)
    leaf = leaves2{i};
    % Just extract first 2 epochs per leaf for speed
    epList = leaf.getAllEpochs(false);
    testEps = epList(1:min(2, length(epList)));
    [d, ~] = epicTreeTools.getResponseMatrix(testEps, 'Amp1');
    assert(~isempty(d), sprintf('Leaf %d: no data after rebuild', i));

    node = leaf;
    path = char(string(leaf.splitValue));
    while ~isempty(node.parent) && ~isempty(node.parent.splitValue)
        node = node.parent;
        path = [char(string(node.splitValue)), ' / ', path];
    end
    fprintf('  %s: %d x %d [OK]\n', path, size(d,1), size(d,2));
end
fprintf('  [PASS]\n');

% Navigate up from deepest leaf
fprintf('\n--- Test 8: Navigate up to root ---\n');
tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType, 'blockInfo.protocol_name', 'parameters.numberOfAverages'});
leaves3 = tree.leafNodes();
deepLeaf = leaves3{1};

depth = 0;
node = deepLeaf;
pathParts = {char(string(deepLeaf.splitValue))};
while ~isempty(node.parent)
    node = node.parent;
    depth = depth + 1;
    if ~isempty(node.splitValue)
        pathParts = [{char(string(node.splitValue))}, pathParts]; %#ok<AGROW>
    end
end
assert(depth == 3, sprintf('Expected depth 3, got %d', depth));
assert(isempty(node.parent), 'Should reach root');
assert(node.epochCount() == 1915, 'Root should have all epochs');
fprintf('  %s\n', strjoin(pathParts, ' -> '));
fprintf('  Depth: %d [PASS]\n', depth);

fprintf('\n========================================\n');
fprintf('  ALL 8 TESTS PASSED\n');
fprintf('========================================\n');
