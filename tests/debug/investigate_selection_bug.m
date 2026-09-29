% Investigate BUG-001: getAllEpochs(true) still returns deselected epochs
%
% This script reproduces the bug and shows exactly where it manifests

function investigate_selection_bug()
    fprintf('\n=== BUG-001 Investigation: Selection State Not Filtering ===\n\n');

    % Load real data
    dataFile = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';
    if ~exist(dataFile, 'file')
        fprintf('Test data not found. Using synthetic data instead.\n\n');
        data = createSyntheticData();
    else
        fprintf('Loading real data: %s\n\n', dataFile);
        [data, ~] = loadEpicTreeData(dataFile);
    end

    % Build tree
    tree = epicTreeTools(data);
    tree.buildTree({'cellInfo.type'});

    fprintf('Tree built with %d total epochs\n', tree.epochCount());
    fprintf('Split into %d cell type groups\n\n', tree.childrenLength());

    % Get first leaf node
    leaves = tree.leafNodes();
    testNode = leaves{1};

    fprintf('Testing with leaf node: %s\n', string(testNode.splitValue));
    fprintf('  Total epochs in node: %d\n', testNode.epochCount());
    fprintf('  Selected count (initial): %d\n', testNode.selectedCount());

    % TEST 1: Direct epoch modification (WRONG WAY - should not work)
    fprintf('\n--- TEST 1: Direct Epoch Modification (Bug Reproducer) ---\n');
    epochs_before = testNode.getAllEpochs(false);

    % Deselect first half by directly modifying returned epochs (WRONG!)
    halfCount = floor(length(epochs_before) / 2);
    for i = 1:halfCount
        epochs_before{i}.isSelected = false;  % Modifying COPY, not original
    end

    % Check if it worked
    selected_after = testNode.getAllEpochs(true);
    fprintf('  Deselected %d epochs by direct modification\n', halfCount);
    fprintf('  getAllEpochs(true) returned: %d epochs\n', length(selected_after));
    fprintf('  selectedCount() reports: %d\n', testNode.selectedCount());

    if length(selected_after) == length(epochs_before)
        fprintf('  ❌ BUG CONFIRMED: Direct modification doesn''t work!\n');
        fprintf('     (Returns all epochs, ignores isSelected changes)\n');
    else
        fprintf('  ✓ Direct modification worked (unexpected)\n');
    end

    % TEST 2: Using setSelected method (CORRECT WAY)
    fprintf('\n--- TEST 2: Using setSelected() Method (Correct) ---\n');

    % Reset by building tree again
    tree2 = epicTreeTools(data);
    tree2.buildTree({'cellInfo.type'});
    leaves2 = tree2.leafNodes();
    testNode2 = leaves2{1};

    % Deselect using setSelected (CORRECT!)
    testNode2.setSelected(false, true);  % Deselect this node recursively

    selected_after2 = testNode2.getAllEpochs(true);
    fprintf('  Called setSelected(false, true) on node\n');
    fprintf('  getAllEpochs(true) returned: %d epochs\n', length(selected_after2));
    fprintf('  selectedCount() reports: %d\n', testNode2.selectedCount());

    if isempty(selected_after2) && testNode2.selectedCount() == 0
        fprintf('  ✓ setSelected() works correctly!\n');
    else
        fprintf('  ❌ BUG: setSelected() didn''t filter properly\n');
    end

    % TEST 3: Check where epochs are actually stored
    fprintf('\n--- TEST 3: Where Are Epochs Stored? ---\n');
    fprintf('  testNode.isLeaf: %d\n', testNode.isLeaf);
    fprintf('  testNode has epochList: %d\n', isprop(testNode, 'epochList'));

    if testNode.isLeaf
        % Check if epochList epochs are the originals
        directEpoch = testNode.epochList{1};
        getAllEpoch = testNode.getAllEpochs(false);
        getAllEpoch = getAllEpoch{1};

        fprintf('\n  Checking if getAllEpochs returns originals or copies:\n');
        directEpoch.testField = 'ORIGINAL';
        if isfield(getAllEpoch, 'testField')
            fprintf('  ✓ getAllEpochs returns references (handle semantics)\n');
        else
            fprintf('  ❌ getAllEpochs returns copies (value semantics)\n');
            fprintf('     This is why direct modification doesn''t work!\n');
        end
    end

    % TEST 4: Verify current getAllEpochs filtering logic
    fprintf('\n--- TEST 4: Testing getAllEpochs(true) Filtering ---\n');

    % Manually check filtering
    tree3 = epicTreeTools(data);
    tree3.buildTree({'cellInfo.type'});
    leaves3 = tree3.leafNodes();
    testNode3 = leaves3{1};

    % Deselect properly
    testNode3.setSelected(false, true);

    % Get epochs both ways
    allEpochs = testNode3.getAllEpochs(false);
    selectedEpochs = testNode3.getAllEpochs(true);

    fprintf('  Total epochs: %d\n', length(allEpochs));
    fprintf('  Selected epochs: %d\n', length(selectedEpochs));

    % Check isSelected flags manually
    selectedCount = 0;
    for i = 1:length(allEpochs)
        if isfield(allEpochs{i}, 'isSelected') && allEpochs{i}.isSelected
            selectedCount = selectedCount + 1;
        end
    end
    fprintf('  Manual count of isSelected=true: %d\n', selectedCount);

    if length(selectedEpochs) == selectedCount
        fprintf('  ✓ getAllEpochs(true) filtering is correct!\n');
    else
        fprintf('  ❌ BUG: getAllEpochs(true) not filtering correctly\n');
        fprintf('     Expected %d, got %d\n', selectedCount, length(selectedEpochs));
    end

    fprintf('\n=== Investigation Complete ===\n\n');
    fprintf('Summary:\n');
    fprintf('- Direct epoch modification (wrong) creates COPIES\n');
    fprintf('- Must use setSelected() to modify originals\n');
    fprintf('- getAllEpochs filtering logic needs verification\n\n');
end

function data = createSyntheticData()
    % Create minimal synthetic data for testing
    data = struct();
    data.experiments = struct();
    data.experiments.cells = {};

    % Create 2 cells with different types
    for cellIdx = 1:2
        cell = struct();
        cell.cellInfo = struct();
        cell.cellInfo.type = sprintf('Cell%d', cellIdx);
        cell.cellInfo.id = cellIdx;
        cell.epoch_groups = {};

        % Create 1 epoch group per cell
        group = struct();
        group.groupInfo = struct();
        group.epoch_blocks = {};

        % Create 1 block with 50 epochs
        block = struct();
        block.blockInfo = struct();
        block.epochs = {};

        for epochIdx = 1:50
            epoch = struct();
            epoch.cellInfo = cell.cellInfo;
            epoch.parameters = struct();
            epoch.isSelected = true;  % All selected initially
            epoch.responses = struct();
            epoch.responses(1).device_name = 'Amp1';
            epoch.responses(1).data = rand(1, 1000);
            epoch.responses(1).sample_rate = 10000;

            block.epochs{end+1} = epoch;
        end

        group.epoch_blocks{1} = block;
        cell.epoch_groups{1} = group;
        data.experiments.cells{end+1} = cell;
    end
end
