%% Test Data Loading Fix
% Verify that loadEpicTreeData works with cell array format

clear; clc;
fprintf('Testing data loading fix...\n\n');

% Add paths
addpath('src');
addpath('src/tree');

% Test file
data_file = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';

fprintf('1. Loading data file: %s\n', data_file);

try
    [data, meta] = loadEpicTreeData(data_file);
    fprintf('\n✓ SUCCESS! Data loaded correctly.\n\n');

    fprintf('2. Creating epicTreeTools...\n');
    tree = epicTreeTools(data);
    fprintf('   ✓ Tree created with %d epochs\n\n', length(tree.allEpochs));

    fprintf('3. Building tree with Cell Type split...\n');
    tree.buildTree({'cellInfo.type'});
    fprintf('   ✓ Tree built with %d top-level nodes\n\n', tree.childrenLength());

    fprintf('4. Showing tree structure:\n');
    for i = 1:tree.childrenLength()
        child = tree.childAt(i);
        fprintf('   - %s: %d epochs\n', string(child.splitValue), child.epochCount());
    end

    fprintf('\n✓ ALL TESTS PASSED!\n');
    fprintf('GUI should now work. Run: epicTreeGUI(''%s'')\n', data_file);

catch ME
    fprintf('\n✗ ERROR: %s\n', ME.message);
    fprintf('\nStack trace:\n');
    for i = 1:length(ME.stack)
        fprintf('  %s (line %d)\n', ME.stack(i).name, ME.stack(i).line);
    end
end
