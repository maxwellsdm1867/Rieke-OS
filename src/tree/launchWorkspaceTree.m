function [tree, gui] = launchWorkspaceTree(matFile, fields, varargin)
% LAUNCHWORKSPACETREE Open a frozen workspace export using semantic split IDs.
%
% [tree, gui] = launchWorkspaceTree('recordings.mat', {'date','cell'});
% [tree, gui] = launchWorkspaceTree('recordings.mat', ...
%     {'cell', {'parameters/history1','parameters/history2','parameters/target'}});
% tree = launchWorkspaceTree('recordings.mat', {'parameters/history1'}, ...
%                            'ShowGUI', false);
% tree = launchWorkspaceTree('recordings.mat', 'ShowGUI', false);
%
% Omitted fields use the exported mapping order. Explicit {} creates a flat
% layout. Only fields captured in metadata.split_mapping_json are available;
% re-export with other fields to make those fields available. Nested cell
% lists resolve an exact ordered composite mapping; they do not execute code.
% Friendly display labels are optional metadata, separate from typed keys.
% Grouping uses
% the export's existing typed JSON strings and never changes membership.
% Only the adjacent selection.ugm is loaded, with exact UUID-set validation.

    useDefault = nargin < 2;
    if ~useDefault && (ischar(fields) || (isstring(fields) && isscalar(fields))) ...
            && strcmp(char(fields), 'ShowGUI')
        varargin = [{fields}, varargin];
        useDefault = true;
    end
    parser = inputParser;
    parser.addParameter('ShowGUI', true, @(value) islogical(value) && isscalar(value));
    parser.parse(varargin{:});
    if ~(ischar(matFile) && isrow(matFile) || isstring(matFile) && isscalar(matFile)) ...
            || ~isfile(matFile)
        error('launchWorkspaceTree:InvalidFile', 'Choose an existing workspace recordings.mat file.');
    end
    [ok, info] = fileattrib(char(matFile));
    if ~ok
        error('launchWorkspaceTree:InvalidFile', 'Cannot resolve the MATLAB export path.');
    end
    matFile = info.Name;
    [data, metadata] = loadEpicTreeData(matFile);
    if ~isfield(metadata, 'split_mapping_json')
        error('launchWorkspaceTree:InvalidMapping', 'Export metadata has no semantic split mapping. Re-export this dataset.');
    end
    encodedMapping = metadata.split_mapping_json;
    if ~ischar(encodedMapping) || ~isrow(encodedMapping) ...
            || isempty(regexp(strtrim(encodedMapping), '^\[[\s\S]*\]$', 'once'))
        error('launchWorkspaceTree:InvalidMapping', 'Export split mapping must be a JSON array.');
    end
    try
        mapping = jsondecode(encodedMapping);
    catch
        error('launchWorkspaceTree:InvalidMapping', 'Export split mapping is not valid JSON.');
    end
    if isempty(mapping)
        if isempty(regexp(encodedMapping, '^\s*\[\s*\]\s*$', 'once'))
            error('launchWorkspaceTree:InvalidMapping', 'Empty split mapping must be a JSON array.');
        end
        mappingFields = {};
        mappingPaths = {};
        mappingComponents = {};
    else
        if ~isstruct(mapping) || ~isvector(mapping) || ...
                ~(isequal(sort(fieldnames(mapping)), sort({'field'; 'label'; 'matlab_path'})) ...
                || isequal(sort(fieldnames(mapping)), sort({'field'; 'label'; 'matlab_path'; 'components'})))
            error('launchWorkspaceTree:InvalidMapping', 'Each split mapping needs field, label, and matlab_path.');
        end
        mappingFields = cell(1, numel(mapping));
        mappingPaths = cell(1, numel(mapping));
        mappingComponents = cell(1, numel(mapping));
        for i = 1:numel(mapping)
            entry = mapping(i);
            if ~ischar(entry.field) || ~isrow(entry.field) || isempty(entry.field) ...
                    || ~ischar(entry.label) || ~isrow(entry.label) || isempty(entry.label) ...
                    || ~ischar(entry.matlab_path) || ~isrow(entry.matlab_path) ...
                    || isempty(regexp(entry.matlab_path, '^workspaceGrouping\.g[0-9]{3}$', 'once'))
                error('launchWorkspaceTree:InvalidMapping', 'Split mapping contains an invalid field, label, or safe MATLAB path.');
            end
            mappingFields{i} = entry.field;
            mappingPaths{i} = entry.matlab_path;
            mappingComponents{i} = {};
            if isfield(entry,'components') && ~isempty(entry.components)
                components = entry.components;
                if ~iscellstr(components) || ~isvector(components) ...
                        || numel(components)<2 || numel(components)>6 ...
                        || any(cellfun(@(v) isempty(v) || ~isrow(v) || startsWith(v,'joint/'),components)) ...
                        || numel(unique(components))~=numel(components) || ~startsWith(entry.field,'joint/')
                    error('launchWorkspaceTree:InvalidMapping','Composite mapping needs two to six distinct non-composite field IDs.');
                end
                mappingComponents{i} = reshape(components,1,[]);
            end
        end
        if numel(unique(mappingFields)) ~= numel(mappingFields) ...
                || numel(unique(mappingPaths)) ~= numel(mappingPaths)
            error('launchWorkspaceTree:InvalidMapping', 'Split mapping contains duplicate field IDs or MATLAB paths.');
        end
    end
    if useDefault
        fields = mappingFields;
    elseif isstring(fields) && isvector(fields)
        fields = cellstr(fields);
    end
    if iscell(fields)
        for i = 1:numel(fields)
            if iscell(fields{i})
                requested = fields{i};
                if ~iscellstr(requested) || ~isvector(requested) || numel(requested)<2 || numel(requested)>6 ...
                        || any(cellfun(@(v) isempty(v) || ~isrow(v),requested)) ...
                        || numel(unique(requested))~=numel(requested)
                    error('launchWorkspaceTree:InvalidFields','A combined level needs two to six distinct field IDs.');
                end
                matches = find(cellfun(@(parts) isequal(parts,reshape(requested,1,[])),mappingComponents));
                if ~isscalar(matches)
                    error('launchWorkspaceTree:UnavailableField','Combined fields were not captured exactly once in this export.');
                end
                fields{i} = mappingFields{matches};
            end
        end
    end
    if ~iscell(fields) || ~(isvector(fields) || isempty(fields)) ...
            || any(~cellfun(@(value) ischar(value) && isrow(value) && ~isempty(value), fields)) ...
            || numel(fields) > 8 || numel(unique(fields)) ~= numel(fields)
        error('launchWorkspaceTree:InvalidFields', 'Choose up to eight distinct semantic field IDs, or {} for a flat tree.');
    end
    [available, indices] = ismember(fields, mappingFields);
    if any(~available)
        error('launchWorkspaceTree:UnavailableField', ...
            'Field "%s" was not captured in this export. Re-export with that grouping field.', fields{find(~available, 1)});
    end
    paths = mappingPaths(indices);
    [orderFields, valueOrders] = readValueOrder(metadata, mappingFields, fields);
    tree = epicTreeTools(data, 'LoadUserMetadata', 'none');
    tree.sourceFile = matFile;
    tree.h5File = '';  % Each epoch/response retains its own source file.
    sequence = readEpochSequence(metadata,tree.allEpochs);
    for i = 1:numel(tree.allEpochs)
        epoch = tree.allEpochs{i};
        for j = 1:numel(paths)
            key = paths{j}(numel('workspaceGrouping.') + 1:end);
            if ~isfield(epoch, 'workspaceGrouping') || ~isstruct(epoch.workspaceGrouping) ...
                    || ~isscalar(epoch.workspaceGrouping) || ~isfield(epoch.workspaceGrouping, key) ...
                    || ~ischar(epoch.workspaceGrouping.(key)) || ~isrow(epoch.workspaceGrouping.(key))
                error('launchWorkspaceTree:InvalidMapping', 'An exported epoch lacks its mapped typed grouping value.');
            end
        end
    end
    maskFile = fullfile(fileparts(matFile), 'selection.ugm');
    if isfile(maskFile)
        validateBundledMask(maskFile, tree.allEpochs);
        if ~tree.loadUserMetadata(maskFile)
            error('launchWorkspaceTree:InvalidSelection', 'The explicit bundled selection mask could not be loaded.');
        end
    end
    tree.buildTree(paths);
    if ~isempty(orderFields)
        reorderChildren(tree, 1, fields, orderFields, valueOrders);
    end
    if ~isempty(sequence)
        sequenceLeaves(tree,sequence);
    end
    % buildTree creates new child nodes; derive their checkboxes from masks.
    tree.refreshNodeSelectionState();
    applyDisplayLabels(tree,metadata,mappingFields,fields);
    gui = [];
    if parser.Results.ShowGUI
        gui = epicTreeGUI(tree);
        gui.h5File = '';  % Preserve per-epoch pointers across multiple sources.
        gui.matFilePath = matFile;
        if isprop(gui,'workspaceMaskPath')
            gui.workspaceMaskPath = maskFile;
        end
    end
end

function validateBundledMask(filename, epochs)
    try
        loaded = load(filename, '-mat');
    catch
        error('launchWorkspaceTree:InvalidSelection', 'Cannot read the bundled selection.ugm.');
    end
    if ~isfield(loaded, 'ugm') || ~isstruct(loaded.ugm) || ~isscalar(loaded.ugm) ...
            || ~all(isfield(loaded.ugm, {'epoch_h5_uuids','epoch_count','selection_mask'}))
        error('launchWorkspaceTree:InvalidSelection', 'Bundled selection mask has incomplete metadata.');
    end
    mask = loaded.ugm;
    ids = cellfun(@(epoch) epoch.h5_uuid, epochs, 'UniformOutput', false);
    % HDF5 MATLAB writers may encode each cell's UUID as a character column.
    % Normalize orientation only; UUID contents and membership stay exact.
    if iscellstr(mask.epoch_h5_uuids) && isvector(mask.epoch_h5_uuids) ...
            && all(cellfun(@isvector,mask.epoch_h5_uuids))
        mask.epoch_h5_uuids = cellfun(@(value) reshape(value,1,[]),mask.epoch_h5_uuids,'UniformOutput',false);
    end
    if ~iscellstr(mask.epoch_h5_uuids) || ~isvector(mask.epoch_h5_uuids) ...
            || any(~cellfun(@isrow,mask.epoch_h5_uuids)) ...
            || ~islogical(mask.selection_mask) || ~isvector(mask.selection_mask) ...
            || ~isnumeric(mask.epoch_count) || ~isscalar(mask.epoch_count) ...
            || mask.epoch_count ~= numel(ids) || numel(mask.selection_mask) ~= numel(ids) ...
            || numel(mask.epoch_h5_uuids) ~= numel(ids) ...
            || numel(unique(mask.epoch_h5_uuids)) ~= numel(ids) ...
            || numel(unique(ids)) ~= numel(ids) ...
            || ~isequal(sort(mask.epoch_h5_uuids(:)), sort(ids(:)))
        error('launchWorkspaceTree:InvalidSelection', 'Bundled mask must match this export exactly by epoch UUID.');
    end
end

function [orderFields, valueOrders] = readValueOrder(metadata, mappingFields, selectedFields)
    orderFields = {};
    valueOrders = {};
    if ~isfield(metadata, 'split_value_order_json')
        return; % Older exports retain their original MATLAB sibling order.
    end
    encoded = metadata.split_value_order_json;
    if ~ischar(encoded) || ~isrow(encoded) ...
            || isempty(regexp(strtrim(encoded), '^\[[\s\S]*\]$', 'once'))
        error('launchWorkspaceTree:InvalidValueOrder', 'Split value order must be a JSON array.');
    end
    try
        orders = jsondecode(encoded);
    catch
        error('launchWorkspaceTree:InvalidValueOrder', 'Split value order is not valid JSON.');
    end
    if isempty(orders)
        if ~isempty(selectedFields)
            error('launchWorkspaceTree:InvalidValueOrder', 'Value order must cover every requested split field.');
        end
        return;
    end
    if ~isstruct(orders) || ~isvector(orders) ...
            || ~isequal(sort(fieldnames(orders)), sort({'field';'values'}))
        error('launchWorkspaceTree:InvalidValueOrder', 'Value order entries need field and values.');
    end
    for i = 1:numel(orders)
        field = orders(i).field;
        values = orders(i).values;
        if isempty(values)
            values = {};
        end
        if ~ischar(field) || ~isrow(field) || ~ismember(field,mappingFields) ...
                || ~iscellstr(values) || ~(isvector(values) || isempty(values)) ...
                || numel(unique(values)) ~= numel(values)
            error('launchWorkspaceTree:InvalidValueOrder', 'Value order contains an unknown field or duplicate/non-string values.');
        end
        orderFields{end+1} = field; %#ok<AGROW>
        valueOrders{end+1} = values(:); %#ok<AGROW>
    end
    if numel(unique(orderFields)) ~= numel(orderFields) || any(~ismember(selectedFields,orderFields))
        error('launchWorkspaceTree:InvalidValueOrder', 'Value order must name each requested field exactly once.');
    end
end

function reorderChildren(node, depth, fields, orderFields, valueOrders)
    if isempty(node.children)
        return;
    end
    if depth > numel(fields)
        error('launchWorkspaceTree:InvalidValueOrder', 'Tree depth differs from the exported split order.');
    end
    values = valueOrders{find(strcmp(orderFields,fields{depth}),1)};
    actual = cellfun(@(child) child.splitValue,node.children,'UniformOutput',false);
    [found, positions] = ismember(actual,values);
    if any(~found)
        error('launchWorkspaceTree:InvalidValueOrder', 'Tree contains a value absent from the exported sibling order.');
    end
    [~, permutation] = sort(positions);
    node.children = node.children(permutation);
    for i = 1:numel(node.children)
        reorderChildren(node.children{i},depth+1,fields,orderFields,valueOrders);
    end
end

function ranks = readEpochSequence(metadata,epochs)
    ranks = [];
    if ~isfield(metadata,'epoch_sequence_json')
        warning('launchWorkspaceTree:LegacySequence', ...
            'Older export has no exact epoch sequence; retaining legacy within-leaf ordering. Re-export for UI sequence parity.');
        return;
    end
    encoded = metadata.epoch_sequence_json;
    if ~ischar(encoded) || ~isrow(encoded) ...
            || isempty(regexp(strtrim(encoded),'^\[[\s\S]*\]$','once'))
        error('launchWorkspaceTree:InvalidSequence','Epoch sequence must be a JSON array of UUIDs.');
    end
    try
        ids = jsondecode(encoded);
    catch
        error('launchWorkspaceTree:InvalidSequence','Epoch sequence is invalid JSON.');
    end
    actual = cellfun(@(epoch) epoch.h5_uuid,epochs,'UniformOutput',false);
    if ~iscellstr(ids) || ~isvector(ids) || any(~cellfun(@isrow,ids)) ...
            || numel(ids) ~= numel(actual) || numel(unique(ids)) ~= numel(ids) ...
            || numel(unique(actual)) ~= numel(actual) || ~isequal(sort(ids(:)),sort(actual(:)))
        error('launchWorkspaceTree:InvalidSequence','Epoch sequence must contain this export exact UUID set once each.');
    end
    ranks = containers.Map('KeyType','char','ValueType','double');
    for i = 1:numel(ids)
        ranks(ids{i}) = i;
    end
end

function sequenceLeaves(node,ranks)
    if isempty(node.children)
        positions = cellfun(@(epoch) ranks(epoch.h5_uuid),node.epochList);
        [~, order] = sort(positions);
        node.epochList = node.epochList(order);
        return;
    end
    for i = 1:numel(node.children)
        sequenceLeaves(node.children{i},ranks);
    end
end

function applyDisplayLabels(tree,metadata,mappingFields,selectedFields)
    if ~isfield(metadata,'split_display_json'), return; end
    encoded=metadata.split_display_json;
    if ~ischar(encoded) || ~isrow(encoded) || isempty(regexp(strtrim(encoded),'^\[[\s\S]*\]$','once'))
        error('launchWorkspaceTree:InvalidDisplay','Split display labels must be a JSON array.');
    end
    try
        entries=jsondecode(encoded);
    catch
        error('launchWorkspaceTree:InvalidDisplay','Split display labels are invalid JSON.');
    end
    if isempty(entries)
        if ~isempty(selectedFields), error('launchWorkspaceTree:InvalidDisplay','Display labels must cover selected fields.'); end
        return;
    end
    if ~isstruct(entries) || ~isvector(entries) || ~isequal(sort(fieldnames(entries)),sort({'field';'label';'values'}))
        error('launchWorkspaceTree:InvalidDisplay','Display entries need field, label and values.');
    end
    names=cell(1,numel(entries));
    for i=1:numel(entries)
        entry=entries(i); names{i}=entry.field;
        if ~ischar(entry.field) || ~isrow(entry.field) || ~ismember(entry.field,mappingFields) ...
                || ~ischar(entry.label) || ~isrow(entry.label) || isempty(entry.label)
            error('launchWorkspaceTree:InvalidDisplay','Display entry has invalid field or label.');
        end
        values=entry.values;
        if isempty(values), continue; end
        if ~isstruct(values) || ~isvector(values) || ~isequal(sort(fieldnames(values)),sort({'value';'label'})) ...
                || any(arrayfun(@(v) ~ischar(v.value) || ~isrow(v.value) || ~ischar(v.label) || ~isrow(v.label) || isempty(v.label),values)) ...
                || numel(unique({values.value}))~=numel(values)
            error('launchWorkspaceTree:InvalidDisplay','Display values must have unique exact keys and readable labels.');
        end
    end
    if numel(unique(names))~=numel(names) || any(~ismember(selectedFields,names))
        error('launchWorkspaceTree:InvalidDisplay','Display fields must be unique and cover every selected field.');
    end
    labelChildren(tree,1,selectedFields,names,entries);
end

function labelChildren(node,depth,fields,names,entries)
    for i=1:numel(node.children)
        child=node.children{i};
        entry=entries(find(strcmp(names,fields{depth}),1));
        if isempty(entry.values), error('launchWorkspaceTree:InvalidDisplay','Display metadata lacks a branch value.'); end
        found=find(strcmp({entry.values.value},child.splitValue));
        if ~isscalar(found), error('launchWorkspaceTree:InvalidDisplay','Display metadata lacks an exact branch value.'); end
        child.putCustom('workspaceFieldLabel',entry.label);
        child.putCustom('workspaceValueLabel',entry.values(found).label);
        labelChildren(child,depth+1,fields,names,entries);
    end
end
