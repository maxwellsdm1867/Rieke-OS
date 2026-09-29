classdef WorkflowTest < matlab.unittest.TestCase
    % WORKFLOWTEST End-to-end integration tests for complete analysis workflows
    %
    % Tests validate that functions work together correctly in realistic
    % researcher workflows - from data loading through tree building to analysis.
    %
    % Workflows tested:
    %   1. Basic Analysis Pipeline - Load, build, analyze, extract results
    %   2. Multi-Level Tree Navigation + Analysis - Deep tree with custom storage
    %   3. Selection-Filtered Analysis - Verify selection filtering works end-to-end
    %   4. Comparative Analysis - Compare results across multiple conditions
    %   5. Tree Reorganization - Verify tree rebuilding preserves data
    %   6. GUI + Analysis Integration - Full GUI pipeline with programmatic control
    %
    % Usage:
    %   runtests('tests/integration/WorkflowTest')

    properties
        DataPath
        H5File
    end

    methods (TestClassSetup)
        function setupPaths(testCase)
            % Add specific paths (avoid genpath which scans recursively)
            repoRoot = '/Users/maxwellsdm/Documents/GitHub/epicTreeGUI';
            addpath(fullfile(repoRoot, 'src'));
            addpath(fullfile(repoRoot, 'src', 'tree'));
            addpath(fullfile(repoRoot, 'src', 'analysis'));
            addpath(fullfile(repoRoot, 'src', 'utilities'));
            addpath(fullfile(repoRoot, 'src', 'splitters'));
            addpath(fullfile(repoRoot, 'src', 'tree', 'graphicalTree'));
            addpath(fullfile(repoRoot, 'tests', 'helpers'));
            addpath(fullfile(repoRoot, 'tests', 'utilities'));

            % Set test data path directly
            testCase.DataPath = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';
        end
    end

    methods (Test)
        %% Workflow 1: Basic Analysis Pipeline
        function testLoadBuildAnalyzeWorkflow(testCase)
            % THE critical path: Load -> Build -> Navigate -> Analyze
            % If this fails, the tool is fundamentally broken.

            % Step 1: Load data
            [data, h5File] = loadEpicTreeData(testCase.DataPath);
            testCase.verifyNotEmpty(data, 'Data loading failed');

            % Step 2: Build tree with single split
            tree = epicTreeTools(data);
            tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType});

            testCase.verifyGreaterThan(tree.childrenLength(), 0, ...
                'Tree should have cell type children');

            % Step 3: Navigate to first cell type child
            cellTypeNode = tree.childAt(1);
            testCase.verifyNotEmpty(cellTypeNode, 'Cell type node is empty');
            testCase.verifyGreaterThan(cellTypeNode.epochCount(), 0, ...
                'Cell type node should have epochs');

            % Step 4: Call analysis function on that node
            result = epicTreeTools.getMeanResponseTrace(cellTypeNode, 'Amp1');

            % Step 5: Verify output struct has valid fields
            testCase.verifyTrue(isstruct(result), 'Result should be struct');
            testCase.verifyTrue(isfield(result, 'mean'), 'Result missing mean field');
            testCase.verifyTrue(isfield(result, 'stdev'), 'Result missing stdev field');
            testCase.verifyTrue(isfield(result, 'SEM'), 'Result missing SEM field');
            testCase.verifyTrue(isfield(result, 'n'), 'Result missing n field');
            testCase.verifyTrue(isfield(result, 'timeVector'), 'Result missing timeVector');
            testCase.verifyTrue(isfield(result, 'sampleRate'), 'Result missing sampleRate');

            testCase.verifyGreaterThan(result.n, 0, 'Result should have epochs');
            testCase.verifyEqual(result.n, cellTypeNode.selectedCount(), ...
                'Result n should match selected count');

            % Verify data dimensions
            testCase.verifyEqual(length(result.mean), length(result.timeVector), ...
                'Mean trace length should match time vector');
            testCase.verifyEqual(length(result.stdev), length(result.timeVector), ...
                'Stdev trace length should match time vector');

            fprintf('Workflow 1 PASS: Basic pipeline from load to analysis works correctly\n');
        end

        %% Workflow 2: Multi-Level Tree Navigation + Analysis
        function testMultiLevelNavigationWorkflow(testCase)
            % Pipeline with deeper tree structure and custom result storage

            % Step 1: Build tree with two split levels
            [tree, data, h5File] = loadTestTree({'cellInfo.type', 'blockInfo.protocol_name'});

            testCase.verifyGreaterThan(tree.childrenLength(), 0, ...
                'Level 1 should have children');

            % Step 2: Navigate to first cell type
            cellTypeNode = tree.childAt(1);
            cellType = cellTypeNode.splitValue;

            testCase.verifyGreaterThan(cellTypeNode.childrenLength(), 0, ...
                'Cell type node should have protocol children');

            % Step 3: Navigate to first protocol
            protocolNode = cellTypeNode.childAt(1);
            protocolName = protocolNode.splitValue;

            fprintf('  Analyzing: %s / %s\n', string(cellType), string(protocolName));

            % Step 4: Extract data with getSelectedData
            [dataMatrix, epochs, fs] = epicTreeTools.getSelectedData(protocolNode, 'Amp1');

            testCase.verifyNotEmpty(dataMatrix, 'Data matrix should not be empty');
            testCase.verifyNotEmpty(epochs, 'Epochs should not be empty');
            testCase.verifyGreaterThan(fs, 0, 'Sample rate should be positive');

            % Step 5: Compute amplitude stats
            stats = epicTreeTools.getResponseAmplitudeStats(protocolNode, 'Amp1');

            testCase.verifyTrue(isstruct(stats), 'Stats should be struct');
            testCase.verifyEqual(stats.n, length(epochs), ...
                'Stats n should match epoch count');

            % Step 6: Store results with putCustom
            protocolNode.putCustom('amplitudeStats', stats);
            protocolNode.putCustom('dataShape', size(dataMatrix));

            % Step 7: Verify stored results can be retrieved
            retrievedStats = protocolNode.getCustom('amplitudeStats');
            testCase.verifyEqual(retrievedStats.n, stats.n, ...
                'Retrieved stats should match stored stats');

            dataShape = protocolNode.getCustom('dataShape');
            testCase.verifyEqual(dataShape, size(dataMatrix), ...
                'Retrieved data shape should match stored shape');

            testCase.verifyTrue(protocolNode.hasCustom('amplitudeStats'), ...
                'Node should report having amplitudeStats');

            fprintf('Workflow 2 PASS: Multi-level navigation with result storage works\n');
        end

        %% Workflow 3: Selection-Filtered Analysis
        function testSelectionFilteredWorkflow(testCase)
            % Verify selection filtering works through entire pipeline

            % Step 1: Build tree
            [tree, data, h5] = loadTestTree({'cellInfo.type'});

            % Step 2: Get a leaf node
            leaves = tree.leafNodes();
            testCase.verifyGreaterThan(length(leaves), 0, 'Should have leaf nodes');

            leafNode = leaves{1};
            totalCount = leafNode.epochCount();

            testCase.verifyGreaterThan(totalCount, 1, ...
                'Need at least 2 epochs to test selection filtering');

            % Step 3: Deselect half the epochs
            epochs = leafNode.getAllEpochs(false);
            halfPoint = floor(totalCount / 2);

            % Deselect first half
            for i = 1:halfPoint
                epochs{i}.isSelected = false;
            end

            expectedSelected = totalCount - halfPoint;
            actualSelected = leafNode.selectedCount();

            testCase.verifyEqual(actualSelected, expectedSelected, ...
                'Selected count should match expected after deselection');

            % Step 4: Call getMeanResponseTrace (uses OnlySelected=true by default)
            result = epicTreeTools.getMeanResponseTrace(leafNode, 'Amp1');

            % Step 5: Verify n in output equals selected count (not total count)
            testCase.verifyEqual(result.n, expectedSelected, ...
                'Result n should equal selected count, not total count');

            % Also verify with getSelectedData
            [dataMatrix, selectedEpochs, fs] = epicTreeTools.getSelectedData(leafNode, 'Amp1');

            testCase.verifyEqual(length(selectedEpochs), expectedSelected, ...
                'getSelectedData should return only selected epochs');
            testCase.verifyEqual(size(dataMatrix, 1), expectedSelected, ...
                'Data matrix rows should match selected count');

            fprintf('Workflow 3 PASS: Selection filtering works end-to-end\n');
        end

        %% Workflow 4: Comparative Analysis Across Conditions
        function testComparativeAnalysisWorkflow(testCase)
            % Multiple condition comparison with result storage

            % Step 1: Build tree with cell type split
            [tree, data, h5] = loadTestTree({'cellInfo.type'});

            % Step 2: Get all cell type children
            nCellTypes = tree.childrenLength();
            testCase.verifyGreaterThan(nCellTypes, 0, 'Should have cell types');

            results = cell(nCellTypes, 1);

            % Step 3: For each cell type, compute getMeanResponseTrace
            for i = 1:nCellTypes
                cellTypeNode = tree.childAt(i);
                cellType = cellTypeNode.splitValue;

                result = epicTreeTools.getMeanResponseTrace(cellTypeNode, 'Amp1');

                % Store result
                results{i} = result;
                cellTypeNode.putCustom('meanTrace', result);

                fprintf('  %s: n=%d epochs\n', string(cellType), result.n);
            end

            % Step 4: Compare n values across conditions
            nValues = cellfun(@(r) r.n, results);
            testCase.verifyTrue(all(nValues > 0), ...
                'All conditions should have at least 1 epoch');

            % Step 5: Store summary at root
            summary = struct();
            summary.cellTypes = cell(nCellTypes, 1);
            summary.nEpochs = nValues;
            summary.totalEpochs = sum(nValues);

            for i = 1:nCellTypes
                cellTypeNode = tree.childAt(i);
                summary.cellTypes{i} = cellTypeNode.splitValue;
            end

            tree.putCustom('comparativeSummary', summary);

            % Step 6: Query results back from all leaf nodes
            leaves = tree.leafNodes();
            nLeavesWithResults = 0;

            for i = 1:length(leaves)
                if leaves{i}.hasCustom('meanTrace')
                    nLeavesWithResults = nLeavesWithResults + 1;
                end
            end

            testCase.verifyGreaterThan(nLeavesWithResults, 0, ...
                'At least some leaves should have stored results');

            % Verify summary can be retrieved
            retrievedSummary = tree.getCustom('comparativeSummary');
            testCase.verifyEqual(retrievedSummary.totalEpochs, tree.epochCount(), ...
                'Summary total should match root epoch count');

            fprintf('Workflow 4 PASS: Comparative analysis across %d conditions\n', nCellTypes);
        end

        %% Workflow 5: Tree Reorganization
        function testTreeReorgWorkflow(testCase)
            % Verify tree rebuilding preserves data

            % Step 1: Build tree with cellInfo.type
            [data, h5File] = loadEpicTreeData(testCase.DataPath);
            tree = epicTreeTools(data);
            tree.buildTree({'cellInfo.type'});

            totalEpochs1 = tree.epochCount();
            testCase.verifyGreaterThan(totalEpochs1, 0, ...
                'Initial tree should have epochs');

            % Get first level split values
            firstLevelValues1 = cell(tree.childrenLength(), 1);
            for i = 1:tree.childrenLength()
                firstLevelValues1{i} = tree.childAt(i).splitValue;
            end

            % Step 2: Rebuild with blockInfo.protocol_name
            tree.buildTree({'blockInfo.protocol_name'});

            % Step 3: Count total epochs again
            totalEpochs2 = tree.epochCount();

            % Step 4: Verify counts match (no data lost)
            testCase.verifyEqual(totalEpochs2, totalEpochs1, ...
                'Total epoch count should be preserved after reorganization');

            % Step 5: Verify tree structure changed
            firstLevelValues2 = cell(tree.childrenLength(), 1);
            for i = 1:tree.childrenLength()
                firstLevelValues2{i} = tree.childAt(i).splitValue;
            end

            % The split values should be different (unless coincidentally same)
            testCase.verifyNotEqual(tree.childrenLength(), length(firstLevelValues1), ...
                'Number of first-level children should likely differ after reorg');

            % Verify all epochs still accessible
            allEpochs = tree.getAllEpochs(false);
            testCase.verifyEqual(length(allEpochs), totalEpochs1, ...
                'getAllEpochs should return same count as epochCount');

            fprintf('Workflow 5 PASS: Tree reorganization preserves data (%d epochs)\n', ...
                totalEpochs1);
        end

        %% Workflow 6: GUI + Analysis Integration
        function testGUIAnalysisWorkflow(testCase)
            % Full GUI pipeline with programmatic control

            % Step 1: Build tree
            [tree, data, h5] = loadTestTree({'cellInfo.type'});

            % Step 2: Launch GUI
            gui = epicTreeGUI(tree);

            % Add teardown to ensure GUI closes
            testCase.addTeardown(@() close(gui.figure));

            % Step 3: Verify GUI initialized
            testCase.verifyTrue(isvalid(gui.figure), 'GUI figure should be valid');
            testCase.verifyNotEmpty(gui.tree, 'GUI should have tree');
            testCase.verifyNotEmpty(gui.graphicalTree, 'GUI should have graphical tree');

            % Step 4: Use TreeNavigationUtility for programmatic control
            util = TreeNavigationUtility(gui);

            % Step 5: Navigate to a leaf node
            currentNode = util.getCurrentNode();
            testCase.verifyNotEmpty(currentNode, 'Should have current node');

            % Expand root if it has children
            if currentNode.childrenLength() > 0
                util.expandNode(currentNode);

                % Navigate to first child
                firstChild = currentNode.childAt(1);
                util.navigateToNode(firstChild);

                currentNode = util.getCurrentNode();
                testCase.verifyEqual(currentNode, firstChild, ...
                    'Current node should be first child after navigation');
            end

            % Step 6: Extract data from current node
            [dataMatrix, epochs, fs] = epicTreeTools.getSelectedData(currentNode, 'Amp1');

            testCase.verifyNotEmpty(epochs, 'Should have epochs at current node');

            % Step 7: Compute analysis
            result = epicTreeTools.getMeanResponseTrace(currentNode, 'Amp1');
            testCase.verifyEqual(result.n, length(epochs), ...
                'Analysis result should match epoch count');

            % Step 8: Close GUI (teardown will handle this, but verify it can be called)
            testCase.verifyTrue(isvalid(gui.figure), 'Figure should still be valid');

            fprintf('Workflow 6 PASS: GUI + analysis integration works\n');
        end
    end
end
