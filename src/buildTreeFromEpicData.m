function tree = buildTreeFromEpicData(treeWidget, treeData)
% BUILDTREEFROMEPICDATA Build uitree from EpicTreeGUI standard format data
%
% Usage:
%   tree = buildTreeFromEpicData(treeWidget, treeData)
%
% Inputs:
%   treeWidget - uitree component to populate
%   treeData - Data structure from loadEpicTreeData
%
% Outputs:
%   tree - Reference to the populated tree (same as treeWidget)
%
% Description:
%   Builds a hierarchical tree view from the standardized data format.
%   The tree reflects the structure: Experiment > Cell > EpochGroup >
%   EpochBlock > Epoch, with each node containing relevant metadata.

    % Clear existing tree
    delete(treeWidget.Children);

    % Root node
    root = uitreenode(treeWidget, ...
        'Text', sprintf('Data (%d experiments)', length(treeData.experiments)), ...
        'NodeData', struct('type', 'root', 'data', treeData));

    % Build tree for each experiment
    for i = 1:length(treeData.experiments)
        exp = treeData.experiments(i);
        addExperimentNode(root, exp);
    end

    % Expand root
    expand(treeWidget);

    tree = treeWidget;
end

function expNode = addExperimentNode(parent, exp)
    % Add experiment node
    expText = sprintf('%s (ID: %d)', exp.exp_name, exp.id);
    if exp.is_mea
        expText = [expText ' [MEA]'];
    else
        expText = [expText ' [Patch]'];
    end

    expNode = uitreenode(parent, ...
        'Text', expText, ...
        'NodeData', struct('type', 'experiment', 'data', exp));

    % Add cell nodes
    for i = 1:length(exp.cells)
        cell = exp.cells(i);
        addCellNode(expNode, cell);
    end
end

function cellNode = addCellNode(parent, cell)
    % Add cell node
    cellText = sprintf('Cell %d', cell.id);
    if ~isempty(cell.type)
        cellText = sprintf('%s (%s)', cellText, cell.type);
    end
    if ~isempty(cell.label)
        cellText = sprintf('%s - %s', cellText, cell.label);
    end

    cellNode = uitreenode(parent, ...
        'Text', cellText, ...
        'NodeData', struct('type', 'cell', 'data', cell));

    % Add epoch group nodes
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
    if ~isempty(eg.label)
        egText = sprintf('%s - %s', egText, eg.label);
    end

    egNode = uitreenode(parent, ...
        'Text', egText, ...
        'NodeData', struct('type', 'epoch_group', 'data', eg));

    % Add epoch block nodes
    for i = 1:length(eg.epoch_blocks)
        eb = eg.epoch_blocks(i);
        addEpochBlockNode(egNode, eb);
    end
end

function ebNode = addEpochBlockNode(parent, eb)
    % Add epoch block node
    ebText = sprintf('Block %d (%d epochs)', eb.id, length(eb.epochs));
    if ~isempty(eb.protocol_name)
        ebText = sprintf('%s - %s', ebText, eb.protocol_name);
    end

    ebNode = uitreenode(parent, ...
        'Text', ebText, ...
        'NodeData', struct('type', 'epoch_block', 'data', eb));

    % Add epoch nodes
    for i = 1:length(eb.epochs)
        epoch = eb.epochs(i);
        addEpochNode(ebNode, epoch);
    end
end

function epochNode = addEpochNode(parent, epoch)
    % Add epoch node
    epochText = sprintf('Epoch %d', epoch.id);
    if ~isempty(epoch.label)
        epochText = sprintf('%s - %s', epochText, epoch.label);
    end

    % Add response count
    nResponses = length(epoch.responses);
    nStimuli = length(epoch.stimuli);
    if nResponses > 0 || nStimuli > 0
        epochText = sprintf('%s [%dR/%dS]', epochText, nResponses, nStimuli);
    end

    epochNode = uitreenode(parent, ...
        'Text', epochText, ...
        'NodeData', struct('type', 'epoch', 'data', epoch));
end
