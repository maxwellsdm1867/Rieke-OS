function [tree, data, h5File] = loadTestTree(splitKeys)
% loadTestTree - Load test data and build epicTreeTools tree
%
% Syntax:
%   [tree, data, h5File] = loadTestTree()
%   [tree, data, h5File] = loadTestTree(splitKeys)
%
% Inputs:
%   splitKeys - Cell array of split keys or function handles (optional)
%               Default: {'cellInfo.type'}
%
% Returns:
%   tree    - epicTreeTools object with tree built using splitKeys
%   data    - Raw data loaded from .mat file
%   h5File  - Path to H5 file (if available)
%
% This is the shared test data loading function used by all test scripts.
% It ensures consistent test data and tree building across the test suite.
%
% Examples:
%   % Load with default split (cell type)
%   [tree, data, h5] = loadTestTree();
%
%   % Load with custom splits
%   [tree, data, h5] = loadTestTree({'cellInfo.type', 'blockInfo.protocol_name'});
%
%   % Load with splitter functions
%   [tree, data, h5] = loadTestTree({@epicTreeTools.splitOnCellType, ...
%                                    @epicTreeTools.splitOnExperimentDate});

    % Add specific src paths (avoid genpath which scans recursively)
    repoRoot = fileparts(fileparts(fileparts(mfilename('fullpath'))));
    addpath(fullfile(repoRoot, 'src'));
    addpath(fullfile(repoRoot, 'src', 'tree'));
    addpath(fullfile(repoRoot, 'src', 'analysis'));
    addpath(fullfile(repoRoot, 'src', 'utilities'));
    addpath(fullfile(repoRoot, 'src', 'splitters'));
    addpath(fullfile(repoRoot, 'src', 'tree', 'graphicalTree'));

    % Default split key
    if nargin < 1 || isempty(splitKeys)
        splitKeys = {'cellInfo.type'};
    end

    % Get test data path
    [matPath, ~] = getTestDataPath();

    % Load data
    [data, h5File] = loadEpicTreeData(matPath);

    % Create tree
    tree = epicTreeTools(data);

    % Build tree with specified split keys
    % Handle both function handles and key path strings
    if iscell(splitKeys) && all(cellfun(@(x) isa(x, 'function_handle'), splitKeys))
        % All function handles - use buildTreeWithSplitters
        tree.buildTreeWithSplitters(splitKeys);
    elseif iscell(splitKeys) && all(cellfun(@ischar, splitKeys) | cellfun(@isstring, splitKeys))
        % All strings - use buildTree
        tree.buildTree(splitKeys);
    elseif iscell(splitKeys)
        % Mixed - use buildTreeWithSplitters (supports both)
        tree.buildTreeWithSplitters(splitKeys);
    else
        error('splitKeys must be a cell array of strings or function handles');
    end
end
