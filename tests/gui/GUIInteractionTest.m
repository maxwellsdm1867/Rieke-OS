classdef GUIInteractionTest < matlab.unittest.TestCase
    % GUIINTERACTIONTEST Automated GUI interaction tests
    %
    % Tests epicTreeGUI via programmatic interaction using TreeNavigationUtility.
    % Validates GUI launch, tree display, checkbox behavior, selection propagation,
    % and data display functionality.
    %
    % IMPORTANT: epicTreeGUI uses traditional figure() not uifigure(), so we use
    % programmatic property/method access instead of App Testing Framework.
    %
    % Usage:
    %   results = runtests('tests/gui/GUIInteractionTest')
    %
    % Test Coverage:
    %   - GUI launch and component creation
    %   - Tree display and node hierarchy
    %   - Checkbox interaction via TreeNavigationUtility
    %   - Node selection and data display updates
    %   - Edge cases and error handling
    %
    % See also: TreeNavigationUtility, epicTreeGUI

    properties
        GUI         % epicTreeGUI instance
        Utility     % TreeNavigationUtility instance
        TestTree    % epicTreeTools instance
    end

    methods (TestMethodSetup)
        function launchGUI(testCase)
            % LAUNCHGUI Set up GUI for each test
            %
            % Fresh GUI instance per test to avoid state leakage

            % Load test data with multi-level tree
            [testCase.TestTree, ~, ~] = loadTestTree({'cellInfo.type', 'blockInfo.protocol_name'});

            % Launch GUI
            testCase.GUI = epicTreeGUI(testCase.TestTree);

            % Create utility for programmatic control
            testCase.Utility = TreeNavigationUtility(testCase.GUI);

            % Add teardown to close GUI
            testCase.addTeardown(@() testCase.cleanupGUI());

            % Small pause to let GUI render
            drawnow;
            pause(0.1);
        end
    end

    methods (Access = private)
        function cleanupGUI(testCase)
            % CLEANUPGUI Close GUI and clean up figure
            if ~isempty(testCase.GUI) && ishandle(testCase.GUI.figure)
                close(testCase.GUI.figure);
            end
            % Extra cleanup: close any stray figures
            allFigs = findall(0, 'Type', 'figure');
            for ii = 1:length(allFigs)
                if isvalid(allFigs(ii))
                    close(allFigs(ii));
                end
            end
        end
    end

    %% GUI Launch Tests

    methods (Test)
        function testGUILaunchesSuccessfully(testCase)
            % Test GUI figure is created and valid

            testCase.verifyNotEmpty(testCase.GUI, 'GUI instance should not be empty');
            testCase.verifyTrue(ishandle(testCase.GUI.figure), ...
                'GUI figure should be valid handle');
            testCase.verifyEqual(testCase.GUI.figure.Visible, 'on', ...
                'GUI figure should be visible');
        end

        function testGUIHasTreeBrowser(testCase)
            % Test tree browser panel exists and is populated

            testCase.verifyNotEmpty(testCase.GUI.treeBrowser, ...
                'Tree browser struct should not be empty');
            testCase.verifyNotEmpty(testCase.GUI.treeBrowser.panel, ...
                'Tree browser panel should exist');
            testCase.verifyNotEmpty(testCase.GUI.treeBrowser.graphTree, ...
                'Graphical tree should be initialized');
            testCase.verifyTrue(isa(testCase.GUI.treeBrowser.graphTree, 'epicGraphicalTree'), ...
                'Tree browser should be epicGraphicalTree instance');
        end

        function testGUIHasPlottingCanvas(testCase)
            % Test plotting/viewer panel exists

            testCase.verifyNotEmpty(testCase.GUI.plottingCanvas, ...
                'Plotting canvas struct should not be empty');
            testCase.verifyNotEmpty(testCase.GUI.plottingCanvas.panel, ...
                'Plotting panel should exist');
            testCase.verifyNotEmpty(testCase.GUI.plottingCanvas.axes, ...
                'Plotting axes should exist');
            testCase.verifyNotEmpty(testCase.GUI.plottingCanvas.infoTable, ...
                'Info table should exist');
        end

        function testGUIHasMenuBar(testCase)
            % Test menu bar exists with expected menus

            fig = testCase.GUI.figure;
            menus = findall(fig, 'Type', 'uimenu', 'Parent', fig);
            testCase.verifyNotEmpty(menus, 'Menu bar should have menus');

            % Check for expected menus
            menuLabels = get(menus, 'Label');
            testCase.verifyTrue(any(contains(menuLabels, 'File')), ...
                'File menu should exist');
            testCase.verifyTrue(any(contains(menuLabels, 'Analysis')), ...
                'Analysis menu should exist');
        end
    end

    %% Tree Display Tests

    methods (Test)
        function testTreeDisplaysRootNode(testCase)
            % Test root node is visible in tree browser

            gTree = testCase.GUI.treeBrowser.graphTree;
            testCase.verifyNotEmpty(gTree.trunk, 'Tree trunk (root) should exist');
            testCase.verifyGreaterThan(gTree.drawCount, 0, ...
                'Tree should have drawn nodes');
        end

        function testTreeDisplaysChildren(testCase)
            % Test first-level children are visible (cell types)

            gTree = testCase.GUI.treeBrowser.graphTree;
            rootNode = gTree.trunk;

            testCase.verifyGreaterThan(rootNode.numChildren(), 0, ...
                'Root node should have children (cell types)');
        end

        function testTreeNodeCount(testCase)
            % Test number of displayed nodes matches tree structure

            gTree = testCase.GUI.treeBrowser.graphTree;

            % At minimum, should have root + first-level children
            expectedMin = 1 + testCase.TestTree.childrenLength();
            testCase.verifyGreaterThanOrEqual(length(gTree.nodeList), expectedMin, ...
                'Node list should contain at least root + children');
        end
    end

    %% Checkbox Interaction Tests

    methods (Test)
        function testCheckboxDefaultState(testCase)
            % Test initial checkbox state (all selected by default)

            % Check root node
            rootSelected = testCase.TestTree.custom.isSelected;
            testCase.verifyTrue(rootSelected, ...
                'Root node should be selected by default');

            % Check total selected count
            totalEpochs = testCase.TestTree.epochCount();
            selectedEpochs = testCase.TestTree.selectedCount();
            testCase.verifyEqual(selectedEpochs, totalEpochs, ...
                'All epochs should be selected by default');
        end

        function testCheckboxToggleOff(testCase)
            % Test deselecting a node via utility

            % Navigate to first child (cell type)
            testCase.Utility.navigateToChild(1);
            initialCount = testCase.Utility.CurrentNode.selectedCount();

            % Deselect
            testCase.Utility.toggleCheckbox(false);
            drawnow;

            % Verify selection state changed
            newCount = testCase.Utility.CurrentNode.selectedCount();
            testCase.verifyLessThan(newCount, initialCount, ...
                'Selected count should decrease after deselecting');
            testCase.verifyFalse(testCase.Utility.CurrentNode.custom.isSelected, ...
                'Node custom.isSelected should be false');
        end

        function testCheckboxToggleOn(testCase)
            % Test reselecting a node

            % Navigate and deselect
            testCase.Utility.navigateToChild(1);
            testCase.Utility.toggleCheckbox(false);
            drawnow;

            % Reselect
            testCase.Utility.toggleCheckbox(true);
            drawnow;

            % Verify selection restored
            testCase.verifyTrue(testCase.Utility.CurrentNode.custom.isSelected, ...
                'Node custom.isSelected should be true after reselecting');
        end

        function testCheckboxRecursiveDeselect(testCase)
            % Test deselecting parent recursively deselects all children

            % Navigate to first child
            testCase.Utility.navigateToChild(1);
            parentNode = testCase.Utility.CurrentNode;

            % Deselect recursively
            testCase.Utility.toggleCheckboxRecursive(false);
            drawnow;

            % Verify parent and all children deselected
            testCase.verifyFalse(parentNode.custom.isSelected, ...
                'Parent should be deselected');

            for ii = 1:parentNode.childrenLength()
                child = parentNode.childAt(ii);
                testCase.verifyFalse(child.custom.isSelected, ...
                    sprintf('Child %d should be deselected', ii));
            end
        end

        function testCheckboxPropagation(testCase)
            % Test checkbox toggle propagates to getSelectedEpochTreeNodes

            % Navigate to first child
            testCase.Utility.navigateToChild(1);

            % Deselect
            testCase.Utility.toggleCheckbox(false);
            drawnow;

            % Get selected nodes from GUI
            selectedNodes = testCase.GUI.getSelectedEpochTreeNodes();

            % Verify current node not in selected list
            currentNodeInList = false;
            for ii = 1:length(selectedNodes)
                if selectedNodes{ii} == testCase.Utility.CurrentNode
                    currentNodeInList = true;
                    break;
                end
            end

            testCase.verifyFalse(currentNodeInList, ...
                'Deselected node should not appear in getSelectedEpochTreeNodes');
        end
    end

    %% Node Selection Tests

    methods (Test)
        function testNodeSelectionUpdatesViewer(testCase)
            % Test selecting a node via highlightCurrentNode updates viewer

            % Navigate to first child
            testCase.Utility.navigateToChild(1);

            % Highlight (select) the node
            testCase.verifyWarningFree(@() testCase.Utility.highlightCurrentNode(), ...
                'Highlighting node should not produce warnings');

            % Verify no error occurred (viewer should update)
            % We can't easily test the actual plot, but verify GUI state is consistent
            drawnow;
        end

        function testSelectDifferentNodes(testCase)
            % Test navigating and selecting multiple different nodes

            % Navigate to first child
            testCase.Utility.navigateToChild(1);
            testCase.Utility.highlightCurrentNode();
            drawnow;

            % Navigate to second child if exists
            testCase.Utility.navigateToParent();
            if testCase.Utility.CurrentNode.childrenLength() >= 2
                testCase.Utility.navigateToChild(2);
                testCase.Utility.highlightCurrentNode();
                drawnow;

                % No crash = success
                testCase.verifyTrue(true, 'Multiple node selections succeeded');
            end
        end
    end

    %% Data Display Tests

    methods (Test)
        function testPlotNodeDataNoError(testCase)
            % Test selecting a leaf node and triggering data display produces no error

            % Navigate to a leaf node
            testCase.Utility.navigateToChild(1);  % Cell type
            if testCase.Utility.CurrentNode.childrenLength() > 0
                testCase.Utility.navigateToChild(1);  % Protocol
            end

            % Highlight node (triggers GUI's onTreeSelectionChanged callback)
            testCase.verifyWarningFree(@() testCase.Utility.highlightCurrentNode(), ...
                'Selecting node and triggering display should not produce warnings');
            drawnow;
        end

        function testInfoTableUpdates(testCase)
            % Test info table updates after selecting a node

            % Navigate to first child
            testCase.Utility.navigateToChild(1);

            % Highlight node (triggers info table update via callback)
            testCase.Utility.highlightCurrentNode();
            drawnow;

            % Verify table data is populated
            tableData = get(testCase.GUI.plottingCanvas.infoTable, 'Data');
            testCase.verifyNotEmpty(tableData, 'Info table should have data');
            testCase.verifyGreaterThan(size(tableData, 1), 0, ...
                'Info table should have rows');
        end
    end

    %% Edge Cases

    methods (Test)
        function testGUICloseNoError(testCase)
            % Test GUI closes cleanly without error

            % Close should happen in teardown, but test explicit close
            fig = testCase.GUI.figure;
            testCase.verifyWarningFree(@() close(fig), ...
                'Closing GUI should not produce warnings');
        end

        function testMultipleGUIInstances(testCase)
            % Test can launch two GUIs simultaneously

            % Launch second GUI
            gui2 = epicTreeGUI(testCase.TestTree);
            testCase.addTeardown(@() close(gui2.figure));
            drawnow;

            % Both should be valid
            testCase.verifyTrue(ishandle(testCase.GUI.figure), ...
                'First GUI should still be valid');
            testCase.verifyTrue(ishandle(gui2.figure), ...
                'Second GUI should be valid');

            % Should have different figure handles
            testCase.verifyNotEqual(testCase.GUI.figure, gui2.figure, ...
                'GUIs should have different figure handles');
        end

        function testEmptyTreeNode(testCase)
            % Test selecting a node with no epochs doesn't crash

            % Navigate to deepest possible node
            testCase.Utility.navigateToChild(1);
            if testCase.Utility.CurrentNode.childrenLength() > 0
                testCase.Utility.navigateToChild(1);
            end

            % Deselect all epochs
            testCase.Utility.toggleCheckboxRecursive(false);
            drawnow;

            % Try to highlight/display (should handle empty data gracefully)
            testCase.verifyWarningFree(@() testCase.Utility.highlightCurrentNode(), ...
                'Selecting empty node should not crash');
            drawnow;
        end

        function testNavigationToInvalidChild(testCase)
            % Test navigating to non-existent child throws appropriate error

            % Try to navigate to child 999 (doesn't exist)
            testCase.verifyError(@() testCase.Utility.navigateToChild(999), ...
                'TreeNavigationUtility:InvalidIndex', ...
                'Should throw error for invalid child index');
        end

        function testNavigateToParentFromRoot(testCase)
            % Test navigating to parent from root throws error

            % Already at root
            testCase.Utility.navigateToRoot();

            testCase.verifyError(@() testCase.Utility.navigateToParent(), ...
                'TreeNavigationUtility:NoParent', ...
                'Should throw error when navigating to parent from root');
        end

        function testDataExtractionFromEmptyNode(testCase)
            % Test extracting data from empty node returns empty

            % Navigate to first child and deselect all
            testCase.Utility.navigateToChild(1);
            testCase.Utility.toggleCheckboxRecursive(false);
            drawnow;

            % Try to extract data
            [data, epochs, ~] = testCase.Utility.extractData('Amp1');

            testCase.verifyEmpty(data, 'Data should be empty for deselected node');
            testCase.verifyEmpty(epochs, 'Epochs should be empty for deselected node');
        end
    end
end
