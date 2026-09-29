classdef epicGraphicalTree < handle
    % GRAPHICALTREE Interactive tree visualization component
    %
    % Renders a tree structure in MATLAB axes with expand/collapse,
    % selection, and keyboard navigation.
    %
    % Usage:
    %   ax = axes('Parent', panel);
    %   tree = graphicalTree(ax, 'Root');
    %   node1 = tree.newNode(tree.trunk, 'Child 1');
    %   node2 = tree.newNode(tree.trunk, 'Child 2');
    %   tree.draw();

    properties
        name                    % Tree name
        axes                    % Parent axes
        figure                  % Parent figure

        % Selection tracking
        selectionSize = 1       % Number of items that can be selected
        selectedWidgetKeys = [] % Currently selected widget keys

        % Callbacks (function handles or cell arrays)
        nodesExpandedFcn        % Called when nodes expanded/collapsed
        nodesCheckedFcn         % Called when selection changes
        nodesSelectedFcn        % Called when node clicked
        nodeBecameCheckedFcn    % Called when single node check changes
    end

    properties (Hidden = true)
        trunk                   % Root epicGraphicalTreeNode
        nodeList = {}           % Cell array of all nodes
        widgetList = {}         % Cell array of all widgets
        initialWidgets = 100    % Initial widget pool size
        drawCount = 0           % Number of visible nodes in current draw
        isBusy = false          % Busy flag for async operations
    end

    methods
        function self = epicGraphicalTree(ax, name)
            % Constructor
            %
            % Usage:
            %   tree = epicGraphicalTree(ax, 'TreeName')

            if nargin < 2
                name = 'Tree';
            end

            self.name = name;
            self.axes = ax;
            self.figure = ancestor(ax, 'figure');

            % Configure axes for tree display
            set(ax, ...
                'YDir', 'reverse', ...          % Top-down
                'XTick', [], 'YTick', [], ...   % No ticks
                'Box', 'off', ...
                'Color', [1 1 1], ...
                'XLim', [0 50], ...
                'YLim', [0 30]);

            % Set up keyboard callback
            if ~isempty(self.figure) && ishandle(self.figure)
                set(self.figure, 'KeyPressFcn', @(src,evt) self.onKeyPress(evt));
            end

            % Create root node
            self.trunk = self.newNode([], name);
            self.trunk.isExpanded = true;

            % Pre-allocate widget pool
            for ii = 1:self.initialWidgets
                epicGraphicalTreeNodeWidget(self);
            end
        end

        function delete(self)
            % Destructor - clean up
            for ii = 1:length(self.widgetList)
                if ~isempty(self.widgetList{ii})
                    delete(self.widgetList{ii});
                end
            end
        end

        function node = newNode(self, parent, name)
            % NEWNODE Create a new tree node
            %
            % Usage:
            %   node = tree.newNode(parentNode, 'Name')
            %   rootNode = tree.newNode([], 'Root')  % For root

            if nargin < 3
                name = 'unnamed';
            end

            node = epicGraphicalTreeNode(name);
            node.tree = self;

            % Register in nodeList
            self.nodeList{end+1} = node;
            node.selfKey = length(self.nodeList);

            % Set up parent-child relationship
            if ~isempty(parent)
                node.parentKey = parent.selfKey;
                node.depth = parent.depth + 1;
                parent.addChild(node);
            end
        end

        function draw(self)
            % DRAW Render the tree

            self.drawCount = 0;

            % Include all visible nodes starting from trunk
            self.trunk.includeUnburied();

            % Bind widgets to visible nodes
            for ii = 1:self.drawCount
                self.widgetList{ii}.bindNode(ii);
            end

            % Hide unused widgets
            for ii = (self.drawCount + 1):length(self.widgetList)
                self.widgetList{ii}.unbindNode();
            end

            % Update axes limits
            yMax = max(self.drawCount * 1.5 + 2, 10);
            set(self.axes, 'YLim', [0 yMax]);

            drawnow;
        end

        function includeInDraw(self, node)
            % INCLUDEINDRAW Add a node to the current draw
            %
            % Called by epicGraphicalTreeNode.includeUnburied()

            self.drawCount = self.drawCount + 1;

            % Expand widget pool if needed
            if self.drawCount > length(self.widgetList)
                newCount = length(self.widgetList) * 2;
                for ii = length(self.widgetList)+1:newCount
                    epicGraphicalTreeNodeWidget(self);
                end
            end

            % Bind widget to node
            self.widgetList{self.drawCount}.boundNodeKey = node.selfKey;
        end

        %% Selection Management
        function [nodes, nodeKeys] = getSelectedNodes(self)
            % GETSELECTEDNODES Get currently selected nodes

            n = length(self.selectedWidgetKeys);
            nodes = cell(1, n);
            nodeKeys = zeros(1, n);

            for ii = 1:n
                wKey = self.selectedWidgetKeys(ii);
                widget = self.widgetList{wKey};
                if ~isempty(widget.boundNodeKey)
                    nodes{ii} = self.nodeList{widget.boundNodeKey};
                    nodeKeys(ii) = widget.boundNodeKey;
                end
            end
        end

        function selectWidget(self, widgetKey, addToSelection)
            % SELECTWIDGET Select a widget (and its node)

            if nargin < 3
                addToSelection = false;
            end

            % Deselect previous if not adding
            if ~addToSelection
                for ii = 1:length(self.selectedWidgetKeys)
                    wKey = self.selectedWidgetKeys(ii);
                    if wKey <= length(self.widgetList)
                        self.widgetList{wKey}.showHighlight(false);
                    end
                end
                self.selectedWidgetKeys = [];
            end

            % Select new widget
            if widgetKey > 0 && widgetKey <= length(self.widgetList)
                self.widgetList{widgetKey}.showHighlight(true);
                self.selectedWidgetKeys(end+1) = widgetKey;
            end

            % Fire callback
            self.fireNodesSelectedFcn();
        end

        %% Event Handlers
        function respondToWidgetLabelClick(self, widgetKey, event)
            % Handle label click - select node

            % Check for shift-click (add to selection)
            addToSelection = false;
            if isprop(event, 'Modifier')
                addToSelection = any(strcmp(event.Modifier, 'shift'));
            end

            self.selectWidget(widgetKey, addToSelection);
        end

        function respondToWidgetExpanderClick(self, widgetKey, ~)
            % Handle expand/collapse click

            widget = self.widgetList{widgetKey};
            if ~isempty(widget.boundNodeKey)
                node = self.nodeList{widget.boundNodeKey};
                node.isExpanded = ~node.isExpanded;
                self.draw();
                self.fireNodesExpandedFcn();
            end
        end

        function respondToWidgetCheckboxClick(self, widgetKey, ~)
            % Handle checkbox click - toggle selection

            widget = self.widgetList{widgetKey};
            if ~isempty(widget.boundNodeKey)
                node = self.nodeList{widget.boundNodeKey};
                node.setChecked(~node.isChecked);
                self.draw();
                self.fireNodesCheckedFcn();
            end
        end

        function onKeyPress(self, event)
            % ONKEYPRESS Handle keyboard navigation

            if isempty(self.selectedWidgetKeys)
                return;
            end

            switch event.Key
                case 'uparrow'
                    self.navigateSelection(-1, event.Modifier);
                case 'downarrow'
                    self.navigateSelection(1, event.Modifier);
                case 'leftarrow'
                    self.collapseSelected();
                case 'rightarrow'
                    self.expandSelected();
                case 'f'
                    self.toggleSelectedCheck();
                case 'space'
                    self.toggleSelectedCheck();
            end
        end

        function navigateSelection(self, direction, modifier)
            % NAVIGATESELECTION Move selection up/down

            if isempty(self.selectedWidgetKeys)
                return;
            end

            currentKey = self.selectedWidgetKeys(end);
            widget = self.widgetList{currentKey};

            if isempty(widget.drawIndex)
                return;
            end

            % Find widget at new position
            newDrawIndex = widget.drawIndex + direction;
            newDrawIndex = max(1, min(newDrawIndex, self.drawCount));

            % Find widget with that draw index
            for ii = 1:length(self.widgetList)
                w = self.widgetList{ii};
                if ~isempty(w.drawIndex) && w.drawIndex == newDrawIndex
                    addToSelection = any(strcmp(modifier, 'shift'));
                    self.selectWidget(ii, addToSelection);
                    break;
                end
            end
        end

        function expandSelected(self)
            % EXPANDSELECTED Expand selected nodes

            [nodes, ~] = self.getSelectedNodes();
            for ii = 1:length(nodes)
                if ~isempty(nodes{ii}) && nodes{ii}.numChildren() > 0
                    nodes{ii}.isExpanded = true;
                end
            end
            self.draw();
            self.fireNodesExpandedFcn();
        end

        function collapseSelected(self)
            % COLLAPSESELECTED Collapse selected nodes

            [nodes, ~] = self.getSelectedNodes();
            for ii = 1:length(nodes)
                if ~isempty(nodes{ii})
                    nodes{ii}.isExpanded = false;
                end
            end
            self.draw();
            self.fireNodesExpandedFcn();
        end

        function toggleSelectedCheck(self)
            % TOGGLESELECTEDCHECK Toggle check state of selected nodes

            [nodes, ~] = self.getSelectedNodes();
            for ii = 1:length(nodes)
                if ~isempty(nodes{ii})
                    nodes{ii}.setChecked(~nodes{ii}.isChecked);
                end
            end
            self.draw();
            self.fireNodesCheckedFcn();
        end

        %% Callback Firing
        function fireNodesSelectedFcn(self)
            if ~isempty(self.nodesSelectedFcn)
                self.fireCallback(self.nodesSelectedFcn);
            end
        end

        function fireNodesExpandedFcn(self)
            if ~isempty(self.nodesExpandedFcn)
                self.fireCallback(self.nodesExpandedFcn);
            end
        end

        function fireNodesCheckedFcn(self)
            if ~isempty(self.nodesCheckedFcn)
                self.fireCallback(self.nodesCheckedFcn);
            end
        end

        function fireNodeBecameCheckedFcn(self, node)
            if ~isempty(self.nodeBecameCheckedFcn)
                cb = self.nodeBecameCheckedFcn;
                if iscell(cb)
                    feval(cb{1}, node, cb{2:end});
                else
                    feval(cb, node);
                end
            end
        end

        function fireCallback(self, cb)
            % FIRECALLBACK Execute a callback

            if iscell(cb)
                if length(cb) > 1
                    feval(cb{1}, self, cb{2:end});
                else
                    feval(cb{1}, self);
                end
            else
                feval(cb, self);
            end
        end
    end
end
