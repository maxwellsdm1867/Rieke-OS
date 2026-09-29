classdef graphicalCheckBox < handle
    % GRAPHICALCHECKBOX Simple checkbox widget for tree visualization
    %
    % Used by graphicalTreeNodeWidget for expand/collapse and selection.
    % Renders as a text element with symbols for checked/unchecked states.

    properties
        parent              % Parent graphics object (hggroup)
        position = [0 0.5]  % [x y] position in data units
        textColor = [0 0 0]
        edgeColor = [0 0 0]
        backgroundColor = 'none'

        isChecked = false
        isAlternateChecked = false

        % Callback: feval(callback{1}, self, event, callback{2:end})
        callback = []
    end

    properties (Hidden = true)
        box                         % Text handle for rendering
        checkedSymbol = 'X'
        uncheckedSymbol = ' '
        altCheckedSymbol = '/'
    end

    methods
        function self = graphicalCheckBox(parent)
            % Constructor
            %
            % Usage:
            %   cb = graphicalCheckBox(parentGroup)

            if nargin < 1
                return
            end

            self.parent = parent;

            % Create text element for checkbox
            self.box = text( ...
                'Margin', 1, ...
                'Editing', 'off', ...
                'FontName', 'Courier', ...
                'FontSize', 9, ...
                'Interpreter', 'none', ...
                'Units', 'data', ...
                'Selected', 'off', ...
                'SelectionHighlight', 'off', ...
                'HorizontalAlignment', 'left', ...
                'VerticalAlignment', 'middle', ...
                'HitTest', 'on', ...
                'ButtonDownFcn', @(obj,evt) self.respondToClick(obj, evt), ...
                'Parent', parent);

            % Set initial appearance
            self.updateAppearance();
        end

        function delete(self)
            % Destructor - clean up graphics
            if ~isempty(self.box) && ishandle(self.box)
                delete(self.box);
            end
        end

        %% Property Set Methods
        function set.parent(self, parent)
            self.parent = parent;
            if ~isempty(self.box) && ishandle(self.box)
                set(self.box, 'Parent', parent);
            end
        end

        function set.position(self, pos)
            self.position = pos;
            if ~isempty(self.box) && ishandle(self.box)
                set(self.box, 'Position', pos);
            end
        end

        function set.textColor(self, color)
            self.textColor = color;
            if ~isempty(self.box) && ishandle(self.box)
                set(self.box, 'Color', color);
            end
        end

        function set.edgeColor(self, color)
            self.edgeColor = color;
            if ~isempty(self.box) && ishandle(self.box)
                set(self.box, 'EdgeColor', color);
            end
        end

        function set.backgroundColor(self, color)
            self.backgroundColor = color;
            if ~isempty(self.box) && ishandle(self.box)
                set(self.box, 'BackgroundColor', color);
            end
        end

        function set.isChecked(self, isChecked)
            self.isChecked = isChecked;
            self.updateSymbol();
        end

        function set.isAlternateChecked(self, isAlt)
            self.isAlternateChecked = isAlt;
            self.updateSymbol();
        end

        %% Internal Methods
        function updateAppearance(self)
            % Update all visual properties
            if isempty(self.box) || ~ishandle(self.box)
                return;
            end

            set(self.box, ...
                'Position', self.position, ...
                'Color', self.textColor, ...
                'EdgeColor', self.edgeColor, ...
                'BackgroundColor', self.backgroundColor);
            self.updateSymbol();
        end

        function updateSymbol(self)
            % Update the displayed symbol based on state
            if isempty(self.box) || ~ishandle(self.box)
                return;
            end

            if self.isAlternateChecked
                set(self.box, 'String', self.altCheckedSymbol);
            elseif self.isChecked
                set(self.box, 'String', self.checkedSymbol);
            else
                set(self.box, 'String', self.uncheckedSymbol);
            end
        end

        function respondToClick(self, ~, event)
            % Handle click event - toggle checked state
            self.isChecked = ~self.isChecked;
            drawnow

            % Fire callback
            cb = self.callback;
            if ~isempty(cb)
                if iscell(cb)
                    if length(cb) > 1
                        feval(cb{1}, self, event, cb{2:end});
                    else
                        feval(cb{1}, self, event);
                    end
                else
                    feval(cb, self, event);
                end
            end
        end
    end
end
