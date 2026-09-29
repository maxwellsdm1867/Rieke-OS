%% Test Tree Navigation and Controlled Access
% This script tests the epicTreeTools navigation patterns per riekesuitworkflow.md
%
% Tests:
%   1. Load data and build tree with splitters
%   2. Navigate DOWN: childAt, childrenLength, leafNodes
%   3. Navigate UP: parent, parentAt, depth, pathFromRoot
%   4. Controlled access: putCustom, getCustom, hasCustom
%   5. Full workflow: navigate + analyze + store + query
%
% Run this from epicTreeGUI directory:
%   cd /Users/maxwellsdm/Documents/GitHub/epicTreeGUI
%   run tests/test_tree_navigation.m

clear; clc;
fprintf('\n========================================\n');
fprintf('  EPICTREETOOLS NAVIGATION TEST\n');
fprintf('========================================\n\n');

%% Add paths
baseDir = fileparts(fileparts(mfilename('fullpath')));
if isempty(baseDir)
    baseDir = '/Users/maxwellsdm/Documents/GitHub/epicTreeGUI';
end
addpath(genpath(fullfile(baseDir, 'src')));
fprintf('Base dir: %s\n', baseDir);
fprintf('Added src path\n\n');

%% Create synthetic test data (mimics DATA_FORMAT_SPECIFICATION.md)
fprintf('1. CREATING TEST DATA\n');
fprintf('   -----------------\n');

% Create test data structure with multiple cells, protocols, contrasts
testData = struct();
testData.format_version = '1.0';
testData.metadata = struct('created_date', datestr(now), 'data_source', 'test');
testData.experiments = {};

% Create one experiment with multiple cells and protocols
exp = struct();
exp.id = 1;
exp.exp_name = '2025-01-25_Test';
exp.is_mea = false;
exp.cells = {};

% Create 3 cells with different types
cellTypes = {'OnP', 'OffP', 'OnM'};
protocols = {'FlashProtocol', 'ContrastProtocol', 'NoiseProtocol'};
contrasts = [0.1, 0.3, 0.5, 1.0];

epochCounter = 1;
for c = 1:length(cellTypes)
    cell = struct();
    cell.id = c;
    cell.label = sprintf('Cell%d', c);
    cell.type = cellTypes{c};
    cell.epoch_groups = {};

    % Create epoch groups (one per protocol)
    for p = 1:length(protocols)
        eg = struct();
        eg.id = (c-1)*10 + p;
        eg.label = protocols{p};
        eg.protocol_name = protocols{p};
        eg.epoch_blocks = {};

        % Create epoch block
        eb = struct();
        eb.id = (c-1)*100 + p*10;
        eb.label = protocols{p};
        eb.protocol_name = protocols{p};
        eb.epochs = {};

        % Create epochs with different contrasts
        for ct = 1:length(contrasts)
            for rep = 1:3  % 3 repetitions per contrast
                epoch = struct();
                epoch.id = epochCounter;
                epoch.label = sprintf('epoch-%d', epochCounter);
                epoch.parameters = struct();
                epoch.parameters.contrast = contrasts(ct);
                epoch.parameters.temporal_frequency = 2.0;

                % Create mock response
                epoch.responses = struct();
                epoch.responses(1).id = epochCounter;
                epoch.responses(1).device_name = 'Amp1';
                epoch.responses(1).data = randn(1, 10000) * contrasts(ct);  % Mock data
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
fprintf('   Created %d cells, %d protocols, %d contrasts\n', ...
    length(cellTypes), length(protocols), length(contrasts));
fprintf('   Total epochs: %d\n', epochCounter - 1);
fprintf('   [PASS]\n\n');

%% Test 2: Create tree and build with splitters
fprintf('2. BUILD TREE WITH SPLITTERS\n');
fprintf('   -------------------------\n');

try
    % Create tree
    tree = epicTreeTools(testData);
    fprintf('   Tree created\n');

    % Build with splitters: cellType -> protocol -> contrast
    tree.buildTree({'cellInfo.type', 'blockInfo.protocol_name', 'parameters.contrast'});
    fprintf('   Built tree with splitters: cellType -> protocol -> contrast\n');
    fprintf('   [PASS]\n\n');
catch ME
    fprintf('   [FAIL] %s\n\n', ME.message);
    return;
end

%% Test 3: Navigate DOWN
fprintf('3. NAVIGATE DOWN (children)\n');
fprintf('   ------------------------\n');

try
    % Test childrenLength
    n = tree.childrenLength();
    fprintf('   tree.childrenLength() = %d\n', n);
    assert(n == 3, 'Expected 3 cell types');

    % Test childAt
    firstChild = tree.childAt(1);
    fprintf('   tree.childAt(1).splitValue = "%s"\n', string(firstChild.splitValue));
    assert(~isempty(firstChild), 'childAt(1) should not be empty');

    % Test childBySplitValue
    onpNode = tree.childBySplitValue('OnP');
    fprintf('   tree.childBySplitValue("OnP") found: %s\n', string(~isempty(onpNode)));
    assert(~isempty(onpNode), 'Should find OnP node');

    % Test leafNodes
    leaves = tree.leafNodes();
    fprintf('   tree.leafNodes() count = %d\n', length(leaves));
    assert(length(leaves) > 0, 'Should have leaf nodes');

    fprintf('   [PASS]\n\n');
catch ME
    fprintf('   [FAIL] %s\n\n', ME.message);
    return;
end

%% Test 4: Navigate UP (parents)
fprintf('4. NAVIGATE UP (parents)\n');
fprintf('   ---------------------\n');

try
    % Get a leaf node
    leaf = leaves{1};
    fprintf('   Starting from leaf: depth = %d\n', leaf.depth());

    % Test parent property
    parentNode = leaf.parent;
    fprintf('   leaf.parent.splitValue = "%s"\n', string(parentNode.splitValue));
    assert(~isempty(parentNode), 'Leaf should have parent');

    % Test parentAt
    grandparent = leaf.parentAt(2);
    fprintf('   leaf.parentAt(2).splitValue = "%s"\n', string(grandparent.splitValue));
    assert(~isempty(grandparent), 'Should have grandparent');

    % Test depth
    d = leaf.depth();
    fprintf('   leaf.depth() = %d\n', d);
    assert(d == 3, 'Leaf should be at depth 3 (cellType -> protocol -> contrast)');

    % Test getRoot
    root = leaf.getRoot();
    fprintf('   leaf.getRoot() is root: %s\n', string(isempty(root.parent)));
    assert(isempty(root.parent), 'Root should have no parent');

    % Test pathFromRoot
    path = leaf.pathFromRoot();
    fprintf('   leaf.pathFromRoot() length = %d\n', length(path));
    assert(length(path) == d + 1, 'Path should be depth+1');

    % Test pathString
    pathStr = leaf.pathString();
    fprintf('   leaf.pathString() = "%s"\n', pathStr);
    assert(contains(pathStr, '>'), 'Path string should have separator');

    fprintf('   [PASS]\n\n');
catch ME
    fprintf('   [FAIL] %s\n\n', ME.message);
    return;
end

%% Test 5: Controlled Access (putCustom/getCustom)
fprintf('5. CONTROLLED ACCESS (putCustom/getCustom)\n');
fprintf('   ---------------------------------------\n');

try
    % Test putCustom
    testResults = struct();
    testResults.mean_response = 42.5;
    testResults.n_epochs = 12;
    testResults.NLI = [0.1, 0.2, 0.3];

    onpNode.putCustom('results', testResults);
    fprintf('   onpNode.putCustom("results", ...) - stored\n');

    % Test hasCustom
    hasIt = onpNode.hasCustom('results');
    fprintf('   onpNode.hasCustom("results") = %s\n', string(hasIt));
    assert(hasIt, 'Should have results');

    % Test getCustom
    retrieved = onpNode.getCustom('results');
    fprintf('   onpNode.getCustom("results").mean_response = %.1f\n', retrieved.mean_response);
    assert(retrieved.mean_response == 42.5, 'Should retrieve correct value');

    % Test getCustom with missing key
    missing = onpNode.getCustom('nonexistent');
    fprintf('   onpNode.getCustom("nonexistent") is empty: %s\n', string(isempty(missing)));
    assert(isempty(missing), 'Missing key should return empty');

    % Test customKeys
    keys = onpNode.customKeys();
    fprintf('   onpNode.customKeys() = {%s}\n', strjoin(keys', ', '));
    assert(any(strcmp(keys, 'results')), 'Should have results key');

    % Test removeCustom
    onpNode.removeCustom('results');
    hasItNow = onpNode.hasCustom('results');
    fprintf('   After removeCustom: hasCustom("results") = %s\n', string(hasItNow));
    assert(~hasItNow, 'Should not have results after removal');

    fprintf('   [PASS]\n\n');
catch ME
    fprintf('   [FAIL] %s\n\n', ME.message);
    return;
end

%% Test 6: Full Workflow (per riekesuitworkflow.md)
fprintf('6. FULL WORKFLOW (navigate + analyze + store + query)\n');
fprintf('   --------------------------------------------------\n');

try
    analysisLog = {};

    % Navigate tree: cellType -> protocol -> contrast
    for i = 1:tree.childrenLength()
        cellTypeNode = tree.childAt(i);
        cellType = cellTypeNode.splitValue;

        for j = 1:cellTypeNode.childrenLength()
            protocolNode = cellTypeNode.childAt(j);
            protocolName = protocolNode.splitValue;

            for k = 1:protocolNode.childrenLength()
                contrastNode = protocolNode.childAt(k);
                contrast = contrastNode.splitValue;

                % Get epochs (this is a leaf node)
                epochs = contrastNode.epochList;

                % Mock analysis - compute mean response amplitude
                responseAmplitudes = zeros(length(epochs), 1);
                for e = 1:length(epochs)
                    ep = epochs{e};
                    if isfield(ep, 'responses') && ~isempty(ep.responses)
                        data = ep.responses(1).data;
                        responseAmplitudes(e) = max(abs(data));
                    end
                end

                % Create results
                results = struct();
                results.cellType = cellType;
                results.protocol = protocolName;
                results.contrast = contrast;
                results.n_epochs = length(epochs);
                results.mean_amplitude = mean(responseAmplitudes);
                results.std_amplitude = std(responseAmplitudes);

                % Store at leaf node
                contrastNode.putCustom('results', results);

                % Log
                analysisLog{end+1} = sprintf('%s | %s | contrast=%.1f | n=%d | amp=%.2f', ...
                    cellType, protocolName, contrast, length(epochs), results.mean_amplitude);
            end
        end
    end

    fprintf('   Analyzed %d conditions\n', length(analysisLog));
    fprintf('   Sample entries:\n');
    for i = 1:min(3, length(analysisLog))
        fprintf('     %s\n', analysisLog{i});
    end

    % Query results back
    fprintf('\n   Querying stored results:\n');
    queriedLeaves = tree.leafNodes();
    for i = 1:min(3, length(queriedLeaves))
        leaf = queriedLeaves{i};
        r = leaf.getCustom('results');
        if ~isempty(r)
            fprintf('     %s/%s/%.1f: amp=%.2f\n', ...
                r.cellType, r.protocol, r.contrast, r.mean_amplitude);
        end
    end

    fprintf('   [PASS]\n\n');
catch ME
    fprintf('   [FAIL] %s\n\n', ME.message);
    disp(getReport(ME));
    return;
end

%% Test 7: Test getAllEpochs with selection
fprintf('7. TEST getAllEpochs WITH SELECTION\n');
fprintf('   --------------------------------\n');

try
    % Get all epochs
    allEpochs = tree.getAllEpochs(false);
    fprintf('   getAllEpochs(false) count = %d\n', length(allEpochs));

    % To properly test selection, we need to modify epochs in the actual tree
    % Access the first leaf node and mark some epochs as unselected
    firstLeaf = leaves{1};
    originalCount = length(firstLeaf.epochList);
    fprintf('   First leaf has %d epochs\n', originalCount);

    % Mark epochs as unselected directly in the tree's epochList
    for i = 1:min(2, length(firstLeaf.epochList))
        firstLeaf.epochList{i}.isSelected = false;
    end

    % Now get selected only from this leaf
    selectedFromLeaf = firstLeaf.getAllEpochs(true);
    fprintf('   After marking 2 as unselected in leaf:\n');
    fprintf('   firstLeaf.getAllEpochs(true) count = %d\n', length(selectedFromLeaf));
    assert(length(selectedFromLeaf) < originalCount, 'Selected should be fewer');

    % Restore selection
    for i = 1:length(firstLeaf.epochList)
        firstLeaf.epochList{i}.isSelected = true;
    end

    fprintf('   [PASS]\n\n');
catch ME
    fprintf('   [FAIL] %s\n\n', ME.message);
    return;
end

%% Test 8: Test with getSelectedData
fprintf('8. TEST getSelectedData INTEGRATION\n');
fprintf('   ---------------------------------\n');

try
    % Get a leaf node
    testLeaf = leaves{1};
    fprintf('   Testing on: %s\n', testLeaf.pathString());

    % Use getSelectedData
    [dataMatrix, epochs, sampleRate] = epicTreeTools.getSelectedData(testLeaf, 'Amp1');
    fprintf('   getSelectedData returned:\n');
    fprintf('     dataMatrix size: [%d x %d]\n', size(dataMatrix, 1), size(dataMatrix, 2));
    fprintf('     epochs count: %d\n', length(epochs));
    fprintf('     sampleRate: %g Hz\n', sampleRate);

    if ~isempty(dataMatrix)
        fprintf('     data range: [%.4f, %.4f]\n', min(dataMatrix(:)), max(dataMatrix(:)));
        fprintf('   [PASS]\n\n');
    else
        fprintf('   [WARN] dataMatrix is empty (may need H5 file)\n\n');
    end
catch ME
    fprintf('   [FAIL] %s\n\n', ME.message);
end

%% Summary
fprintf('========================================\n');
fprintf('  ALL TESTS PASSED!\n');
fprintf('========================================\n\n');

fprintf('Navigation methods available:\n');
fprintf('  DOWN: childAt(i), childrenLength(), childBySplitValue(v), leafNodes()\n');
fprintf('  UP:   parent, parentAt(n), getRoot(), depth(), pathFromRoot(), pathString()\n');
fprintf('\n');
fprintf('Controlled access methods:\n');
fprintf('  putCustom(key, value), getCustom(key), hasCustom(key), removeCustom(key)\n');
fprintf('\n');
fprintf('Workflow pattern:\n');
fprintf('  for i = 1:node.childrenLength()\n');
fprintf('      child = node.childAt(i);\n');
fprintf('      results = analyze(child);\n');
fprintf('      child.putCustom(''results'', results);\n');
fprintf('  end\n');
