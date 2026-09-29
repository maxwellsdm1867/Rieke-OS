classdef epicGraphicalTreeNode < handle
    % GRAPHICALTREENODE Node for tree visualization
    %
    % Represents a node in the graphicalTree visualization system.
    % Separate from epicTreeTools (the data structure) to allow GUI-specific
    % state like expansion, selection display, etc.

    properties
        tree                    % Reference to parent graphicalTree
        selfKey                 % This node's key in tree.nodeList
        parentKey               % Parent node's key
        childrenKeys = []       % Array of child node keys

        depth = 0               % Depth in tree (0 = root)
        numDescendants = 0      % Total descendant count
        numCheckedDescendants = 0

        name = 'no name'        % Display name
        textColor = [0 0 0]     % Text color [r g b]
        textBackgroundColor = 'none'  % Background color

        userData = []           % Link to epicTreeTools node

        isExpanded = false      % Is this node expanded in GUI?
        isChecked = false       % Is this node checked (selected)?

        % When becoming checked, should children become checked too?
        recursiveCheck = true

        % Does this node count in checked descendant calculations?
        isVisibleDescendant = true
    end

    methods
        function self = epicGraphicalTreeNode(name, isVisibleDescendant)
            % Constructor
            %
            % Usage:
            %   node = epicGraphicalTreeNode('NodeName')
            %   node = epicGraphicalTreeNode('NodeName', false)  % invisible

            if nargin > 0
                self.name = name;
            end
            if nargin > 1
                self.isVisibleDescendant = isVisibleDescendant;
            end
        end

        function parent = getParent(self)
            % GETPARENT Get parent node
            if ~isempty(self.parentKey) && ~isempty(self.tree)
                parent = self.tree.nodeList{self.parentKey};
            else
                parent = [];
            end
        end

        function addChild(self, child)
            % ADDCHILD Add a child node
            self.childrenKeys(end+1) = child.selfKey;
            if child.isVisibleDescendant
                self.incrementDescendants();
            end
        end

        function child = getChild(self, idx)
            % GETCHILD Get child node by index (1-based)
            if idx > length(self.childrenKeys)
                child = [];
            else
                child = self.tree.nodeList{self.childrenKeys(idx)};
            end
        end

        function n = numChildren(self)
            % NUMCHILDREN Get number of children
            n = length(self.childrenKeys);
        end

        function incrementDescendants(self)
            % INCREMENTDESCENDANTS Increment descendant count up the tree
            self.numDescendants = self.numDescendants + 1;
            parent = self.getParent();
            if ~isempty(parent)
                parent.incrementDescendants();
            end
        end

        function incrementCheckedDescendants(self, diff)
            % INCREMENTCHECKEDDESCENDANTS Update checked count up the tree
            self.numCheckedDescendants = self.numCheckedDescendants + diff;
            parent = self.getParent();
            if ~isempty(parent)
                parent.incrementCheckedDescendants(diff);
            end
        end

        function setChecked(self, isChecked)
            % SETCHECKED Set checked state (recursive down, update up)

            checkDiff = isChecked - self.isChecked;
            ncdWas = self.numCheckedDescendants;
            ncd = self.becomeChecked(isChecked);

            diff = self.isVisibleDescendant * checkDiff + ncd - ncdWas;
            parent = self.getParent();
            if ~isempty(parent) && diff ~= 0
                parent.incrementCheckedDescendants(diff);
            end
        end

        function ncd = becomeChecked(self, isChecked)
            % BECOMECHECKED Internal method to set checked state

            checkChanged = xor(self.isChecked, isChecked);
            self.isChecked = isChecked;

            % Fire callback if state changed
            if checkChanged && ~isempty(self.tree)
                self.tree.fireNodeBecameCheckedFcn(self);
            end

            % Handle children
            ncd = 0;
            if self.numChildren() > 0
                if self.recursiveCheck
                    % Recursively set children
                    for ii = 1:self.numChildren()
                        child = self.getChild(ii);
                        ncd = ncd + (isChecked && child.isVisibleDescendant) + child.becomeChecked(isChecked);
                    end
                    self.numCheckedDescendants = ncd;
                else
                    % Only count, don't set
                    ncd = self.countCheckedDescendants();
                end
            end
        end

        function ncd = countCheckedDescendants(self)
            % COUNTCHECKEDDESCENDANTS Count checked descendants

            if self.numChildren() > 0
                ncd = 0;
                for ii = 1:self.numChildren()
                    child = self.getChild(ii);
                    ncd = ncd + (child.isChecked && child.isVisibleDescendant) + child.countCheckedDescendants();
                end
            else
                ncd = 0;
            end
            self.numCheckedDescendants = ncd;
        end

        function includeUnburied(self)
            % INCLUDEUNBURIED Add this node to draw list if visible

            % Tell tree to include this node in the current draw
            self.tree.includeInDraw(self);

            % Recurse on children if expanded
            if self.isExpanded && self.numChildren() > 0
                for ii = 1:self.numChildren()
                    child = self.getChild(ii);
                    child.includeUnburied();
                end
            end
        end
    end
end
