classdef TreeNavigationTest < matlab.unittest.TestCase
    % TreeNavigationTest - Comprehensive tests for epicTreeTools navigation and access
    %
    % This test class validates all tree navigation methods, controlled access
    % methods, selection filtering, and tree building with real experiment data.
    %
    % Run tests:
    %   results = runtests('tests/unit/TreeNavigationTest');
    %
    % Coverage:
    %   - Navigation DOWN: childrenLength, childAt, childBySplitValue, leafNodes
    %   - Navigation UP: parent, parentAt, depth, getRoot, pathFromRoot, pathString
    %   - Controlled Access: putCustom, getCustom, hasCustom, removeCustom, customKeys
    %   - Selection: getAllEpochs, epochCount, selectedCount, setSelected
    %   - Tree Building: buildTree, buildTreeWithSplitters

    properties
        Tree        % epicTreeTools root node
        Data        % Raw loaded data
        H5File      % Path to H5 file
    end

    methods (TestClassSetup)
        function loadData(testCase)
            % Load test data with multi-level splits for thorough testing
            % Split by cell type (level 1) and protocol name (level 2)
            addpath(genpath('tests/helpers'));
            addpath(genpath('src'));

            try
                [testCase.Tree, testCase.Data, testCase.H5File] = loadTestTree(...
                    {'cellInfo.type', 'blockInfo.protocol_name'});
            catch ME
                error('Failed to load test data: %s\nEnsure test data is available.', ...
                    ME.message);
            end
        end
    end

    methods (TestMethodSetup)
        function resetSelection(testCase)
            % Reset all epochs to selected before each test
            % Prevents test interference from selection state changes
            testCase.Tree.setSelected(true, true);
        end
    end

    %% Navigation DOWN tests
    methods (Test)
        function testChildrenLength(testCase)
            % Verify childrenLength returns expected count
            nChildren = testCase.Tree.childrenLength();

            % Should have at least 1 child (at least one cell type)
            testCase.verifyGreaterThan(nChildren, 0, ...
                'Root should have at least one child node');

            % Count should match actual children array length
            testCase.verifyEqual(nChildren, length(testCase.Tree.children), ...
                'childrenLength should match children array length');
        end

        function testChildAt(testCase)
            % childAt(1) returns valid node with expected properties
            if testCase.Tree.childrenLength() == 0
                testCase.verifyFail('No children to test');
            end

            child = testCase.Tree.childAt(1);

            % Child should be valid epicTreeTools object
            testCase.verifyClass(child, 'epicTreeTools', ...
                'childAt should return epicTreeTools object');

            % Child should have non-empty splitValue
            testCase.verifyNotEmpty(child.splitValue, ...
                'Child should have splitValue set');

            % Child should have correct parent reference
            testCase.verifyEqual(child.parent, testCase.Tree, ...
                'Child parent should reference correct parent node');
        end

        function testChildAtOutOfBounds(testCase)
            % childAt with invalid indices should throw error or return empty
            nChildren = testCase.Tree.childrenLength();

            % Test index 0 (MATLAB is 1-based)
            testCase.verifyError(@() testCase.Tree.childAt(0), ...
                'MATLAB:badsubscript', ...
                'childAt(0) should throw error');

            % Test index beyond range
            testCase.verifyError(@() testCase.Tree.childAt(nChildren + 1), ...
                'MATLAB:badsubscript', ...
                'childAt(N+1) should throw error');
        end

        function testChildBySplitValue(testCase)
            % Find child by split value and verify epoch counts
            if testCase.Tree.childrenLength() == 0
                testCase.verifyFail('No children to test');
            end

            % Get first child's split value
            firstChild = testCase.Tree.childAt(1);
            targetValue = firstChild.splitValue;

            % Find using childBySplitValue
            foundChild = testCase.Tree.childBySplitValue(targetValue);

            % Should return the same node
            testCase.verifyEqual(foundChild, firstChild, ...
                'childBySplitValue should find correct child');

            % Epoch counts should match
            testCase.verifyEqual(foundChild.epochCount(), firstChild.epochCount(), ...
                'Found child should have same epoch count');
        end

        function testChildBySplitValueNotFound(testCase)
            % Unknown split value should return empty
            foundChild = testCase.Tree.childBySplitValue('__NONEXISTENT_VALUE__');

            testCase.verifyEmpty(foundChild, ...
                'childBySplitValue should return empty for unknown value');
        end

        function testLeafNodes(testCase)
            % leafNodes returns cell array of actual leaves
            leaves = testCase.Tree.leafNodes();

            % Should return cell array
            testCase.verifyClass(leaves, 'cell', ...
                'leafNodes should return cell array');

            % Should have at least one leaf
            testCase.verifyGreaterThan(length(leaves), 0, ...
                'Should have at least one leaf node');

            % All returned nodes should be actual leaves
            for i = 1:length(leaves)
                leaf = leaves{i};
                testCase.verifyEqual(leaf.childrenLength(), 0, ...
                    sprintf('Leaf %d should have 0 children', i));
                testCase.verifyTrue(leaf.isLeaf, ...
                    sprintf('Leaf %d should have isLeaf=true', i));
            end
        end

        function testLeafNodesEpochCount(testCase)
            % Sum of all leaf epoch counts equals root epoch count
            leaves = testCase.Tree.leafNodes();
            rootEpochCount = testCase.Tree.epochCount();

            % Sum epochs from all leaves
            leafEpochSum = 0;
            for i = 1:length(leaves)
                leafEpochSum = leafEpochSum + leaves{i}.epochCount();
            end

            testCase.verifyEqual(leafEpochSum, rootEpochCount, ...
                'Sum of leaf epochs should equal root epoch count (no epochs lost)');
        end
    end

    %% Navigation UP tests
    methods (Test)
        function testParent(testCase)
            % child.parent returns correct parent node
            if testCase.Tree.childrenLength() == 0
                testCase.verifyFail('No children to test');
            end

            child = testCase.Tree.childAt(1);
            parent = child.parent;

            testCase.verifyEqual(parent, testCase.Tree, ...
                'Child parent should reference root node');
        end

        function testParentOfRoot(testCase)
            % Root node parent should be empty
            rootParent = testCase.Tree.parent;

            testCase.verifyEmpty(rootParent, ...
                'Root node should have empty parent');
        end

        function testParentAt(testCase)
            % parentAt navigates up correct number of levels
            leaves = testCase.Tree.leafNodes();
            if isempty(leaves)
                testCase.verifyFail('No leaf nodes to test');
            end

            leaf = leaves{1};
            leafDepth = leaf.depth();

            if leafDepth < 1
                testCase.verifyFail('Leaf depth too shallow for test');
            end

            % Go up 1 level
            parent1 = leaf.parentAt(1);
            testCase.verifyEqual(parent1, leaf.parent, ...
                'parentAt(1) should equal direct parent');

            % Go up to root
            root = leaf.parentAt(leafDepth);
            testCase.verifyEqual(root, testCase.Tree, ...
                sprintf('parentAt(%d) should reach root', leafDepth));
        end

        function testDepth(testCase)
            % Root depth is 0, children depth increases
            rootDepth = testCase.Tree.depth();
            testCase.verifyEqual(rootDepth, 0, ...
                'Root depth should be 0');

            if testCase.Tree.childrenLength() > 0
                child = testCase.Tree.childAt(1);
                childDepth = child.depth();
                testCase.verifyEqual(childDepth, 1, ...
                    'First-level child depth should be 1');
            end
        end

        function testGetRoot(testCase)
            % Any node's getRoot() returns the root
            leaves = testCase.Tree.leafNodes();
            if isempty(leaves)
                testCase.verifyFail('No leaf nodes to test');
            end

            leaf = leaves{1};
            root = leaf.getRoot();

            testCase.verifyEqual(root, testCase.Tree, ...
                'getRoot should return tree root from any node');
        end

        function testPathFromRoot(testCase)
            % Path length equals depth + 1
            leaves = testCase.Tree.leafNodes();
            if isempty(leaves)
                testCase.verifyFail('No leaf nodes to test');
            end

            leaf = leaves{1};
            path = leaf.pathFromRoot();
            leafDepth = leaf.depth();

            testCase.verifyNumElements(path, leafDepth + 1, ...
                'Path length should equal depth + 1');

            % First element should be root
            testCase.verifyEqual(path{1}, testCase.Tree, ...
                'First path element should be root');

            % Last element should be the leaf itself
            testCase.verifyEqual(path{end}, leaf, ...
                'Last path element should be the leaf node');
        end

        function testPathString(testCase)
            % Path string contains separator character
            leaves = testCase.Tree.leafNodes();
            if isempty(leaves)
                testCase.verifyFail('No leaf nodes to test');
            end

            leaf = leaves{1};
            pathStr = leaf.pathString();

            % Default separator is '>'
            if leaf.depth() > 0
                testCase.verifyTrue(contains(pathStr, '>'), ...
                    'Path string should contain default separator ">"');
            end

            % Custom separator
            pathStrCustom = leaf.pathString(' / ');
            if leaf.depth() > 0
                testCase.verifyTrue(contains(pathStrCustom, ' / '), ...
                    'Path string should contain custom separator " / "');
            end
        end
    end

    %% Controlled Access tests
    methods (Test)
        function testPutGetCustom(testCase)
            % Store and retrieve struct, verify values match
            testData = struct('value', 42, 'name', 'test', 'array', [1 2 3]);

            testCase.Tree.putCustom('testData', testData);
            retrieved = testCase.Tree.getCustom('testData');

            testCase.verifyEqual(retrieved.value, testData.value, ...
                'Retrieved value should match stored value');
            testCase.verifyEqual(retrieved.name, testData.name, ...
                'Retrieved name should match stored name');
            testCase.verifyEqual(retrieved.array, testData.array, ...
                'Retrieved array should match stored array');
        end

        function testHasCustom(testCase)
            % Returns true for stored key, false for missing key
            testCase.Tree.putCustom('existingKey', 123);

            testCase.verifyTrue(testCase.Tree.hasCustom('existingKey'), ...
                'hasCustom should return true for existing key');

            testCase.verifyFalse(testCase.Tree.hasCustom('nonExistentKey'), ...
                'hasCustom should return false for missing key');
        end

        function testRemoveCustom(testCase)
            % After removal, hasCustom returns false
            testCase.Tree.putCustom('keyToRemove', 'value');
            testCase.verifyTrue(testCase.Tree.hasCustom('keyToRemove'), ...
                'Key should exist before removal');

            testCase.Tree.removeCustom('keyToRemove');
            testCase.verifyFalse(testCase.Tree.hasCustom('keyToRemove'), ...
                'Key should not exist after removal');
        end

        function testGetCustomMissing(testCase)
            % Returns empty for non-existent key
            retrieved = testCase.Tree.getCustom('nonExistentKey');

            testCase.verifyEmpty(retrieved, ...
                'getCustom should return empty for non-existent key');
        end

        function testCustomKeys(testCase)
            % Returns correct list of stored keys
            % Store multiple keys
            testCase.Tree.putCustom('key1', 'value1');
            testCase.Tree.putCustom('key2', 'value2');
            testCase.Tree.putCustom('key3', 'value3');

            keys = testCase.Tree.customKeys();

            % Should contain all three keys
            testCase.verifyTrue(ismember('key1', keys), ...
                'customKeys should include key1');
            testCase.verifyTrue(ismember('key2', keys), ...
                'customKeys should include key2');
            testCase.verifyTrue(ismember('key3', keys), ...
                'customKeys should include key3');
        end
    end

    %% Selection and Epochs tests
    methods (Test)
        function testGetAllEpochsFalse(testCase)
            % Returns all epochs regardless of selection
            allEpochs = testCase.Tree.getAllEpochs(false);

            testCase.verifyGreaterThan(length(allEpochs), 0, ...
                'Should return at least one epoch');

            % Should return same as epochCount
            testCase.verifyEqual(length(allEpochs), testCase.Tree.epochCount(), ...
                'getAllEpochs(false) count should match epochCount');
        end

        function testGetAllEpochsTrue(testCase)
            % After deselecting some, returns fewer epochs
            allCount = testCase.Tree.epochCount();

            % Deselect first child
            if testCase.Tree.childrenLength() > 0
                firstChild = testCase.Tree.childAt(1);
                firstChild.setSelected(false, true);

                selectedEpochs = testCase.Tree.getAllEpochs(true);
                selectedCount = length(selectedEpochs);

                % Should have fewer selected epochs than total
                testCase.verifyLessThan(selectedCount, allCount, ...
                    'Selected epoch count should be less than total after deselection');
            end
        end

        function testEpochCount(testCase)
            % Matches length of getAllEpochs(false)
            count = testCase.Tree.epochCount();
            allEpochs = testCase.Tree.getAllEpochs(false);

            testCase.verifyEqual(count, length(allEpochs), ...
                'epochCount should match getAllEpochs(false) length');
        end

        function testSelectedCount(testCase)
            % After deselecting, selectedCount < epochCount
            if testCase.Tree.childrenLength() == 0
                testCase.verifyFail('No children to test');
            end

            % Deselect first child
            firstChild = testCase.Tree.childAt(1);
            firstChild.setSelected(false, true);

            selectedCount = testCase.Tree.selectedCount();
            totalCount = testCase.Tree.epochCount();

            testCase.verifyLessThan(selectedCount, totalCount, ...
                'selectedCount should be less than epochCount after deselection');
        end

        function testSetSelectedRecursive(testCase)
            % setSelected(false, true) deselects all descendants
            if testCase.Tree.childrenLength() == 0
                testCase.verifyFail('No children to test');
            end

            % Deselect first child recursively
            firstChild = testCase.Tree.childAt(1);
            initialCount = firstChild.epochCount();

            firstChild.setSelected(false, true);

            % All descendants should be deselected
            selectedCount = firstChild.selectedCount();
            testCase.verifyEqual(selectedCount, 0, ...
                'After recursive deselection, selectedCount should be 0');
        end
    end

    %% Tree Building tests
    methods (Test)
        function testBuildTreeSingleSplit(testCase)
            % Build with one key, verify structure
            newTree = epicTreeTools(testCase.Data);
            newTree.buildTree({'cellInfo.type'});

            testCase.verifyGreaterThan(newTree.childrenLength(), 0, ...
                'Tree should have children after building with one split key');

            % Root should not be a leaf
            testCase.verifyFalse(newTree.isLeaf, ...
                'Root should not be a leaf after building');
        end

        function testBuildTreeMultiSplit(testCase)
            % Build with two keys, verify depth
            newTree = epicTreeTools(testCase.Data);
            newTree.buildTree({'cellInfo.type', 'blockInfo.protocol_name'});

            % Should have at least 2 levels (root is depth 0)
            leaves = newTree.leafNodes();
            if ~isempty(leaves)
                maxDepth = max(cellfun(@(n) n.depth(), leaves));
                testCase.verifyGreaterThanOrEqual(maxDepth, 2, ...
                    'Tree should have depth >= 2 with two split keys');
            end
        end

        function testBuildTreeWithSplitters(testCase)
            % Build with function handle splitters
            newTree = epicTreeTools(testCase.Data);

            % Use built-in splitter function
            newTree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType});

            testCase.verifyGreaterThan(newTree.childrenLength(), 0, ...
                'Tree should have children after building with splitter function');
        end

        function testRebuildTreePreservesEpochs(testCase)
            % Rebuilding with different keys preserves epoch count
            originalCount = testCase.Tree.epochCount();

            % Rebuild with different split key
            testCase.Tree.buildTree({'blockInfo.protocol_name'});
            newCount = testCase.Tree.epochCount();

            testCase.verifyEqual(newCount, originalCount, ...
                'Epoch count should be preserved after rebuilding tree');
        end
    end
end
