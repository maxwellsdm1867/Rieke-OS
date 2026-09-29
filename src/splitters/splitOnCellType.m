function splitChildren = splitOnCellType(parent, data)
% SPLITONCELLTYPE Split tree node by cell type
%
% Usage:
%   splitChildren = splitOnCellType(parent, data)
%
% Inputs:
%   parent - Parent tree node to split
%   data - Full data structure (experiments array)
%
% Outputs:
%   splitChildren - Array of child nodes organized by cell type
%
% Description:
%   Creates child nodes for each unique cell type found in the data.
%   Each child contains all cells of that type.

    splitChildren = [];
    
    % Collect all unique cell types
    cellTypes = {};
    cellsByType = struct();
    
    % Traverse all experiments and cells
    for i = 1:length(data)
        exp = data(i);
        for j = 1:length(exp.cells)
            cell = exp.cells(j);
            cellType = cell.type;
            
            if isempty(cellType)
                cellType = 'Unknown';
            end
            
            % Add to collection
            if ~isfield(cellsByType, cellType)
                cellTypes{end+1} = cellType;
                cellsByType.(cellType) = [];
            end
            cellsByType.(cellType) = [cellsByType.(cellType) cell];
        end
    end
    
    % Create child nodes for each cell type
    for i = 1:length(cellTypes)
        cellType = cellTypes{i};
        cells = cellsByType.(cellType);
        
        % Create node
        childText = sprintf('%s (n=%d)', cellType, length(cells));
        childNode = uitreenode(parent, ...
            'Text', childText, ...
            'NodeData', struct('type', 'cell_type_group', ...
                              'cell_type', cellType, ...
                              'cells', cells, ...
                              'data', cells));
        
        % Add cells as children
        for j = 1:length(cells)
            addCellNode(childNode, cells(j));
        end
        
        splitChildren = [splitChildren; childNode];
    end
end

function cellNode = addCellNode(parent, cell)
    % Add cell node with its epoch groups
    
    cellText = sprintf('Cell %d', cell.id);
    if ~isempty(cell.label)
        cellText = sprintf('%s - %s', cellText, cell.label);
    end
    
    cellNode = uitreenode(parent, ...
        'Text', cellText, ...
        'NodeData', struct('type', 'cell', 'data', cell));
    
    % Add epoch groups
    for i = 1:length(cell.epoch_groups)
        eg = cell.epoch_groups(i);
        addEpochGroupNode(cellNode, eg);
    end
end

function egNode = addEpochGroupNode(parent, eg)
    % Add epoch group node
    
    egText = sprintf('Group %d', eg.id);
    if ~isempty(eg.protocol_name)
        egText = sprintf('%s (%s)', egText, eg.protocol_name);
    end
    
    egNode = uitreenode(parent, ...
        'Text', egText, ...
        'NodeData', struct('type', 'epoch_group', 'data', eg));
    
    % Add epoch blocks
    for i = 1:length(eg.epoch_blocks)
        eb = eg.epoch_blocks(i);
        addEpochBlockNode(egNode, eb);
    end
end

function ebNode = addEpochBlockNode(parent, eb)
    % Add epoch block node
    
    ebText = sprintf('Block %d (%d epochs)', eb.id, length(eb.epochs));
    
    ebNode = uitreenode(parent, ...
        'Text', ebText, ...
        'NodeData', struct('type', 'epoch_block', 'data', eb));
    
    % Add epochs (limit to first 50 for performance)
    n_show = min(50, length(eb.epochs));
    for i = 1:n_show
        epoch = eb.epochs(i);
        epochText = sprintf('Epoch %d', epoch.id);
        uitreenode(ebNode, ...
            'Text', epochText, ...
            'NodeData', struct('type', 'epoch', 'data', epoch));
    end
    
    if length(eb.epochs) > 50
        uitreenode(ebNode, ...
            'Text', sprintf('... and %d more epochs', length(eb.epochs) - 50), ...
            'NodeData', struct('type', 'placeholder'));
    end
end
