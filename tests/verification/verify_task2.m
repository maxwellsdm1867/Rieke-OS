% Test save and load round-trip
[data, ~] = loadEpicTreeData('/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat');
tree = epicTreeTools(data);

% Deselect first child's epochs
tree.buildTree({'cellInfo.type'});
child = tree.childAt(1);
child.setSelected(false, true);

% Verify some deselected
allEp = tree.getAllEpochs(true);
totalEp = tree.getAllEpochs(false);
assert(length(allEp) < length(totalEp), 'Should have fewer selected than total');

% Save (should print command window message)
ugmPath = epicTreeTools.generateUGMFilename(tree.sourceFile);
tree.saveUserMetadata(ugmPath);
assert(exist(ugmPath, 'file') == 2, '.ugm file should exist');

% Load into fresh tree (should print command window warning)
tree2 = epicTreeTools(data);
tree2.buildTree({'cellInfo.type'});
success = tree2.loadUserMetadata(ugmPath);
assert(success, 'loadUserMetadata should succeed');

% Verify same selection state
allEp2 = tree2.getAllEpochs(true);
assert(length(allEp2) == length(allEp), 'Selection should match after round-trip');

% Cleanup
delete(ugmPath);

% Test findLatestUGM
latestPath = epicTreeTools.findLatestUGM(tree.sourceFile);
assert(ischar(latestPath) || isstring(latestPath), 'findLatestUGM should return char/string');

disp('Task 2 verification PASSED');
