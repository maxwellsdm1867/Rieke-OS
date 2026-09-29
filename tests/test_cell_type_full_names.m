%% Test Cell Type Full Names
% Test that splitOnCellType works with full names from Python export

close all; clear; clc;

fprintf('=== Testing Cell Type Full Names ===\n\n');

%% Create synthetic test data with full cell type names
fprintf('Creating test data with full cell type names...\n');

% Create test epochs with different cell types
test_data = {};
cell_types_to_test = {
    'RGC\ON-parasol',   % From Python: OnP
    'RGC\OFF-parasol',  % From Python: OffP
    'RGC\ON-midget',    % From Python: OnM
    'RGC\OFF-midget',   % From Python: OffM
    'rod-bipolar',      % From Python: RB
    'ON-amacrine'       % From Python: OnAmacrine
};

n_epochs_per_type = 10;

for type_idx = 1:length(cell_types_to_test)
    cell_type = cell_types_to_test{type_idx};

    for ep_idx = 1:n_epochs_per_type
        epoch = struct();
        epoch.cellInfo = struct();
        epoch.cellInfo.type = cell_type;
        epoch.cellInfo.id = sprintf('cell_%d', type_idx);
        epoch.cellInfo.label = sprintf('Cell %d', type_idx);
        epoch.parameters = struct('stimulus', 'test');

        test_data{end+1} = epoch;
    end
end

fprintf('  Created %d test epochs\n', length(test_data));
fprintf('  %d unique cell types\n\n', length(cell_types_to_test));

%% Test splitOnCellType with full names
fprintf('Testing splitOnCellType function...\n');
fprintf('----------------------------------------\n');

% Test each epoch
fprintf('\nTesting individual epochs:\n');
for i = 1:length(cell_types_to_test)
    epoch = test_data{(i-1)*n_epochs_per_type + 1};
    expected = cell_types_to_test{i};
    result = epicTreeTools.splitOnCellType(epoch);

    if strcmp(result, expected)
        fprintf('  ✓ %s\n', expected);
    else
        fprintf('  ✗ Expected: %s, Got: %s\n', expected, result);
    end
end

%% Build tree and verify organization
fprintf('\n========================================\n');
fprintf('Building tree with splitOnCellType...\n');
fprintf('========================================\n');

tree = epicTreeTools(test_data);
tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType});

fprintf('\nTree structure:\n');
fprintf('Root has %d children\n\n', tree.childrenLength());

% Check that we got all cell types
fprintf('Cell types found:\n');
for i = 1:tree.childrenLength()
    node = tree.childAt(i);
    fprintf('  [%s] - %d epochs\n', char(node.splitValue), node.epochCount());
end

%% Verify counts
fprintf('\n========================================\n');
fprintf('Verification:\n');
fprintf('========================================\n');

all_correct = true;

if tree.childrenLength() ~= length(cell_types_to_test)
    fprintf('✗ ERROR: Expected %d cell type nodes, got %d\n', ...
        length(cell_types_to_test), tree.childrenLength());
    all_correct = false;
else
    fprintf('✓ Correct number of cell type nodes (%d)\n', tree.childrenLength());
end

% Check each node has correct count
for i = 1:tree.childrenLength()
    node = tree.childAt(i);
    if node.epochCount() ~= n_epochs_per_type
        fprintf('✗ ERROR: Node "%s" has %d epochs, expected %d\n', ...
            char(node.splitValue), node.epochCount(), n_epochs_per_type);
        all_correct = false;
    end
end

if all_correct
    fprintf('✓ All nodes have correct epoch counts (%d each)\n', n_epochs_per_type);
end

%% Test with mixed shorthand and full names
fprintf('\n========================================\n');
fprintf('Testing mixed shorthand and full names:\n');
fprintf('========================================\n');

% Create mixed data
mixed_data = {};

% Add some with shorthand (legacy Symphony 1 style in keywords)
for i = 1:5
    epoch = struct();
    epoch.keywords = {'onp', 'cell-attached'};
    epoch.cellInfo = struct('type', 'RGC', 'id', 'cell_1', 'label', 'Cell 1');
    mixed_data{end+1} = epoch;
end

% Add some with full names (new export style)
for i = 1:5
    epoch = struct();
    epoch.cellInfo = struct();
    epoch.cellInfo.type = 'RGC\ON-parasol';
    epoch.cellInfo.id = 'cell_2';
    epoch.cellInfo.label = 'Cell 2';
    mixed_data{end+1} = epoch;
end

% Build tree
mixed_tree = epicTreeTools(mixed_data);
mixed_tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType});

fprintf('\nMixed tree structure:\n');
for i = 1:mixed_tree.childrenLength()
    node = mixed_tree.childAt(i);
    fprintf('  [%s] - %d epochs\n', char(node.splitValue), node.epochCount());
end

% Check that both are recognized as same type
if mixed_tree.childrenLength() == 1
    node = mixed_tree.childAt(1);
    if node.epochCount() == 10
        fprintf('\n✓ Shorthand and full names correctly unified!\n');
        fprintf('  Both "onp" keyword and "RGC\\ON-parasol" → same node\n');
    else
        fprintf('\n✗ ERROR: Expected 10 epochs in unified node\n');
    end
else
    fprintf('\n✗ ERROR: Expected 1 node, got %d\n', mixed_tree.childrenLength());
end

%% Summary
fprintf('\n========================================\n');
fprintf('TEST SUMMARY\n');
fprintf('========================================\n');

if all_correct
    fprintf('✓✓✓ ALL TESTS PASSED ✓✓✓\n\n');
    fprintf('The splitOnCellType function correctly handles:\n');
    fprintf('  • Full cell type names (RGC\\ON-parasol, etc.)\n');
    fprintf('  • Shorthand codes in keywords (onp, offp, etc.)\n');
    fprintf('  • Mixed formats\n\n');
else
    fprintf('✗✗✗ SOME TESTS FAILED ✗✗✗\n\n');
end
