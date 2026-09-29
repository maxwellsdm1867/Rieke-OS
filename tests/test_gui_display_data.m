%% Test GUI Display and Data Retrieval
% Comprehensive tests for epicTreeGUI display functionality and data retrieval
%
% Tests:
%   Part A: GUI Display Tests
%     1. graphicalTree creation and widget pool
%     2. Node rendering (names, counts, states)
%     3. Expand/collapse functionality
%     4. Selection management
%     5. Checkbox state sync
%     6. Keyboard navigation
%
%   Part B: Data Retrieval Tests
%     7. getSelectedData with tree nodes
%     8. getSelectedData with epoch lists
%     9. getResponseMatrix with embedded data
%    10. H5 lazy loading (real data)
%    11. Selection filtering
%    12. Full workflow: display -> select -> retrieve
%
% Run from epicTreeGUI directory:
%   cd /Users/maxwellsdm/Documents/GitHub/epicTreeGUI
%   run tests/test_gui_display_data.m

clear; clc;
fprintf('\n========================================================\n');
fprintf('  EPICTREEGUI DISPLAY & DATA RETRIEVAL TESTS\n');
fprintf('========================================================\n\n');

%% Setup
baseDir = fileparts(fileparts(mfilename('fullpath')));
if isempty(baseDir)
    baseDir = '/Users/maxwellsdm/Documents/GitHub/epicTreeGUI';
end
addpath(genpath(fullfile(baseDir, 'src')));
fprintf('Base dir: %s\n', baseDir);

% Test results tracking
testResults = struct('passed', 0, 'failed', 0, 'tests', {{}});

%% Create test data (synthetic + setup for real data tests)
fprintf('\n--- SETUP: Creating Test Data ---\n');

% Create synthetic test data
testData = createSyntheticData();
fprintf('Created synthetic data: %d cells, %d epochs\n', 3, 108);

% Configure H5 for real data tests
h5Dir = '/Users/maxwellsdm/Documents/epicTreeTest/h5';
dataPath = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';
hasRealData = exist(dataPath, 'file') && exist(h5Dir, 'dir');
if hasRealData
    epicTreeConfig('h5_dir', h5Dir);
    fprintf('Real data available for H5 tests\n');
else
    fprintf('[SKIP] Real data not available, some tests will be skipped\n');
end

%% ================================================================
%  PART A: GUI DISPLAY TESTS
%  ================================================================
fprintf('\n========================================================\n');
fprintf('  PART A: GUI DISPLAY TESTS\n');
fprintf('========================================================\n');

%% Test A1: graphicalTree Creation and Widget Pool
testName = 'A1. graphicalTree creation and widget pool';
fprintf('\n%s\n', testName);
fprintf('   %s\n', repmat('-', 1, length(testName)));

try
    % Create figure and axes
    testFig = figure('Visible', 'off', 'Name', 'Test GUI');
    testAxes = axes('Parent', testFig);

    % Create graphicalTree
    gTree = graphicalTree(testAxes, 'TestTree');

    % Verify initial state
    assert(~isempty(gTree.trunk), 'Trunk should be created');
    assert(strcmp(gTree.trunk.name, 'TestTree'), 'Trunk should have correct name');
    assert(gTree.trunk.isExpanded, 'Trunk should be expanded');
    assert(length(gTree.widgetList) >= 100, 'Widget pool should be pre-allocated (>=100)');

    % Add some nodes
    node1 = gTree.newNode(gTree.trunk, 'Child1');
    node2 = gTree.newNode(gTree.trunk, 'Child2');
    node3 = gTree.newNode(node1, 'Grandchild1');

    % Verify nodes created
    assert(length(gTree.nodeList) == 4, 'Should have 4 nodes (trunk + 3)');
    assert(node1.depth == 1, 'Child depth should be 1');
    assert(node3.depth == 2, 'Grandchild depth should be 2');

    % Draw tree
    gTree.draw();
    assert(gTree.drawCount > 0, 'drawCount should be > 0 after draw');

    close(testFig);

    testResults.passed = testResults.passed + 1;
    testResults.tests{end+1} = {testName, 'PASS', ''};
    fprintf('   [PASS]\n');
catch ME
    testResults.failed = testResults.failed + 1;
    testResults.tests{end+1} = {testName, 'FAIL', ME.message};
    fprintf('   [FAIL] %s\n', ME.message);
    if exist('testFig', 'var') && ishandle(testFig)
        close(testFig);
    end
end

%% Test A2: Node Rendering (Names, Counts, States)
testName = 'A2. Node rendering (names, counts, states)';
fprintf('\n%s\n', testName);
fprintf('   %s\n', repmat('-', 1, length(testName)));

try
    % Create tree with data
    tree = epicTreeTools(testData);
    tree.buildTree({'cellInfo.type', 'blockInfo.protocol_name'});

    % Verify tree structure
    nChildren = tree.childrenLength();
    assert(nChildren == 3, 'Should have 3 cell types');

    % Check split values
    firstChild = tree.childAt(1);
    assert(~isempty(firstChild.splitValue), 'Child should have split value');

    % Check epoch counts
    totalEpochs = 0;
    for i = 1:tree.childrenLength()
        childNode = tree.childAt(i);
        nodeEpochs = childNode.epochCount();
        assert(nodeEpochs > 0, 'Each child should have epochs');
        totalEpochs = totalEpochs + nodeEpochs;
    end
    assert(totalEpochs == 108, sprintf('Total epochs should be 108, got %d', totalEpochs));

    % Check leaf nodes
    leaves = tree.leafNodes();
    assert(length(leaves) == 9, 'Should have 9 leaf nodes (3 cell types x 3 protocols)');

    % Verify leaf epoch counts
    for i = 1:length(leaves)
        leaf = leaves{i};
        assert(leaf.isLeaf, 'Leaf nodes should be marked as leaves');
        assert(length(leaf.epochList) == 12, 'Each leaf should have 12 epochs');
    end

    testResults.passed = testResults.passed + 1;
    testResults.tests{end+1} = {testName, 'PASS', ''};
    fprintf('   [PASS]\n');
catch ME
    testResults.failed = testResults.failed + 1;
    testResults.tests{end+1} = {testName, 'FAIL', ME.message};
    fprintf('   [FAIL] %s\n', ME.message);
end

%% Test A3: Expand/Collapse Functionality
testName = 'A3. Expand/collapse functionality';
fprintf('\n%s\n', testName);
fprintf('   %s\n', repmat('-', 1, length(testName)));

try
    testFig = figure('Visible', 'off', 'Name', 'Test Expand/Collapse');
    testAxes = axes('Parent', testFig);

    gTree = graphicalTree(testAxes, 'Test');
    node1 = gTree.newNode(gTree.trunk, 'Parent');
    node2 = gTree.newNode(node1, 'Child1');
    node3 = gTree.newNode(node1, 'Child2');

    % Initially, trunk is expanded, node1 is collapsed
    assert(gTree.trunk.isExpanded, 'Trunk should be expanded');
    node1.isExpanded = false;

    % Draw and count visible
    gTree.draw();
    collapsedCount = gTree.drawCount;

    % Expand node1
    node1.isExpanded = true;
    gTree.draw();
    expandedCount = gTree.drawCount;

    assert(expandedCount > collapsedCount, ...
        sprintf('Expanded count (%d) should be > collapsed (%d)', expandedCount, collapsedCount));

    close(testFig);

    testResults.passed = testResults.passed + 1;
    testResults.tests{end+1} = {testName, 'PASS', ''};
    fprintf('   [PASS]\n');
catch ME
    testResults.failed = testResults.failed + 1;
    testResults.tests{end+1} = {testName, 'FAIL', ME.message};
    fprintf('   [FAIL] %s\n', ME.message);
    if exist('testFig', 'var') && ishandle(testFig)
        close(testFig);
    end
end

%% Test A4: Selection Management
testName = 'A4. Selection management';
fprintf('\n%s\n', testName);
fprintf('   %s\n', repmat('-', 1, length(testName)));

try
    testFig = figure('Visible', 'off', 'Name', 'Test Selection');
    testAxes = axes('Parent', testFig);

    gTree = graphicalTree(testAxes, 'Test');
    node1 = gTree.newNode(gTree.trunk, 'Node1');
    node2 = gTree.newNode(gTree.trunk, 'Node2');

    gTree.draw();

    % Initially no selection
    [selNodes, ~] = gTree.getSelectedNodes();
    assert(isempty(selNodes) || all(cellfun(@isempty, selNodes)), ...
        'Initially no nodes should be selected');

    % Select widget 1
    gTree.selectWidget(1, false);
    [selNodes, selKeys] = gTree.getSelectedNodes();
    assert(~isempty(selKeys), 'Should have selection after selectWidget');

    % Select widget 2 with shift (add to selection)
    gTree.selectWidget(2, true);
    [selNodes, selKeys] = gTree.getSelectedNodes();
    assert(length(selKeys) >= 1, 'Should have at least one selection');

    close(testFig);

    testResults.passed = testResults.passed + 1;
    testResults.tests{end+1} = {testName, 'PASS', ''};
    fprintf('   [PASS]\n');
catch ME
    testResults.failed = testResults.failed + 1;
    testResults.tests{end+1} = {testName, 'FAIL', ME.message};
    fprintf('   [FAIL] %s\n', ME.message);
    if exist('testFig', 'var') && ishandle(testFig)
        close(testFig);
    end
end

%% Test A5: Checkbox State Sync (custom.isSelected)
testName = 'A5. Checkbox state sync (custom.isSelected)';
fprintf('\n%s\n', testName);
fprintf('   %s\n', repmat('-', 1, length(testName)));

try
    % Create tree with selection state
    tree = epicTreeTools(testData);
    tree.buildTree({'cellInfo.type'});

    % Initially all selected
    assert(tree.custom.isSelected, 'Root should be selected initially');

    % Deselect first child
    firstChild = tree.childAt(1);
    firstChild.putCustom('isSelected', false);

    % Verify it was stored
    assert(~firstChild.getCustom('isSelected'), 'First child should be deselected');

    % Verify other children still selected
    secondChild = tree.childAt(2);
    assert(secondChild.getCustom('isSelected'), 'Second child should still be selected');

    % Test setSelected method
    tree.setSelected(true, true);  % Select all recursively
    assert(firstChild.getCustom('isSelected'), 'First child should be selected after setSelected');

    testResults.passed = testResults.passed + 1;
    testResults.tests{end+1} = {testName, 'PASS', ''};
    fprintf('   [PASS]\n');
catch ME
    testResults.failed = testResults.failed + 1;
    testResults.tests{end+1} = {testName, 'FAIL', ME.message};
    fprintf('   [FAIL] %s\n', ME.message);
end

%% Test A6: Keyboard Navigation (simulated)
testName = 'A6. Keyboard navigation (simulated)';
fprintf('\n%s\n', testName);
fprintf('   %s\n', repmat('-', 1, length(testName)));

try
    testFig = figure('Visible', 'off', 'Name', 'Test Keyboard');
    testAxes = axes('Parent', testFig);

    gTree = graphicalTree(testAxes, 'Test');
    for i = 1:5
        gTree.newNode(gTree.trunk, sprintf('Node%d', i));
    end
    gTree.draw();

    % Select first widget
    gTree.selectWidget(1, false);

    % Simulate down arrow
    gTree.navigateSelection(1, {});  % direction=1 (down)
    [~, keys1] = gTree.getSelectedNodes();

    % Simulate up arrow
    gTree.navigateSelection(-1, {});  % direction=-1 (up)
    [~, keys2] = gTree.getSelectedNodes();

    % Both should have selections
    assert(~isempty(keys1), 'Should have selection after down');
    assert(~isempty(keys2), 'Should have selection after up');

    close(testFig);

    testResults.passed = testResults.passed + 1;
    testResults.tests{end+1} = {testName, 'PASS', ''};
    fprintf('   [PASS]\n');
catch ME
    testResults.failed = testResults.failed + 1;
    testResults.tests{end+1} = {testName, 'FAIL', ME.message};
    fprintf('   [FAIL] %s\n', ME.message);
    if exist('testFig', 'var') && ishandle(testFig)
        close(testFig);
    end
end

%% ================================================================
%  PART B: DATA RETRIEVAL TESTS
%  ================================================================
fprintf('\n========================================================\n');
fprintf('  PART B: DATA RETRIEVAL TESTS\n');
fprintf('========================================================\n');

%% Test B7: getSelectedData with Tree Nodes
testName = 'B7. getSelectedData with tree nodes';
fprintf('\n%s\n', testName);
fprintf('   %s\n', repmat('-', 1, length(testName)));

try
    tree = epicTreeTools(testData);
    tree.buildTree({'cellInfo.type'});

    % Get data from first child node
    firstChild = tree.childAt(1);
    [dataMatrix, epochs, sampleRate] = epicTreeTools.getSelectedData(firstChild, 'Amp1');

    % Verify output
    assert(~isempty(dataMatrix), 'dataMatrix should not be empty');
    assert(size(dataMatrix, 1) == 36, sprintf('Should have 36 epochs for one cell type, got %d', size(dataMatrix, 1)));
    assert(size(dataMatrix, 2) == 10000, 'Should have 10000 samples');
    assert(sampleRate == 10000, 'Sample rate should be 10000');
    assert(length(epochs) == 36, 'Should return 36 epoch structs');

    % Verify data has actual values (not all zeros)
    assert(any(dataMatrix(:) ~= 0), 'Data should have non-zero values');

    testResults.passed = testResults.passed + 1;
    testResults.tests{end+1} = {testName, 'PASS', ''};
    fprintf('   [PASS]\n');
    fprintf('   Data matrix: [%d x %d], sample rate: %d Hz\n', ...
        size(dataMatrix, 1), size(dataMatrix, 2), sampleRate);
catch ME
    testResults.failed = testResults.failed + 1;
    testResults.tests{end+1} = {testName, 'FAIL', ME.message};
    fprintf('   [FAIL] %s\n', ME.message);
end

%% Test B8: getSelectedData with Epoch Lists
testName = 'B8. getSelectedData with epoch lists';
fprintf('\n%s\n', testName);
fprintf('   %s\n', repmat('-', 1, length(testName)));

try
    tree = epicTreeTools(testData);
    tree.buildTree({'cellInfo.type'});

    % Get epochs directly
    allEpochs = tree.getAllEpochs(false);
    subset = allEpochs(1:10);  % First 10 epochs

    % Pass as cell array directly
    [dataMatrix, epochs, sampleRate] = epicTreeTools.getSelectedData(subset, 'Amp1');

    assert(size(dataMatrix, 1) == 10, 'Should have 10 epochs');
    assert(length(epochs) == 10, 'Should return 10 epoch structs');

    testResults.passed = testResults.passed + 1;
    testResults.tests{end+1} = {testName, 'PASS', ''};
    fprintf('   [PASS]\n');
catch ME
    testResults.failed = testResults.failed + 1;
    testResults.tests{end+1} = {testName, 'FAIL', ME.message};
    fprintf('   [FAIL] %s\n', ME.message);
end

%% Test B9: getResponseMatrix with Embedded Data
testName = 'B9. getResponseMatrix with embedded data';
fprintf('\n%s\n', testName);
fprintf('   %s\n', repmat('-', 1, length(testName)));

try
    tree = epicTreeTools(testData);
    tree.buildTree({'cellInfo.type'});

    epochs = tree.getAllEpochs(false);
    testEpochs = epochs(1:5);

    % Get response matrix
    [respMatrix, fs] = epicTreeTools.getResponseMatrix(testEpochs, 'Amp1');

    assert(size(respMatrix, 1) == 5, 'Should have 5 rows');
    assert(fs == 10000, 'Sample rate should be 10000');
    assert(~isempty(respMatrix), 'Response matrix should not be empty');

    % Check that each row has data
    for i = 1:5
        rowRange = max(respMatrix(i,:)) - min(respMatrix(i,:));
        assert(rowRange > 0, sprintf('Row %d should have non-constant data', i));
    end

    testResults.passed = testResults.passed + 1;
    testResults.tests{end+1} = {testName, 'PASS', ''};
    fprintf('   [PASS]\n');
catch ME
    testResults.failed = testResults.failed + 1;
    testResults.tests{end+1} = {testName, 'FAIL', ME.message};
    fprintf('   [FAIL] %s\n', ME.message);
end

%% Test B10: H5 Lazy Loading (Real Data)
testName = 'B10. H5 lazy loading (real data)';
fprintf('\n%s\n', testName);
fprintf('   %s\n', repmat('-', 1, length(testName)));

if ~hasRealData
    fprintf('   [SKIP] Real data not available\n');
    testResults.tests{end+1} = {testName, 'SKIP', 'Real data not available'};
else
    try
        % Load real data
        realData = load(dataPath);
        tree = epicTreeTools(realData);
        tree.buildTree({'cellInfo.type', 'blockInfo.protocol_name'});

        % Get a leaf node
        leaves = tree.leafNodes();
        testLeaf = leaves{1};

        fprintf('   Testing leaf: %s (%d epochs)\n', testLeaf.pathString(), length(testLeaf.epochList));

        % Get H5 file
        if isfield(realData, 'experiments')
            if iscell(realData.experiments)
                exp = realData.experiments{1};
            else
                exp = realData.experiments(1);
            end
            if isfield(exp, 'exp_name')
                exp_name = exp.exp_name;
            else
                exp_name = '2025-12-02_F';
            end
        else
            exp_name = '2025-12-02_F';
        end
        h5_file = getH5FilePath(exp_name);

        % Get data with H5 loading
        [dataMatrix, epochs, sampleRate] = epicTreeTools.getSelectedData(testLeaf, 'Amp1', h5_file);

        assert(~isempty(dataMatrix), 'dataMatrix should not be empty from H5');
        assert(any(dataMatrix(:) ~= 0), 'Data should have non-zero values');
        assert(sampleRate > 0, 'Sample rate should be positive');

        fprintf('   Loaded: [%d x %d], fs=%g Hz\n', size(dataMatrix, 1), size(dataMatrix, 2), sampleRate);
        fprintf('   Data range: [%.4f, %.4f]\n', min(dataMatrix(:)), max(dataMatrix(:)));

        testResults.passed = testResults.passed + 1;
        testResults.tests{end+1} = {testName, 'PASS', ''};
        fprintf('   [PASS]\n');
    catch ME
        testResults.failed = testResults.failed + 1;
        testResults.tests{end+1} = {testName, 'FAIL', ME.message};
        fprintf('   [FAIL] %s\n', ME.message);
    end
end

%% Test B11: Selection Filtering
testName = 'B11. Selection filtering';
fprintf('\n%s\n', testName);
fprintf('   %s\n', repmat('-', 1, length(testName)));

try
    tree = epicTreeTools(testData);
    tree.buildTree({'cellInfo.type'});

    % Get a leaf node
    leaves = tree.leafNodes();
    testLeaf = leaves{1};
    originalCount = length(testLeaf.epochList);

    % Mark half as unselected
    for i = 1:floor(originalCount/2)
        testLeaf.epochList{i}.isSelected = false;
    end

    % Get selected data
    [dataMatrix, epochs, ~] = epicTreeTools.getSelectedData(testLeaf, 'Amp1');

    expectedCount = originalCount - floor(originalCount/2);
    assert(size(dataMatrix, 1) == expectedCount, ...
        sprintf('Should have %d selected epochs, got %d', expectedCount, size(dataMatrix, 1)));
    assert(length(epochs) == expectedCount, ...
        sprintf('Should return %d epoch structs, got %d', expectedCount, length(epochs)));

    % Verify all returned epochs are selected
    for i = 1:length(epochs)
        assert(epochs{i}.isSelected, 'Returned epoch should be selected');
    end

    % Restore selection for other tests
    for i = 1:originalCount
        testLeaf.epochList{i}.isSelected = true;
    end

    testResults.passed = testResults.passed + 1;
    testResults.tests{end+1} = {testName, 'PASS', ''};
    fprintf('   [PASS]\n');
    fprintf('   Original: %d, After filter: %d\n', originalCount, expectedCount);
catch ME
    testResults.failed = testResults.failed + 1;
    testResults.tests{end+1} = {testName, 'FAIL', ME.message};
    fprintf('   [FAIL] %s\n', ME.message);
end

%% Test B12: Full Workflow (Display -> Select -> Retrieve)
testName = 'B12. Full workflow (display -> select -> retrieve)';
fprintf('\n%s\n', testName);
fprintf('   %s\n', repmat('-', 1, length(testName)));

try
    % 1. Create GUI (invisible)
    testFig = figure('Visible', 'off', 'Name', 'Test Workflow');
    testAxes = axes('Parent', testFig);

    % 2. Create tree and build
    tree = epicTreeTools(testData);
    tree.buildTree({'cellInfo.type', 'parameters.contrast'});

    % 3. Verify tree structure
    nCellTypes = tree.childrenLength();
    assert(nCellTypes == 3, 'Should have 3 cell types');

    % 4. Navigate to specific node: OnP -> contrast=0.5
    onpNode = tree.childBySplitValue('OnP');
    assert(~isempty(onpNode), 'Should find OnP node');

    contrastNode = onpNode.childBySplitValue(0.5);
    assert(~isempty(contrastNode), 'Should find contrast=0.5 node');

    % 5. Get data from selected node
    [data1, epochs1, fs1] = epicTreeTools.getSelectedData(contrastNode, 'Amp1');
    assert(~isempty(data1), 'Should have data for contrast=0.5');

    % 6. Mark some epochs as unselected
    nToDeselect = 2;
    for i = 1:nToDeselect
        contrastNode.epochList{i}.isSelected = false;
    end

    % 7. Get data again - should be fewer
    [data2, epochs2, ~] = epicTreeTools.getSelectedData(contrastNode, 'Amp1');
    assert(size(data2, 1) == size(data1, 1) - nToDeselect, ...
        'Should have fewer epochs after deselection');

    % 8. Store analysis results using controlled access
    results = struct();
    results.meanResponse = mean(data2, 1);
    results.n = size(data2, 1);
    results.contrast = contrastNode.splitValue;
    contrastNode.putCustom('analysisResults', results);

    % 9. Retrieve and verify
    storedResults = contrastNode.getCustom('analysisResults');
    assert(storedResults.n == size(data2, 1), 'Stored n should match');
    assert(storedResults.contrast == 0.5, 'Stored contrast should be 0.5');

    close(testFig);

    testResults.passed = testResults.passed + 1;
    testResults.tests{end+1} = {testName, 'PASS', ''};
    fprintf('   [PASS]\n');
    fprintf('   Workflow complete: tree -> navigate -> select -> retrieve -> analyze -> store\n');
catch ME
    testResults.failed = testResults.failed + 1;
    testResults.tests{end+1} = {testName, 'FAIL', ME.message};
    fprintf('   [FAIL] %s\n', ME.message);
    if exist('testFig', 'var') && ishandle(testFig)
        close(testFig);
    end
end

%% ================================================================
%  SUMMARY
%  ================================================================
fprintf('\n========================================================\n');
fprintf('  TEST SUMMARY\n');
fprintf('========================================================\n\n');

fprintf('Results: %d PASSED, %d FAILED\n\n', testResults.passed, testResults.failed);

fprintf('Test Details:\n');
for i = 1:length(testResults.tests)
    t = testResults.tests{i};
    if strcmp(t{2}, 'PASS')
        fprintf('  [PASS] %s\n', t{1});
    elseif strcmp(t{2}, 'SKIP')
        fprintf('  [SKIP] %s - %s\n', t{1}, t{3});
    else
        fprintf('  [FAIL] %s - %s\n', t{1}, t{3});
    end
end

if testResults.failed == 0
    fprintf('\n*** ALL TESTS PASSED ***\n');
else
    fprintf('\n*** %d TEST(S) FAILED ***\n', testResults.failed);
end

fprintf('\nTest Coverage:\n');
fprintf('  GUI Display:\n');
fprintf('    - graphicalTree creation and widget pool\n');
fprintf('    - Node rendering (names, counts, states)\n');
fprintf('    - Expand/collapse functionality\n');
fprintf('    - Selection management\n');
fprintf('    - Checkbox state sync\n');
fprintf('    - Keyboard navigation\n');
fprintf('  Data Retrieval:\n');
fprintf('    - getSelectedData with tree nodes\n');
fprintf('    - getSelectedData with epoch lists\n');
fprintf('    - getResponseMatrix with embedded data\n');
fprintf('    - H5 lazy loading (real data)\n');
fprintf('    - Selection filtering\n');
fprintf('    - Full workflow integration\n');

%% Helper function: Create synthetic test data
function testData = createSyntheticData()
    testData = struct();
    testData.format_version = '1.0';
    testData.metadata = struct('created_date', datestr(now), 'data_source', 'test');
    testData.experiments = {};

    exp = struct();
    exp.id = 1;
    exp.exp_name = '2025-01-25_Test';
    exp.is_mea = false;
    exp.cells = {};

    cellTypes = {'OnP', 'OffP', 'OnM'};
    protocols = {'FlashProtocol', 'ContrastProtocol', 'NoiseProtocol'};
    contrasts = [0.1, 0.5, 1.0];

    epochCounter = 1;
    for c = 1:length(cellTypes)
        cell = struct();
        cell.id = c;
        cell.label = sprintf('Cell%d', c);
        cell.type = cellTypes{c};
        cell.epoch_groups = {};

        for p = 1:length(protocols)
            eg = struct();
            eg.id = (c-1)*10 + p;
            eg.label = protocols{p};
            eg.protocol_name = protocols{p};
            eg.epoch_blocks = {};

            eb = struct();
            eb.id = (c-1)*100 + p*10;
            eb.label = protocols{p};
            eb.protocol_name = protocols{p};
            eb.epochs = {};

            for ct = 1:length(contrasts)
                for rep = 1:4
                    epoch = struct();
                    epoch.id = epochCounter;
                    epoch.label = sprintf('epoch-%d', epochCounter);
                    epoch.isSelected = true;
                    epoch.parameters = struct();
                    epoch.parameters.contrast = contrasts(ct);
                    epoch.parameters.preTime = 500;
                    epoch.parameters.stimTime = 1000;
                    epoch.parameters.tailTime = 500;

                    % Create mock response data - scaled by contrast
                    epoch.responses = struct();
                    epoch.responses(1).id = epochCounter;
                    epoch.responses(1).device_name = 'Amp1';
                    epoch.responses(1).data = randn(1, 10000) * contrasts(ct) + contrasts(ct)*2;
                    epoch.responses(1).spike_times = [];
                    epoch.responses(1).sample_rate = 10000;
                    epoch.responses(1).h5_path = '';

                    eb.epochs{end+1} = epoch;
                    epochCounter = epochCounter + 1;
                end
            end

            eg.epoch_blocks{end+1} = eb;
            cell.epoch_groups{end+1} = eg;
        end

        exp.cells{end+1} = cell;
    end

    testData.experiments{1} = exp;
end
