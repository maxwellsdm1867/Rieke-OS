classdef test_selection_state < matlab.unittest.TestCase
    % TEST_SELECTION_STATE Validate selection filtering (BUG-001 regression tests)
    %
    % This test suite validates that selection state management works correctly
    % and that BUG-001 (selection state not persisting) is fixed.
    %
    % BUG-001 Root Cause: Test code was modifying epochs returned by getAllEpochs(),
    % which are COPIES of the epoch structs. Direct modification of these copies
    % does NOT affect the tree's internal epoch list. The correct API is setSelected().
    %
    % These tests serve as regression guards to ensure:
    % 1. setSelected() correctly updates isSelected flags on internal epoch list
    % 2. getAllEpochs(true) correctly filters based on isSelected flags
    % 3. Recursive propagation works (parent deselect cascades to children)
    % 4. epicTreeTools.getSelectedData() respects selection state
    % 5. The anti-pattern (direct epoch modification) is documented

    properties
        TestDataPath = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';
        TreeData
    end

    methods (TestClassSetup)
        function loadData(testCase)
            % Load real test data once for all tests
            testCase.assumeTrue(exist(testCase.TestDataPath, 'file') == 2, ...
                sprintf('Test data file not found: %s', testCase.TestDataPath));
            [testCase.TreeData, ~] = loadEpicTreeData(testCase.TestDataPath);
        end
    end

    methods (TestMethodSetup)
        function resetSelectionState(testCase)
            % Reset selection state is handled by creating fresh tree per test
            % No action needed here - just documenting the pattern
        end
    end

    methods (Test)

        function testSetSelectedDeselectsAllEpochs(testCase)
            % Verify that setSelected(false, true) deselects all epochs
            % and getAllEpochs(true) returns empty array

            % Build tree with one level split
            tree = epicTreeTools(testCase.TreeData);
            tree.buildTree({'cellInfo.type'});

            % Get a leaf node
            firstChild = tree.childAt(1);
            if firstChild.isLeaf
                leaf = firstChild;
            else
                leaf = firstChild.childAt(1);
            end

            % Verify epochs initially selected
            initialCount = length(leaf.getAllEpochs(true));
            testCase.verifyGreaterThan(initialCount, 0, ...
                'Leaf should have selected epochs initially');

            % Deselect all epochs recursively
            leaf.setSelected(false, true);

            % Verify getAllEpochs(true) returns empty
            selectedEpochs = leaf.getAllEpochs(true);
            testCase.verifyEmpty(selectedEpochs, ...
                'After deselect, getAllEpochs(true) should return empty');

            % Verify getAllEpochs(false) still returns all epochs
            allEpochs = leaf.getAllEpochs(false);
            testCase.verifyEqual(length(allEpochs), initialCount, ...
                'getAllEpochs(false) should still return all epochs');
        end

        function testSetSelectedReselectsAllEpochs(testCase)
            % Verify that deselect then reselect restores epoch count

            tree = epicTreeTools(testCase.TreeData);
            tree.buildTree({'cellInfo.type'});

            firstChild = tree.childAt(1);
            if firstChild.isLeaf
                leaf = firstChild;
            else
                leaf = firstChild.childAt(1);
            end

            % Record initial count
            initialCount = length(leaf.getAllEpochs(true));

            % Deselect all
            leaf.setSelected(false, true);
            testCase.verifyEmpty(leaf.getAllEpochs(true), ...
                'After deselect, should have no selected epochs');

            % Reselect all
            leaf.setSelected(true, true);

            % Verify count restored
            finalCount = length(leaf.getAllEpochs(true));
            testCase.verifyEqual(finalCount, initialCount, ...
                'After reselect, epoch count should match initial');
        end

        function testRecursiveDeselect(testCase)
            % Verify that deselecting an internal node recursively
            % deselects all descendant leaves' epochs

            % Build multi-level tree
            tree = epicTreeTools(testCase.TreeData);
            tree.buildTree({'cellInfo.type', 'cellInfo.id'});

            % Get first internal node (cell type level)
            cellTypeNode = tree.childAt(1);
            testCase.verifyFalse(cellTypeNode.isLeaf, ...
                'Cell type node should be internal (not leaf)');

            % Record initial counts
            initialTotal = length(cellTypeNode.getAllEpochs(true));
            testCase.verifyGreaterThan(initialTotal, 0, ...
                'Cell type node should have selected epochs initially');

            % Deselect this node recursively
            cellTypeNode.setSelected(false, true);

            % Verify all descendant epochs are deselected
            selectedAfter = cellTypeNode.getAllEpochs(true);
            testCase.verifyEmpty(selectedAfter, ...
                'Recursive deselect should deselect all descendant epochs');

            % Verify each child leaf is empty
            for i = 1:cellTypeNode.childrenLength()
                child = cellTypeNode.childAt(i);
                childSelected = child.getAllEpochs(true);
                testCase.verifyEmpty(childSelected, ...
                    sprintf('Child %d should have no selected epochs', i));
            end
        end

        function testRootDeselectAll(testCase)
            % Verify that root.setSelected(false, true) deselects
            % the entire tree

            tree = epicTreeTools(testCase.TreeData);
            tree.buildTree({'cellInfo.type'});

            % Verify tree has selected epochs initially
            initialCount = length(tree.getAllEpochs(true));
            testCase.verifyGreaterThan(initialCount, 0, ...
                'Root should have selected epochs initially');

            % Deselect entire tree from root
            tree.setSelected(false, true);

            % Verify entire tree is deselected
            selectedEpochs = tree.getAllEpochs(true);
            testCase.verifyEmpty(selectedEpochs, ...
                'Root deselect should deselect entire tree');
        end

        function testRootReselectAll(testCase)
            % Verify that after deselecting root, reselecting root
            % recursively restores all epochs

            tree = epicTreeTools(testCase.TreeData);
            tree.buildTree({'cellInfo.type'});

            % Record initial count
            initialCount = length(tree.getAllEpochs(true));

            % Deselect entire tree
            tree.setSelected(false, true);
            testCase.verifyEmpty(tree.getAllEpochs(true));

            % Reselect entire tree
            tree.setSelected(true, true);

            % Verify count restored
            finalCount = length(tree.getAllEpochs(true));
            testCase.verifyEqual(finalCount, initialCount, ...
                'Root reselect should restore all epochs');
        end

        function testPartialSelection(testCase)
            % Verify that deselecting one child while keeping another
            % selected results in getAllEpochs(true) returning only
            % the selected child's epochs

            tree = epicTreeTools(testCase.TreeData);
            tree.buildTree({'cellInfo.type'});

            % Verify we have at least 2 children
            testCase.verifyGreaterThanOrEqual(tree.childrenLength(), 2, ...
                'Tree needs at least 2 cell type children for partial selection test');

            % Get two children
            child1 = tree.childAt(1);
            child2 = tree.childAt(2);

            % Record counts
            count1 = length(child1.getAllEpochs(true));
            count2 = length(child2.getAllEpochs(true));

            % Deselect child1
            child1.setSelected(false, true);

            % Verify root returns only child2's epochs
            rootSelected = tree.getAllEpochs(true);
            testCase.verifyEqual(length(rootSelected), count2, ...
                'Root should return only child2 epochs after child1 deselected');

            % Verify child1 is empty
            child1Selected = child1.getAllEpochs(true);
            testCase.verifyEmpty(child1Selected, ...
                'Child1 should have no selected epochs');

            % Verify child2 unchanged
            child2Selected = child2.getAllEpochs(true);
            testCase.verifyEqual(length(child2Selected), count2, ...
                'Child2 should still have all its epochs selected');
        end

        function testGetSelectedDataRespectsSelection(testCase)
            % Verify that epicTreeTools.getSelectedData() respects selection state
            % and returns fewer rows after deselection

            tree = epicTreeTools(testCase.TreeData);
            tree.buildTree({'cellInfo.type'});

            % Auto-detect stream name from first epoch
            allEpochs = tree.getAllEpochs(false);
            testCase.assumeNotEmpty(allEpochs, 'Tree has no epochs');

            firstEpoch = allEpochs{1};
            testCase.assumeTrue(isfield(firstEpoch, 'responses') && ...
                                ~isempty(firstEpoch.responses), ...
                                'First epoch has no responses');

            streamName = firstEpoch.responses(1).device_name;

            % Get data with all epochs selected
            [dataAll, ~, ~] = epicTreeTools.getSelectedData(tree, streamName);
            testCase.assumeNotEmpty(dataAll, 'No data returned for stream');
            initialRows = size(dataAll, 1);

            % Deselect first child
            child1 = tree.childAt(1);
            child1.setSelected(false, true);

            % Get data after deselection
            [dataPartial, ~, ~] = epicTreeTools.getSelectedData(tree, streamName);
            partialRows = size(dataPartial, 1);

            % Verify fewer rows returned
            testCase.verifyLessThan(partialRows, initialRows, ...
                'getSelectedData should return fewer rows after deselection');
        end

        function testSelectedCountMatchesGetAllEpochs(testCase)
            % Verify that selectedCount() equals length(getAllEpochs(true))
            % after partial deselection

            tree = epicTreeTools(testCase.TreeData);
            tree.buildTree({'cellInfo.type'});

            % Deselect first child
            if tree.childrenLength() > 0
                child1 = tree.childAt(1);
                child1.setSelected(false, true);
            end

            % Compare counts
            countMethod = tree.selectedCount();
            countEpochs = length(tree.getAllEpochs(true));

            testCase.verifyEqual(countMethod, countEpochs, ...
                'selectedCount() should match length(getAllEpochs(true))');
        end

        function testDirectEpochModificationDoesNotWork(testCase)
            % ANTI-PATTERN DOCUMENTATION: This test documents the root cause
            % of BUG-001. Modifying epochs returned by getAllEpochs() does NOT
            % affect the tree because getAllEpochs() returns COPIES, not references.
            %
            % CORRECT PATTERN: Use setSelected() method instead.

            tree = epicTreeTools(testCase.TreeData);
            tree.buildTree({'cellInfo.type'});

            % Get epochs (these are COPIES)
            epochs = tree.getAllEpochs(false);
            testCase.assumeNotEmpty(epochs, 'Tree has no epochs');

            % ANTI-PATTERN: Modify isSelected on returned copies
            for i = 1:length(epochs)
                epochs{i}.isSelected = false;  % This modifies the COPY
            end

            % Verify that getAllEpochs(true) is NOT affected
            % because we modified copies, not the tree's internal epoch list
            selectedEpochs = tree.getAllEpochs(true);
            testCase.verifyNotEmpty(selectedEpochs, ...
                ['Modifying returned epoch copies does NOT affect tree. ' ...
                 'This is the root cause of BUG-001. ' ...
                 'CORRECT PATTERN: Use setSelected() method instead.']);
        end

        function testRefreshNodeSelectionState(testCase)
            % Verify that refreshNodeSelectionState() syncs node.custom.isSelected
            % with actual epoch states after manual modification
            %
            % NOTE: This tests the internal refresh mechanism. Normal users
            % should never manually modify epochList - use setSelected() instead.

            tree = epicTreeTools(testCase.TreeData);
            tree.buildTree({'cellInfo.type'});

            % Get a leaf node
            firstChild = tree.childAt(1);
            if firstChild.isLeaf
                leaf = firstChild;
            else
                leaf = firstChild.childAt(1);
            end

            % Manually modify isSelected on leaf's epochList items (INTERNAL access)
            % This simulates corruption or direct manipulation
            if ~isempty(leaf.epochList)
                for i = 1:length(leaf.epochList)
                    leaf.epochList{i}.isSelected = false;
                end
            end

            % At this point, node.custom.isSelected may be out of sync
            % Call refreshNodeSelectionState to sync
            tree.refreshNodeSelectionState();

            % Verify node state reflects actual epoch states
            if leaf.hasCustom('isSelected')
                nodeIsSelected = leaf.getCustom('isSelected');
                % Leaf should be marked as not selected since all epochs are deselected
                testCase.verifyFalse(nodeIsSelected, ...
                    'After refresh, node.custom.isSelected should reflect epoch states');
            end

            % Verify getAllEpochs(true) respects the changes
            selectedEpochs = leaf.getAllEpochs(true);
            testCase.verifyEmpty(selectedEpochs, ...
                'getAllEpochs(true) should return empty after manual deselect');
        end

    end
end
