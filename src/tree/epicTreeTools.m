classdef epicTreeTools < handle
    % EPICTREETOOLS Hierarchical tree structure for organizing epoch data
    %
    % This class provides tree-based organization and navigation for epoch
    % data, with controlled access to node custom properties.
    %
    % NAVIGATION PATTERNS:
    % ====================
    % Navigate DOWN (to children):
    %   n = node.childrenLength()          % Number of children
    %   child = node.childAt(idx)          % Get child by index (1-based)
    %   child = node.childBySplitValue(v)  % Find child by split value
    %   leaves = node.leafNodes()          % Get all leaf nodes below
    %
    % Navigate UP (to parents):
    %   parent = node.parent               % Direct parent
    %   ancestor = node.parentAt(3)        % Go up 3 levels
    %   root = node.getRoot()              % Get root node
    %   d = node.depth()                   % Levels from root (root=0)
    %
    % Loop over children:
    %   for i = 1:node.childrenLength()
    %       child = node.childAt(i);
    %       % process child
    %   end
    %
    % CONTROLLED ACCESS (put/get custom data):
    % ========================================
    % Store analysis results at a node:
    %   results.ImageSum = ImageResp;
    %   results.NLI = NLI;
    %   node.putCustom('results', results);
    %
    % Retrieve stored results:
    %   results = node.getCustom('results');
    %   if ~isempty(results)
    %       ImageSum = results.ImageSum;
    %   end
    %
    % Check if key exists:
    %   if node.hasCustom('results')
    %       % process
    %   end
    %
    % TYPICAL ANALYSIS WORKFLOW:
    % ==========================
    %   % Navigate tree and analyze
    %   for i = 1:rootNode.childrenLength()
    %       cellTypeNode = rootNode.childAt(i);
    %       cellType = cellTypeNode.splitValue;
    %
    %       for j = 1:cellTypeNode.childrenLength()
    %           dateNode = cellTypeNode.childAt(j);
    %
    %           for k = 1:dateNode.childrenLength()
    %               cellNode = dateNode.childAt(k);
    %
    %               % Run analysis
    %               epochs = cellNode.getAllEpochs(true);  % selected only
    %               [data, fs] = getSelectedData(epochs, 'Amp1');
    %               results = analyzeData(data);
    %
    %               % Store results at cell level
    %               cellNode.putCustom('results', results);
    %           end
    %       end
    %   end
    %
    %   % Later: query stored results
    %   results = cellNode.getCustom('results');
    %
    % Properties:
    %   splitKey    - Key path used for this split (empty for root)
    %   splitValue  - Value at this split (empty for root)
    %   children    - Cell array of child epicTreeTools nodes
    %   epochList   - Cell array of epochs (only for leaf nodes)
    %   isLeaf      - True if this is a leaf node
    %   parent      - Reference to parent node (empty for root)
    %
    % See also: loadEpicTreeData, getSelectedData, CompatibilityList

    properties
        splitKey = ''           % Key path used for splitting at this node
        splitValue = []         % Value at this split
        children = {}           % Cell array of child epicTreeTools nodes
        epochList = {}          % Cell array of epochs (leaf nodes only)
        isLeaf = false          % True if this is a leaf node
        parent = []             % Reference to parent node
        allEpochs = {}          % Flattened epoch list (root only)
        treeData = []           % Original hierarchical data (root only)
        sourceFile = ''         % Path to source .mat file (for .ugm file discovery)
        h5File = ''             % Path to H5 file for lazy loading (set on root, inherited by children)
    end

    properties (SetAccess = private)
        % Custom properties for GUI state (replaces Java HashMap)
        % PROTECTED - use putCustom()/getCustom() for access
        % - isSelected: Selection state for this tree node
        % - isExample: Flag to mark this node as an example (highlights in GUI)
        % - display: Struct with name, color, backgroundColor for rendering
        % - results: Struct to cache analysis results on this node
        custom = struct('isSelected', true, 'isExample', false, ...
                       'display', struct('name', '', 'color', [0 0 0], 'backgroundColor', 'none'), ...
                       'results', struct())
    end

    methods
        function obj = epicTreeTools(dataOrParent, varargin)
            % Constructor - create epicTreeTools from data or as child node
            %
            % Usage:
            %   tree = epicTreeTools(treeData)  % Create root from loaded data
            %   tree = epicTreeTools(parent)    % Create child node
            %   tree = epicTreeTools()          % Create empty node
            %   tree = epicTreeTools(treeData, 'LoadUserMetadata', 'auto')
            %   tree = epicTreeTools(treeData, 'LoadUserMetadata', 'latest')
            %   tree = epicTreeTools(treeData, 'LoadUserMetadata', 'none')
            %   tree = epicTreeTools(treeData, 'LoadUserMetadata', '/path/to/file.ugm')
            %
            % Name-Value Arguments:
            %   LoadUserMetadata - Controls .ugm file loading:
            %     'auto' (default) - Auto-load latest .ugm if exists (silent if not found)
            %     'latest'         - Load latest .ugm, error if none exists
            %     'none'           - Skip loading (all epochs selected)
            %     '/path/file.ugm' - Load specific .ugm file

            if nargin == 0
                return;
            end

            if isa(dataOrParent, 'epicTreeTools')
                % Creating child node - don't parse varargin for LoadUserMetadata
                obj.parent = dataOrParent;
            elseif isstruct(dataOrParent)
                % Creating root from data
                obj.treeData = dataOrParent;
                obj.allEpochs = obj.extractAllEpochs(dataOrParent);

                % Tag each epoch with unique index for tracking across tree structure
                % This allows setSelected to efficiently update epochs in root.allEpochs
                for i = 1:length(obj.allEpochs)
                    obj.allEpochs{i}.epochIndex = i;
                end

                obj.epochList = obj.allEpochs;
                obj.isLeaf = true;  % Until buildTree is called

                % Capture source file path if available in data
                if isfield(dataOrParent, 'source_file')
                    obj.sourceFile = dataOrParent.source_file;
                end

                % Auto-resolve H5 file from epicTreeConfig
                try
                    h5Dir = epicTreeConfig('h5_dir');
                    if ~isempty(h5Dir) && ~isempty(obj.sourceFile)
                        [~, expName, ~] = fileparts(obj.sourceFile);
                        candidateH5 = fullfile(h5Dir, [expName '.h5']);
                        if exist(candidateH5, 'file')
                            obj.h5File = candidateH5;
                        end
                    elseif ~isempty(h5Dir)
                        % Try to find H5 from experiment name in data
                        if isfield(dataOrParent, 'experiments')
                            exps = dataOrParent.experiments;
                            exp = epicTreeTools.getElement(exps, 1);
                            if isfield(exp, 'exp_name')
                                candidateH5 = fullfile(h5Dir, [exp.exp_name '.h5']);
                                if exist(candidateH5, 'file')
                                    obj.h5File = candidateH5;
                                end
                            end
                        end
                    end
                catch
                    % epicTreeConfig may not be available — no H5 auto-resolve
                end

                % Parse optional arguments
                p = inputParser;
                p.KeepUnmatched = true;  % Allow unknown params
                addParameter(p, 'LoadUserMetadata', 'auto', @(x) ischar(x) || isstring(x));
                addParameter(p, 'H5File', '', @(x) ischar(x) || isstring(x));
                parse(p, varargin{:});

                % Explicit H5File overrides auto-resolved
                if ~isempty(p.Results.H5File)
                    obj.h5File = char(p.Results.H5File);
                end

                loadOption = char(p.Results.LoadUserMetadata);

                if strcmp(loadOption, 'auto')
                    % Auto-load latest .ugm if exists (silent if none found)
                    if ~isempty(obj.sourceFile)
                        ugmFile = epicTreeTools.findLatestUGM(obj.sourceFile);
                        if ~isempty(ugmFile)
                            fprintf('Auto-loading selection mask: %s\n', ugmFile);
                            obj.loadUserMetadata(ugmFile);  % This prints its own warning
                        end
                    end
                elseif strcmp(loadOption, 'latest')
                    % Load latest, error if none exists
                    if isempty(obj.sourceFile)
                        error('epicTreeTools:NoSourceFile', ...
                            'Cannot find .ugm files: sourceFile not set. Set sourceFile property or pass data with source_file field.');
                    end
                    ugmFile = epicTreeTools.findLatestUGM(obj.sourceFile);
                    if isempty(ugmFile)
                        error('epicTreeTools:NoUGMFiles', ...
                            'No .ugm files found for: %s', obj.sourceFile);
                    end
                    obj.loadUserMetadata(ugmFile);
                elseif strcmp(loadOption, 'none')
                    % Skip loading, all epochs selected by default (already the case)
                else
                    % Assume it's a filename path
                    if ~obj.loadUserMetadata(loadOption)
                        warning('epicTreeTools:UGMLoadFailed', ...
                            'Failed to load user metadata from: %s', loadOption);
                    end
                end
            end
        end

        function buildTree(obj, keyPaths)
            % BUILDTREE Build hierarchical tree by grouping on key paths
            %
            % Usage:
            %   tree.buildTree({'cellInfo.type', 'protocolSettings.contrast'})
            %
            % Inputs:
            %   keyPaths - Cell array of key path strings for splitting
            %
            % Description:
            %   Reorganizes the flat epoch list into a hierarchical tree
            %   structure. Each key path creates a level in the tree.

            if isempty(obj.allEpochs) && ~isempty(obj.epochList)
                obj.allEpochs = obj.epochList;
            end

            if isempty(obj.allEpochs)
                warning('epicTreeTools:NoData', 'No epochs to build tree from');
                return;
            end

            % Build tree recursively
            obj.buildTreeRecursive(obj.allEpochs, keyPaths);
        end

        function buildTreeWithSplitters(obj, splitters)
            % BUILDTREEWITHSPLITTERS Build tree using custom splitter functions
            %
            % Usage:
            %   tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType, ...
            %                                @epicTreeTools.splitOnContrast})
            %
            %   % Or mix key paths and function handles:
            %   tree.buildTreeWithSplitters({'cellInfo.type', ...
            %                                @epicTreeTools.splitOnF1F2Phase})
            %
            % Inputs:
            %   splitters - Cell array of splitters. Each can be:
            %               - String: key path (e.g., 'parameters.contrast')
            %               - Function handle: @(epoch) -> split value
            %
            % Description:
            %   Like buildTree but accepts function handles for custom splitting.
            %   Function handles should take an epoch struct and return a value.

            if isempty(obj.allEpochs) && ~isempty(obj.epochList)
                obj.allEpochs = obj.epochList;
            end

            if isempty(obj.allEpochs)
                warning('epicTreeTools:NoData', 'No epochs to build tree from');
                return;
            end

            % Build tree recursively with splitters
            obj.buildTreeWithSplittersRecursive(obj.allEpochs, splitters);
        end

        function node = childBySplitValue(obj, value)
            % CHILDBYSPLITVALUE Find child node by its split value
            %
            % Usage:
            %   child = tree.childBySplitValue('OnP')
            %   child = tree.childBySplitValue(0.5)
            %   child = tree.childBySplitValue('SingleSpot')  % matches 'edu...SingleSpot'
            %
            % First tries exact match. If no exact match and value is a
            % string, falls back to substring match (contains).
            % Returns empty [] if not found.

            node = [];

            % First pass: exact match
            for i = 1:length(obj.children)
                child = obj.children{i};
                if obj.valuesEqual(child.splitValue, value)
                    node = child;
                    return;
                end
            end

            % Second pass: substring match for strings
            if (ischar(value) || isstring(value))
                for i = 1:length(obj.children)
                    child = obj.children{i};
                    if (ischar(child.splitValue) || isstring(child.splitValue)) ...
                            && contains(string(child.splitValue), string(value))
                        node = child;
                        return;
                    end
                end
            end
        end

        function leaves = leafNodes(obj)
            % LEAFNODES Get all leaf nodes under this node
            %
            % Usage:
            %   leaves = tree.leafNodes()
            %
            % Returns cell array of epicTreeTools leaf nodes

            leaves = {};

            if obj.isLeaf
                leaves = {obj};
                return;
            end

            for i = 1:length(obj.children)
                childLeaves = obj.children{i}.leafNodes();
                leaves = [leaves; childLeaves(:)];
            end
        end

        function sv = splitValues(obj)
            % SPLITVALUES Get all split key-values from root to this node
            %
            % Usage:
            %   sv = node.splitValues()
            %
            % Returns struct with fields for each split key

            sv = struct();
            node = obj;

            while ~isempty(node)
                if ~isempty(node.splitKey) && ~isempty(node.splitValue)
                    fieldName = strrep(node.splitKey, '.', '_');
                    fieldName = matlab.lang.makeValidName(fieldName);
                    sv.(fieldName) = node.splitValue;
                end

                node = node.parent;
            end
        end

        function epochs = sortedBy(obj, keyPath)
            % SORTEDBY Return epochs sorted by key path value
            %
            % Usage:
            %   sorted = tree.sortedBy('protocolSettings.contrast')

            epochs = obj.epochList;
            if isempty(epochs)
                return;
            end

            % Extract values
            n = length(epochs);
            values = cell(n, 1);
            for i = 1:n
                values{i} = obj.getNestedValue(epochs{i}, keyPath);
            end

            % Sort
            [sortIdx, ~] = obj.sortValues(values);
            epochs = epochs(sortIdx);
        end

        function names = responseStreamNames(obj)
            % RESPONSESTREAMNAMES Get unique response stream names
            %
            % Usage:
            %   names = tree.responseStreamNames()

            names = obj.getStreamNames('responses');
        end

        function names = stimuliStreamNames(obj)
            % STIMULISTREAMNAMES Get unique stimulus stream names
            %
            % Usage:
            %   names = tree.stimuliStreamNames()

            names = obj.getStreamNames('stimuli');
        end

        function info = nodeInfo(obj)
            % NODEINFO Get comprehensive metadata summary for this node
            %
            % Returns a struct with all discoverable metadata from this
            % node's epochs — parameters, cell info, protocol info, etc.
            % Use this to see what parameters are available for splitting
            % or analysis, even if you didn't split on them.
            %
            % Usage:
            %   info = node.nodeInfo()
            %
            % Returns struct with:
            %   .epochCount      - Number of epochs
            %   .selectedCount   - Number of selected epochs
            %   .splitPath       - Path from root (string)
            %   .cellTypes       - Unique cell types
            %   .protocols       - Unique protocol names
            %   .parameterNames  - All parameter field names (union across epochs)
            %   .parameters      - Struct of unique values per parameter
            %   .responseStreams - Available response stream names
            %   .sampleRate      - Sample rate (from first epoch)

            info = struct();
            info.epochCount = obj.epochCount();
            info.selectedCount = obj.selectedCount();
            info.splitPath = obj.pathString();
            info.isLeaf = obj.isLeaf;

            epochs = obj.getAllEpochs(false);
            if isempty(epochs)
                return;
            end

            % Collect unique cell types
            cellTypes = {};
            for i = 1:length(epochs)
                ct = epicTreeTools.getNestedValue(epochs{i}, 'cellInfo.type');
                if ~isempty(ct)
                    ct = char(string(ct));
                    if ~any(strcmp(cellTypes, ct))
                        cellTypes{end+1} = ct;
                    end
                end
            end
            info.cellTypes = cellTypes;

            % Collect unique protocols
            protocols = {};
            for i = 1:length(epochs)
                prot = epicTreeTools.getNestedValue(epochs{i}, 'blockInfo.protocol_name');
                if ~isempty(prot)
                    prot = char(string(prot));
                    if ~any(strcmp(protocols, prot))
                        protocols{end+1} = prot;
                    end
                end
            end
            info.protocols = protocols;

            % Collect all parameter names and unique values
            paramNames = {};
            paramValues = struct();
            for i = 1:length(epochs)
                ep = epochs{i};
                if isfield(ep, 'parameters') && isstruct(ep.parameters)
                    fns = fieldnames(ep.parameters);
                    for j = 1:length(fns)
                        fn = fns{j};
                        if ~any(strcmp(paramNames, fn))
                            paramNames{end+1} = fn;
                        end
                        % Collect unique values
                        safeFn = matlab.lang.makeValidName(fn);
                        val = ep.parameters.(fn);
                        valStr = epicTreeTools.valueToString(val);
                        if ~isfield(paramValues, safeFn)
                            paramValues.(safeFn) = {valStr};
                        else
                            if ~any(strcmp(paramValues.(safeFn), valStr))
                                paramValues.(safeFn){end+1} = valStr;
                            end
                        end
                    end
                end
            end
            info.parameterNames = sort(paramNames);
            info.parameters = paramValues;

            % Response streams
            if obj.isLeaf
                info.responseStreams = obj.responseStreamNames();
            else
                % Use first leaf
                leaves = obj.leafNodes();
                if ~isempty(leaves)
                    info.responseStreams = leaves{1}.responseStreamNames();
                else
                    info.responseStreams = {};
                end
            end

            % Sample rate from first epoch
            if ~isempty(epochs) && isfield(epochs{1}, 'responses')
                resp = epicTreeTools.getResponseByName(epochs{1}, 'Amp1');
                if ~isempty(resp) && isfield(resp, 'sample_rate')
                    info.sampleRate = resp.sample_rate;
                else
                    info.sampleRate = [];
                end
            else
                info.sampleRate = [];
            end
        end

        function printInfo(obj)
            % PRINTINFO Print formatted metadata summary for this node
            %
            % Usage:
            %   node.printInfo()
            %
            % Displays: path, epoch counts, cell types, protocols,
            % parameter names with unique values.

            info = obj.nodeInfo();

            fprintf('\n=== Node Info: %s ===\n', info.splitPath);
            fprintf('  Epochs: %d (%d selected)\n', info.epochCount, info.selectedCount);
            fprintf('  Leaf: %s\n', string(info.isLeaf));

            if ~isempty(info.cellTypes)
                fprintf('  Cell types: %s\n', strjoin(info.cellTypes, ', '));
            end
            if ~isempty(info.protocols)
                fprintf('  Protocols: %s\n', strjoin(info.protocols, ', '));
            end
            if ~isempty(info.responseStreams)
                fprintf('  Response streams: %s\n', strjoin(info.responseStreams, ', '));
            end
            if ~isempty(info.sampleRate)
                fprintf('  Sample rate: %.0f Hz\n', double(info.sampleRate));
            end

            if ~isempty(info.parameterNames)
                fprintf('\n  Parameters (%d):\n', length(info.parameterNames));
                fns = fieldnames(info.parameters);
                for i = 1:length(fns)
                    vals = info.parameters.(fns{i});
                    if length(vals) <= 5
                        valStr = strjoin(string(vals), ', ');
                    else
                        valStr = sprintf('%s, ... (%d unique)', ...
                            strjoin(string(vals(1:3)), ', '), length(vals));
                    end
                    fprintf('    %s: [%s]\n', fns{i}, valStr);
                end
            end
            fprintf('\n');
        end

        function n = length(obj)
            % LENGTH Number of epochs in this node's epochList
            n = length(obj.epochList);
        end

        function epoch = elements(obj, idx)
            % ELEMENTS Get epoch by index (1-based)
            %
            % Usage:
            %   epoch = tree.elements(1)
            %   allEpochs = tree.elements()  % returns all

            if nargin < 2
                epoch = obj.epochList;
            else
                epoch = obj.epochList{idx};
            end
        end

        function disp(obj)
            % Display tree node info
            if obj.isLeaf
                fprintf('epicTreeTools (leaf): %d epochs\n', length(obj.epochList));
            else
                fprintf('epicTreeTools: %d children\n', length(obj.children));
            end
            if ~isempty(obj.splitKey)
                fprintf('  splitKey: %s\n', obj.splitKey);
                fprintf('  splitValue: %s\n', string(obj.splitValue));
            end
        end

        %% ================================================================
        % TREE NAVIGATION METHODS (from JAUIMODEL EpochTree interface)
        % ================================================================

        function child = child(obj, index)
            % CHILD Get child node by index (1-based)
            %
            % Usage:
            %   child = tree.child(1)  % Get first child
            %
            % Equivalent to Java: children(int index)

            if index < 1 || index > length(obj.children)
                error('epicTreeTools:InvalidIndex', 'Child index out of range');
            end
            child = obj.children{index};
        end

        function leaf = leafNode(obj, index)
            % LEAFNODE Get specific leaf node by index (1-based)
            %
            % Usage:
            %   leaf = tree.leafNode(1)  % Get first leaf
            %
            % Equivalent to Java: leafNodes(int index)

            leaves = obj.leafNodes();
            if index < 1 || index > length(leaves)
                error('epicTreeTools:InvalidIndex', 'Leaf index out of range');
            end
            leaf = leaves{index};
        end

        function value = splitValueByKey(obj, key)
            % SPLITVALUEBYKEY Get specific split value by key
            %
            % Usage:
            %   contrast = node.splitValueByKey('parameters.contrast')
            %
            % Equivalent to Java: splitValues(String key)

            sv = obj.splitValues();
            fieldName = strrep(key, '.', '_');
            fieldName = matlab.lang.makeValidName(fieldName);
            if isfield(sv, fieldName)
                value = sv.(fieldName);
            else
                value = [];
            end
        end

        function paths = splitKeyPaths(obj)
            % SPLITKEYPATHS Get array of all split key paths from root to this node
            %
            % Usage:
            %   paths = node.splitKeyPaths()
            %
            % Returns cell array of key path strings used for splitting.
            % Equivalent to Java: splitKeyPaths()

            paths = {};
            node = obj;

            while ~isempty(node)
                if ~isempty(node.splitKey)
                    paths = [{node.splitKey}; paths];
                end
                node = node.parent;
            end
        end

        function nodes = descendentsDepthFirst(obj)
            % DESCENDENTSDEPTHFIRST Get all descendant nodes in depth-first order
            %
            % Usage:
            %   allNodes = tree.descendentsDepthFirst()
            %
            % Equivalent to Java: descendentsDepthFirst()

            nodes = {};

            if obj.isLeaf
                nodes = {obj};
                return;
            end

            for i = 1:length(obj.children)
                childNodes = obj.children{i}.descendentsDepthFirst();
                nodes = [nodes; childNodes(:)];
            end
        end

        function epoch = firstValue(obj)
            % FIRSTVALUE Get first epoch in epoch list
            %
            % Usage:
            %   epoch = node.firstValue()
            %
            % Equivalent to Java: CompatabilityList.firstValue()

            if isempty(obj.epochList)
                epoch = [];
            else
                epoch = obj.epochList{1};
            end
        end

        function epoch = valueByIndex(obj, index)
            % VALUEBYINDEX Get epoch by index (alias for elements)
            %
            % Usage:
            %   epoch = node.valueByIndex(1)
            %
            % Equivalent to Java: CompatabilityList.valueByIndex(int)

            epoch = obj.elements(index);
        end

        function n = numChildren(obj)
            % NUMCHILDREN Get number of children
            %
            % Usage:
            %   n = node.numChildren()

            n = length(obj.children);
        end

        function n = numLeaves(obj)
            % NUMLEAVES Get number of leaf nodes
            %
            % Usage:
            %   n = tree.numLeaves()

            leaves = obj.leafNodes();
            n = length(leaves);
        end

        %% ================================================================
        % CONTROLLED ACCESS METHODS (replaces Java HashMap custom property)
        % These methods provide controlled access to node custom data.
        % Analysis code should use these instead of direct property access.
        % ================================================================

        function putCustom(obj, key, value)
            % PUTCUSTOM Store data in node's custom property
            %
            % Usage:
            %   node.putCustom('results', myResults)
            %   node.putCustom('NLIs', nliArray)
            %
            % This is the ONLY way to store custom data on nodes.
            % Equivalent to Java: node.custom.put(key, value)
            %
            % Common keys:
            %   'results'    - Analysis results struct
            %   'stimParamz' - Stimulus parameters
            %   'norNLI'     - Normalized NLI values
            %   'NLIs'       - NLI array for cell type
            %
            % Example:
            %   % Store analysis results
            %   results.ImageSum = ImageResp;
            %   results.DiscSum = DiscResp;
            %   results.NLI = NLI;
            %   node.putCustom('results', results);

            if ~ischar(key) && ~isstring(key)
                error('epicTreeTools:InvalidKey', 'Key must be a string');
            end

            % Use dynamic field name to set the value
            obj.custom.(key) = value;
        end

        function value = getCustom(obj, key)
            % GETCUSTOM Retrieve data from node's custom property
            %
            % Usage:
            %   results = node.getCustom('results')
            %   nlis = node.getCustom('NLIs')
            %
            % Returns empty [] if key not found.
            % Equivalent to Java: node.custom.get(key)
            %
            % Example:
            %   % Retrieve stored results
            %   results = node.getCustom('results');
            %   if ~isempty(results)
            %       ImageSum = results.ImageSum;
            %       DiscSum = results.DiscSum;
            %   end

            if ~ischar(key) && ~isstring(key)
                error('epicTreeTools:InvalidKey', 'Key must be a string');
            end

            if isfield(obj.custom, key)
                value = obj.custom.(key);
            else
                value = [];
            end
        end

        function tf = hasCustom(obj, key)
            % HASCUSTOM Check if key exists in custom property
            %
            % Usage:
            %   if node.hasCustom('results')
            %       % process results
            %   end

            tf = isfield(obj.custom, key);
        end

        function removeCustom(obj, key)
            % REMOVECUSTOM Remove key from custom property
            %
            % Usage:
            %   node.removeCustom('tempData')

            if isfield(obj.custom, key)
                obj.custom = rmfield(obj.custom, key);
            end
        end

        function keys = customKeys(obj)
            % CUSTOMKEYS Get all keys in custom property
            %
            % Usage:
            %   keys = node.customKeys()

            keys = fieldnames(obj.custom);
        end

        %% ================================================================
        % CHILDREN NAVIGATION METHODS
        % These provide Java-style access patterns for tree traversal.
        % ================================================================

        function child = childAt(obj, index)
            % CHILDAT Get child by 1-based index
            %
            % Usage:
            %   child = node.childAt(1)  % Get first child
            %
            % Same as child() but clearer name for indexed access.
            % Equivalent to Java: children.elements(index)

            if index < 1 || index > length(obj.children)
                error('epicTreeTools:InvalidIndex', ...
                    'Child index %d out of range [1, %d]', index, length(obj.children));
            end
            child = obj.children{index};
        end

        function n = childrenLength(obj)
            % CHILDRENLENGTH Get number of children
            %
            % Usage:
            %   for i = 1:node.childrenLength()
            %       child = node.childAt(i);
            %   end
            %
            % Equivalent to Java: children.length

            n = length(obj.children);
        end

        function iter = childIterator(obj)
            % CHILDITERATOR Get cell array of children for iteration
            %
            % Usage:
            %   for child = node.childIterator()
            %       % process child{1}
            %   end
            %
            % Or use directly:
            %   children = node.childIterator();
            %   for i = 1:length(children)
            %       child = children{i};
            %   end

            iter = obj.children;
        end

        function list = getChildren(obj)
            % GETCHILDREN Get children as CompatibilityList for Java-style access
            %
            % Usage:
            %   children = node.getChildren();
            %   for i = 1:children.length
            %       child = children.elements(i);
            %   end
            %
            % This provides Java-style navigation:
            %   node.getChildren().length       % number of children
            %   node.getChildren().elements(i)  % get child by index
            %
            % Equivalent to Java: node.children (as CompatibilityList)

            list = CompatibilityList(obj.children);
        end

        function list = getEpochList(obj)
            % GETEPOCHLIST Get epoch list as CompatibilityList for Java-style access
            %
            % Usage:
            %   epochs = node.getEpochList();
            %   for i = 1:epochs.length
            %       epoch = epochs.elements(i);
            %   end
            %
            % This provides Java-style navigation:
            %   node.getEpochList().length       % number of epochs
            %   node.getEpochList().elements(i)  % get epoch by index
            %
            % Equivalent to Java: node.epochList (as CompatibilityList)

            list = CompatibilityList(obj.epochList);
        end

        %% ================================================================
        % PARENT NAVIGATION METHODS
        % The .parent property provides upward tree traversal for accessing
        % higher levels in the tree hierarchy.
        % ================================================================

        function ancestor = parentAt(obj, levelsUp)
            % PARENTAT Get ancestor node N levels up
            %
            % Usage:
            %   grandparent = node.parentAt(2)  % Go up 2 levels
            %   root = node.parentAt(node.depth())  % Go to root
            %
            % Returns empty [] if levelsUp exceeds tree depth.
            %
            % Example:
            %   % If at Level 5 and need Level 2 (3 levels up):
            %   target = currentNode.parentAt(3);

            ancestor = obj;
            for i = 1:levelsUp
                if isempty(ancestor.parent)
                    ancestor = [];
                    return;
                end
                ancestor = ancestor.parent;
            end
        end

        function d = depth(obj)
            % DEPTH Get depth of this node from root (root = 0)
            %
            % Usage:
            %   d = node.depth()
            %
            % Example:
            %   % Leaf at depth 5 means 5 levels below root

            d = 0;
            node = obj;
            while ~isempty(node.parent)
                d = d + 1;
                node = node.parent;
            end
        end

        function path = pathFromRoot(obj)
            % PATHFROMROOT Get array of nodes from root to this node
            %
            % Usage:
            %   path = node.pathFromRoot()
            %   % path{1} = root, path{end} = node
            %
            % Useful for displaying full path or navigating.

            path = {obj};
            node = obj;
            while ~isempty(node.parent)
                node = node.parent;
                path = [{node}; path];
            end
        end

        function str = pathString(obj, separator)
            % PATHSTRING Get string representation of path from root
            %
            % Usage:
            %   str = node.pathString()      % Uses ' > ' separator
            %   str = node.pathString('/')   % Custom separator
            %
            % Example:
            %   % Returns: 'Root > OnP > 0.5 > epoch-123'

            if nargin < 2
                separator = ' > ';
            end

            path = obj.pathFromRoot();
            parts = {};
            for i = 1:length(path)
                node = path{i};
                if isempty(node.splitValue)
                    parts{end+1} = 'Root';
                elseif isnumeric(node.splitValue)
                    parts{end+1} = sprintf('%g', node.splitValue);
                else
                    parts{end+1} = char(string(node.splitValue));
                end
            end
            str = strjoin(parts, separator);
        end

        %% ================================================================
        % DATA MATRIX METHODS (from JAUIMODEL EpochList interface)
        % ================================================================

        function dataMatrix = stimuliByStreamName(obj, streamName)
            % STIMULIBYSTREAMNAME Get stimulus data matrix for all epochs
            %
            % Usage:
            %   stimMatrix = node.stimuliByStreamName('Stage')
            %
            % Returns matrix where each row is one epoch's stimulus data.
            % Equivalent to Java: EpochList.stimuliByStreamName(String)

            epochs = obj.epochList;
            if isempty(epochs)
                dataMatrix = [];
                return;
            end

            % Get first stimulus to determine size
            firstStim = epicTreeTools.getStimulusByName(epochs{1}, streamName);
            if isempty(firstStim) || ~isfield(firstStim, 'data') || isempty(firstStim.data)
                dataMatrix = [];
                return;
            end

            nSamples = length(firstStim.data);
            nEpochs = length(epochs);
            dataMatrix = zeros(nEpochs, nSamples);
            dataMatrix(1, :) = firstStim.data(:)';

            for i = 2:nEpochs
                stim = epicTreeTools.getStimulusByName(epochs{i}, streamName);
                if ~isempty(stim) && isfield(stim, 'data') && ~isempty(stim.data)
                    data = stim.data(:)';
                    if length(data) == nSamples
                        dataMatrix(i, :) = data;
                    elseif length(data) < nSamples
                        dataMatrix(i, 1:length(data)) = data;
                    else
                        dataMatrix(i, :) = data(1:nSamples);
                    end
                end
            end
        end

        function dataMatrix = responsesByStreamName(obj, streamName)
            % RESPONSESBYSTREAMNAME Get response data matrix for all epochs
            %
            % Usage:
            %   respMatrix = node.responsesByStreamName('Amp1')
            %
            % Returns matrix where each row is one epoch's response data.
            % Automatically handles H5 lazy loading using the tree's h5File.
            %
            % Equivalent to Java: EpochList.stimuliByStreamName(String)

            epochs = obj.epochList;
            if isempty(epochs)
                dataMatrix = [];
                return;
            end

            % Use getResponseMatrix which handles H5 loading
            h5 = obj.resolveH5File();
            [dataMatrix, ~] = epicTreeTools.getResponseMatrix(epochs, streamName, h5);
        end

        function [dataMatrix, sampleRate] = dataMatrix(obj, deviceName)
            % DATAMATRIX Get response data matrix and sample rate
            %
            % Usage:
            %   [data, fs] = node.dataMatrix('Amp1')
            %
            % Convenience method that returns [nEpochs x nSamples] matrix
            % and sample rate. Handles H5 lazy loading automatically.
            % Equivalent to Java: GenericEpochList.dataMatrix()

            epochs = obj.epochList;
            sampleRate = [];

            if isempty(epochs)
                dataMatrix = [];
                return;
            end

            % Use getResponseMatrix which handles H5 loading
            h5 = obj.resolveH5File();
            [dataMatrix, sampleRate] = epicTreeTools.getResponseMatrix(epochs, deviceName, h5);
        end

        function spikesMatrix = spikeTimesMatrix(obj, deviceName)
            % SPIKETIMESMATRIX Get spike times for all epochs
            %
            % Usage:
            %   spikes = node.spikeTimesMatrix('Amp1')
            %
            % Returns cell array where each cell contains spike times for one epoch.

            epochs = obj.epochList;
            nEpochs = length(epochs);
            spikesMatrix = cell(nEpochs, 1);

            for i = 1:nEpochs
                [~, ~, spikes] = epicTreeTools.getResponseData(epochs{i}, deviceName);
                spikesMatrix{i} = spikes;
            end
        end

        function [data, selectedEpochs, sampleRate] = selectedData(obj, streamName)
            % SELECTEDDATA Get response data for selected epochs only
            %
            % Usage:
            %   [data, epochs, fs] = node.selectedData('Amp1')
            %
            % Equivalent to getSelectedData(node, streamName) but as a
            % method on the node itself. Resolves H5 file automatically.
            %
            % Returns:
            %   data           - [nSelected x nSamples] response matrix
            %   selectedEpochs - Cell array of selected epoch structs
            %   sampleRate     - Sample rate in Hz

            h5 = obj.resolveH5File();
            [data, selectedEpochs, sampleRate] = epicTreeTools.getSelectedData(obj, streamName, h5);
        end

        %% ================================================================
        % EPOCH LIST MODIFICATION METHODS
        % ================================================================

        function append(obj, epoch)
            % APPEND Add epoch to epoch list
            %
            % Usage:
            %   node.append(newEpoch)
            %
            % Equivalent to Java: EpochList.append()

            if iscell(epoch)
                obj.epochList = [obj.epochList; epoch(:)];
            else
                obj.epochList{end+1} = epoch;
            end

            % Update allEpochs if we're root
            if isempty(obj.parent)
                obj.allEpochs = obj.epochList;
            end
        end

        function insertEpoch(obj, epoch)
            % INSERTEPOCH Insert epoch into tree (rebuilds subtree)
            %
            % Usage:
            %   tree.insertEpoch(newEpoch)
            %
            % Equivalent to Java: EpochTree.insertEpoch()
            %
            % Note: This adds the epoch and rebuilds the tree using current splitKeyPaths.

            % Add to root's allEpochs
            root = obj.getRoot();
            root.allEpochs{end+1} = epoch;

            % Rebuild tree
            paths = obj.splitKeyPaths();
            if ~isempty(paths)
                root.buildTree(paths);
            end
        end

        function insertEpochs(obj, epochs)
            % INSERTEPOCHS Insert multiple epochs into tree
            %
            % Usage:
            %   tree.insertEpochs(newEpochs)
            %
            % Equivalent to Java: EpochTree.insertEpochs()

            root = obj.getRoot();

            if iscell(epochs)
                root.allEpochs = [root.allEpochs; epochs(:)];
            else
                % Struct array
                for i = 1:length(epochs)
                    root.allEpochs{end+1} = epochs(i);
                end
            end

            % Rebuild tree
            paths = obj.splitKeyPaths();
            if ~isempty(paths)
                root.buildTree(paths);
            end
        end

        function root = getRoot(obj)
            % GETROOT Get root node of tree
            %
            % Usage:
            %   root = node.getRoot()

            root = obj;
            while ~isempty(root.parent)
                root = root.parent;
            end
        end

        function epochs = getAllEpochs(obj, onlySelected)
            % GETALLEPOCHS Get all epochs under this node (recursive)
            %
            % Usage:
            %   epochs = tree.getAllEpochs()           % All epochs
            %   epochs = tree.getAllEpochs(true)       % Only selected epochs
            %
            % This is a CRITICAL function for analysis workflows.
            % When onlySelected=true, only returns epochs with isSelected=true.

            if nargin < 2
                onlySelected = false;
            end

            if obj.isLeaf
                if onlySelected
                    % Filter by isSelected flag
                    epochs = {};
                    for i = 1:length(obj.epochList)
                        ep = obj.epochList{i};
                        if isfield(ep, 'isSelected') && ep.isSelected
                            epochs{end+1} = ep;
                        elseif ~isfield(ep, 'isSelected')
                            % Include if isSelected field doesn't exist (backwards compat)
                            epochs{end+1} = ep;
                        end
                    end
                    epochs = epochs(:);
                else
                    epochs = obj.epochList;
                end
            else
                % Internal node - recurse to children
                epochs = {};
                for i = 1:length(obj.children)
                    childEpochs = obj.children{i}.getAllEpochs(onlySelected);
                    epochs = [epochs; childEpochs(:)];
                end
            end
        end

        function setSelected(obj, isSelected, recursive)
            % SETSELECTED Set selection state on this node and optionally children
            %
            % Usage:
            %   node.setSelected(true)           % Select this node only
            %   node.setSelected(true, true)     % Select this node and all descendants
            %
            % Also updates isSelected flag on epochs in leaf nodes AND root.allEpochs.

            if nargin < 3
                recursive = false;
            end

            % Set node's custom.isSelected
            obj.custom.isSelected = isSelected;

            % If leaf, set isSelected on epochs in BOTH epochList AND root.allEpochs
            if obj.isLeaf
                % Get root to access allEpochs
                root = obj.getRoot();

                % Update epochs using their epochIndex to directly access root.allEpochs
                for i = 1:length(obj.epochList)
                    % Update epoch in epochList
                    obj.epochList{i}.isSelected = isSelected;

                    % Also update the SAME epoch in root.allEpochs using epochIndex
                    if isfield(obj.epochList{i}, 'epochIndex')
                        idx = obj.epochList{i}.epochIndex;
                        root.allEpochs{idx}.isSelected = isSelected;
                    end
                end
            end

            % Recurse to children if requested
            if recursive && ~obj.isLeaf
                for i = 1:length(obj.children)
                    obj.children{i}.setSelected(isSelected, true);
                end
            end
        end

        function setSelectedByIndex(obj, indices)
            % SETSELECTEDBYINDEX Select only the epochs at given indices (1-based)
            %
            % Deselects all epochs in this node first, then selects only
            % the ones at the specified indices. Works on leaf nodes.
            %
            % Usage:
            %   node.setSelectedByIndex([1, 3, 5])       % Select epochs 1, 3, 5
            %   node.setSelectedByIndex(1:50)             % Select first 50
            %
            % See also: setSelectedByMask, setSelected

            obj.setSelected(false, true);  % deselect all first

            if obj.isLeaf
                root = obj.getRoot();
                for i = 1:length(indices)
                    idx = indices(i);
                    if idx >= 1 && idx <= length(obj.epochList)
                        obj.epochList{idx}.isSelected = true;
                        if isfield(obj.epochList{idx}, 'epochIndex')
                            rootIdx = obj.epochList{idx}.epochIndex;
                            root.allEpochs{rootIdx}.isSelected = true;
                        end
                    end
                end
            else
                % For non-leaf nodes, gather all epochs and select by index
                allEps = obj.getAllEpochs(false);
                root = obj.getRoot();
                for i = 1:length(indices)
                    idx = indices(i);
                    if idx >= 1 && idx <= length(allEps)
                        ep = allEps{idx};
                        if isfield(ep, 'epochIndex')
                            rootIdx = ep.epochIndex;
                            root.allEpochs{rootIdx}.isSelected = true;
                        end
                    end
                end
                % Sync leaf epochLists with root
                obj.propagateSelectionToLeaves();
            end
        end

        function setSelectedByMask(obj, mask)
            % SETSELECTEDBYMASK Select epochs using a logical mask
            %
            % mask must be a logical vector with length == epochCount().
            % true = selected, false = deselected.
            %
            % Usage:
            %   % Select epochs where spotIntensity > 0.5
            %   eps = node.getAllEpochs(false);
            %   mask = false(length(eps), 1);
            %   for i = 1:length(eps)
            %       mask(i) = eps{i}.parameters.spotIntensity > 0.5;
            %   end
            %   node.setSelectedByMask(mask);
            %
            % See also: setSelectedByIndex, setSelected

            allEps = obj.getAllEpochs(false);
            assert(length(mask) == length(allEps), ...
                sprintf('Mask length (%d) must match epoch count (%d)', length(mask), length(allEps)));

            indices = find(mask);
            obj.setSelectedByIndex(indices);
        end

        function count = epochCount(obj)
            % EPOCHCOUNT Count total epochs under this node
            %
            % Usage:
            %   n = tree.epochCount()

            epochs = obj.getAllEpochs(false);
            count = length(epochs);
        end

        function count = selectedCount(obj)
            % SELECTEDCOUNT Count selected epochs under this node
            %
            % Usage:
            %   n = tree.selectedCount()

            epochs = obj.getAllEpochs(true);
            count = length(epochs);
        end

        function saveUserMetadata(obj, filepath)
            % SAVEUSERMETA Save selection state to .ugm file
            %
            % Usage:
            %   tree.saveUserMetadata('/path/to/file.ugm')
            %
            % Saves selection state to .ugm file with metadata.
            % Builds selection mask from epoch isSelected flags (one-time on save).

            % Get root node to access all epochs directly
            root = obj.getRoot();

            % Access allEpochs property directly for consistency
            if ~isprop(root, 'allEpochs') || isempty(root.allEpochs)
                error('epicTreeTools:NoEpochs', 'Root node has no allEpochs property');
            end

            % Build mask from isSelected flags (ONE-TIME on save)
            mask = false(length(root.allEpochs), 1);
            for i = 1:length(root.allEpochs)
                if isfield(root.allEpochs{i}, 'isSelected') && root.allEpochs{i}.isSelected
                    mask(i) = true;
                end
            end

            % Extract basename for .ugm file metadata
            if ~isempty(root.sourceFile)
                [~, basename, ~] = fileparts(root.sourceFile);
            else
                [~, basename, ~] = fileparts(filepath);
            end

            % Build epoch_h5_uuids array (for DataJoint round-trip)
            epoch_h5_uuids = cell(length(root.allEpochs), 1);
            for i = 1:length(root.allEpochs)
                if isfield(root.allEpochs{i}, 'h5_uuid')
                    epoch_h5_uuids{i} = root.allEpochs{i}.h5_uuid;
                else
                    epoch_h5_uuids{i} = '';
                end
            end

            % Build ugm struct
            ugm = struct();
            ugm.version = '1.1';
            ugm.created = datestr(now, 'yyyy-mm-dd HH:MM:SS');  % Use string instead of datetime object
            ugm.epoch_count = length(root.allEpochs);
            ugm.mat_file_basename = basename;
            ugm.selection_mask = mask;
            ugm.epoch_h5_uuids = epoch_h5_uuids;

            % Save to file
            save(filepath, 'ugm', '-v7.3');

            % Print command window message
            fprintf('Saved selection mask to: %s\n  %d of %d epochs selected (%.1f%%)\n', ...
                filepath, sum(mask), length(mask), 100*sum(mask)/length(mask));
        end

        function success = loadUserMetadata(obj, filepath)
            % LOADUSERMETADATA Load selection state from .ugm file
            %
            % Usage:
            %   success = tree.loadUserMetadata('/path/to/file.ugm')
            %
            % Returns:
            %   success - true if loaded successfully, false otherwise
            %
            % Loads selection state from .ugm file and applies to epochs.
            % Copies mask to isSelected flags (one-time on load).
            % Prints command window warning showing excluded epoch count.

            success = false;

            % Check file exists
            if ~exist(filepath, 'file')
                warning('epicTreeTools:FileNotFound', 'File not found: %s', filepath);
                return;
            end

            % Try loading (use -mat flag for .ugm extension compatibility)
            try
                loaded = load(filepath, '-mat');
            catch ME
                warning('epicTreeTools:LoadFailed', 'Failed to load %s: %s', filepath, ME.message);
                return;
            end

            % Validate struct
            if ~isfield(loaded, 'ugm')
                warning('epicTreeTools:InvalidFormat', 'File does not contain ugm struct: %s', filepath);
                return;
            end

            ugm = loaded.ugm;

            if ~isfield(ugm, 'selection_mask') || ~isfield(ugm, 'epoch_count')
                warning('epicTreeTools:InvalidFormat', 'ugm struct missing required fields');
                return;
            end

            % Get root node to access all epochs directly (not through getAllEpochs)
            root = obj.getRoot();

            % Access allEpochs property directly to modify originals, not copies
            if ~isprop(root, 'allEpochs') || isempty(root.allEpochs)
                warning('epicTreeTools:NoEpochs', 'Root node has no allEpochs property');
                return;
            end

            % Require h5_uuid on both .ugm and epochs — no positional matching
            if ~isfield(ugm, 'epoch_h5_uuids') || isempty(ugm.epoch_h5_uuids)
                warning('epicTreeTools:NoUUIDs', ...
                    'This .ugm file has no epoch_h5_uuids. Re-export from DataJoint and re-save the .ugm.');
                return;
            end

            if ~isfield(root.allEpochs{1}, 'h5_uuid') || isempty(root.allEpochs{1}.h5_uuid)
                warning('epicTreeTools:NoUUIDs', ...
                    'Epochs have no h5_uuid. Re-export from DataJoint to get UUIDs on epochs.');
                return;
            end

            % UUID-based matching (robust to reordering/repopulation)
            ugmUuids = ugm.epoch_h5_uuids;
            ugmMask = ugm.selection_mask;
            uuidToSelected = containers.Map('KeyType', 'char', 'ValueType', 'logical');
            for i = 1:length(ugmUuids)
                uuid = ugmUuids{i};
                if ~isempty(uuid)
                    uuidToSelected(uuid) = logical(ugmMask(i));
                end
            end

            matched = 0;
            unmatched = 0;
            for i = 1:length(root.allEpochs)
                uuid = root.allEpochs{i}.h5_uuid;
                if ~isempty(uuid) && uuidToSelected.isKey(uuid)
                    root.allEpochs{i}.isSelected = uuidToSelected(uuid);
                    matched = matched + 1;
                else
                    root.allEpochs{i}.isSelected = true;  % Default for unmatched
                    unmatched = unmatched + 1;
                end
            end

            if unmatched > 0
                fprintf('  Note: %d epochs had no UUID match (kept selected)\n', unmatched);
            end

            fprintf('Selection mask loaded: %s\n', filepath);
            fprintf('  %d/%d epochs matched by h5_uuid\n', matched, length(root.allEpochs));

            % Propagate isSelected from root.allEpochs to all leaf epochLists
            root.propagateSelectionToLeaves();

            % Refresh node selection state cache
            root.refreshNodeSelectionState();

            % Print summary
            excludedCount = 0;
            for i = 1:length(root.allEpochs)
                if ~root.allEpochs{i}.isSelected
                    excludedCount = excludedCount + 1;
                end
            end
            fprintf('  %d of %d epochs excluded (%.1f%%)\n', ...
                excludedCount, length(root.allEpochs), 100*excludedCount/length(root.allEpochs));

            success = true;
        end

        function refreshNodeSelectionState(obj)
            % REFRESHNODESELECTIONSTATE Sync node.custom.isSelected with epoch states
            %
            % Usage:
            %   tree.refreshNodeSelectionState()
            %
            % Walks tree and updates node.custom.isSelected based on actual
            % epoch isSelected flags. Call after loading .ugm files.

            if obj.isLeaf
                % Check if any epoch is selected
                anySelected = false;
                for i = 1:length(obj.epochList)
                    if isfield(obj.epochList{i}, 'isSelected') && obj.epochList{i}.isSelected
                        anySelected = true;
                        break;
                    end
                end
                obj.custom.isSelected = anySelected;
            else
                % Recurse to children
                anyChildSelected = false;
                for i = 1:length(obj.children)
                    obj.children{i}.refreshNodeSelectionState();
                    if obj.children{i}.custom.isSelected
                        anyChildSelected = true;
                    end
                end
                obj.custom.isSelected = anyChildSelected;
            end
        end

        function propagateSelectionToLeaves(obj)
            % PROPAGATESELECTIONTOLEAVES Copy isSelected from root.allEpochs to leaf epochLists
            %
            % Usage:
            %   tree.propagateSelectionToLeaves()
            %
            % After updating isSelected in root.allEpochs (e.g., after loading .ugm),
            % propagate those changes to all leaf node epochList copies.
            % Uses epochIndex field to match epochs.

            if obj.isLeaf
                % Update each epoch in epochList from root.allEpochs
                root = obj.getRoot();
                for i = 1:length(obj.epochList)
                    if isfield(obj.epochList{i}, 'epochIndex')
                        idx = obj.epochList{i}.epochIndex;
                        % Copy isSelected from root.allEpochs to this leaf's epochList
                        obj.epochList{i}.isSelected = root.allEpochs{idx}.isSelected;
                    end
                end
            else
                % Recurse to children
                for i = 1:length(obj.children)
                    obj.children{i}.propagateSelectionToLeaves();
                end
            end
        end
    end

    methods (Access = private)
        function buildTreeRecursive(obj, epochs, keyPaths)
            % Recursive tree building algorithm

            if isempty(keyPaths)
                % Base case: leaf node — sort by start_time for consistent ordering
                obj.epochList = obj.sortEpochsByStartTime(epochs);
                obj.children = {};
                obj.isLeaf = true;
                return;
            end

            % Pop first key path
            keyPath = keyPaths{1};
            remainingPaths = keyPaths(2:end);

            % Group epochs by value at this key path
            groups = obj.groupByKeyPath(epochs, keyPath);

            % Sort groups by value
            groups = obj.sortGroups(groups);

            % Create child nodes
            obj.children = {};
            obj.epochList = {};
            obj.isLeaf = false;

            for i = 1:length(groups)
                group = groups{i};

                % Create child node
                child = epicTreeTools(obj);
                child.splitKey = keyPath;
                child.splitValue = group.value;

                % Recursively build subtree
                child.buildTreeRecursive(group.epochs, remainingPaths);

                obj.children{end+1} = child;
            end
        end

        function buildTreeWithSplittersRecursive(obj, epochs, splitters)
            % Recursive tree building with splitter functions

            if isempty(splitters)
                % Base case: leaf node — sort by start_time for consistent ordering
                obj.epochList = obj.sortEpochsByStartTime(epochs);
                obj.children = {};
                obj.isLeaf = true;
                return;
            end

            % Pop first splitter
            splitter = splitters{1};
            remainingSplitters = splitters(2:end);

            % Determine splitter type and get split name
            if isa(splitter, 'function_handle')
                splitName = func2str(splitter);
                % Clean up function name for display
                splitName = regexprep(splitName, '^@?\(?([^)]+)\)?.*', '$1');
                splitName = regexprep(splitName, '.*\.', '');  % Remove class prefix
            else
                splitName = splitter;  % It's a key path string
            end

            % Group epochs by splitter value
            groups = obj.groupBySplitter(epochs, splitter);

            % Sort groups by value
            groups = obj.sortGroups(groups);

            % Create child nodes
            obj.children = {};
            obj.epochList = {};
            obj.isLeaf = false;

            for i = 1:length(groups)
                group = groups{i};

                % Create child node
                child = epicTreeTools(obj);
                child.splitKey = splitName;
                child.splitValue = group.value;

                % Recursively build subtree
                child.buildTreeWithSplittersRecursive(group.epochs, remainingSplitters);

                obj.children{end+1} = child;
            end
        end

        function groups = groupBySplitter(obj, epochs, splitter)
            % Group epochs by splitter value (function handle or key path)

            groups = {};
            valueToIdx = containers.Map();

            for i = 1:length(epochs)
                epoch = epochs{i};

                % Get value using splitter
                if isa(splitter, 'function_handle')
                    value = splitter(epoch);
                else
                    value = obj.getNestedValue(epoch, splitter);
                end

                valueKey = obj.valueToString(value);

                if valueToIdx.isKey(valueKey)
                    idx = valueToIdx(valueKey);
                    groups{idx}.epochs{end+1} = epoch;
                else
                    idx = length(groups) + 1;
                    groups{idx} = struct('value', value, 'epochs', {{epoch}});
                    valueToIdx(valueKey) = idx;
                end
            end
        end

        function groups = groupByKeyPath(obj, epochs, keyPath)
            % Group epochs by value at keyPath

            groups = {};
            valueToIdx = containers.Map();

            for i = 1:length(epochs)
                epoch = epochs{i};
                value = obj.getNestedValue(epoch, keyPath);
                valueKey = obj.valueToString(value);

                if valueToIdx.isKey(valueKey)
                    idx = valueToIdx(valueKey);
                    groups{idx}.epochs{end+1} = epoch;
                else
                    idx = length(groups) + 1;
                    groups{idx} = struct('value', value, 'epochs', {{epoch}});
                    valueToIdx(valueKey) = idx;
                end
            end
        end

        function groups = sortGroups(~, groups)
            % Sort groups by their value

            if isempty(groups)
                return;
            end

            n = length(groups);
            values = cell(n, 1);
            for i = 1:n
                values{i} = groups{i}.value;
            end

            % Check if all numeric
            allNumeric = true;
            numericVals = zeros(n, 1);
            for i = 1:n
                if isnumeric(values{i}) && isscalar(values{i})
                    numericVals(i) = values{i};
                else
                    allNumeric = false;
                    break;
                end
            end

            if allNumeric
                [~, sortIdx] = sort(numericVals);
            else
                strVals = cell(n, 1);
                for i = 1:n
                    if isempty(values{i})
                        strVals{i} = '';
                    elseif ischar(values{i})
                        strVals{i} = values{i};
                    elseif isnumeric(values{i})
                        strVals{i} = sprintf('%g', values{i});
                    else
                        strVals{i} = char(string(values{i}));
                    end
                end
                [~, sortIdx] = sort(strVals);
            end

            groups = groups(sortIdx);
        end

        function [sortIdx, sortedVals] = sortValues(~, values)
            % Sort values and return indices

            n = length(values);

            % Check if all numeric
            allNumeric = true;
            numericVals = zeros(n, 1);
            for i = 1:n
                if isnumeric(values{i}) && isscalar(values{i})
                    numericVals(i) = values{i};
                else
                    allNumeric = false;
                    break;
                end
            end

            if allNumeric
                [sortedVals, sortIdx] = sort(numericVals);
            else
                strVals = cell(n, 1);
                for i = 1:n
                    if isempty(values{i})
                        strVals{i} = char(intmax);
                    elseif ischar(values{i})
                        strVals{i} = values{i};
                    elseif isnumeric(values{i})
                        strVals{i} = sprintf('%020g', values{i});
                    else
                        strVals{i} = char(string(values{i}));
                    end
                end
                [sortedVals, sortIdx] = sort(strVals);
            end
        end

        function sorted = sortEpochsByStartTime(~, epochs)
            % Sort epochs by start_time for consistent ordering across exports.
            % Handles both .NET ticks (int64) and date strings ("YYYY-MM-DD HH:MM:SS").

            n = length(epochs);
            if n <= 1
                sorted = epochs;
                return;
            end

            % Extract sortable time values
            timeVals = nan(n, 1);
            for i = 1:n
                ep = epochs{i};
                st = [];

                % Try epoch-level start_time first
                if isfield(ep, 'start_time')
                    st = ep.start_time;
                elseif isfield(ep, 'blockInfo') && isfield(ep.blockInfo, 'start_time')
                    st = ep.blockInfo.start_time;
                end

                if isempty(st)
                    timeVals(i) = i;  % Preserve original order if no time
                    continue;
                end

                % .NET ticks (int64 or large numeric)
                if isnumeric(st) || isinteger(st)
                    timeVals(i) = double(st);
                elseif ischar(st) || isstring(st)
                    % Date string — parse to datenum
                    try
                        timeVals(i) = datenum(char(st));
                    catch
                        timeVals(i) = i;  % Fallback: preserve order
                    end
                else
                    timeVals(i) = i;
                end
            end

            [~, sortIdx] = sort(timeVals);
            sorted = epochs(sortIdx);
        end

        function h5 = resolveH5File(obj)
            % RESOLVEH5FILE Get H5 file path from this node or root
            %
            % Walks up the tree to find h5File on the root node, or uses
            % epicTreeConfig as fallback.

            h5 = '';

            % Check this node first
            if ~isempty(obj.h5File)
                h5 = obj.h5File;
                return;
            end

            % Walk up to root
            node = obj;
            while ~isempty(node.parent)
                node = node.parent;
            end
            if ~isempty(node.h5File)
                h5 = node.h5File;
                return;
            end

            % Fallback: try epicTreeConfig
            try
                h5Dir = epicTreeConfig('h5_dir');
                if ~isempty(h5Dir) && ~isempty(node.sourceFile)
                    [~, expName, ~] = fileparts(node.sourceFile);
                    candidate = fullfile(h5Dir, [expName '.h5']);
                    if exist(candidate, 'file')
                        h5 = candidate;
                    end
                end
            catch
            end
        end

        function names = getStreamNames(obj, streamType)
            % Get unique stream names from epochs

            names = {};
            nameSet = containers.Map();

            epochs = obj.epochList;
            if isempty(epochs) && ~isempty(obj.allEpochs)
                epochs = obj.allEpochs;
            end

            for i = 1:length(epochs)
                epoch = epochs{i};
                if ~isfield(epoch, streamType)
                    continue;
                end

                streams = epoch.(streamType);
                if isstruct(streams)
                    for j = 1:length(streams)
                        if isfield(streams(j), 'device_name')
                            name = streams(j).device_name;
                            if ~isempty(name) && ~nameSet.isKey(name)
                                nameSet(name) = true;
                                names{end+1} = name;
                            end
                        end
                    end
                elseif iscell(streams)
                    for j = 1:length(streams)
                        s = streams{j};
                        if isfield(s, 'device_name')
                            name = s.device_name;
                            if ~isempty(name) && ~nameSet.isKey(name)
                                nameSet(name) = true;
                                names{end+1} = name;
                            end
                        end
                    end
                end
            end

            names = sort(names);
        end
    end

    methods (Static)
        function value = getNestedValue(obj, keyPath)
            % GETNESTEDVALUE Access nested struct fields via dot notation
            %
            % Usage:
            %   val = epicTreeTools.getNestedValue(epoch, 'protocolSettings.contrast')
            %
            % Supports both 'protocolSettings' and 'parameters' for compatibility

            value = [];

            if isempty(obj) || isempty(keyPath)
                return;
            end

            % Handle protocolSettings -> parameters alias
            keyPath = strrep(keyPath, 'protocolSettings', 'parameters');

            parts = strsplit(keyPath, '.');
            current = obj;

            for i = 1:length(parts)
                part = parts{i};
                if isempty(part)
                    continue;
                end

                if isstruct(current)
                    if isfield(current, part)
                        current = current.(part);
                    else
                        return;
                    end
                elseif iscell(current) && numel(current) == 1
                    current = current{1};
                    if isstruct(current) && isfield(current, part)
                        current = current.(part);
                    else
                        return;
                    end
                else
                    return;
                end
            end

            value = current;
        end

        function epochs = extractAllEpochs(treeData)
            % EXTRACTALLEPOCHS Flatten hierarchy to cell array of epochs
            %
            % Usage:
            %   epochs = epicTreeTools.extractAllEpochs(treeData)
            %
            % Handles both cell arrays and struct arrays in the hierarchy.

            epochs = {};

            if ~isfield(treeData, 'experiments')
                return;
            end

            experiments = treeData.experiments;
            for expIdx = 1:length(experiments)
                exp = epicTreeTools.getElement(experiments, expIdx);

                expInfo = struct();
                if isfield(exp, 'id'), expInfo.id = exp.id; end
                if isfield(exp, 'exp_name'), expInfo.exp_name = exp.exp_name; end
                if isfield(exp, 'is_mea'), expInfo.is_mea = exp.is_mea; end
                if isfield(exp, 'h5_uuid'), expInfo.h5_uuid = exp.h5_uuid; end

                % Resolve H5 file path for lazy loading
                expH5File = '';
                if isfield(exp, 'h5_file') && ~isempty(exp.h5_file)
                    expH5File = exp.h5_file;
                end

                if ~isfield(exp, 'cells'), continue; end

                cells = exp.cells;
                for cellIdx = 1:length(cells)
                    cellData = epicTreeTools.getElement(cells, cellIdx);

                    cellInfo = struct();
                    if isfield(cellData, 'id'), cellInfo.id = cellData.id; end
                    if isfield(cellData, 'type'), cellInfo.type = cellData.type; else, cellInfo.type = ''; end
                    if isfield(cellData, 'label'), cellInfo.label = cellData.label; else, cellInfo.label = ''; end
                    if isfield(cellData, 'h5_uuid'), cellInfo.h5_uuid = cellData.h5_uuid; end

                    if ~isfield(cellData, 'epoch_groups'), continue; end

                    epochGroups = cellData.epoch_groups;
                    for groupIdx = 1:length(epochGroups)
                        eg = epicTreeTools.getElement(epochGroups, groupIdx);

                        groupInfo = struct();
                        if isfield(eg, 'id'), groupInfo.id = eg.id; end
                        if isfield(eg, 'protocol_name'), groupInfo.protocol_name = eg.protocol_name; else, groupInfo.protocol_name = ''; end
                        if isfield(eg, 'label'), groupInfo.label = eg.label; else, groupInfo.label = ''; end
                        if isfield(eg, 'h5_uuid'), groupInfo.h5_uuid = eg.h5_uuid; end
                        if isfield(eg, 'start_time'), groupInfo.start_time = eg.start_time; end
                        if isfield(eg, 'end_time'), groupInfo.end_time = eg.end_time; end
                        if isfield(eg, 'recording_technique'), groupInfo.recording_technique = eg.recording_technique; end
                        if isfield(eg, 'external_solution'), groupInfo.external_solution = eg.external_solution; end
                        if isfield(eg, 'internal_solution'), groupInfo.internal_solution = eg.internal_solution; end
                        if isfield(eg, 'pipette_solution'), groupInfo.pipette_solution = eg.pipette_solution; end
                        if isfield(eg, 'series_resistance_comp'), groupInfo.series_resistance_comp = eg.series_resistance_comp; end

                        if ~isfield(eg, 'epoch_blocks'), continue; end

                        epochBlocks = eg.epoch_blocks;
                        for blockIdx = 1:length(epochBlocks)
                            eb = epicTreeTools.getElement(epochBlocks, blockIdx);

                            blockInfo = struct();
                            if isfield(eb, 'id'), blockInfo.id = eb.id; end
                            if isfield(eb, 'protocol_name'), blockInfo.protocol_name = eb.protocol_name; else, blockInfo.protocol_name = ''; end
                            if isfield(eb, 'protocol_id'), blockInfo.protocol_id = eb.protocol_id; end
                            if isfield(eb, 'h5_uuid'), blockInfo.h5_uuid = eb.h5_uuid; end
                            if isfield(eb, 'start_time'), blockInfo.start_time = eb.start_time; end
                            if isfield(eb, 'end_time'), blockInfo.end_time = eb.end_time; end

                            if ~isfield(eb, 'epochs'), continue; end

                            epochList = eb.epochs;
                            for epochIdx = 1:length(epochList)
                                epoch = epicTreeTools.getElement(epochList, epochIdx);

                                % Attach parent references
                                epoch.cellInfo = cellInfo;
                                epoch.groupInfo = groupInfo;
                                epoch.blockInfo = blockInfo;
                                epoch.expInfo = expInfo;

                                % Attach H5 file path for lazy loading
                                if ~isempty(expH5File) && ~isfield(epoch, 'h5_file')
                                    epoch.h5_file = expH5File;
                                end

                                % Alias parameters as protocolSettings for compatibility
                                if isfield(epoch, 'parameters') && ~isfield(epoch, 'protocolSettings')
                                    epoch.protocolSettings = epoch.parameters;
                                end

                                % Initialize selection state (CRITICAL for GUI)
                                epoch.isSelected = true;
                                epoch.includeInAnalysis = true;

                                epochs{end+1} = epoch;
                            end
                        end
                    end
                end
            end

            epochs = epochs(:);
        end

        function elem = getElement(arr, idx)
            % GETELEMENT Get element from cell array or struct array
            %
            % Handles both cell arrays and struct arrays uniformly.
            if iscell(arr)
                elem = arr{idx};
            else
                elem = arr(idx);
            end
        end

        function response = getResponseByName(epoch, deviceName)
            % GETRESPONSEBYNAME Get response struct by device name
            %
            % Usage:
            %   resp = epicTreeTools.getResponseByName(epoch, 'Amp1')

            response = [];
            if ~isfield(epoch, 'responses'), return; end

            responses = epoch.responses;
            if isstruct(responses)
                for i = 1:length(responses)
                    if strcmp(responses(i).device_name, deviceName)
                        response = responses(i);
                        return;
                    end
                end
            elseif iscell(responses)
                for i = 1:length(responses)
                    r = responses{i};
                    if isfield(r, 'device_name') && strcmp(r.device_name, deviceName)
                        response = r;
                        return;
                    end
                end
            end
        end

        function stimulus = getStimulusByName(epoch, deviceName)
            % GETSTIMULUSBYNAME Get stimulus struct by device name
            %
            % If stimulus.data is empty but stimulus_id and
            % stimulus_parameters exist, auto-reconstructs the waveform
            % using epicStimulusGenerators.
            %
            % Usage:
            %   stim = epicTreeTools.getStimulusByName(epoch, 'LED')

            stimulus = [];
            if ~isfield(epoch, 'stimuli'), return; end

            stimuli = epoch.stimuli;
            if isstruct(stimuli)
                for i = 1:length(stimuli)
                    if strcmp(stimuli(i).device_name, deviceName)
                        stimulus = stimuli(i);
                        break;
                    end
                end
            elseif iscell(stimuli)
                for i = 1:length(stimuli)
                    s = stimuli{i};
                    if isfield(s, 'device_name') && strcmp(s.device_name, deviceName)
                        stimulus = s;
                        break;
                    end
                end
            end

            if isempty(stimulus), return; end

            % Auto-reconstruct if data is empty but stimulus_id exists
            hasData = isfield(stimulus, 'data') && ~isempty(stimulus.data);
            hasID = isfield(stimulus, 'stimulus_id') && ~isempty(stimulus.stimulus_id);

            if ~hasData && hasID
                try
                    stimParams = struct();
                    if isfield(stimulus, 'stimulus_parameters')
                        stimParams = stimulus.stimulus_parameters;
                        if ~isstruct(stimParams)
                            stimParams = struct();
                        end
                    end
                    [data, sr] = epicStimulusGenerators.generateStimulus( ...
                        stimulus.stimulus_id, stimParams);
                    stimulus.data = data;
                    if sr > 0
                        stimulus.sample_rate = sr;
                    end
                catch ME
                    warning('epicTreeTools:getStimulusByName:reconstructFailed', ...
                        'Failed to reconstruct stimulus from %s: %s', ...
                        stimulus.stimulus_id, ME.message);
                end
            end
        end

        function [data, sampleRate, spikeTimes] = getResponseData(epoch, deviceName)
            % GETRESPONSEDATA Get response data, sample rate, spike times
            %
            % Usage:
            %   [data, fs, spikes] = epicTreeTools.getResponseData(epoch, 'Amp1')

            data = [];
            sampleRate = [];
            spikeTimes = [];

            resp = epicTreeTools.getResponseByName(epoch, deviceName);
            if isempty(resp), return; end

            if isfield(resp, 'data')
                data = resp.data(:)';  % Row vector
            end
            if isfield(resp, 'sample_rate')
                sampleRate = resp.sample_rate;
            end
            if isfield(resp, 'spike_times')
                spikeTimes = resp.spike_times(:)';  % Row vector
            end
        end

        function eq = valuesEqual(a, b)
            % Compare two values for equality

            if isempty(a) && isempty(b)
                eq = true;
            elseif isempty(a) || isempty(b)
                eq = false;
            elseif isequal(a, b)
                eq = true;
            elseif isnumeric(a) && isnumeric(b) && isscalar(a) && isscalar(b)
                eq = abs(a - b) < 1e-10;
            elseif (ischar(a) || isstring(a)) && (ischar(b) || isstring(b))
                eq = strcmp(char(a), char(b));
            else
                eq = isequal(a, b);
            end
        end

        function str = valueToString(value)
            % Convert value to string for grouping

            if isempty(value)
                str = '__empty__';
            elseif ischar(value)
                str = value;
            elseif isstring(value)
                str = char(value);
            elseif isnumeric(value) && isscalar(value)
                str = sprintf('%.10g', value);
            elseif islogical(value)
                if value, str = 'true'; else, str = 'false'; end
            else
                str = '__other__';
            end
        end

        %% ================================================================
        % PHASE 3: SPLITTER FUNCTIONS
        % These static methods return a split value from an epoch.
        % Use with buildTreeWithSplitters() or as custom key paths.
        % ================================================================

        function V = splitOnExperimentDate(epoch)
            % SPLITONEXPERIMENTDATE Split by experiment date
            %
            % Usage:
            %   value = epicTreeTools.splitOnExperimentDate(epoch)
            %
            % Returns the experiment name/date string.
            % Compatible with DATA_FORMAT_SPECIFICATION: uses expInfo.exp_name

            V = '';
            if isfield(epoch, 'expInfo') && isfield(epoch.expInfo, 'exp_name')
                V = epoch.expInfo.exp_name;
            elseif isfield(epoch, 'expInfo') && isfield(epoch.expInfo, 'start_time')
                V = datestr(epoch.expInfo.start_time);
            end
        end

        function V = splitOnCellType(epoch)
            % SPLITONCELLTYPE Split by cell type
            %
            % Usage:
            %   value = epicTreeTools.splitOnCellType(epoch)
            %
            % Returns the cell type (OnP, OffP, OnM, etc.)
            % Also checks keywords for legacy Symphony 1 compatibility.

            V = 'Unknown';

            % Try cellInfo.type first (DATA_FORMAT_SPECIFICATION)
            if isfield(epoch, 'cellInfo') && isfield(epoch.cellInfo, 'type')
                cellType = epoch.cellInfo.type;
                if ~isempty(cellType) && ~strcmp(cellType, 'unknown')
                    V = cellType;
                    return;
                end
            end

            % Try parameters source:type (Symphony 2)
            params = epicTreeTools.getParams(epoch);
            if isfield(params, 'source_type')
                V = params.source_type;
                if ~isempty(V) && ~strcmp(V, 'unknown')
                    return;
                end
            end

            % Fall back to keywords (Symphony 1)
            V = epicTreeTools.checkCellTypeKeywords(epoch);
        end

        function V = splitOnKeywords(epoch)
            % SPLITONKEYWORDS Split by epoch keywords
            %
            % Usage:
            %   value = epicTreeTools.splitOnKeywords(epoch)
            %
            % Returns concatenated keywords string.

            V = '';
            if isfield(epoch, 'keywords')
                kw = epoch.keywords;
                if iscell(kw)
                    V = strjoin(kw, ', ');
                elseif ischar(kw)
                    V = kw;
                end
            end
        end

        function V = splitOnKeywordsExcluding(epoch, excludeList)
            % SPLITONKEYWORDSEXCLUDING Split by keywords, excluding some
            %
            % Usage:
            %   value = epicTreeTools.splitOnKeywordsExcluding(epoch, {'example'})
            %
            % Returns concatenated keywords excluding specified ones.

            V = '';
            if ~isfield(epoch, 'keywords')
                return;
            end

            kw = epoch.keywords;
            if iscell(kw)
                % Filter out excluded keywords
                keep = true(size(kw));
                for i = 1:length(kw)
                    for j = 1:length(excludeList)
                        if strcmp(kw{i}, excludeList{j})
                            keep(i) = false;
                            break;
                        end
                    end
                end
                V = strjoin(kw(keep), ', ');
            elseif ischar(kw)
                V = kw;
            end
        end

        function V = splitOnF1F2Contrast(epoch)
            % SPLITONF1F2CONTRAST Split for F1/F2 contrast analysis
            %
            % Usage:
            %   value = epicTreeTools.splitOnF1F2Contrast(epoch)
            %
            % Handles ContrastF1F2 and SplitFieldCentering protocols.
            % Returns currentContrast or contrast value.

            V = [];
            params = epicTreeTools.getParams(epoch);

            if isfield(params, 'currentContrast')
                V = params.currentContrast;
            elseif isfield(params, 'contrast')
                V = params.contrast;
            end
        end

        function V = splitOnF1F2CenterSize(epoch)
            % SPLITONF1F2CENTERSIZE Split for F1/F2 center size analysis
            %
            % Usage:
            %   value = epicTreeTools.splitOnF1F2CenterSize(epoch)
            %
            % Returns spotDiameter or apertureDiameter.

            V = [];
            params = epicTreeTools.getParams(epoch);

            if isfield(params, 'spotDiameter')
                V = params.spotDiameter;
            elseif isfield(params, 'apertureDiameter')
                V = params.apertureDiameter;
            end
        end

        function V = splitOnF1F2Phase(epoch)
            % SPLITONF1F2PHASE Split for F1/F2 phase analysis
            %
            % Usage:
            %   value = epicTreeTools.splitOnF1F2Phase(epoch)
            %
            % Returns 'F1' or 'F2' based on splitField or currentPhase.

            V = '';
            params = epicTreeTools.getParams(epoch);

            if isfield(params, 'splitField')
                if params.splitField
                    V = 'F2';
                else
                    V = 'F1';
                end
            elseif isfield(params, 'currentPhase')
                if params.currentPhase == 0
                    V = 'F1';
                elseif params.currentPhase == 90
                    V = 'F2';
                end
            end
        end

        function V = splitOnRadiusOrDiameter(epoch, paramString)
            % SPLITONRADIUSORDIAMETER Split by radius or diameter
            %
            % Usage:
            %   value = epicTreeTools.splitOnRadiusOrDiameter(epoch, 'aperture')
            %   value = epicTreeTools.splitOnRadiusOrDiameter(epoch, 'mask')
            %
            % Handles Symphony 1->2 transition (radius to diameter).

            V = [];
            params = epicTreeTools.getParams(epoch);

            radiusField = [paramString, 'Radius'];
            diamField = [paramString, 'Diameter'];

            if isfield(params, radiusField)
                V = 2 * params.(radiusField);  % Convert radius to diameter
            elseif isfield(params, diamField)
                V = params.(diamField);
            end
        end

        function V = splitOnHoldingSignal(epoch)
            % SPLITONHOLDINGSIGNAL Split by holding/offset signal
            %
            % Usage:
            %   value = epicTreeTools.splitOnHoldingSignal(epoch)
            %
            % Returns Amp1 offset (Symphony 2) or Amplifier_Ch1 background.

            V = [];
            params = epicTreeTools.getParams(epoch);

            % Symphony 2 format (colon replaced with underscore in MATLAB)
            if isfield(params, 'stimuli_Amp1_offset')
                V = params.stimuli_Amp1_offset;
            elseif isfield(params, 'background_Amplifier_Ch1')
                V = params.background_Amplifier_Ch1;
            % Alternative field names
            elseif isfield(params, 'holdingSignal')
                V = params.holdingSignal;
            elseif isfield(params, 'amp1Offset')
                V = params.amp1Offset;
            end
        end

        function V = splitOnOLEDLevel(epoch)
            % SPLITONOLEDLEVEL Split by OLED brightness level
            %
            % Usage:
            %   value = epicTreeTools.splitOnOLEDLevel(epoch)
            %
            % Returns brightness level (maximum/high/medium/low/minimum).

            V = 'Not OLED';
            params = epicTreeTools.getParams(epoch);

            % Symphony 2 format
            if isfield(params, 'background_Microdisplay_Stage_localhost_microdisplayBrightness')
                V = params.background_Microdisplay_Stage_localhost_microdisplayBrightness;
            elseif isfield(params, 'microdisplayBrightness')
                V = params.microdisplayBrightness;
            elseif isfield(params, 'oledBrightness')
                % Symphony 1: convert numeric to label
                brightness = params.oledBrightness;
                switch brightness
                    case 23
                        V = 'maximum';
                    case 25
                        V = 'high';
                    case 73
                        V = 'medium';
                    case 120
                        V = 'low';
                    case 229
                        V = 'minimum';
                    otherwise
                        V = sprintf('%g', brightness);
                end
            end
        end

        function V = splitOnRecKeyword(epoch)
            % SPLITONRECKEYWORD Split by recording type keyword
            %
            % Usage:
            %   value = epicTreeTools.splitOnRecKeyword(epoch)
            %
            % Returns recording type (exc/inh/extracellular/gClamp/iClamp).

            V = 'noRecordingTag';
            keywords = epicTreeTools.getKeywordsString(epoch);

            if contains(keywords, 'exc')
                V = 'exc';
            elseif contains(keywords, 'inh')
                V = 'inh';
            elseif contains(keywords, 'extracellular')
                V = 'extracellular';
            elseif contains(keywords, 'gClamp')
                V = 'gClamp';
            elseif contains(keywords, 'iClamp')
                V = 'iClamp';
            end
        end

        function V = splitOnLogIRtag(epoch)
            % SPLITONLOGIRTAG Split by log IR tag in keywords
            %
            % Usage:
            %   value = epicTreeTools.splitOnLogIRtag(epoch)
            %
            % Returns IR level tag (12.0, 13.6, etc.).

            V = 'noIRTag';
            keywords = epicTreeTools.getKeywordsString(epoch);

            if contains(keywords, '12.0')
                V = '12.0';
            elseif contains(keywords, '13.6')
                V = '13.6';
            end
        end

        function V = splitOnPatchContrast_NatImage(epoch)
            % SPLITONPATCHCONTRAST_NATIMAGE Split for natural image patch contrast
            %
            % Usage:
            %   value = epicTreeTools.splitOnPatchContrast_NatImage(epoch)
            %
            % Returns patchContrast value or 'all' for random patches.

            V = 'all';
            params = epicTreeTools.getParams(epoch);

            if isfield(params, 'patchContrast')
                V = params.patchContrast;
            end
        end

        function V = splitOnPatchSampling_NatImage(epoch)
            % SPLITONPATCHSAMPLING_NATIMAGE Split for natural image patch sampling
            %
            % Usage:
            %   value = epicTreeTools.splitOnPatchSampling_NatImage(epoch)
            %
            % Returns patchSampling value or 'random' for first version.

            V = 'random';
            params = epicTreeTools.getParams(epoch);

            if isfield(params, 'patchSampling')
                V = params.patchSampling;
            end
        end

        function V = splitOnEpochBlockStart(epoch)
            % SPLITONEPOCHBLOCKSTART Split by epoch block start time
            %
            % Usage:
            %   value = epicTreeTools.splitOnEpochBlockStart(epoch)
            %
            % Returns block start time string.

            V = '';
            if isfield(epoch, 'blockInfo') && isfield(epoch.blockInfo, 'start_time')
                V = datestr(epoch.blockInfo.start_time);
            end
        end

        function V = splitOnBarWidth(epoch)
            % SPLITONBARWIDTH Split by bar width parameter
            %
            % Usage:
            %   value = epicTreeTools.splitOnBarWidth(epoch)

            V = [];
            params = epicTreeTools.getParams(epoch);

            if isfield(params, 'currentBarWidth')
                V = abs(params.currentBarWidth);
            elseif isfield(params, 'barWidth')
                V = abs(params.barWidth);
            end
        end

        function V = splitOnFlashDelay(epoch)
            % SPLITONFLASHDELAY Split by flash delay time
            %
            % Usage:
            %   value = epicTreeTools.splitOnFlashDelay(epoch)

            V = [];
            params = epicTreeTools.getParams(epoch);

            if isfield(params, 'currentFlashDelay')
                V = params.currentFlashDelay;
            elseif isfield(params, 'flashDelay')
                V = params.flashDelay;
            end
        end

        function V = splitOnStimulusCenter(epoch)
            % SPLITONSTIMULUSENTER Split by stimulus center offset
            %
            % Usage:
            %   value = epicTreeTools.splitOnStimulusCenter(epoch)
            %
            % Returns X coordinate of center offset.

            V = [];
            params = epicTreeTools.getParams(epoch);

            % Check various possible field names
            possibleFields = {
                'background_Microdisplay_Stage_localhost_centerOffset'
                'background_LightCrafter_Stage_localhost_centerOffset'
                'centerOffset'
                'stimulusCenter'
            };

            for i = 1:length(possibleFields)
                if isfield(params, possibleFields{i})
                    offset = params.(possibleFields{i});
                    if isnumeric(offset) && ~isempty(offset)
                        V = offset(1);  % X coordinate
                    end
                    break;
                end
            end
        end

        function V = splitOnTemporalFrequency(epoch)
            % SPLITONTEMPORALFREQUENCY Split by temporal frequency
            %
            % Usage:
            %   value = epicTreeTools.splitOnTemporalFrequency(epoch)

            V = [];
            params = epicTreeTools.getParams(epoch);

            if isfield(params, 'temporal_frequency')
                V = params.temporal_frequency;
            elseif isfield(params, 'temporalFrequency')
                V = params.temporalFrequency;
            end
        end

        function V = splitOnSpatialFrequency(epoch)
            % SPLITONSPATIALFREQUENCY Split by spatial frequency
            %
            % Usage:
            %   value = epicTreeTools.splitOnSpatialFrequency(epoch)

            V = [];
            params = epicTreeTools.getParams(epoch);

            if isfield(params, 'spatial_frequency')
                V = params.spatial_frequency;
            elseif isfield(params, 'spatialFrequency')
                V = params.spatialFrequency;
            end
        end

        function V = splitOnContrast(epoch)
            % SPLITONCONTRAST Split by contrast parameter
            %
            % Usage:
            %   value = epicTreeTools.splitOnContrast(epoch)

            V = [];
            params = epicTreeTools.getParams(epoch);

            if isfield(params, 'contrast')
                V = params.contrast;
            elseif isfield(params, 'currentContrast')
                V = params.currentContrast;
            end
        end

        function V = splitOnProtocol(epoch)
            % SPLITONPROTOCOL Split by protocol name
            %
            % Usage:
            %   value = epicTreeTools.splitOnProtocol(epoch)

            V = '';
            if isfield(epoch, 'blockInfo') && isfield(epoch.blockInfo, 'protocol_name')
                V = epoch.blockInfo.protocol_name;
            elseif isfield(epoch, 'groupInfo') && isfield(epoch.groupInfo, 'protocol_name')
                V = epoch.groupInfo.protocol_name;
            end
        end

        %% ================================================================
        % HELPER METHODS FOR SPLITTERS
        % ================================================================

        function params = getParams(epoch)
            % GETPARAMS Get parameters struct from epoch
            %
            % Handles both 'parameters' and 'protocolSettings' field names.

            params = struct();
            if isfield(epoch, 'parameters')
                params = epoch.parameters;
            elseif isfield(epoch, 'protocolSettings')
                params = epoch.protocolSettings;
            end
        end

        function kw = getKeywordsString(epoch)
            % GETKEYWORDSSTRING Get keywords as a single string
            %
            % Returns lowercase concatenated keywords for pattern matching.

            kw = '';
            if isfield(epoch, 'keywords')
                keywords = epoch.keywords;
                if iscell(keywords)
                    kw = lower(strjoin(keywords, ' '));
                elseif ischar(keywords)
                    kw = lower(keywords);
                end
            end
        end

        function cellType = checkCellTypeKeywords(epoch)
            % CHECKCELLTYPEKEYWORDS Determine cell type from keywords
            %
            % Legacy Symphony 1 compatibility: cell type stored as keyword.

            cellType = 'noCellTypeTag';
            keywords = epicTreeTools.getKeywordsString(epoch);

            if contains(keywords, 'onparasol')
                cellType = 'RGC\ON-parasol';
            elseif contains(keywords, 'offparasol')
                cellType = 'RGC\OFF-parasol';
            elseif contains(keywords, 'onmidget')
                cellType = 'RGC\ON-midget';
            elseif contains(keywords, 'offmidget')
                cellType = 'RGC\OFF-midget';
            elseif contains(keywords, 'horizontal')
                cellType = 'horizontal';
            elseif contains(keywords, 'onp')
                cellType = 'OnP';
            elseif contains(keywords, 'offp')
                cellType = 'OffP';
            elseif contains(keywords, 'onm')
                cellType = 'OnM';
            elseif contains(keywords, 'offm')
                cellType = 'OffM';
            end
        end

        function filepath = findLatestUGM(matFilePath)
            % FINDLATESTUGM Find most recent .ugm file for a .mat file
            %
            % Usage:
            %   ugmPath = epicTreeTools.findLatestUGM('/path/to/data.mat')
            %
            % Returns:
            %   filepath - Path to most recent .ugm file, or '' if none found
            %
            % Search order:
            %   1. epicTreeConfig('ugm_dir') if set
            %   2. Same directory as the .mat file
            %
            % Searches for .ugm files with pattern: basename_*.ugm
            % Sorts by filename (ISO 8601 timestamps sort lexicographically)

            filepath = '';

            if isempty(matFilePath)
                return;
            end

            [matDir, basename, ~] = fileparts(matFilePath);

            % Determine search directories
            searchDirs = {};
            ugmDir = epicTreeConfig('ugm_dir');
            if ~isempty(ugmDir) && exist(ugmDir, 'dir')
                searchDirs{end+1} = ugmDir;
            end
            searchDirs{end+1} = matDir;

            % Search each directory for matching .ugm files
            for d = 1:length(searchDirs)
                pattern = fullfile(searchDirs{d}, [basename '_*.ugm']);
                files = dir(pattern);

                if ~isempty(files)
                    names = {files.name};
                    [~, idx] = sort(names);
                    idx = flip(idx);
                    filepath = fullfile(searchDirs{d}, files(idx(1)).name);
                    return;
                end
            end
        end

        function filepath = generateUGMFilename(matFilePath)
            % GENERATEUGMFILENAME Generate timestamped .ugm filename
            %
            % Usage:
            %   ugmPath = epicTreeTools.generateUGMFilename('/path/to/data.mat')
            %
            % Returns:
            %   filepath - Generated .ugm filepath with timestamp
            %
            % Saves to epicTreeConfig('ugm_dir') if set, otherwise next to
            % the .mat file.
            %
            % Format: basename_YYYY-MM-DD_HH-mm-ss.ugm

            if isempty(matFilePath)
                error('epicTreeTools:EmptyPath', 'matFilePath cannot be empty');
            end

            [matDir, basename, ~] = fileparts(matFilePath);

            % Use configured ugm_dir if set, otherwise same dir as .mat
            ugmDir = epicTreeConfig('ugm_dir');
            if ~isempty(ugmDir)
                if ~exist(ugmDir, 'dir')
                    mkdir(ugmDir);
                end
                directory = ugmDir;
            else
                directory = matDir;
            end

            % Generate timestamp
            timestamp = string(datetime('now'), 'uuuu-MM-dd_HH-mm-ss');

            % Build filepath
            filepath = fullfile(directory, sprintf('%s_%s.ugm', basename, timestamp));
        end

        %% ================================================================
        % ANALYSIS FUNCTIONS (formerly standalone files)
        % ================================================================

        function [dataMatrix, selectedEpochs, sampleRate] = getSelectedData(treeNodeOrEpochs, streamName, h5_file)
            % GETSELECTEDDATA Get response data for ONLY selected epochs
            %
            % THIS IS THE CRITICAL FUNCTION FOR ALL ANALYSIS WORKFLOWS.
            %
            % Usage:
            %   [data, epochs] = epicTreeTools.getSelectedData(treeNode, 'Amp1')
            %   [data, epochs, fs] = epicTreeTools.getSelectedData(epochList, 'Amp1')
            %   [data, epochs, fs] = epicTreeTools.getSelectedData(epochList, 'Amp1', h5_file)
            %
            % Inputs:
            %   treeNodeOrEpochs - Either:
            %                      - epicTreeTools node (extracts epochs from tree)
            %                      - Cell array of epoch structs (uses directly)
            %   streamName       - Response stream name (e.g., 'Amp1', 'Amp2')
            %   h5_file          - (Optional) Path to H5 file for lazy loading
            %
            % Outputs:
            %   dataMatrix      - [nSelected x nSamples] response data matrix
            %   selectedEpochs  - Cell array of selected epoch structs
            %   sampleRate      - Sample rate in Hz (from first epoch)
            %
            % See also: getResponseMatrix, epicTreeTools.getAllEpochs

            if nargin < 3
                h5_file = '';
            end

            if isa(treeNodeOrEpochs, 'epicTreeTools')
                allEpochs = treeNodeOrEpochs.getAllEpochs(false);
            elseif iscell(treeNodeOrEpochs)
                allEpochs = treeNodeOrEpochs;
            else
                error('getSelectedData:InvalidInput', ...
                    'Input must be epicTreeTools node or cell array of epochs');
            end

            selectedEpochs = {};
            for i = 1:length(allEpochs)
                ep = allEpochs{i};
                if isfield(ep, 'isSelected')
                    if ep.isSelected
                        selectedEpochs{end+1} = ep; %#ok<AGROW>
                    end
                else
                    selectedEpochs{end+1} = ep; %#ok<AGROW>
                end
            end
            selectedEpochs = selectedEpochs(:);

            if isempty(selectedEpochs)
                dataMatrix = [];
                sampleRate = [];
                return;
            end

            [dataMatrix, sampleRate] = epicTreeTools.getResponseMatrix(selectedEpochs, streamName, h5_file);
        end

        function epochList = getTreeEpochs(treeNode, onlySelected)
            % GETTREEEPOCHS Get all epochs under a tree node
            %
            % Convenience wrapper for epicTreeTools.getAllEpochs().
            %
            % Usage:
            %   epochs = epicTreeTools.getTreeEpochs(tree)
            %   epochs = epicTreeTools.getTreeEpochs(tree, true)
            %
            % See also: epicTreeTools.getAllEpochs, epicTreeTools.getSelectedData

            if nargin < 2
                onlySelected = false;
            end

            if ~isa(treeNode, 'epicTreeTools')
                error('getTreeEpochs:InvalidInput', 'Input must be an epicTreeTools node');
            end

            epochList = treeNode.getAllEpochs(onlySelected);
        end

        function results = MeanSelectedNodes(nodes, streamName, varargin)
            % MEANSELECTEDNODES Compare mean responses across multiple tree nodes
            %
            % Usage:
            %   results = epicTreeTools.MeanSelectedNodes(nodes, 'Amp1')
            %   results = epicTreeTools.MeanSelectedNodes(nodes, 'Amp1', 'PreTime', 500)
            %
            % See also: epicTreeTools.getSelectedData, epicTreeTools.getMeanResponseTrace

            p = inputParser;
            p.addRequired('nodes', @iscell);
            p.addRequired('streamName', @ischar);
            p.addParameter('h5_file', '', @ischar);
            p.addParameter('PreTime', [], @(x) isempty(x) || isnumeric(x));
            p.addParameter('StimTime', [], @(x) isempty(x) || isnumeric(x));
            p.addParameter('BaselineCorrect', true, @islogical);
            p.addParameter('Normalize', false, @islogical);
            p.addParameter('SmoothPts', 10, @isnumeric);
            p.addParameter('PlotOffset', 0, @isnumeric);
            p.addParameter('LineWidth', 1.5, @isnumeric);
            p.addParameter('Colors', 'auto', @(x) ischar(x) || isnumeric(x));
            p.addParameter('Figure', [], @(x) isempty(x) || isnumeric(x) || ishandle(x));
            p.addParameter('HoldOn', false, @islogical);
            p.addParameter('ShowLegend', true, @islogical);
            p.addParameter('ShowAnalysis', true, @islogical);
            p.parse(nodes, streamName, varargin{:});
            opts = p.Results;

            nNodes = length(nodes);
            if nNodes == 0
                error('MeanSelectedNodes:NoNodes', 'No nodes provided');
            end

            if ischar(opts.Colors) && strcmp(opts.Colors, 'auto')
                colors = lines(nNodes);
            else
                colors = opts.Colors;
                if size(colors, 1) < nNodes
                    colors = repmat(colors, ceil(nNodes/size(colors,1)), 1);
                end
            end

            results = struct();
            results.splitValue = zeros(1, nNodes);
            results.respAmp = zeros(1, nNodes);
            results.nEpochs = zeros(1, nNodes);
            results.meanResponse = [];
            results.semResponse = [];

            legendLabels = cell(1, nNodes);

            for i = 1:nNodes
                node = nodes{i};

                [dataMatrix, epochs, sampleRate] = epicTreeTools.getSelectedData(node, streamName, opts.h5_file);

                if isempty(dataMatrix)
                    warning('MeanSelectedNodes:NoData', 'No data for node %d', i);
                    continue;
                end

                if isempty(results.meanResponse)
                    results.sampleRate = sampleRate;
                    nSamples = size(dataMatrix, 2);
                    results.meanResponse = zeros(nNodes, nSamples);
                    results.semResponse = zeros(nNodes, nSamples);
                    results.timeVector = (1:nSamples) / sampleRate;
                end

                if ~isempty(epochs) && isfield(epochs{1}, 'parameters')
                    params = epochs{1}.parameters;
                    if isempty(opts.PreTime) && isfield(params, 'preTime')
                        preTime = params.preTime;
                    else
                        preTime = opts.PreTime;
                    end
                    if isempty(opts.StimTime) && isfield(params, 'stimTime')
                        stimTime = params.stimTime;
                    else
                        stimTime = opts.StimTime;
                    end
                else
                    preTime = opts.PreTime;
                    stimTime = opts.StimTime;
                end

                if ~isempty(preTime)
                    prePts = round(preTime / 1000 * sampleRate);
                else
                    prePts = round(size(dataMatrix, 2) * 0.1);
                end
                if ~isempty(stimTime)
                    stimPts = round(stimTime / 1000 * sampleRate);
                else
                    stimPts = round(size(dataMatrix, 2) * 0.5);
                end

                if opts.BaselineCorrect && prePts > 1
                    baselines = mean(dataMatrix(:, 1:prePts), 2, 'omitnan');
                    dataMatrix = dataMatrix - baselines;
                end

                meanTrace = mean(dataMatrix, 1, 'omitnan');
                nValidRows = sum(~all(isnan(dataMatrix), 2));
                semTrace = std(dataMatrix, 0, 1, 'omitnan') / sqrt(max(nValidRows, 1));

                if opts.SmoothPts > 1
                    kernel = gausswin(opts.SmoothPts);
                    kernel = kernel / sum(kernel);
                    meanTrace = conv(meanTrace, kernel, 'same');
                    semTrace = conv(semTrace, kernel, 'same');
                end

                results.meanResponse(i, :) = meanTrace;
                results.semResponse(i, :) = semTrace;
                results.nEpochs(i) = size(dataMatrix, 1);

                if prePts + stimPts <= length(meanTrace)
                    stimRegion = meanTrace(prePts+1 : prePts+stimPts);
                    results.respAmp(i) = sum(stimRegion) / sampleRate;
                else
                    results.respAmp(i) = sum(meanTrace(prePts+1:end)) / sampleRate;
                end

                if isnumeric(node.splitValue)
                    results.splitValue(i) = node.splitValue;
                    legendLabels{i} = sprintf('%g (n=%d)', node.splitValue, results.nEpochs(i));
                else
                    results.splitValue(i) = i;
                    legendLabels{i} = sprintf('%s (n=%d)', string(node.splitValue), results.nEpochs(i));
                end
            end

            if opts.Normalize && max(abs(results.respAmp)) > 0
                results.respAmp = results.respAmp / max(abs(results.respAmp));
            end

            if opts.ShowAnalysis
                numSubplots = 2;
            else
                numSubplots = 1;
            end

            if isempty(opts.Figure)
                fig = figure('Name', 'Mean Selected Nodes', 'NumberTitle', 'off');
            else
                fig = figure(opts.Figure);
            end

            if ~opts.HoldOn
                clf(fig);
            end

            subplot(1, numSubplots, 1);
            hold on;

            for i = 1:nNodes
                if results.nEpochs(i) > 0
                    t = results.timeVector;
                    y = results.meanResponse(i, :) + opts.PlotOffset * (i-1);

                    yUpper = y + results.semResponse(i, :);
                    yLower = y - results.semResponse(i, :);
                    fill([t fliplr(t)], [yUpper fliplr(yLower)], colors(i,:), ...
                        'EdgeColor', 'none', 'FaceAlpha', 0.2);

                    plot(t, y, 'Color', colors(i,:), 'LineWidth', opts.LineWidth);
                end
            end

            xlabel('Time (s)');
            ylabel('Response');
            title('Mean Responses');

            if opts.ShowLegend
                legend(legendLabels{results.nEpochs > 0}, 'Location', 'best');
            end

            if opts.ShowAnalysis
                subplot(1, numSubplots, 2);
                hold on;

                validIdx = results.nEpochs > 0;
                plot(results.splitValue(validIdx), results.respAmp(validIdx), 'ko-', ...
                    'MarkerFaceColor', 'k', 'LineWidth', 1.5, 'MarkerSize', 8);

                xlabel('Split Value');
                ylabel('Integrated Response');
                title('Response vs Condition');
                grid on;
            end
        end

        function result = getCycleAverageResponse(epochListOrNode, streamName, varargin)
            % GETCYCLEAVERAGERESPONSE Compute cycle-averaged response for periodic stimuli
            %
            % Usage:
            %   result = epicTreeTools.getCycleAverageResponse(epochs, 'Amp1', 'Frequency', 2)
            %   result = epicTreeTools.getCycleAverageResponse(treeNode, 'Amp1')
            %
            % See also: epicTreeTools.getMeanResponseTrace

            ip = inputParser;
            ip.addRequired('epochListOrNode');
            ip.addRequired('streamName', @ischar);
            ip.addParameter('Frequency', [], @isnumeric);
            ip.addParameter('NumCycles', [], @isnumeric);
            ip.addParameter('SkipCycles', 1, @isnumeric);
            ip.addParameter('OnlySelected', true, @islogical);
            ip.addParameter('BaselineSubtract', true, @islogical);
            ip.parse(epochListOrNode, streamName, varargin{:});

            stimFreq = ip.Results.Frequency;
            numCycles = ip.Results.NumCycles;
            skipCycles = ip.Results.SkipCycles;
            onlySelected = ip.Results.OnlySelected;
            baselineSubtract = ip.Results.BaselineSubtract;

            if isa(epochListOrNode, 'epicTreeTools')
                epochs = epochListOrNode.getAllEpochs(onlySelected);
            elseif iscell(epochListOrNode)
                if onlySelected
                    epochs = {};
                    for i = 1:length(epochListOrNode)
                        ep = epochListOrNode{i};
                        if ~isfield(ep, 'isSelected') || ep.isSelected
                            epochs{end+1} = ep; %#ok<AGROW>
                        end
                    end
                    epochs = epochs(:);
                else
                    epochs = epochListOrNode;
                end
            else
                error('Input must be epicTreeTools node or cell array of epochs');
            end

            result = struct();
            result.n = length(epochs);

            if result.n == 0
                result.cycleAverage = [];
                result.cycleStd = [];
                result.cycleSEM = [];
                result.cycleTime = [];
                result.F1amplitude = NaN;
                result.F1phase = NaN;
                result.F2amplitude = NaN;
                result.F2phase = NaN;
                result.F1F2ratio = NaN;
                result.DC = NaN;
                result.frequency = NaN;
                result.nCycles = 0;
                return;
            end

            if isempty(stimFreq)
                epoch1 = epochs{1};
                if isfield(epoch1, 'parameters')
                    params = epoch1.parameters;
                    if isfield(params, 'temporal_frequency')
                        stimFreq = params.temporal_frequency;
                    elseif isfield(params, 'temporalFrequency')
                        stimFreq = params.temporalFrequency;
                    end
                end
            end

            if isempty(stimFreq) || stimFreq <= 0
                error('Stimulus frequency must be provided or available in epoch.parameters.temporal_frequency');
            end

            result.frequency = stimFreq;

            [dataMatrix, sampleRate] = epicTreeTools.getResponseMatrix(epochs, streamName);

            if isempty(dataMatrix)
                result.cycleAverage = [];
                result.cycleStd = [];
                result.cycleSEM = [];
                result.cycleTime = [];
                result.F1amplitude = NaN;
                result.F1phase = NaN;
                result.F2amplitude = NaN;
                result.F2phase = NaN;
                result.F1F2ratio = NaN;
                result.DC = NaN;
                result.nCycles = 0;
                return;
            end

            preTime = 0;
            stimTime = 1;
            if ~isempty(epochs)
                epoch1 = epochs{1};
                if isfield(epoch1, 'parameters')
                    params = epoch1.parameters;
                    if isfield(params, 'preTime')
                        preTime = params.preTime / 1000;
                    end
                    if isfield(params, 'stimTime')
                        stimTime = params.stimTime / 1000;
                    end
                end
            end

            if baselineSubtract
                baselinePoints = max(1, round(preTime * sampleRate));
                baselines = mean(dataMatrix(:, 1:baselinePoints), 2, 'omitnan');
                dataMatrix = dataMatrix - baselines;
            end

            nSamples = size(dataMatrix, 2);
            timeVector = (0:nSamples-1) / sampleRate;
            stimIdx = timeVector >= preTime & timeVector < (preTime + stimTime);
            stimData = dataMatrix(:, stimIdx);
            stimTime_actual = timeVector(stimIdx) - preTime;

            cyclePeriod = 1 / stimFreq;
            pointsPerCycle = round(cyclePeriod * sampleRate);
            totalCycles = floor(length(stimTime_actual) / pointsPerCycle);

            if isempty(numCycles) || numCycles > (totalCycles - skipCycles)
                numCycles = totalCycles - skipCycles;
            end

            if numCycles < 1
                warning('Not enough cycles for averaging');
                result.cycleAverage = [];
                result.cycleStd = [];
                result.cycleSEM = [];
                result.cycleTime = [];
                result.F1amplitude = NaN;
                result.F1phase = NaN;
                result.F2amplitude = NaN;
                result.F2phase = NaN;
                result.F1F2ratio = NaN;
                result.DC = NaN;
                result.nCycles = 0;
                return;
            end

            result.nCycles = numCycles;
            result.cycleTime = (0:pointsPerCycle-1) / sampleRate;

            allCycles = [];

            for i = 1:result.n
                trace = stimData(i, :);

                for c = (skipCycles + 1):(skipCycles + numCycles)
                    startIdx = (c - 1) * pointsPerCycle + 1;
                    endIdx = c * pointsPerCycle;

                    if endIdx <= length(trace)
                        cycle = trace(startIdx:endIdx);
                        allCycles = [allCycles; cycle]; %#ok<AGROW>
                    end
                end
            end

            if isempty(allCycles)
                result.cycleAverage = [];
                result.cycleStd = [];
                result.cycleSEM = [];
                result.F1amplitude = NaN;
                result.F1phase = NaN;
                result.F2amplitude = NaN;
                result.F2phase = NaN;
                result.F1F2ratio = NaN;
                result.DC = NaN;
                return;
            end

            result.cycleAverage = mean(allCycles, 1, 'omitnan');
            result.cycleStd = std(allCycles, 0, 1, 'omitnan');
            nValidCycles = sum(~all(isnan(allCycles), 2));
            result.cycleSEM = result.cycleStd / sqrt(max(nValidCycles, 1));

            result.DC = mean(result.cycleAverage);

            n = length(result.cycleAverage);
            t = (0:n-1) / sampleRate;
            sinComponent = sum(result.cycleAverage .* sin(2*pi*stimFreq*t)) * 2 / n;
            cosComponent = sum(result.cycleAverage .* cos(2*pi*stimFreq*t)) * 2 / n;
            result.F1amplitude = sqrt(sinComponent^2 + cosComponent^2);
            result.F1phase = atan2d(sinComponent, cosComponent);

            sinComponent2 = sum(result.cycleAverage .* sin(2*pi*2*stimFreq*t)) * 2 / n;
            cosComponent2 = sum(result.cycleAverage .* cos(2*pi*2*stimFreq*t)) * 2 / n;
            result.F2amplitude = sqrt(sinComponent2^2 + cosComponent2^2);
            result.F2phase = atan2d(sinComponent2, cosComponent2);

            if result.F2amplitude > 0
                result.F1F2ratio = result.F1amplitude / result.F2amplitude;
            else
                result.F1F2ratio = Inf;
            end
        end

        function result = getLinearFilterAndPrediction(epochListOrNode, stimStreamName, respStreamName, varargin)
            % GETLINEARFILTERANDPREDICTION Compute linear filter (STA) and prediction
            %
            % Usage:
            %   result = epicTreeTools.getLinearFilterAndPrediction(epochs, 'Stage', 'Amp1')
            %   result = epicTreeTools.getLinearFilterAndPrediction(treeNode, 'LED', 'Amp1', 'FilterLength', 500)
            %
            % See also: epicTreeTools.getMeanResponseTrace, epicTreeTools.getCycleAverageResponse

            ip = inputParser;
            ip.addRequired('epochListOrNode');
            ip.addRequired('stimStreamName', @ischar);
            ip.addRequired('respStreamName', @ischar);
            ip.addParameter('FilterLength', 500, @isnumeric);
            ip.addParameter('OnlySelected', true, @islogical);
            ip.addParameter('Method', 'correlation', @ischar);
            ip.parse(epochListOrNode, stimStreamName, respStreamName, varargin{:});

            filterLengthMs = ip.Results.FilterLength;
            onlySelected = ip.Results.OnlySelected;
            method = lower(ip.Results.Method);

            if isa(epochListOrNode, 'epicTreeTools')
                epochs = epochListOrNode.getAllEpochs(onlySelected);
            elseif iscell(epochListOrNode)
                if onlySelected
                    epochs = {};
                    for i = 1:length(epochListOrNode)
                        ep = epochListOrNode{i};
                        if ~isfield(ep, 'isSelected') || ep.isSelected
                            epochs{end+1} = ep; %#ok<AGROW>
                        end
                    end
                    epochs = epochs(:);
                else
                    epochs = epochListOrNode;
                end
            else
                error('Input must be epicTreeTools node or cell array of epochs');
            end

            result = struct();
            result.n = length(epochs);

            if result.n == 0
                result.filter = [];
                result.filterTime = [];
                result.prediction = [];
                result.response = [];
                result.stimulus = [];
                result.correlation = NaN;
                result.sampleRate = [];
                return;
            end

            [respMatrix, sampleRate] = epicTreeTools.getResponseMatrix(epochs, respStreamName);

            if isempty(respMatrix)
                result.filter = [];
                result.filterTime = [];
                result.prediction = [];
                result.response = [];
                result.stimulus = [];
                result.correlation = NaN;
                result.sampleRate = [];
                return;
            end

            result.sampleRate = sampleRate;

            try
                [stimMatrix, ~] = epicTreeTools.getStimulusMatrix(epochs, stimStreamName);
            catch
                stimMatrix = [];
            end

            if isempty(stimMatrix)
                % Fallback: try getStimulusByName per-epoch
                stimMatrix = zeros(size(respMatrix));
                for i = 1:result.n
                    stim = epicTreeTools.getStimulusByName(epochs{i}, stimStreamName);
                    if ~isempty(stim) && isfield(stim, 'data') && ~isempty(stim.data)
                        data = stim.data(:)';
                        if length(data) >= size(stimMatrix, 2)
                            stimMatrix(i, :) = data(1:size(stimMatrix, 2));
                        else
                            stimMatrix(i, 1:length(data)) = data;
                        end
                    end
                end
            elseif size(stimMatrix, 2) ~= size(respMatrix, 2)
                % Trim or pad to match response length
                if size(stimMatrix, 2) > size(respMatrix, 2)
                    stimMatrix = stimMatrix(:, 1:size(respMatrix, 2));
                else
                    padded = zeros(size(respMatrix));
                    padded(:, 1:size(stimMatrix, 2)) = stimMatrix;
                    stimMatrix = padded;
                end
            end

            filterLength = round(filterLengthMs / 1000 * sampleRate);
            result.filterTime = (0:filterLength-1) / sampleRate * 1000;

            allStim = [];
            allResp = [];
            for i = 1:result.n
                allStim = [allStim, stimMatrix(i, :)]; %#ok<AGROW>
                allResp = [allResp, respMatrix(i, :)]; %#ok<AGROW>
            end

            allStim = allStim - mean(allStim);
            allResp = allResp - mean(allResp);

            result.stimulus = allStim;
            result.response = allResp;

            switch method
                case 'correlation'
                    result.filter = epicTreeTools.computeFilterByCorrelation(allStim, allResp, filterLength);
                case 'sta'
                    result.filter = epicTreeTools.computeFilterByCorrelation(allStim, allResp, filterLength);
                otherwise
                    result.filter = epicTreeTools.computeFilterByCorrelation(allStim, allResp, filterLength);
            end

            if max(abs(result.filter)) > 0
                result.filter = result.filter / max(abs(result.filter));
            end

            result.prediction = conv(allStim, result.filter, 'same');

            scaleFactor = std(allResp) / std(result.prediction);
            result.prediction = result.prediction * scaleFactor;

            validIdx = ~isnan(result.response) & ~isnan(result.prediction);
            if sum(validIdx) > 0
                R = corrcoef(result.response(validIdx), result.prediction(validIdx));
                result.correlation = R(1, 2);
            else
                result.correlation = NaN;
            end
        end

        function response = getMeanResponseTrace(epochListOrNode, streamName, varargin)
            % GETMEANRESPONSETRACE Compute mean response trace with statistics
            %
            % Usage:
            %   response = epicTreeTools.getMeanResponseTrace(epochs, 'Amp1')
            %   response = epicTreeTools.getMeanResponseTrace(treeNode, 'Amp1')
            %   response = epicTreeTools.getMeanResponseTrace(epochs, 'Amp1', 'RecordingType', 'exc')
            %
            % See also: epicTreeTools.getSelectedData, getResponseMatrix, epicTreeTools.getResponseAmplitudeStats

            ip = inputParser;
            ip.addRequired('epochListOrNode');
            ip.addRequired('streamName', @ischar);
            ip.addParameter('RecordingType', 'raw', @ischar);
            ip.addParameter('BaselineSubtract', [], @islogical);
            ip.addParameter('PSTHsigma', 10, @isnumeric);
            ip.addParameter('OnlySelected', true, @islogical);
            ip.parse(epochListOrNode, streamName, varargin{:});

            recordingType = lower(ip.Results.RecordingType);
            PSTHsigma = ip.Results.PSTHsigma;
            onlySelected = ip.Results.OnlySelected;

            if isempty(ip.Results.BaselineSubtract)
                baselineSubtract = ismember(recordingType, {'exc', 'inh'});
            else
                baselineSubtract = ip.Results.BaselineSubtract;
            end

            if isa(epochListOrNode, 'epicTreeTools')
                epochs = epochListOrNode.getAllEpochs(onlySelected);
            elseif iscell(epochListOrNode)
                if onlySelected
                    epochs = {};
                    for i = 1:length(epochListOrNode)
                        ep = epochListOrNode{i};
                        if ~isfield(ep, 'isSelected') || ep.isSelected
                            epochs{end+1} = ep; %#ok<AGROW>
                        end
                    end
                    epochs = epochs(:);
                else
                    epochs = epochListOrNode;
                end
            else
                error('Input must be epicTreeTools node or cell array of epochs');
            end

            response = struct();
            response.n = length(epochs);

            if response.n == 0
                response.mean = [];
                response.stdev = [];
                response.SEM = [];
                response.timeVector = [];
                response.sampleRate = [];
                response.units = '';
                response.baseline = [];
                return;
            end

            h5_file = '';
            if ~isempty(epochs)
                epoch1 = epochs{1};
                if isfield(epoch1, 'h5_file') && ~isempty(epoch1.h5_file)
                    h5_file = epoch1.h5_file;
                end
            end

            [dataMatrix, sampleRate] = epicTreeTools.getResponseMatrix(epochs, streamName, h5_file);

            if isempty(dataMatrix)
                response.mean = [];
                response.stdev = [];
                response.SEM = [];
                response.timeVector = [];
                response.sampleRate = [];
                response.units = '';
                response.baseline = [];
                return;
            end

            if iscell(sampleRate)
                sampleRate = sampleRate{1};
            end
            sampleRate = double(sampleRate);
            response.sampleRate = sampleRate;

            nSamples = size(dataMatrix, 2);
            response.timeVector = (0:nSamples-1) / sampleRate;

            preTime = 0;
            if ~isempty(epochs)
                epoch1 = epochs{1};
                if isfield(epoch1, 'parameters') && isfield(epoch1.parameters, 'preTime')
                    preTime = epoch1.parameters.preTime / 1000;
                end
            end
            baselinePoints = max(1, round(preTime * sampleRate));

            switch recordingType
                case 'extracellular'
                    response.units = 'spikes/s';

                    spikeTimes = cell(response.n, 1);
                    for i = 1:response.n
                        resp = epicTreeTools.getResponseByName(epochs{i}, streamName);
                        if ~isempty(resp) && isfield(resp, 'spike_times')
                            spikeTimes{i} = resp.spike_times / 1000;
                        else
                            spikeTimes{i} = [];
                        end
                    end

                    dataMatrix = epicTreeTools.computePSTH(spikeTimes, response.timeVector, PSTHsigma/1000);
                    response.baseline = [];

                case {'exc', 'inh'}
                    response.units = 'pA';

                    if baselineSubtract && baselinePoints > 1
                        baselines = mean(dataMatrix(:, 1:baselinePoints), 2, 'omitnan');
                        dataMatrix = dataMatrix - baselines;
                        response.baseline = mean(baselines, 'omitnan');
                    else
                        response.baseline = [];
                    end

                case 'iclamp'
                    response.units = 'mV';

                    if baselineSubtract && baselinePoints > 1
                        baselines = mean(dataMatrix(:, 1:baselinePoints), 2, 'omitnan');
                        dataMatrix = dataMatrix - baselines;
                        response.baseline = mean(baselines, 'omitnan');
                    else
                        response.baseline = [];
                    end

                otherwise
                    response.units = 'AU';
                    response.baseline = [];
            end

            response.mean = mean(dataMatrix, 1, 'omitnan');
            response.stdev = std(dataMatrix, 0, 1, 'omitnan');
            nValidRows = sum(~all(isnan(dataMatrix), 2));
            response.SEM = response.stdev / sqrt(max(nValidRows, 1));
        end

        function stats = getResponseAmplitudeStats(epochListOrNode, streamName, varargin)
            % GETRESPONSEAMPLITUDESTATS Compute response amplitude statistics
            %
            % Usage:
            %   stats = epicTreeTools.getResponseAmplitudeStats(epochs, 'Amp1')
            %   stats = epicTreeTools.getResponseAmplitudeStats(treeNode, 'Amp1', 'ResponseWindow', [0.5 1.5])
            %
            % See also: epicTreeTools.getMeanResponseTrace, epicTreeTools.getSelectedData

            ip = inputParser;
            ip.addRequired('epochListOrNode');
            ip.addRequired('streamName', @ischar);
            ip.addParameter('RecordingType', 'exc', @ischar);
            ip.addParameter('ResponseWindow', [], @isnumeric);
            ip.addParameter('BaselineWindow', [], @isnumeric);
            ip.addParameter('OnlySelected', true, @islogical);
            ip.parse(epochListOrNode, streamName, varargin{:});

            recordingType = lower(ip.Results.RecordingType);
            responseWindow = ip.Results.ResponseWindow;
            baselineWindow = ip.Results.BaselineWindow;
            onlySelected = ip.Results.OnlySelected;

            if isa(epochListOrNode, 'epicTreeTools')
                epochs = epochListOrNode.getAllEpochs(onlySelected);
            elseif iscell(epochListOrNode)
                if onlySelected
                    epochs = {};
                    for i = 1:length(epochListOrNode)
                        ep = epochListOrNode{i};
                        if ~isfield(ep, 'isSelected') || ep.isSelected
                            epochs{end+1} = ep; %#ok<AGROW>
                        end
                    end
                    epochs = epochs(:);
                else
                    epochs = epochListOrNode;
                end
            else
                error('Input must be epicTreeTools node or cell array of epochs');
            end

            stats = struct();
            stats.n = length(epochs);

            if stats.n == 0
                stats.peakAmplitude = [];
                stats.peakTime = [];
                stats.integratedResponse = [];
                stats.meanAmplitude = [];
                stats.baseline = [];
                stats.mean_peak = NaN;
                stats.std_peak = NaN;
                stats.sem_peak = NaN;
                stats.mean_integrated = NaN;
                stats.std_integrated = NaN;
                stats.sem_integrated = NaN;
                stats.units = '';
                return;
            end

            [dataMatrix, sampleRate] = epicTreeTools.getResponseMatrix(epochs, streamName);

            if isempty(dataMatrix)
                stats.peakAmplitude = [];
                stats.peakTime = [];
                stats.integratedResponse = [];
                stats.meanAmplitude = [];
                stats.baseline = [];
                stats.mean_peak = NaN;
                stats.std_peak = NaN;
                stats.sem_peak = NaN;
                stats.mean_integrated = NaN;
                stats.std_integrated = NaN;
                stats.sem_integrated = NaN;
                stats.units = '';
                return;
            end

            nSamples = size(dataMatrix, 2);
            timeVector = (0:nSamples-1) / sampleRate;

            preTime = 0;
            stimTime = 1;
            if ~isempty(epochs)
                epoch1 = epochs{1};
                if isfield(epoch1, 'parameters')
                    params = epoch1.parameters;
                    if isfield(params, 'preTime')
                        preTime = params.preTime / 1000;
                    end
                    if isfield(params, 'stimTime')
                        stimTime = params.stimTime / 1000;
                    end
                end
            end

            if isempty(baselineWindow)
                baselineWindow = [0, preTime];
            end
            if isempty(responseWindow)
                responseWindow = [preTime, preTime + stimTime];
            end

            baselineIdx = timeVector >= baselineWindow(1) & timeVector < baselineWindow(2);
            responseIdx = timeVector >= responseWindow(1) & timeVector < responseWindow(2);

            if sum(baselineIdx) == 0
                baselineIdx(1:min(10, nSamples)) = true;
            end
            if sum(responseIdx) == 0
                responseIdx = true(1, nSamples);
            end

            switch recordingType
                case 'exc'
                    stats.units = 'pA';
                case 'inh'
                    stats.units = 'pA';
                case 'extracellular'
                    stats.units = 'spikes';
                otherwise
                    stats.units = 'AU';
            end

            stats.baseline = mean(dataMatrix(:, baselineIdx), 2, 'omitnan');

            dataSubtracted = dataMatrix - stats.baseline;

            responseData = dataSubtracted(:, responseIdx);
            responseTime = timeVector(responseIdx);

            nEpochs = stats.n;
            stats.peakAmplitude = zeros(nEpochs, 1);
            stats.peakTime = zeros(nEpochs, 1);
            stats.integratedResponse = zeros(nEpochs, 1);
            stats.meanAmplitude = zeros(nEpochs, 1);

            dt = 1 / sampleRate;

            for i = 1:nEpochs
                trace = responseData(i, :);

                if strcmp(recordingType, 'inh')
                    [pk, pkIdx] = max(trace);
                else
                    [pk, pkIdx] = min(trace);
                end

                stats.peakAmplitude(i) = pk;
                stats.peakTime(i) = responseTime(pkIdx);

                stats.integratedResponse(i) = trapz(trace) * dt;

                stats.meanAmplitude(i) = mean(trace);
            end

            stats.mean_peak = mean(stats.peakAmplitude);
            stats.std_peak = std(stats.peakAmplitude);
            stats.sem_peak = stats.std_peak / sqrt(nEpochs);

            stats.mean_integrated = mean(stats.integratedResponse);
            stats.std_integrated = std(stats.integratedResponse);
            stats.sem_integrated = stats.std_integrated / sqrt(nEpochs);

            stats.mean_meanAmplitude = mean(stats.meanAmplitude);
            stats.std_meanAmplitude = std(stats.meanAmplitude);
            stats.sem_meanAmplitude = stats.std_meanAmplitude / sqrt(nEpochs);
        end

        %% ================================================================
        % PRIVATE HELPER METHODS (used by analysis functions above)
        % ================================================================

        function filter = computeFilterByCorrelation(stimulus, response, filterLength)
            % COMPUTEFILTERBYCORRELATION Compute filter using cross-correlation
            %
            % Uses Wiener-Hopf equation: filter = R_ss^(-1) * R_sr

            n = length(stimulus);

            xcorr_sr = zeros(1, filterLength);
            for lag = 0:filterLength-1
                if lag + 1 <= n
                    xcorr_sr(lag + 1) = sum(stimulus(1:n-lag) .* response(lag+1:n)) / (n - lag);
                end
            end

            xcorr_ss = zeros(filterLength, filterLength);
            for i = 0:filterLength-1
                for j = 0:filterLength-1
                    lag = abs(i - j);
                    if lag + 1 <= n
                        xcorr_ss(i+1, j+1) = sum(stimulus(1:n-lag) .* stimulus(lag+1:n)) / (n - lag);
                    end
                end
            end

            lambda = 0.01 * trace(xcorr_ss) / filterLength;
            filter = (xcorr_ss + lambda * eye(filterLength)) \ xcorr_sr';
            filter = filter';
        end

        function psth = computePSTH(spikeTimes, timeVector, sigma)
            % COMPUTEPSTH Compute PSTH from spike times using Gaussian kernel

            nTrials = length(spikeTimes);
            nTimePoints = length(timeVector);
            dt = timeVector(2) - timeVector(1);

            kernelWidth = ceil(4 * sigma / dt);
            kernelX = (-kernelWidth:kernelWidth) * dt;
            kernel = exp(-kernelX.^2 / (2 * sigma^2));
            kernel = kernel / (sigma * sqrt(2 * pi));

            psth = zeros(nTrials, nTimePoints);

            for i = 1:nTrials
                spikes = spikeTimes{i};
                if isempty(spikes)
                    continue;
                end

                spikeTrain = zeros(1, nTimePoints);
                for j = 1:length(spikes)
                    idx = find(timeVector >= spikes(j), 1, 'first');
                    if ~isempty(idx) && idx <= nTimePoints
                        spikeTrain(idx) = spikeTrain(idx) + 1;
                    end
                end

                smoothed = conv(spikeTrain, kernel, 'same');
                psth(i, :) = smoothed;
            end
        end

        function [dataMatrix, sampleRate] = getResponseMatrix(epochList, streamName, h5_file)
            % GETRESPONSEMATRIX Extract response data matrix from epoch list
            %
            % THIS IS THE CORE DATA EXTRACTION FUNCTION.
            % Returns a matrix where each row is one epoch's response data.
            %
            % Usage:
            %   [data, fs] = epicTreeTools.getResponseMatrix(epochs, 'Amp1')
            %   [data, fs] = epicTreeTools.getResponseMatrix(epochs, 'Amp1', '/path/to/file.h5')
            %
            % Inputs:
            %   epochList  - Cell array of epoch structs
            %   streamName - Device name (e.g., 'Amp1', 'Amp2', 'Stage')
            %   h5_file    - (Optional) Fallback when the response/epoch has no H5 pointer
            %
            % Outputs:
            %   dataMatrix - [nEpochs x nSamples] response data matrix
            %   sampleRate - Sample rate in Hz (from first epoch)
            %
            % Errors on variable-length responses (matching legacy Java
            % riekesuite.getResponseMatrix behavior). All epochs must have
            % the same response length for the given stream.
            %
            % See also: epicTreeTools.getSelectedData, epicTreeTools.getResponseFromEpoch

            % Validate input
            if isempty(epochList)
                dataMatrix = [];
                sampleRate = [];
                return;
            end

            % Ensure epochList is a cell array
            if ~iscell(epochList)
                epochList = {epochList};
            end

            % Handle optional h5_file parameter
            if nargin < 3
                h5_file = '';
            end

            nEpochs = length(epochList);

            % Get first response to determine size and sample rate
            [firstData, sampleRate] = epicTreeTools.getResponseFromEpoch(epochList{1}, streamName, h5_file);

            if isempty(firstData)
                warning('epicTreeTools:getResponseMatrix:StreamNotFound', ...
                    'Response stream "%s" not found in first epoch', streamName);
                dataMatrix = [];
                return;
            end

            nSamples = length(firstData);

            % Pre-allocate output matrix
            dataMatrix = zeros(nEpochs, nSamples);
            dataMatrix(1, :) = firstData;

            % Extract data from remaining epochs
            for i = 2:nEpochs
                [data, ~] = epicTreeTools.getResponseFromEpoch(epochList{i}, streamName, h5_file);

                if isempty(data)
                    error('epicTreeTools:getResponseMatrix:StreamNotFound', ...
                        'Response stream "%s" not found in epoch %d of %d.', ...
                        streamName, i, nEpochs);
                end

                % Strict length check (matches legacy Java behavior)
                if length(data) ~= nSamples
                    error('epicTreeTools:getResponseMatrix:InconsistentLength', ...
                        'Inconsistent data length in epoch %d (was %d, expected %d). All epochs must have same response length for stream "%s".', ...
                        i, length(data), nSamples, streamName);
                end

                dataMatrix(i, :) = data;
            end
        end

        function [data, sampleRate] = getResponseFromEpoch(epoch, streamName, h5_file)
            % GETRESPONSEFROMEPOCH Extract response data from a single epoch
            %
            % Searches epoch.responses array for matching device_name.
            % Supports lazy loading from H5 files when data field is empty.
            %
            % Inputs:
            %   epoch      - Epoch struct with responses field
            %   streamName - Device name to find (e.g., 'Amp1')
            %   h5_file    - (Optional) Fallback when the response/epoch has no H5 pointer

            data = [];
            sampleRate = [];

            if nargin < 3
                h5_file = '';
            end

            % Check if responses field exists
            if ~isfield(epoch, 'responses')
                return;
            end

            responses = epoch.responses;

            % Find the matching response
            resp = [];
            if isstruct(responses)
                for i = 1:length(responses)
                    if isfield(responses(i), 'device_name') && strcmp(responses(i).device_name, streamName)
                        resp = responses(i);
                        break;
                    end
                end
            elseif iscell(responses)
                for i = 1:length(responses)
                    r = responses{i};
                    if isfield(r, 'device_name') && strcmp(r.device_name, streamName)
                        resp = r;
                        break;
                    end
                end
            end

            if isempty(resp)
                return;
            end

            % Get sample rate
            if isfield(resp, 'sample_rate')
                sampleRate = resp.sample_rate;
            end

            % Get data - try direct field first, then lazy load from H5
            if isfield(resp, 'data') && ~isempty(resp.data) && ~isfield(resp, 'source_sha256')
                data = resp.data(:)';  % Ensure row vector
            else
                % Lazy load from H5 file
                hasH5Path = isfield(resp, 'h5_path') && ~isempty(resp.h5_path);

                % Per-stream acquisition pointers take precedence over a project-wide
                % fallback, which may belong to another recording in this tree.
                % Use loadH5ResponseData(resp, path) for an intentional override.
                actualH5File = '';
                if isfield(resp, 'h5_file') && ~isempty(resp.h5_file)
                    actualH5File = resp.h5_file;
                end
                if isempty(actualH5File) && isfield(epoch, 'h5_file') && ~isempty(epoch.h5_file)
                    actualH5File = epoch.h5_file;
                end

                if isempty(actualH5File)
                    actualH5File = h5_file;
                end

                if isfield(resp, 'source_sha256') && (~hasH5Path || isempty(actualH5File))
                    error('workspaceSource:Unavailable', 'Workspace response lacks its H5 source or dataset pointer.');
                end
                if hasH5Path && ~isempty(actualH5File)
                    try
                        data = epicTreeTools.loadH5ResponseData(resp, actualH5File);
                        if ~isempty(data)
                            data = data(:)';  % Ensure row vector
                        end
                    catch ME
                        if startsWith(ME.identifier, 'workspaceSource:')
                            rethrow(ME);
                        end
                        warning('epicTreeTools:getResponseFromEpoch:H5LoadFailed', ...
                            'Failed to load H5 data: %s', ME.message);
                    end
                elseif hasH5Path
                    warning('epicTreeTools:getResponseFromEpoch:noH5File', ...
                        'Response has h5_path but no h5_file. Set h5_dir using epicTreeConfig.');
                end
            end
        end

        function data = loadH5ResponseData(response, h5_file)
            % LOADH5RESPONSEDATA Load response data from H5 file on demand
            %
            % Implements lazy loading of response data from H5 files.
            %
            % Usage:
            %   data = epicTreeTools.loadH5ResponseData(response)
            %   data = epicTreeTools.loadH5ResponseData(response, h5_file)
            %
            % Input:
            %   response - Response struct with .h5_path, optionally .h5_file, .data
            %   h5_file  - (Optional) Path to H5 file, overrides response.h5_file
            %
            % Output:
            %   data - Response data as column vector
            %
            % See also: epicTreeTools.getResponseMatrix, epicTreeTools.getResponseFromEpoch

            data = [];

            % Handle cell array of responses
            if iscell(response)
                response = response{1};
            end

            workspaceSource = isfield(response, 'source_sha256');

            % Check if data is already loaded
            if ~workspaceSource && isfield(response, 'data') && ~isempty(response.data)
                data = response.data(:);
                return;
            end

            % Get H5 file path - prefer parameter, then response field
            if nargin < 2 || isempty(h5_file)
                if isfield(response, 'h5_file') && ~isempty(response.h5_file)
                    h5_file = response.h5_file;
                else
                    if workspaceSource
                        error('workspaceSource:Unavailable', 'Workspace response has no H5 source path.');
                    end
                    warning('epicTreeTools:loadH5ResponseData:noH5File', ...
                        'No h5_file provided and none in response struct');
                    return;
                end
            end

            % Handle path mappings (NAS paths may differ between systems)
            if ~exist(h5_file, 'file')
                altPaths = {
                    strrep(h5_file, '/Volumes/rieke-nas/', '/Volumes/rieke/'),
                    strrep(h5_file, '/Volumes/rieke/', '/Volumes/rieke-nas/'),
                    strrep(h5_file, '/mnt/rieke-nas/', '/Volumes/rieke-nas/'),
                };

                for i = 1:length(altPaths)
                    if exist(altPaths{i}, 'file')
                        h5_file = altPaths{i};
                        break;
                    end
                end

                if ~exist(h5_file, 'file')
                    if workspaceSource
                        error('workspaceSource:Unavailable', 'Workspace H5 source is missing: %s', h5_file);
                    end
                    warning('epicTreeTools:loadH5ResponseData:fileNotFound', ...
                        'H5 file not found: %s', h5_file);
                    return;
                end
            end

            % Workspace exports bind lazy pointers to immutable source bytes.
            % Keep integrity errors outside the legacy HDF5 fallback catches.
            if workspaceSource
                token = verifyWorkspaceSource(h5_file, response.source_sha256);
                legacyResponse = rmfield(response, 'source_sha256');
                legacyResponse.data = []; % Never substitute cached waveform bytes for the verified source.
                try
                    data = epicTreeTools.loadH5ResponseData(legacyResponse, h5_file);
                catch cause
                    error('workspaceSource:ReadFailed', 'Cannot read verified workspace H5 waveform: %s', cause.message);
                end
                verifyWorkspaceSource(h5_file, response.source_sha256, token);
                if isempty(data)
                    error('workspaceSource:ReadFailed', ...
                        'Verified workspace H5 source did not yield waveform data: %s', h5_file);
                end
                return;
            end

            % Get H5 path within file
            if ~isfield(response, 'h5_path') || isempty(response.h5_path)
                warning('epicTreeTools:loadH5ResponseData:noH5Path', 'No h5_path in response');
                return;
            end

            h5_path = response.h5_path;

            % Clean path (remove leading slash if present)
            if h5_path(1) == '/'
                h5_path = h5_path(2:end);
            end

            % Load data from H5 file
            try
                dataPath = ['/' h5_path '/data'];
                rawData = h5read(h5_file, dataPath);

                if isstruct(rawData)
                    if isfield(rawData, 'quantity')
                        data = double(rawData.quantity(:));
                    elseif isfield(rawData, 'Quantity')
                        data = double(rawData.Quantity(:));
                    else
                        fn = fieldnames(rawData);
                        for i = 1:length(fn)
                            if isnumeric(rawData.(fn{i}))
                                data = double(rawData.(fn{i})(:));
                                break;
                            end
                        end
                    end
                else
                    data = double(rawData(:));
                end

            catch ME
                try
                    altPath = ['/' h5_path '/data/quantity'];
                    data = h5read(h5_file, altPath);
                    data = double(data(:));
                catch
                    try
                        info = h5info(h5_file, ['/' h5_path]);
                        for i = 1:length(info.Datasets)
                            if strcmpi(info.Datasets(i).Name, 'data')
                                data = h5read(h5_file, ['/' h5_path '/' info.Datasets(i).Name]);
                                if isstruct(data) && isfield(data, 'quantity')
                                    data = double(data.quantity(:));
                                else
                                    data = double(data(:));
                                end
                                return;
                            end
                        end

                        warning('epicTreeTools:loadH5ResponseData:noData', ...
                            'Could not find data in %s. Error: %s', h5_path, ME.message);
                    catch ME2
                        warning('epicTreeTools:loadH5ResponseData:readError', ...
                            'Error reading H5 file %s path %s: %s', ...
                            h5_file, h5_path, ME2.message);
                    end
                end
            end
        end

        function [data, sampleRate] = getStimulusFromEpoch(epoch, streamName)
            % GETSTIMULUSFROMEPOCH Extract stimulus data from a single epoch
            %
            % Searches epoch.stimuli for matching device_name. If the
            % stimulus .data field is empty but .stimulus_id and
            % .stimulus_parameters exist, auto-reconstructs the waveform
            % using epicStimulusGenerators.
            %
            % Mirrors getResponseFromEpoch for stimulus data.
            %
            % Inputs:
            %   epoch      - Epoch struct with stimuli field
            %   streamName - Stimulus device name (e.g., 'LED', 'Stage')
            %
            % Outputs:
            %   data       - 1xN row vector of stimulus waveform
            %   sampleRate - Sample rate in Hz
            %
            % See also: epicTreeTools.getStimulusMatrix, epicTreeTools.getStimulusByName

            data = [];
            sampleRate = [];

            stim = epicTreeTools.getStimulusByName(epoch, streamName);
            if isempty(stim)
                return;
            end

            if isfield(stim, 'sample_rate') && ~isempty(stim.sample_rate)
                sampleRate = stim.sample_rate;
            end

            if isfield(stim, 'data') && ~isempty(stim.data)
                data = stim.data(:)';
            end
        end

        function [dataMatrix, sampleRate] = getStimulusMatrix(epochList, streamName)
            % GETSTIMULUSMATRIX Extract stimulus data matrix from epoch list
            %
            % Returns a matrix where each row is one epoch's stimulus data.
            % Auto-reconstructs stimuli when .data is empty but stimulus_id
            % and stimulus_parameters are present (via getStimulusByName).
            %
            % Mirrors getResponseMatrix for stimulus data.
            %
            % Usage:
            %   [data, fs] = epicTreeTools.getStimulusMatrix(epochs, 'LED')
            %
            % Inputs:
            %   epochList  - Cell array of epoch structs
            %   streamName - Stimulus device name (e.g., 'LED', 'Stage')
            %
            % Outputs:
            %   dataMatrix - [nEpochs x nSamples] stimulus data matrix
            %   sampleRate - Sample rate in Hz (from first epoch)
            %
            % See also: epicTreeTools.getStimulusFromEpoch, epicTreeTools.getResponseMatrix

            if isempty(epochList)
                dataMatrix = [];
                sampleRate = [];
                return;
            end

            if ~iscell(epochList)
                epochList = {epochList};
            end

            nEpochs = length(epochList);

            [firstData, sampleRate] = epicTreeTools.getStimulusFromEpoch(epochList{1}, streamName);

            if isempty(firstData)
                dataMatrix = [];
                return;
            end

            nSamples = length(firstData);
            dataMatrix = zeros(nEpochs, nSamples);
            dataMatrix(1, :) = firstData;

            for i = 2:nEpochs
                [epochData, ~] = epicTreeTools.getStimulusFromEpoch(epochList{i}, streamName);

                if isempty(epochData)
                    warning('epicTreeTools:getStimulusMatrix:StreamNotFound', ...
                        'Stimulus stream "%s" not found in epoch %d of %d.', ...
                        streamName, i, nEpochs);
                    continue;
                end

                if length(epochData) ~= nSamples
                    warning('epicTreeTools:getStimulusMatrix:InconsistentLength', ...
                        'Inconsistent stimulus length in epoch %d (was %d, expected %d).', ...
                        i, length(epochData), nSamples);
                    len = min(length(epochData), nSamples);
                    dataMatrix(i, 1:len) = epochData(1:len);
                else
                    dataMatrix(i, :) = epochData;
                end
            end
        end
    end
end
