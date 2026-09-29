%% Test DataJoint Export .mat File
% Verifies that a .mat file exported from the DataJoint web app
% works correctly with epicTreeGUI: loading, tree building, navigation,
% selection, and waveform extraction.
%
% This test uses ONLY the exported .mat file — no original analysis files.
% The H5 directory is derived from the h5_file field inside the export.

close all; clear; clc;

fprintf('=== Test DataJoint Export .mat File ===\n\n');

% Setup paths
baseDir = fileparts(mfilename('fullpath'));
projectDir = fileparts(baseDir);
addpath(fullfile(projectDir, 'src'));
addpath(fullfile(projectDir, 'src', 'tree'));

% --- ONLY INPUT: the exported .mat file ---
exportFile = '/Users/maxwellsdm/Downloads/epictree_export_20260216_100041.mat';
fprintf('Export file: %s\n', exportFile);

% Load data
[data, meta] = loadEpicTreeData(exportFile);

% Configure H5 directory from the export's own h5_file field
tree = epicTreeTools(data, 'LoadUserMetadata', 'none');
tree.buildTree({'cellInfo.type'});
allEps = tree.getAllEpochs(false);
h5File = allEps{1}.responses{1}.h5_file;
h5Dir = fileparts(h5File);
epicTreeConfig('h5_dir', h5Dir);
fprintf('H5 directory (from export): %s\n\n', h5Dir);

% --- Test 1: Build tree ---
fprintf('--- Test 1: Build tree ---\n');
tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType, @epicTreeTools.splitOnProtocol});
assert(tree.childrenLength() > 0, 'Tree should have children');
assert(tree.epochCount() == 1915, sprintf('Expected 1915 epochs, got %d', tree.epochCount()));
fprintf('  Root: %d children, %d epochs [PASS]\n', tree.childrenLength(), tree.epochCount());

% --- Test 2: Navigate hierarchy ---
fprintf('\n--- Test 2: Navigate hierarchy ---\n');
for i = 1:tree.childrenLength()
    cellNode = tree.childAt(i);
    assert(~isempty(cellNode.splitValue), 'Cell type should not be empty');
    fprintf('  %s (%d epochs, %d protocols)\n', ...
        string(cellNode.splitValue), cellNode.epochCount(), cellNode.childrenLength());
    for j = 1:cellNode.childrenLength()
        protNode = cellNode.childAt(j);
        assert(~isempty(protNode.splitValue), 'Protocol should not be empty');
        fprintf('    %s: %d epochs\n', string(protNode.splitValue), protNode.epochCount());
    end
end
fprintf('  [PASS]\n');

% --- Test 3: childBySplitValue with short names ---
fprintf('\n--- Test 3: childBySplitValue (substring match) ---\n');
firstCell = tree.childAt(1);
ssNode = firstCell.childBySplitValue('SingleSpot');
assert(~isempty(ssNode), 'Should find SingleSpot by short name');
fprintf('  childBySplitValue(''SingleSpot'') -> %s (%d epochs) [PASS]\n', ...
    string(ssNode.splitValue), ssNode.epochCount());

vmnNode = firstCell.childBySplitValue('VariableMeanNoise');
assert(~isempty(vmnNode), 'Should find VariableMeanNoise by short name');
fprintf('  childBySplitValue(''VariableMeanNoise'') -> %s (%d epochs) [PASS]\n', ...
    string(vmnNode.splitValue), vmnNode.epochCount());

% --- Test 4: Selection management ---
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

% --- Test 5: Extract waveforms from SingleSpot ---
fprintf('\n--- Test 5: Extract SingleSpot waveforms ---\n');
[ssData, ssEpochs, ssFs] = epicTreeTools.getSelectedData(ssNode, 'Amp1');
assert(~isempty(ssData), 'Should get response data');
assert(ssFs == 10000, sprintf('Expected fs=10000, got %g', ssFs));
assert(size(ssData,1) == ssNode.epochCount(), 'Trace count mismatch');
fprintf('  %d traces x %d samples, fs=%g Hz [PASS]\n', ...
    size(ssData,1), size(ssData,2), ssFs);

% --- Test 6: Extract from all leaves ---
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
    end
end
assert(totalTraces == 1915, sprintf('Expected 1915 total traces, got %d', totalTraces));
fprintf('  %d/%d leaves, %d traces [PASS]\n', nExtracted, length(leaves), totalTraces);

% --- Test 7: Rebuild with different splitters ---
fprintf('\n--- Test 7: Rebuild + verify ---\n');
tree.buildTreeWithSplitters({'cellInfo.label', 'parameters.stimTime'});
assert(tree.epochCount() == 1915, 'Epoch count changed after rebuild');
fprintf('  Rebuild OK: %d epochs [PASS]\n', tree.epochCount());

% --- Test 8: Navigate up to root ---
fprintf('\n--- Test 8: Navigate up to root ---\n');
tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType, 'blockInfo.protocol_name', 'parameters.numberOfAverages'});
leaves3 = tree.leafNodes();
deepLeaf = leaves3{1};
depth = 0;
node = deepLeaf;
while ~isempty(node.parent)
    node = node.parent;
    depth = depth + 1;
end
assert(depth == 3, sprintf('Expected depth 3, got %d', depth));
assert(isempty(node.parent), 'Should reach root');
assert(node.epochCount() == 1915, 'Root should have all epochs');
fprintf('  Depth: %d, root epochs: %d [PASS]\n', depth, node.epochCount());

% --- Plot: visual verification ---
fprintf('\n--- Plotting waveforms from export ---\n');
tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType, @epicTreeTools.splitOnProtocol});
firstCell = tree.childAt(1);
ssNode = firstCell.childBySplitValue('SingleSpot');
vmnNode = firstCell.childBySplitValue('VariableMeanNoise');

[ssData, ~, ssFs] = epicTreeTools.getSelectedData(ssNode, 'Amp1');
[vmnData, ~, vmnFs] = epicTreeTools.getSelectedData(vmnNode, 'Amp1');

fig = figure('Position', [100 100 1000 400]);
subplot(1,2,1);
t_ss = (1:size(ssData,2)) / ssFs * 1000;
plot(t_ss, ssData(1,:), 'b', 'LineWidth', 1.2); hold on;
if size(ssData,1) > 1
    plot(t_ss, ssData(2,:), 'Color', [0.5 0.5 1], 'LineWidth', 1);
end
xlabel('Time (ms)'); ylabel('Response (pA)');
title('SingleSpot (RGC)'); legend('Epoch 1', 'Epoch 2'); grid on;

subplot(1,2,2);
t_vmn = (1:size(vmnData,2)) / vmnFs * 1000;
plot(t_vmn, vmnData(1,:), 'r', 'LineWidth', 1.2); hold on;
plot(t_vmn, vmnData(2,:), 'Color', [1 0.5 0.5], 'LineWidth', 1);
xlabel('Time (ms)'); ylabel('Response (pA)');
title('VariableMeanNoise (RGC)'); legend('Epoch 1', 'Epoch 2'); grid on;

sgtitle('DataJoint Export \rightarrow epicTreeGUI: Verified Waveforms', 'FontWeight', 'bold');
saveas(fig, fullfile(fileparts(exportFile), 'datajoint_export_test_traces.png'));

fprintf('\n========================================\n');
fprintf('  ALL 8 TESTS PASSED (DataJoint export)\n');
fprintf('  Plot: %s\n', fullfile(fileparts(exportFile), 'datajoint_export_test_traces.png'));
fprintf('========================================\n');
