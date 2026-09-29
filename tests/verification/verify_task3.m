% Test constructor with 'none' option (should not print auto-loading message)
% Scientific recordings are local-only and never bundled.
if ~isfile(getenv('RIEKE_TEST_MAT'))
    warning('epicTreeGUI:SkippedLocalFixture', ...
        'Skipped: set RIEKE_TEST_MAT to a local recording export.');
    return;
end

[data, ~] = loadEpicTreeData(getenv('RIEKE_TEST_MAT'));
tree = epicTreeTools(data, 'LoadUserMetadata', 'none');
assert(~isempty(tree.allEpochs), 'Tree should have epochs');
allSelected = tree.getAllEpochs(true);
allTotal = tree.getAllEpochs(false);
assert(length(allSelected) == length(allTotal), 'With none option, all epochs should be selected');

% Test constructor with default (auto) - should print auto-loading message if .ugm exists
tree2 = epicTreeTools(data);
assert(~isempty(tree2.allEpochs), 'Tree should have epochs with default constructor');

disp('Task 3 verification PASSED');
