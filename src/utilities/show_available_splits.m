%% Show Available Splits in Your Data
% This will tell you what organizational axes are available

clear; clc;
addpath('src');
addpath('src/tree');

fprintf('=== Analyzing Available Splits ===\n\n');

[data, ~] = loadEpicTreeData('/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat');
tree = epicTreeTools(data);

fprintf('Total epochs: %d\n\n', length(tree.allEpochs));

% Check cell types
fprintf('1. CELL TYPES:\n');
tree.buildTree({'cellInfo.type'});
fprintf('   %d unique cell types:\n', tree.childrenLength());
for i = 1:tree.childrenLength()
    child = tree.childAt(i);
    fprintf('   - %s: %d epochs\n', string(child.splitValue), child.epochCount());
end

% Check contrasts
fprintf('\n2. CONTRAST VALUES:\n');
tree.buildTree({'parameters.contrast'});
fprintf('   %d unique contrast values:\n', tree.childrenLength());
for i = 1:tree.childrenLength()
    child = tree.childAt(i);
    fprintf('   - %.2f: %d epochs\n', child.splitValue, child.epochCount());
end

% Check protocols
fprintf('\n3. PROTOCOLS:\n');
tree.buildTreeWithSplitters({@epicTreeTools.splitOnProtocol});
fprintf('   %d unique protocols:\n', tree.childrenLength());
for i = 1:tree.childrenLength()
    child = tree.childAt(i);
    fprintf('   - %s: %d epochs\n', string(child.splitValue), child.epochCount());
end

% Two-level split example
fprintf('\n4. TWO-LEVEL SPLIT (Cell Type + Contrast):\n');
tree.buildTree({'cellInfo.type', 'parameters.contrast'});
fprintf('   Cell types: %d\n', tree.childrenLength());
for i = 1:tree.childrenLength()
    cellNode = tree.childAt(i);
    fprintf('   %s (%d epochs):\n', string(cellNode.splitValue), cellNode.epochCount());
    for j = 1:min(5, cellNode.childrenLength())
        contrastNode = cellNode.childAt(j);
        fprintf('     - Contrast %.2f: %d epochs\n', ...
            contrastNode.splitValue, contrastNode.epochCount());
    end
    if cellNode.childrenLength() > 5
        fprintf('     ... and %d more contrast values\n', cellNode.childrenLength() - 5);
    end
end

fprintf('\n=== Try These in the GUI ===\n');
fprintf('In the dropdown, select:\n');
fprintf('- "Contrast" to see grouping by stimulus contrast\n');
fprintf('- "Protocol" to see grouping by experimental protocol\n');
fprintf('- "Cell Type + Contrast" to see nested hierarchy\n\n');
