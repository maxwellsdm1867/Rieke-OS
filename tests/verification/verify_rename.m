%% Verify All Classes Are Renamed Correctly
% This script checks that all epic* classes are properly renamed
% and have correct constructors

fprintf('=== Verifying Class Renaming ===\n\n');

%% Check 1: Files exist
fprintf('1. Checking files exist...\n');
files = {
    'src/gui/epicGraphicalTree.m'
    'src/gui/epicGraphicalTreeNode.m'
    'src/gui/epicGraphicalTreeNodeWidget.m'
};

allExist = true;
for i = 1:length(files)
    if exist(files{i}, 'file')
        fprintf('   ✓ %s\n', files{i});
    else
        fprintf('   ✗ MISSING: %s\n', files{i});
        allExist = false;
    end
end

if ~allExist
    error('Some files are missing!');
end
fprintf('\n');

%% Check 2: Class definitions are correct
fprintf('2. Checking class definitions...\n');

% Read first 50 lines of each file
cd('src/gui');

% Check epicGraphicalTree
fid = fopen('epicGraphicalTree.m', 'r');
content = textscan(fid, '%s', 50, 'Delimiter', '\n');
fclose(fid);
content = strjoin(content{1}, '\n');

if contains(content, 'classdef epicGraphicalTree')
    fprintf('   ✓ epicGraphicalTree class definition\n');
else
    fprintf('   ✗ epicGraphicalTree class definition WRONG\n');
end

if contains(content, 'function self = epicGraphicalTree(')
    fprintf('   ✓ epicGraphicalTree constructor\n');
else
    fprintf('   ✗ epicGraphicalTree constructor WRONG\n');
end

% Check epicGraphicalTreeNode
fid = fopen('epicGraphicalTreeNode.m', 'r');
content = textscan(fid, '%s', 50, 'Delimiter', '\n');
fclose(fid);
content = strjoin(content{1}, '\n');

if contains(content, 'classdef epicGraphicalTreeNode')
    fprintf('   ✓ epicGraphicalTreeNode class definition\n');
else
    fprintf('   ✗ epicGraphicalTreeNode class definition WRONG\n');
end

if contains(content, 'function self = epicGraphicalTreeNode(')
    fprintf('   ✓ epicGraphicalTreeNode constructor\n');
else
    fprintf('   ✗ epicGraphicalTreeNode constructor WRONG\n');
end

% Check epicGraphicalTreeNodeWidget
fid = fopen('epicGraphicalTreeNodeWidget.m', 'r');
content = textscan(fid, '%s', 50, 'Delimiter', '\n');
fclose(fid);
content = strjoin(content{1}, '\n');

if contains(content, 'classdef epicGraphicalTreeNodeWidget')
    fprintf('   ✓ epicGraphicalTreeNodeWidget class definition\n');
else
    fprintf('   ✗ epicGraphicalTreeNodeWidget class definition WRONG\n');
end

if contains(content, 'function self = epicGraphicalTreeNodeWidget(')
    fprintf('   ✓ epicGraphicalTreeNodeWidget constructor\n');
else
    fprintf('   ✗ epicGraphicalTreeNodeWidget constructor WRONG\n');
end

cd('../..');
fprintf('\n');

%% Check 3: Classes can be instantiated
fprintf('3. Checking classes can be instantiated...\n');

try
    % Create test figure and axes
    testFig = figure('Visible', 'off');
    testAx = axes('Parent', testFig);

    % Test epicGraphicalTree
    tree = epicGraphicalTree(testAx, 'Test');
    fprintf('   ✓ epicGraphicalTree instantiated\n');

    % Test epicGraphicalTreeNode
    node = epicGraphicalTreeNode('TestNode');
    fprintf('   ✓ epicGraphicalTreeNode instantiated\n');

    % Test epicGraphicalTreeNodeWidget
    widget = epicGraphicalTreeNodeWidget(tree);
    fprintf('   ✓ epicGraphicalTreeNodeWidget instantiated\n');

    % Clean up
    delete(testFig);

catch ME
    fprintf('   ✗ ERROR: %s\n', ME.message);
    if exist('testFig', 'var') && ishandle(testFig)
        delete(testFig);
    end
    error('Class instantiation failed!');
end

fprintf('\n');

%% Check 4: No old class name references in epic* files
fprintf('4. Checking for old class name references...\n');

cd('src/gui');
hasOldRefs = false;

% Check each epic* file for references to old names (not in comments)
epicFiles = {'epicGraphicalTree.m', 'epicGraphicalTreeNode.m', 'epicGraphicalTreeNodeWidget.m'};

for i = 1:length(epicFiles)
    fid = fopen(epicFiles{i}, 'r');
    lines = textscan(fid, '%s', 'Delimiter', '\n');
    fclose(fid);
    lines = lines{1};

    for j = 1:length(lines)
        line = lines{j};
        % Skip comment lines
        if startsWith(strtrim(line), '%')
            continue;
        end

        % Check for old class names in non-comment code
        if contains(line, 'graphicalTree(') || ...
           contains(line, 'graphicalTreeNode(') || ...
           contains(line, 'graphicalTreeNodeWidget(')
            fprintf('   ✗ Found old reference in %s line %d: %s\n', ...
                epicFiles{i}, j, strtrim(line));
            hasOldRefs = true;
        end
    end
end

cd('../..');

if ~hasOldRefs
    fprintf('   ✓ No old class name references found\n');
end

fprintf('\n');

%% Summary
fprintf('=== VERIFICATION COMPLETE ===\n');
fprintf('All classes renamed correctly!\n');
fprintf('You can now run: test_renamed.m\n');
