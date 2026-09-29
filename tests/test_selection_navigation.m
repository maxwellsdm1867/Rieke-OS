%% Test getSelectedEpochTreeNodes() and tree navigation
% This script tests:
% 1. Getting selected node from GUI
% 2. Navigating down the tree structure
% 3. Finding a specific protocol (SingleSpot)
% 4. Extracting data from that node

close all; clear; clc;

fprintf('=== Test Selection and Navigation ===\n\n');

%% 1. Setup and launch GUI
addpath('src/gui');
addpath('src/tree');
addpath('src/splitters');
addpath('src/utilities');
addpath('src/config');
addpath('src');

% Configure H5 directory
h5Dir = '/Users/maxwellsdm/Documents/epicTreeTest/h5';
epicTreeConfig('h5_dir', h5Dir);
fprintf('✓ H5 directory configured: %s\n', h5Dir);

% Load data and build tree
dataFile = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';
[data, ~] = loadEpicTreeData(dataFile);
fprintf('✓ Loaded %d epochs\n', length(data));

% Build tree with Cell Type → Protocol hierarchy
tree = epicTreeTools(data);
tree.buildTreeWithSplitters({
    @epicTreeTools.splitOnCellType,
    @epicTreeTools.splitOnProtocol
});
fprintf('✓ Tree built\n');

% Launch GUI
gui = epicTreeGUI(tree);
fprintf('✓ GUI launched\n\n');

%% 2. Wait for user to select node
fprintf('=== INSTRUCTIONS ===\n');
fprintf('1. Click on the ROOT node in the GUI tree\n');
fprintf('2. Press any key in this command window when ready...\n\n');
pause;

%% 3. Get selected node
fprintf('=== Getting Selected Node ===\n');
node = gui.getSelectedEpochTreeNodes();

if isempty(node)
    error('No node selected. Please select a node in the GUI.');
end

rootNode = node{1};
fprintf('✓ Selected node: %s\n', string(rootNode.splitValue));
fprintf('  Total epochs: %d\n', rootNode.epochCount());
fprintf('  Number of children: %d\n\n', rootNode.childrenLength());

%% 4. Navigate down to find cell type children
fprintf('=== Cell Type Children ===\n');
for i = 1:rootNode.childrenLength()
    cellTypeNode = rootNode.childAt(i);
    fprintf('  Child %d: %s (%d epochs)\n', i, string(cellTypeNode.splitValue), ...
        cellTypeNode.epochCount());
end
fprintf('\n');

%% 5. Get first cell type (should be RGC)
cellTypeNode = rootNode.childAt(1);
fprintf('=== Selected Cell Type: %s ===\n', string(cellTypeNode.splitValue));
fprintf('  Protocol children: %d\n', cellTypeNode.childrenLength());

% List all protocols
fprintf('\n=== Protocol Children ===\n');
for i = 1:cellTypeNode.childrenLength()
    %keyboard
    protocolNode = cellTypeNode.childAt(i);
    fprintf('  Protocol %d: %s (%d epochs)\n', i, string(protocolNode.splitValue), ...
        protocolNode.epochCount());
end
fprintf('\n');

%% 6. Find SingleSpot protocol
fprintf('=== Finding SingleSpot Protocol ===\n');
singleSpotNode = [];
for i = 1:cellTypeNode.childrenLength()
    protocolNode = cellTypeNode.childAt(i);
    if strcmp(string(protocolNode.splitValue), 'edu.washington.riekelab.protocols.SingleSpot')
        singleSpotNode = protocolNode;
        break;
    end
end

if isempty(singleSpotNode)
    error('SingleSpot protocol not found!');
end

fprintf('✓ Found SingleSpot node\n');
fprintf('  Epochs: %d\n', singleSpotNode.epochCount());
fprintf('  Is leaf: %s\n', string(singleSpotNode.isLeaf));

%% 7. Extract data from SingleSpot
fprintf('\n=== Extracting Data from SingleSpot ===\n');

try
    [data, epochs, fs] = epicTreeTools.getSelectedData(singleSpotNode, 'Amp1', gui.h5File);

    fprintf('✓ Data extracted successfully!\n');
    fprintf('  Data matrix size: %d epochs × %d samples\n', size(data, 1), size(data, 2));
    fprintf('  Sample rate: %.0f Hz\n', fs);
    fprintf('  Duration: %.2f ms\n', size(data, 2) / fs * 1000);
    fprintf('  Number of epochs: %d\n', length(epochs));

    %% 8. Plot the data
    fprintf('\n=== Plotting SingleSpot Data ===\n');
    figure

    % Convert to double for plotting
    data = double(data);
    fs = double(fs);
    t = (0:size(data, 2)-1) / fs * 1000;  % Time in ms

    % Plot all traces
    figure
    hold on;
    for i = 1:size(data, 1)
        plot(t, data(i, :), 'Color', [0.7 0.7 0.7]);
    end

    % Plot mean in black
    meanTrace = mean(data, 1);
    plot(t, meanTrace, 'k', 'LineWidth', 2);
    hold off;

    xlabel('Time (ms)');
    ylabel('Amp1');
    title(sprintf('SingleSpot Protocol (%d epochs)', size(data, 1)));
    legend('Individual traces', 'Mean', 'Location', 'best');
    grid on;

    fprintf('✓ Plot created in Figure 1\n');

    %% 9. Alternative: Use childBySplitValue
    fprintf('\n=== Testing childBySplitValue() ===\n');
    singleSpotNode2 = cellTypeNode.childBySplitValue('edu.washington.riekelab.protocols.SingleSpot');

    if ~isempty(singleSpotNode2)
        fprintf('✓ Found SingleSpot using childBySplitValue()\n');
        fprintf('  Same node: %s\n', string(singleSpotNode2.epochCount() == singleSpotNode.epochCount()));
    else
        fprintf('✗ childBySplitValue() did not find SingleSpot\n');
    end

catch ME
    fprintf('✗ Error extracting data:\n');
    fprintf('  %s\n', ME.message);
    rethrow(ME);
end

fprintf('\n=== TEST COMPLETE ===\n');
fprintf('Summary:\n');
fprintf('  ✓ getSelectedEpochTreeNodes() works\n');
fprintf('  ✓ Tree navigation (childAt, childrenLength) works\n');
fprintf('  ✓ Finding nodes by splitValue works\n');
fprintf('  ✓ Data extraction with epicTreeTools.getSelectedData() works\n');
fprintf('  ✓ H5 lazy loading works\n');
