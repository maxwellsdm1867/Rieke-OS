function [treeData, metadata] = loadEpicTreeData(filename)
% LOADEPICTREEDATA Load data from EpicTreeGUI standard format
%
% Usage:
%   [treeData, metadata] = loadEpicTreeData(filename)
%
% Inputs:
%   filename - Path to .mat file in EpicTreeGUI standard format
%
% Outputs:
%   treeData - Hierarchical structure containing all experimental data
%   metadata - Export metadata (creation date, source, etc.)
%
% Description:
%   Loads data exported from DataJoint or other sources into the
%   standardized EpicTreeGUI format. The returned structure can be
%   used directly by visualization and analysis functions.
%
% Example:
%   [data, meta] = loadEpicTreeData('export_20250123.mat');
%   disp(meta.created_date);
%   disp(['Number of experiments: ' num2str(length(data.experiments))]);

    % Load file
    if nargin < 1
        [file, path] = uigetfile('*.mat', 'Select EpicTree Data File');
        if file == 0
            treeData = [];
            metadata = [];
            return;
        end
        filename = fullfile(path, file);
    end

    fprintf('Loading EpicTree data from: %s\n', filename);

    try
        loaded = load(filename);
    catch ME
        error('Failed to load file: %s', ME.message);
    end

    % Validate format
    if ~isfield(loaded, 'format_version')
        error('Invalid data format: missing format_version field');
    end

    if ~isfield(loaded, 'experiments')
        error('Invalid data format: missing experiments field');
    end

    % Check version compatibility
    format_version = loaded.format_version;
    if ~strcmp(format_version, '1.0')
        warning('Data format version %s may not be fully compatible', format_version);
    end

    % Extract data
    metadata = loaded.metadata;
    treeData.format_version = format_version;
    treeData.experiments = loaded.experiments;

    % Store source file path so epicTreeTools can discover .ugm files
    treeData.source_file = filename;

    % Print summary
    fprintf('\n');
    fprintf('========================================\n');
    fprintf('EpicTree Data Loaded Successfully\n');
    fprintf('========================================\n');
    fprintf('Format Version: %s\n', format_version);
    fprintf('Created: %s\n', metadata.created_date);
    fprintf('Source: %s\n', metadata.data_source);
    fprintf('User: %s\n', metadata.export_user);
    fprintf('\nExperiments: %d\n', length(treeData.experiments));

    % Count cells and epochs
    totalCells = 0;
    totalEpochs = 0;

    for i = 1:length(treeData.experiments)
        % Handle both cell arrays and struct arrays
        if iscell(treeData.experiments)
            exp = treeData.experiments{i};
        else
            exp = treeData.experiments(i);
        end

        totalCells = totalCells + length(exp.cells);

        for j = 1:length(exp.cells)
            % Handle both cell arrays and struct arrays
            if iscell(exp.cells)
                cell = exp.cells{j};
            else
                cell = exp.cells(j);
            end

            for k = 1:length(cell.epoch_groups)
                if iscell(cell.epoch_groups)
                    eg = cell.epoch_groups{k};
                else
                    eg = cell.epoch_groups(k);
                end

                for m = 1:length(eg.epoch_blocks)
                    if iscell(eg.epoch_blocks)
                        eb = eg.epoch_blocks{m};
                    else
                        eb = eg.epoch_blocks(m);
                    end
                    totalEpochs = totalEpochs + length(eb.epochs);
                end
            end
        end
    end

    fprintf('Total Cells: %d\n', totalCells);
    fprintf('Total Epochs: %d\n', totalEpochs);
    fprintf('========================================\n\n');

end
