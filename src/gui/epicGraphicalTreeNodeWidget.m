classdef epicGraphicalTreeNodeWidget < handle
    % GRAPHICALTREENODEWIDGET Reusable visual widget for tree nodes
    %
    % Each widget can be bound/unbound to different epicGraphicalTreeNode objects
    % to efficiently render large trees. Uses a widget pool pattern where
    % widgets are pre-allocated and reused during drawing.

    properties
        tree                    % Reference to parent epicGraphicalTree
        axes                    % Parent axes
        selfKey                 % This widget's key in tree.widgetList
        boundNodeKey            % Currently bound node's key (or empty)
        drawIndex               % Position in current draw order

        inset = 3               % Horizontal indentation per depth level
        downset = 1.5           % Vertical spacing between rows
        position                % [x y] position

        group                   % hggroup containing all graphics
        expandBox               % graphicalCheckBox for expand/collapse
        checkBox                % graphicalCheckBox for selection
        nameText                % Text handle for node name
    end

    methods
        function self = epicGraphicalTreeNodeWidget(tree)
            % Constructor
            %
            % Usage:
            %   widget = epicGraphicalTreeNodeWidget(tree)

            if nargin < 1
                return
            end

            self.tree = tree;

            % Register with tree
            tree.widgetList{end+1} = self;
            self.selfKey = length(tree.widgetList);

            % Set axes (triggers widget building)
            self.axes = tree.axes;
        end

        function delete(self)
            % Destructor - clean up graphics
            if ~isempty(self.group) && ishandle(self.group)
                delete(self.group);
            end
        end

        function buildWidgets(self)
            % BUILDWIDGETS Create the graphics objects

            % Main container group
            self.group = hggroup('Parent', self.axes, 'Visible', 'off');
            gTree = self.tree;

            % Text label for node name
            self.nameText = text( ...
                'BackgroundColor', 'none', ...
                'Margin', 1, ...
                'Editing', 'off', ...
                'FontName', 'Courier', ...
                'FontSize', 9, ...
                'LineStyle', '-', ...
                'LineWidth', 1, ...
                'Interpreter', 'none', ...
                'Units', 'data', ...
                'Selected', 'off', ...
                'SelectionHighlight', 'off', ...
                'VerticalAlignment', 'middle', ...
                'HorizontalAlignment', 'left', ...
                'HitTest', 'on', ...
                'ButtonDownFcn', @(obj,evt) gTree.respondToWidgetLabelClick(self.selfKey, evt), ...
                'Parent', self.group);

            % Expand/collapse box
            self.expandBox = graphicalCheckBox(self.group);
            self.expandBox.textColor = [0 0 0];
            self.expandBox.edgeColor = 'none';
            self.expandBox.backgroundColor = [1 1 1] * 0.75;
            self.expandBox.checkedSymbol = 'v';      % Expanded
            self.expandBox.uncheckedSymbol = '>';    % Collapsed
            self.expandBox.altCheckedSymbol = ' ';   % No children
            self.expandBox.callback = {@epicGraphicalTreeNodeWidget.expanderCallback, self.selfKey, gTree};

            % Selection checkbox
            self.checkBox = graphicalCheckBox(self.group);
            self.checkBox.textColor = [0 0 0];
            self.checkBox.edgeColor = [1 1 1] * 0.25;
            self.checkBox.backgroundColor = [1 1 1] * 0.75;
            self.checkBox.checkedSymbol = 'F';       % Fully checked
            self.checkBox.uncheckedSymbol = ' ';     % Unchecked
            self.checkBox.altCheckedSymbol = 'f';    % Partially checked
            self.checkBox.callback = {@epicGraphicalTreeNodeWidget.checkboxCallback, self.selfKey, gTree};
        end

        function bindNode(self, drawCount)
            % BINDNODE Bind this widget to display a node
            %
            % Usage:
            %   widget.bindNode(drawIndex)

            self.drawIndex = drawCount;
            node = self.tree.nodeList{self.boundNodeKey};

            % Position based on draw order and depth
            self.setPositions(drawCount, node.depth);

            % Update appearance from node
            set(self.nameText, ...
                'String', node.name, ...
                'Color', node.textColor, ...
                'BackgroundColor', node.textBackgroundColor);

            % Show the widget
            set(self.group, 'Visible', 'on');

            % Update expand box
            self.expandBox.isAlternateChecked = (node.numChildren() == 0);
            self.expandBox.isChecked = node.isExpanded;

            % Update check box
            self.checkBox.isAlternateChecked = self.partialSelection();
            self.checkBox.isChecked = node.isChecked;
        end

        function unbindNode(self)
            % UNBINDNODE Unbind this widget (hide it)

            self.boundNodeKey = [];
            self.drawIndex = [];
            if ~isempty(self.group) && ishandle(self.group)
                set(self.group, 'Visible', 'off');
            end
        end

        function setPositions(self, row, col)
            % SETPOSITIONS Set position based on row (draw index) and column (depth)

            pos = [col * self.inset, (row - 0.5) * self.downset];
            self.position = pos;
            self.expandBox.position = pos;
            set(self.nameText, 'Position', pos + [4 0]);
            self.checkBox.position = pos + [2 0];
        end

        function showHighlight(self, isHighlighted)
            % SHOWHIGHLIGHT Highlight/unhighlight this widget

            if isHighlighted
                set(self.nameText, 'EdgeColor', [0 0 1]);
            else
                set(self.nameText, 'EdgeColor', 'none');
            end
        end

        function showBusy(self, isBusy)
            % SHOWBUSY Show busy indicator

            if isBusy
                set(self.nameText, 'String', '...');
            elseif ~isempty(self.boundNodeKey)
                node = self.tree.nodeList{self.boundNodeKey};
                set(self.nameText, 'String', node.name);
            end
        end

        function isPartial = partialSelection(self)
            % PARTIALSELECTION Check if this node has partial selection

            node = self.tree.nodeList{self.boundNodeKey};
            if node.numDescendants > 0
                isPartial = node.isChecked && ...
                    (node.numCheckedDescendants / node.numDescendants < 1);
            else
                isPartial = false;
            end
        end

        function set.axes(self, ax)
            % Set axes and build widgets if needed
            self.axes = ax;
            if ~isempty(self.group) && ishandle(self.group)
                set(self.group, 'Parent', ax);
            else
                self.buildWidgets();
            end
        end
    end

    methods (Static)
        function expanderCallback(checkbox, event, widgetKey, tree)
            % Callback for expand/collapse clicks
            tree.respondToWidgetExpanderClick(widgetKey, event);
        end

        function checkboxCallback(checkbox, event, widgetKey, tree)
            % Callback for selection checkbox clicks
            tree.respondToWidgetCheckboxClick(widgetKey, event);
        end
    end
end
