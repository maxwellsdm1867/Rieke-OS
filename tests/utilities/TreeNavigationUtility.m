classdef TreeNavigationUtility < handle
    % TREENAVIGATIONUTILITY Programmatic tree navigation and GUI control utility
    %
    % Wraps epicTreeGUI for command-line testing of tree navigation and
    % checkbox selection state. Provides full programmatic access without
    % manual clicking.
    %
    % CRITICAL: This utility controls ACTUAL GUI checkboxes, not just the
    % setSelected() method. It finds the graphical widgets and triggers
    % their callbacks to fully simulate user interaction.
    %
    % Usage:
    %   % Launch GUI and attach utility
    %   [tree, ~, ~] = loadTestTree({'cellInfo.type', 'blockInfo.protocol_name'});
    %   gui = epicTreeGUI(tree);
    %   util = TreeNavigationUtility(gui);
    %
    %   % Navigate tree
    %   util.navigateToChild(1);           % Go to first child by index
    %   util.navigateToChild('OnP');       % Go to child by splitValue
    %   util.navigateToNode('OnP', 'SingleSpot');  % Navigate by path
    %
    %   % Control checkboxes
    %   util.toggleCheckbox(false);        % Deselect current node
    %   util.toggleCheckbox(true);         % Reselect
    %   util.toggleCheckboxRecursive(false); % Deselect with descendants
    %   util.selectAll();                  % Select entire tree
    %
    %   % Inspect tree
    %   util.printTree(2);                 % Print tree to depth 2
    %   info = util.getCurrentNodeInfo();  % Get current node metadata
    %
    %   % Extract data
    %   [data, epochs, fs] = util.extractData('Amp1');
    %
    % See also: epicTreeGUI, epicTreeTools, epicGraphicalTree

    properties
        GUI             % epicTreeGUI handle
        CurrentNode     % Current epicTreeTools node being navigated
    end

    methods
        function obj = TreeNavigationUtility(gui)
            % TREENAVIGATIONUTILITY Constructor
            %
            % Usage:
            %   util = TreeNavigationUtility(gui)
            %
            % Inputs:
            %   gui - epicTreeGUI instance

            if nargin < 1 || isempty(gui)
                error('TreeNavigationUtility:NoGUI', 'Must provide epicTreeGUI instance');
            end

            if ~isa(gui, 'epicTreeGUI')
                error('TreeNavigationUtility:InvalidGUI', 'Input must be epicTreeGUI instance');
            end

            obj.GUI = gui;
            obj.CurrentNode = gui.tree;  % Start at root
        end

        %% Navigation Methods

        function navigateToChild(obj, indexOrName)
            % NAVIGATETOCHILD Navigate to a child of current node
            %
            % Usage:
            %   util.navigateToChild(1)        % By index (1-based)
            %   util.navigateToChild('OnP')    % By splitValue
            %
            % Inputs:
            %   indexOrName - Integer index or string/numeric splitValue

            if isempty(obj.CurrentNode.children)
                error('TreeNavigationUtility:NoChildren', 'Current node has no children');
            end

            if isnumeric(indexOrName) && isscalar(indexOrName) && indexOrName == floor(indexOrName)
                % Navigate by index
                child = obj.CurrentNode.childAt(indexOrName);
                if isempty(child)
                    error('TreeNavigationUtility:InvalidIndex', ...
                        'Child index %d out of range (1-%d)', indexOrName, obj.CurrentNode.childrenLength());
                end
                obj.CurrentNode = child;

            else
                % Navigate by splitValue
                child = obj.CurrentNode.childBySplitValue(indexOrName);
                if isempty(child)
                    error('TreeNavigationUtility:InvalidSplitValue', ...
                        'No child found with splitValue: %s', string(indexOrName));
                end
                obj.CurrentNode = child;
            end
        end

        function navigateToParent(obj)
            % NAVIGATETOPARENT Navigate to parent of current node
            %
            % Usage:
            %   util.navigateToParent()

            parent = obj.CurrentNode.parent;
            if isempty(parent)
                error('TreeNavigationUtility:NoParent', 'Current node has no parent (already at root)');
            end
            obj.CurrentNode = parent;
        end

        function navigateToRoot(obj)
            % NAVIGATETOROOT Navigate to root node
            %
            % Usage:
            %   util.navigateToRoot()

            obj.CurrentNode = obj.GUI.tree;
        end

        function navigateToNode(obj, varargin)
            % NAVIGATETONODE Navigate by path of splitValues
            %
            % Usage:
            %   util.navigateToNode('OnP')                    % One level
            %   util.navigateToNode('OnP', 'SingleSpot')      % Two levels
            %   util.navigateToNode('OnP', 'SingleSpot', 42)  % Three levels
            %
            % Inputs:
            %   varargin - Sequence of splitValues to navigate

            obj.navigateToRoot();  % Start from root

            for ii = 1:length(varargin)
                splitValue = varargin{ii};
                obj.navigateToChild(splitValue);
            end
        end

        function info = getCurrentNodeInfo(obj)
            % GETCURRENTNODEINFO Get metadata about current node
            %
            % Returns:
            %   info - Struct with fields:
            %     splitKey       - Split criterion key
            %     splitValue     - Split criterion value
            %     epochCount     - Total epochs in subtree
            %     selectedCount  - Selected epochs in subtree
            %     depth          - Depth in tree (0 = root)
            %     childCount     - Number of children
            %     isLeaf         - True if leaf node
            %     isSelected     - True if node is selected

            node = obj.CurrentNode;

            info = struct();
            info.splitKey = node.splitKey;
            info.splitValue = node.splitValue;
            info.epochCount = node.epochCount();
            info.selectedCount = node.selectedCount();
            info.depth = node.depth();
            info.childCount = node.childrenLength();
            info.isLeaf = node.isLeaf;
            info.isSelected = node.custom.isSelected;
        end

        %% Checkbox/Selection Methods

        function toggleCheckbox(obj, selected)
            % TOGGLECHECKBOX Set checkbox state on current node
            %
            % CRITICAL: This method finds the actual GUI checkbox widget
            % and triggers its callback, fully simulating a user click.
            % Does NOT just call setSelected() on the data node.
            %
            % Usage:
            %   util.toggleCheckbox(true)   % Check
            %   util.toggleCheckbox(false)  % Uncheck
            %
            % Inputs:
            %   selected - Boolean selection state

            % Find the graphical node widget for current data node
            graphNode = obj.findGraphicalNode(obj.CurrentNode);

            if isempty(graphNode)
                error('TreeNavigationUtility:NodeNotFound', ...
                    'Could not find graphical widget for current node');
            end

            % Get the widget bound to this graphical node
            widget = obj.findWidgetForGraphNode(graphNode);

            if isempty(widget)
                error('TreeNavigationUtility:WidgetNotFound', ...
                    'Could not find widget for graphical node');
            end

            % Only toggle if state differs
            if graphNode.isChecked ~= selected
                % Simulate clicking the checkbox by calling the tree's callback
                obj.GUI.treeBrowser.graphTree.respondToWidgetCheckboxClick(widget.selfKey, []);
            end
        end

        function toggleCheckboxRecursive(obj, selected)
            % TOGGLECHECKBOXRECURSIVE Set checkbox on current node and descendants
            %
            % Usage:
            %   util.toggleCheckboxRecursive(false)  % Deselect tree
            %
            % Inputs:
            %   selected - Boolean selection state

            % Since epicGraphicalTreeNode.setChecked is already recursive,
            % we can just toggle the current node and it will propagate
            obj.toggleCheckbox(selected);
        end

        function selectAll(obj)
            % SELECTALL Select all nodes in entire tree
            %
            % Usage:
            %   util.selectAll()

            obj.GUI.tree.setSelected(true, true);
            obj.GUI.initTreeBrowser();  % Refresh display
        end

        function deselectAll(obj)
            % DESELECTALL Deselect all nodes in entire tree
            %
            % Usage:
            %   util.deselectAll()

            obj.GUI.tree.setSelected(false, true);
            obj.GUI.initTreeBrowser();  % Refresh display
        end

        %% Data Extraction

        function [data, epochs, fs] = extractData(obj, streamName)
            % EXTRACTDATA Get selected data from current node
            %
            % Usage:
            %   [data, epochs, fs] = util.extractData('Amp1')
            %
            % Inputs:
            %   streamName - Name of response stream (e.g., 'Amp1')
            %
            % Returns:
            %   data   - Response matrix [epochs x samples]
            %   epochs - Cell array of selected epoch structs
            %   fs     - Sample rate (Hz)

            if nargin < 2
                streamName = 'Amp1';
            end

            [data, epochs, fs] = epicTreeTools.getSelectedData(obj.CurrentNode, streamName);
        end

        %% Tree Display

        function printTree(obj, maxDepth)
            % PRINTTREE Print tree structure from current node
            %
            % Usage:
            %   util.printTree()       % Print all
            %   util.printTree(2)      % Limit to depth 2
            %
            % Inputs:
            %   maxDepth - Maximum depth to print (optional, default: inf)

            if nargin < 2
                maxDepth = inf;
            end

            fprintf('\nTree from node: %s\n', string(obj.CurrentNode.splitValue));
            fprintf('=====================================\n');
            obj.printNodeRecursive(obj.CurrentNode, 0, maxDepth);
            fprintf('=====================================\n\n');
        end

        function printChildren(obj)
            % PRINTCHILDREN Print immediate children of current node
            %
            % Usage:
            %   util.printChildren()

            node = obj.CurrentNode;
            fprintf('\nChildren of %s (%d total):\n', string(node.splitValue), node.childrenLength());
            fprintf('-------------------------------------\n');

            for ii = 1:node.childrenLength()
                child = node.childAt(ii);
                selFlag = '';
                if child.custom.isSelected
                    selFlag = ' [*]';
                end
                fprintf('%2d. %s (%d epochs, %d selected)%s\n', ...
                    ii, string(child.splitValue), child.epochCount(), ...
                    child.selectedCount(), selFlag);
            end
            fprintf('-------------------------------------\n\n');
        end

        %% GUI Sync

        function highlightCurrentNode(obj)
            % HIGHLIGHTCURRENTNODE Highlight current node in GUI
            %
            % Programmatically triggers the GUI's node selection to highlight
            % the current node in the tree display.
            %
            % Usage:
            %   util.highlightCurrentNode()

            % Find the graphical node for current data node
            graphNode = obj.findGraphicalNode(obj.CurrentNode);

            if isempty(graphNode)
                warning('TreeNavigationUtility:NodeNotFound', ...
                    'Could not find graphical node to highlight');
                return;
            end

            % Find the widget
            widget = obj.findWidgetForGraphNode(graphNode);

            if isempty(widget)
                warning('TreeNavigationUtility:WidgetNotFound', ...
                    'Could not find widget to highlight');
                return;
            end

            % Select the widget (triggers GUI callback)
            obj.GUI.treeBrowser.graphTree.selectWidget(widget.selfKey, false);
        end
    end

    %% Private Methods
    methods (Access = private)
        function graphNode = findGraphicalNode(obj, treeNode)
            % FINDGRAPHICALNODE Find epicGraphicalTreeNode matching epicTreeTools node
            %
            % Strategy: Walk the graphical tree nodeList and check userData
            % references. The marryEpochNodesToWidgets method stores the
            % epicTreeTools node in graphNode.userData.

            gTree = obj.GUI.treeBrowser.graphTree;

            for ii = 1:length(gTree.nodeList)
                gNode = gTree.nodeList{ii};
                if ~isempty(gNode) && ~isempty(gNode.userData)
                    % Check if userData points to our tree node
                    if isa(gNode.userData, 'epicTreeTools') && gNode.userData == treeNode
                        graphNode = gNode;
                        return;
                    end
                end
            end

            % Not found
            graphNode = [];
        end

        function widget = findWidgetForGraphNode(obj, graphNode)
            % FINDWIDGETFORGRAPHNODE Find the widget currently displaying a graphical node
            %
            % Strategy: Check all widgets to see which one has boundNodeKey
            % matching graphNode.selfKey

            gTree = obj.GUI.treeBrowser.graphTree;

            for ii = 1:length(gTree.widgetList)
                w = gTree.widgetList{ii};
                if ~isempty(w) && ~isempty(w.boundNodeKey) && w.boundNodeKey == graphNode.selfKey
                    widget = w;
                    return;
                end
            end

            % Not found (node might not be visible/drawn)
            widget = [];
        end

        function printNodeRecursive(obj, node, depth, maxDepth)
            % PRINTNODERECURSIVE Recursive helper for printTree

            if depth > maxDepth
                return;
            end

            % Build indent
            indent = repmat('  ', 1, depth);

            % Selection marker
            selFlag = '';
            if node.custom.isSelected
                selFlag = ' [*]';
            end

            % Print node
            fprintf('%s%s (%d/%d)%s\n', ...
                indent, string(node.splitValue), ...
                node.selectedCount(), node.epochCount(), selFlag);

            % Recurse on children
            for ii = 1:node.childrenLength()
                child = node.childAt(ii);
                obj.printNodeRecursive(child, depth + 1, maxDepth);
            end
        end
    end
end
