classdef CompatibilityList < handle
    % COMPATIBILITYLIST Wrapper to mimic Java CompatibilityList for tree navigation
    %
    % This class provides Java-style access patterns for tree children:
    %   node.children.length        - number of children
    %   node.children.elements(idx) - get child by index (1-based)
    %
    % Usage:
    %   % In epicTreeTools, children is a CompatibilityList:
    %   for i = 1:node.children.length
    %       child = node.children.elements(i);
    %       % process child
    %   end
    %
    % This matches the Java pattern from riekesuite:
    %   for idx = 1:rootNode.children.length
    %       cellTypeNode = rootNode.children.elements(idx);
    %   end
    %
    % See also: epicTreeTools

    properties (SetAccess = private)
        items = {}     % Cell array of items
    end

    properties (Dependent)
        length         % Number of items (read-only)
    end

    methods
        function obj = CompatibilityList(items)
            % Constructor
            %
            % Usage:
            %   list = CompatibilityList(cellArray)
            %   list = CompatibilityList()

            if nargin > 0
                if iscell(items)
                    obj.items = items(:);
                else
                    obj.items = {items};
                end
            else
                obj.items = {};
            end
        end

        function n = get.length(obj)
            % Get number of items
            n = numel(obj.items);
        end

        function item = elements(obj, idx)
            % ELEMENTS Get item by 1-based index
            %
            % Usage:
            %   item = list.elements(idx)
            %
            % Equivalent to Java: children.elements(int index)

            if nargin < 2
                % Return all elements as cell array
                item = obj.items;
            else
                if idx < 1 || idx > length(obj.items)
                    error('CompatibilityList:InvalidIndex', ...
                        'Index %d out of range [1, %d]', idx, length(obj.items));
                end
                item = obj.items{idx};
            end
        end

        function item = firstValue(obj)
            % FIRSTVALUE Get first item
            %
            % Usage:
            %   first = list.firstValue()
            %
            % Equivalent to Java: CompatibilityList.firstValue()

            if isempty(obj.items)
                item = [];
            else
                item = obj.items{1};
            end
        end

        function item = valueByIndex(obj, idx)
            % VALUEBYINDEX Get item by index (alias for elements)
            %
            % Usage:
            %   item = list.valueByIndex(idx)
            %
            % Equivalent to Java: CompatibilityList.valueByIndex(int)

            item = obj.elements(idx);
        end

        function append(obj, item)
            % APPEND Add item to end of list
            %
            % Usage:
            %   list.append(item)

            obj.items{end+1} = item;
        end

        function setItems(obj, items)
            % SETITEMS Replace all items
            %
            % Usage:
            %   list.setItems(cellArray)

            if iscell(items)
                obj.items = items(:);
            else
                obj.items = {items};
            end
        end

        function isEmpty = isempty(obj)
            % ISEMPTY Check if list is empty
            isEmpty = isempty(obj.items);
        end

        function disp(obj)
            % Display list info
            fprintf('CompatibilityList: %d items\n', length(obj.items));
        end

        function varargout = subsref(obj, s)
            % SUBSREF Custom subscript reference to support () indexing
            %
            % This allows list(idx) as alternative to list.elements(idx)

            switch s(1).type
                case '()'
                    if length(s(1).subs) == 1
                        idx = s(1).subs{1};
                        if isnumeric(idx) && isscalar(idx)
                            varargout{1} = obj.elements(idx);
                            return;
                        elseif strcmp(idx, ':')
                            varargout{1} = obj.items;
                            return;
                        end
                    end
                    error('CompatibilityList:InvalidSubscript', ...
                        'Only single numeric index or : supported');

                case '.'
                    % Handle property/method access normally
                    [varargout{1:nargout}] = builtin('subsref', obj, s);

                case '{}'
                    % Also support {} indexing like cell arrays
                    if length(s(1).subs) == 1
                        idx = s(1).subs{1};
                        if isnumeric(idx)
                            varargout{1} = obj.items{idx};
                            return;
                        end
                    end
                    error('CompatibilityList:InvalidSubscript', ...
                        'Only single numeric index supported for {} indexing');
            end
        end
    end
end
