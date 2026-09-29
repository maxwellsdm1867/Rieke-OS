function splitChildren = splitOnParameter(parent, data, paramName)
% SPLITONPARAMETER Split tree node by arbitrary parameter value
%
% Usage:
%   splitChildren = splitOnParameter(parent, data, paramName)
%
% Inputs:
%   parent - Parent tree node to split
%   data - Full data structure (experiments array)
%   paramName - Name of parameter to split on (e.g., 'contrast', 'size')
%
% Outputs:
%   splitChildren - Array of child nodes organized by parameter value
%
% Description:
%   Generic splitter that organizes epochs by any parameter found in
%   epoch.parameters. Creates child nodes for each unique parameter value.

    splitChildren = [];
    
    % Collect all unique parameter values across all epochs
    paramValues = [];
    epochsByParam = struct();
    
    % Traverse all experiments, cells, groups, blocks, epochs
    for i = 1:length(data)
        exp = data(i);
        for j = 1:length(exp.cells)
            cell = exp.cells(j);
            for k = 1:length(cell.epoch_groups)
                eg = cell.epoch_groups(k);
                for m = 1:length(eg.epoch_blocks)
                    eb = eg.epoch_blocks(m);
                    for n = 1:length(eb.epochs)
                        epoch = eb.epochs(n);
                        
                        % Check if parameter exists
                        if isfield(epoch, 'parameters') && ...
                           isfield(epoch.parameters, paramName)
                            
                            pval = epoch.parameters.(paramName);
                            
                            % Convert to string key for struct field
                            if isnumeric(pval)
                                pkey = sprintf('val_%g', pval);
                                pdisplay = num2str(pval);
                            elseif ischar(pval)
                                pkey = matlab.lang.makeValidName(pval);
                                pdisplay = pval;
                            else
                                pkey = 'other';
                                pdisplay = 'other';
                            end
                            
                            % Add to collection
                            if ~isfield(epochsByParam, pkey)
                                paramValues(end+1) = pval;
                                epochsByParam.(pkey).value = pval;
                                epochsByParam.(pkey).display = pdisplay;
                                epochsByParam.(pkey).epochs = [];
                            end
                            
                            % Store epoch with cell reference
                            epochInfo = struct('epoch', epoch, 'cell', cell);
                            epochsByParam.(pkey).epochs = ...
                                [epochsByParam.(pkey).epochs epochInfo];
                        end
                    end
                end
            end
        end
    end
    
    % Create child nodes for each parameter value
    pkeys = fieldnames(epochsByParam);
    
    % Sort parameter values
    sortedVals = [];
    sortedKeys = {};
    for i = 1:length(pkeys)
        sortedVals(i) = epochsByParam.(pkeys{i}).value;
        sortedKeys{i} = pkeys{i};
    end
    [~, sortIdx] = sort(sortedVals);
    
    for i = 1:length(sortIdx)
        idx = sortIdx(i);
        pkey = sortedKeys{idx};
        pinfo = epochsByParam.(pkey);
        
        % Create node
        childText = sprintf('%s = %s (n=%d epochs)', ...
            paramName, pinfo.display, length(pinfo.epochs));
        
        childNode = uitreenode(parent, ...
            'Text', childText, ...
            'NodeData', struct('type', 'parameter_group', ...
                              'parameter_name', paramName, ...
                              'parameter_value', pinfo.value, ...
                              'epochs', pinfo.epochs));
        
        % Group epochs by cell
        epochsByCell = struct();
        for j = 1:length(pinfo.epochs)
            cellId = pinfo.epochs(j).cell.id;
            cellKey = sprintf('cell_%d', cellId);
            
            if ~isfield(epochsByCell, cellKey)
                epochsByCell.(cellKey).cell = pinfo.epochs(j).cell;
                epochsByCell.(cellKey).epochs = [];
            end
            epochsByCell.(cellKey).epochs = ...
                [epochsByCell.(cellKey).epochs pinfo.epochs(j).epoch];
        end
        
        % Add cells as children
        cellKeys = fieldnames(epochsByCell);
        for j = 1:length(cellKeys)
            cellInfo = epochsByCell.(cellKeys{j});
            addCellWithEpochs(childNode, cellInfo.cell, cellInfo.epochs);
        end
        
        splitChildren = [splitChildren; childNode];
    end
end

function cellNode = addCellWithEpochs(parent, cell, epochs)
    % Add cell node with specific epochs
    
    cellText = sprintf('Cell %d (%s) - %d epochs', ...
        cell.id, cell.type, length(epochs));
    
    cellNode = uitreenode(parent, ...
        'Text', cellText, ...
        'NodeData', struct('type', 'cell_filtered', ...
                          'data', cell, ...
                          'epochs', epochs));
    
    % Add epochs (limit to first 20 for performance)
    n_show = min(20, length(epochs));
    for i = 1:n_show
        epoch = epochs(i);
        epochText = sprintf('Epoch %d', epoch.id);
        uitreenode(cellNode, ...
            'Text', epochText, ...
            'NodeData', struct('type', 'epoch', 'data', epoch));
    end
    
    if length(epochs) > 20
        uitreenode(cellNode, ...
            'Text', sprintf('... and %d more epochs', length(epochs) - 20), ...
            'NodeData', struct('type', 'placeholder'));
    end
end
