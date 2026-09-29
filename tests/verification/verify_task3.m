% Test constructor with 'none' option (should not print auto-loading message)
[data, ~] = loadEpicTreeData('/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat');
tree = epicTreeTools(data, 'LoadUserMetadata', 'none');
assert(~isempty(tree.allEpochs), 'Tree should have epochs');
allSelected = tree.getAllEpochs(true);
allTotal = tree.getAllEpochs(false);
assert(length(allSelected) == length(allTotal), 'With none option, all epochs should be selected');

% Test constructor with default (auto) - should print auto-loading message if .ugm exists
tree2 = epicTreeTools(data);
assert(~isempty(tree2.allEpochs), 'Tree should have epochs with default constructor');

disp('Task 3 verification PASSED');
