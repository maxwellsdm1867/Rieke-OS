function rebuildTreeWithSplit(treeWidget, treeData, splitMethod)
% REBUILDTREEWITHSPLIT Rebuild tree with specified split/organization
%
% Usage:
%   rebuildTreeWithSplit(treeWidget, treeData, splitMethod)
%
% Inputs:
%   treeWidget - uitree component to rebuild
%   treeData - Data structure from loadEpicTreeData
%   splitMethod - Organization method: 'none', 'cellType', or parameter name
%
% Description:
%   Clears and rebuilds the tree using the specified organization method.
%   Supports:
%   - 'none': Default hierarchical (Exp > Cell > Group > Block > Epoch)
%   - 'cellType': Group all cells by type
%   - Parameter name: Group epochs by parameter value (e.g., 'contrast')

    % Clear existing tree
    delete(treeWidget.Children);
    
    % Create root node
    root = uitreenode(treeWidget, ...
        'Text', sprintf('Data (%d experiments)', length(treeData.experiments)), ...
        'NodeData', struct('type', 'root', 'data', treeData));
    
    % Apply split
    switch splitMethod
        case 'none'
            % Default hierarchical organization
            buildTreeFromEpicData(treeWidget, treeData);
            
        case 'cellType'
            % Split by cell type
            addpath(fullfile(fileparts(mfilename('fullpath')), 'splitters'));
            splitOnCellType(root, treeData.experiments);
            
        otherwise
            % Split by parameter (e.g., 'contrast', 'size')
            addpath(fullfile(fileparts(mfilename('fullpath')), 'splitters'));
            splitOnParameter(root, treeData.experiments, splitMethod);
    end
    
    % Expand root
    expand(treeWidget);
end
