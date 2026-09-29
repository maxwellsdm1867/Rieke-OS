%% EpicTreeGUI Quickstart Example
% This script demonstrates the basic workflow for loading, organizing,
% and analyzing neurophysiology epoch data using epicTreeGUI.
%
% Prerequisites: Run install.m from repository root
%
% This example uses bundled sample data (20 epochs, 2 cell types, 2 protocols)

%% Setup and Path Check

% Get script directory for relative path resolution
scriptDir = fileparts(mfilename('fullpath'));

% Check if epicTreeTools is on path, if not run install
if isempty(which('epicTreeTools'))
    fprintf('epicTreeTools not found on path. Running install...\n');
    parentDir = fileparts(scriptDir);
    installScript = fullfile(parentDir, 'install.m');
    if exist(installScript, 'file')
        run(installScript);
    else
        error('install.m not found. Please run install.m from repository root.');
    end
end

%% Load Sample Data

% Construct path to bundled sample data
dataFile = fullfile(scriptDir, 'data', 'sample_epochs.mat');

if ~exist(dataFile, 'file')
    error('Sample data not found: %s\nPlease check examples/data/ directory.', dataFile);
end

fprintf('Loading data from: %s\n', dataFile);
[epochs, metadata] = loadEpicTreeData(dataFile);
fprintf('Loaded %d epochs\n', length(epochs));

%% Build Tree Structure

% Create tree and organize by cell type, then protocol
tree = epicTreeTools(epochs, 'LoadUserMetadata', 'none');
tree.buildTreeWithSplitters({
    @epicTreeTools.splitOnCellType,    % Level 1: Cell type
    @epicTreeTools.splitOnProtocol     % Level 2: Protocol name
});

fprintf('\nTree structure:\n');
for i = 1:tree.childrenLength()
    cellNode = tree.childAt(i);
    fprintf('+ %s (%d epochs)\n', string(cellNode.splitValue), cellNode.epochCount());

    for j = 1:cellNode.childrenLength()
        protocolNode = cellNode.childAt(j);
        fprintf('  - %s (%d epochs)\n', string(protocolNode.splitValue), protocolNode.epochCount());
    end
end

%% Navigate to Leaf Node and Extract Data

% Get all leaf nodes (terminal nodes containing epoch data)
leaves = tree.leafNodes();
fprintf('\nFound %d leaf nodes\n', length(leaves));

% Select first leaf for analysis
targetLeaf = leaves{1};
fprintf('Analyzing: %s\n', targetLeaf.pathString());
fprintf('  Epochs: %d selected / %d total\n', ...
    targetLeaf.selectedCount(), targetLeaf.epochCount());

% Extract response data matrix
% Returns [nEpochs x nSamples] matrix for device 'Amp1'
[dataMatrix, selectedEpochs, sampleRate] = epicTreeTools.getSelectedData(targetLeaf, 'Amp1');

fprintf('  Data matrix: %d epochs × %d samples\n', size(dataMatrix, 1), size(dataMatrix, 2));
fprintf('  Sample rate: %g Hz\n', sampleRate);

%% Compute Mean Response

% Calculate mean and standard error across epochs
meanTrace = mean(dataMatrix, 1);
semTrace = std(dataMatrix, [], 1) / sqrt(size(dataMatrix, 1));

% Create time vector (convert to milliseconds)
timeVector = (1:length(meanTrace)) / sampleRate * 1000;

%% Plot Results

figure('Name', 'Quickstart Example - Mean Response');

% Plot with shaded error region
hold on;
fill([timeVector, fliplr(timeVector)], ...
     [meanTrace + semTrace, fliplr(meanTrace - semTrace)], ...
     [0.8 0.8 1.0], 'EdgeColor', 'none', 'FaceAlpha', 0.5);
plot(timeVector, meanTrace, 'b', 'LineWidth', 2);
hold off;

% Labels and formatting
xlabel('Time (ms)');
ylabel('Response Amplitude');
title(sprintf('Mean Response (n=%d epochs)', size(dataMatrix, 1)));
grid on;

fprintf('\nQuickstart complete! See figure window for results.\n');
fprintf('Next steps:\n');
fprintf('  - Try different tree organizations: tree.buildTree({''parameters.contrast''})\n');
fprintf('  - Explore docs/UserGuide.md for advanced features\n');
fprintf('  - Run examples/example_analysis_workflow.m for more patterns\n');
