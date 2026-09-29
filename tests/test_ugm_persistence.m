classdef test_ugm_persistence < matlab.unittest.TestCase
    % TEST_UGM_PERSISTENCE Validate .ugm file save/load/find operations with one-time mask building
    %
    % This test suite validates the .ugm (User Generated Metadata) persistence
    % system that saves and loads selection state across sessions.
    %
    % Architecture tested:
    % - .ugm file format (version, created, epoch_count, selection_mask, mat_file_basename)
    % - One-time mask building: mask built from isSelected flags on save, copied on load
    % - No centralized selectionMask property (simplified architecture)
    % - Three-file pattern: .mat (raw data), .ugm (selection state), workspace (active tree)
    %
    % Tests cover:
    % 1. Save operations (create file, correct fields, mask length)
    % 2. Load operations (round-trip, validation, error handling)
    % 3. Find operations (no files, single file, multiple files with timestamps)
    % 4. Constructor options ('auto', 'none', explicit file)
    % 5. One-time mask building validation (no centralized mask property)
    % 6. Command window warnings (save/load print epoch counts)

    properties
        TestDataPath = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';
        TreeData
        TempDir
        TempMatPath  % Simulated .mat path in temp dir for .ugm file discovery
    end

    methods (TestClassSetup)
        function loadData(testCase)
            % Load real test data once for all tests
            testCase.assumeTrue(exist(testCase.TestDataPath, 'file') == 2, ...
                sprintf('Test data file not found: %s', testCase.TestDataPath));
            [testCase.TreeData, ~] = loadEpicTreeData(testCase.TestDataPath);
        end
    end

    methods (TestMethodSetup)
        function createTempDir(testCase)
            % Create temporary directory for .ugm file testing
            testCase.TempDir = tempname;
            mkdir(testCase.TempDir);

            % Create a fake .mat file path in temp dir for .ugm naming
            testCase.TempMatPath = fullfile(testCase.TempDir, 'test_data.mat');

            % Create a dummy .mat file so file operations work
            dummyData = struct('test', 1);
            save(testCase.TempMatPath, 'dummyData', '-v7.3');
        end
    end

    methods (TestMethodTeardown)
        function cleanupTempDir(testCase)
            % Clean up temporary directory and all created files
            if exist(testCase.TempDir, 'dir')
                rmdir(testCase.TempDir, 's');
            end
        end
    end

    methods (Test)

        function testSaveCreatesUGMFile(testCase)
            % Verify that saveUserMetadata creates a .ugm file on disk

            tree = epicTreeTools(testCase.TreeData);
            tree.buildTree({'cellInfo.type'});

            % Generate .ugm filename
            ugmPath = epicTreeTools.generateUGMFilename(testCase.TempMatPath);

            % Save
            tree.saveUserMetadata(ugmPath);

            % Verify file exists
            testCase.verifyTrue(exist(ugmPath, 'file') == 2, ...
                'saveUserMetadata should create .ugm file');
        end

        function testSaveContainsCorrectFields(testCase)
            % Verify that saved .ugm file contains all required fields

            tree = epicTreeTools(testCase.TreeData);
            tree.buildTree({'cellInfo.type'});

            ugmPath = epicTreeTools.generateUGMFilename(testCase.TempMatPath);
            tree.saveUserMetadata(ugmPath);

            % Load the .ugm file manually
            loaded = load(ugmPath, '-mat');

            % Verify ugm struct exists
            testCase.verifyTrue(isfield(loaded, 'ugm'), ...
                '.ugm file should contain ugm struct');

            ugm = loaded.ugm;

            % Verify required fields
            testCase.verifyTrue(isfield(ugm, 'version'), ...
                'ugm struct should have version field');
            testCase.verifyTrue(isfield(ugm, 'created'), ...
                'ugm struct should have created field');
            testCase.verifyTrue(isfield(ugm, 'epoch_count'), ...
                'ugm struct should have epoch_count field');
            testCase.verifyTrue(isfield(ugm, 'selection_mask'), ...
                'ugm struct should have selection_mask field');
            testCase.verifyTrue(isfield(ugm, 'mat_file_basename'), ...
                'ugm struct should have mat_file_basename field');

            % Verify field types
            testCase.verifyClass(ugm.version, 'char', ...
                'version should be string');
            testCase.verifyClass(ugm.created, 'char', ...
                'created should be string (datestr format)');
            testCase.verifyClass(ugm.epoch_count, 'double', ...
                'epoch_count should be numeric');
            testCase.verifyClass(ugm.selection_mask, 'logical', ...
                'selection_mask should be logical array');
        end

        function testSaveAndLoadRoundTrip(testCase)
            % Verify that save/load round-trip preserves exact selection state

            tree = epicTreeTools(testCase.TreeData);
            tree.buildTree({'cellInfo.type'});

            % Deselect half the epochs (first child)
            if tree.childrenLength() > 0
                firstChild = tree.childAt(1);
                firstChild.setSelected(false, true);
            end

            % Record selection state
            selectedBefore = tree.getAllEpochs(true);
            countBefore = length(selectedBefore);

            % Save
            ugmPath = epicTreeTools.generateUGMFilename(testCase.TempMatPath);
            tree.saveUserMetadata(ugmPath);

            % Create fresh tree (all epochs selected by default)
            freshTree = epicTreeTools(testCase.TreeData);
            freshTree.buildTree({'cellInfo.type'});

            % Verify fresh tree has all epochs selected
            allSelected = freshTree.getAllEpochs(true);
            testCase.verifyEqual(length(allSelected), tree.epochCount(), ...
                'Fresh tree should have all epochs selected initially');

            % Load .ugm
            success = freshTree.loadUserMetadata(ugmPath);
            testCase.verifyTrue(success, ...
                'loadUserMetadata should return true on success');

            % Verify selection state restored
            selectedAfter = freshTree.getAllEpochs(true);
            countAfter = length(selectedAfter);

            testCase.verifyEqual(countAfter, countBefore, ...
                'Round-trip should preserve exact selection count');
        end

        function testSelectionMaskLength(testCase)
            % Verify that selection_mask length equals epoch count

            tree = epicTreeTools(testCase.TreeData);
            tree.buildTree({'cellInfo.type'});

            ugmPath = epicTreeTools.generateUGMFilename(testCase.TempMatPath);
            tree.saveUserMetadata(ugmPath);

            % Load and verify
            loaded = load(ugmPath, '-mat');
            ugm = loaded.ugm;

            testCase.verifyEqual(length(ugm.selection_mask), tree.epochCount(), ...
                'selection_mask length should match total epoch count');

            testCase.verifyEqual(ugm.epoch_count, tree.epochCount(), ...
                'epoch_count field should match actual epoch count');
        end

        function testLoadValidatesEpochCount(testCase)
            % Verify that loadUserMetadata warns and returns false
            % when epoch_count doesn't match current tree

            tree = epicTreeTools(testCase.TreeData);
            tree.buildTree({'cellInfo.type'});

            % Save with current tree
            ugmPath = epicTreeTools.generateUGMFilename(testCase.TempMatPath);
            tree.saveUserMetadata(ugmPath);

            % Manually modify epoch_count in .ugm file
            loaded = load(ugmPath, '-mat');
            ugm = loaded.ugm;
            ugm.epoch_count = ugm.epoch_count + 10;  % Corrupt the count
            save(ugmPath, 'ugm', '-v7.3');

            % Attempt to load with original tree
            % Should warn and return false
            testCase.verifyWarning(@() tree.loadUserMetadata(ugmPath), ...
                'epicTreeTools:EpochCountMismatch', ...
                'loadUserMetadata should warn when epoch count mismatch');

            % Note: verifyWarning doesn't work well with return values
            % So we test separately
            success = tree.loadUserMetadata(ugmPath);
            testCase.verifyFalse(success, ...
                'loadUserMetadata should return false on epoch count mismatch');
        end

        function testLoadMissingFile(testCase)
            % Verify that loading nonexistent .ugm file returns false with warning

            tree = epicTreeTools(testCase.TreeData);
            tree.buildTree({'cellInfo.type'});

            nonexistentPath = fullfile(testCase.TempDir, 'does_not_exist.ugm');

            % Attempt to load
            testCase.verifyWarning(@() tree.loadUserMetadata(nonexistentPath), ...
                'epicTreeTools:FileNotFound', ...
                'loadUserMetadata should warn for missing file');

            success = tree.loadUserMetadata(nonexistentPath);
            testCase.verifyFalse(success, ...
                'loadUserMetadata should return false for missing file');
        end

        function testLoadCorruptedFile(testCase)
            % Verify that loading invalid .ugm file returns false with warning

            tree = epicTreeTools(testCase.TreeData);
            tree.buildTree({'cellInfo.type'});

            % Create corrupted file (not a valid MAT file)
            corruptedPath = fullfile(testCase.TempDir, 'corrupted.ugm');
            fid = fopen(corruptedPath, 'w');
            fprintf(fid, 'This is not a valid MAT file');
            fclose(fid);

            % Attempt to load
            testCase.verifyWarning(@() tree.loadUserMetadata(corruptedPath), ...
                'epicTreeTools:LoadFailed', ...
                'loadUserMetadata should warn for corrupted file');

            success = tree.loadUserMetadata(corruptedPath);
            testCase.verifyFalse(success, ...
                'loadUserMetadata should return false for corrupted file');
        end

        function testFindLatestUGMNoFiles(testCase)
            % Verify that findLatestUGM returns empty string when no .ugm files exist

            latestUGM = epicTreeTools.findLatestUGM(testCase.TempMatPath);

            testCase.verifyEmpty(latestUGM, ...
                'findLatestUGM should return empty string when no .ugm files exist');
        end

        function testFindLatestUGMSingleFile(testCase)
            % Verify that findLatestUGM returns the only .ugm file

            % Create one .ugm file
            ugmPath = epicTreeTools.generateUGMFilename(testCase.TempMatPath);

            tree = epicTreeTools(testCase.TreeData);
            tree.buildTree({'cellInfo.type'});
            tree.saveUserMetadata(ugmPath);

            % Find it
            latestUGM = epicTreeTools.findLatestUGM(testCase.TempMatPath);

            testCase.verifyEqual(latestUGM, ugmPath, ...
                'findLatestUGM should return the only .ugm file');
        end

        function testFindLatestUGMMultipleFiles(testCase)
            % Verify that findLatestUGM returns the newest .ugm file
            % when multiple files exist

            tree = epicTreeTools(testCase.TreeData);
            tree.buildTree({'cellInfo.type'});

            % Create multiple .ugm files with different timestamps
            % Use manually named files to ensure predictable ordering
            [dir_path, basename, ~] = fileparts(testCase.TempMatPath);

            file1 = fullfile(dir_path, [basename, '_2026-01-01_10-00-00.ugm']);
            file2 = fullfile(dir_path, [basename, '_2026-01-02_10-00-00.ugm']);
            file3 = fullfile(dir_path, [basename, '_2026-01-03_10-00-00.ugm']);

            tree.saveUserMetadata(file1);
            tree.saveUserMetadata(file2);
            tree.saveUserMetadata(file3);

            % Find latest
            latestUGM = epicTreeTools.findLatestUGM(testCase.TempMatPath);

            % Should return file3 (newest timestamp)
            testCase.verifyEqual(latestUGM, file3, ...
                'findLatestUGM should return the newest timestamped file');
        end

        function testGenerateUGMFilename(testCase)
            % Verify that generateUGMFilename creates correct path format

            ugmPath = epicTreeTools.generateUGMFilename(testCase.TempMatPath);

            % Verify path is in same directory as .mat file
            [ugmDir, ~, ~] = fileparts(ugmPath);
            [matDir, ~, ~] = fileparts(testCase.TempMatPath);
            testCase.verifyEqual(ugmDir, matDir, ...
                '.ugm file should be in same directory as .mat file');

            % Verify .ugm extension
            [~, ~, ext] = fileparts(ugmPath);
            testCase.verifyEqual(ext, '.ugm', ...
                'Generated filename should have .ugm extension');

            % Verify contains timestamp pattern (YYYY-MM-DD_HH-mm-ss)
            [~, name, ~] = fileparts(ugmPath);
            testCase.verifyTrue(contains(name, '_20'), ...
                'Filename should contain timestamp starting with _20XX');
        end

        function testConstructorLoadUserMetadataNone(testCase)
            % Verify that LoadUserMetadata='none' keeps all epochs selected
            % even if .ugm file exists

            % Create and save a .ugm file with partial selection
            tree1 = epicTreeTools(testCase.TreeData);
            tree1.buildTree({'cellInfo.type'});

            % Deselect first child
            if tree1.childrenLength() > 0
                tree1.childAt(1).setSelected(false, true);
            end

            % Save
            ugmPath = epicTreeTools.generateUGMFilename(testCase.TempMatPath);
            tree1.saveUserMetadata(ugmPath);

            % Update TreeData to include sourceFile for auto-discovery
            testCase.TreeData.source_file = testCase.TempMatPath;

            % Create new tree with LoadUserMetadata='none'
            tree2 = epicTreeTools(testCase.TreeData, 'LoadUserMetadata', 'none');
            tree2.buildTree({'cellInfo.type'});

            % Verify all epochs are selected (ignoring .ugm file)
            selectedCount = length(tree2.getAllEpochs(true));
            totalCount = tree2.epochCount();

            testCase.verifyEqual(selectedCount, totalCount, ...
                'LoadUserMetadata=none should keep all epochs selected');
        end

        function testConstructorLoadUserMetadataAuto(testCase)
            % Verify that LoadUserMetadata='auto' (default) auto-loads
            % .ugm file when it exists

            % Create and save a .ugm file with partial selection
            tree1 = epicTreeTools(testCase.TreeData);
            tree1.buildTree({'cellInfo.type'});

            % Deselect first child
            if tree1.childrenLength() > 0
                tree1.childAt(1).setSelected(false, true);
            end

            selectedBefore = length(tree1.getAllEpochs(true));

            % Save
            ugmPath = epicTreeTools.generateUGMFilename(testCase.TempMatPath);
            tree1.saveUserMetadata(ugmPath);

            % Update TreeData to include sourceFile for auto-discovery
            testCase.TreeData.source_file = testCase.TempMatPath;

            % Create new tree with default 'auto' mode
            tree2 = epicTreeTools(testCase.TreeData);
            tree2.buildTree({'cellInfo.type'});

            % Verify selection state was auto-loaded
            selectedAfter = length(tree2.getAllEpochs(true));

            testCase.verifyEqual(selectedAfter, selectedBefore, ...
                'LoadUserMetadata=auto should auto-load .ugm file');
        end

        function testOneTimeMaskBuilding(testCase)
            % Validate simplified architecture: mask built from isSelected flags
            % on save (one-time), no centralized selectionMask property

            tree = epicTreeTools(testCase.TreeData);
            tree.buildTree({'cellInfo.type'});

            % Verify no centralized selectionMask property exists
            testCase.verifyFalse(isprop(tree, 'selectionMask'), ...
                'Tree should NOT have centralized selectionMask property');

            % Deselect some epochs
            if tree.childrenLength() > 0
                tree.childAt(1).setSelected(false, true);
            end

            % Save (this builds mask ONE-TIME from isSelected flags)
            ugmPath = epicTreeTools.generateUGMFilename(testCase.TempMatPath);
            tree.saveUserMetadata(ugmPath);

            % Load and verify mask was built from isSelected flags
            loaded = load(ugmPath, '-mat');
            ugm = loaded.ugm;

            % Count true values in mask
            selectedInMask = sum(ugm.selection_mask);

            % Should match tree's selected count
            selectedInTree = tree.selectedCount();

            testCase.verifyEqual(selectedInMask, selectedInTree, ...
                'Mask should be built from current isSelected flags');

            % Create fresh tree and load
            freshTree = epicTreeTools(testCase.TreeData);
            freshTree.buildTree({'cellInfo.type'});
            freshTree.loadUserMetadata(ugmPath);

            % Verify mask was COPIED to isSelected flags (one-time on load)
            selectedAfterLoad = freshTree.selectedCount();

            testCase.verifyEqual(selectedAfterLoad, selectedInMask, ...
                'Load should copy mask to isSelected flags');

            % Verify still no centralized mask property
            testCase.verifyFalse(isprop(freshTree, 'selectionMask'), ...
                'Fresh tree should still NOT have selectionMask property');
        end

        function testCommandWindowWarnings(testCase)
            % Verify that save and load print expected messages to command window

            tree = epicTreeTools(testCase.TreeData);
            tree.buildTree({'cellInfo.type'});

            % Deselect some epochs
            if tree.childrenLength() > 0
                tree.childAt(1).setSelected(false, true);
            end

            ugmPath = epicTreeTools.generateUGMFilename(testCase.TempMatPath);

            % Capture save output
            saveOutput = evalc('tree.saveUserMetadata(ugmPath);');

            % Verify save prints selection count
            testCase.verifyTrue(contains(saveOutput, 'Saved selection mask'), ...
                'Save should print "Saved selection mask" message');
            testCase.verifyTrue(contains(saveOutput, 'epochs selected'), ...
                'Save should print epoch count');

            % Create fresh tree
            freshTree = epicTreeTools(testCase.TreeData);
            freshTree.buildTree({'cellInfo.type'});

            % Capture load output
            loadOutput = evalc('freshTree.loadUserMetadata(ugmPath);');

            % Verify load prints excluded count
            testCase.verifyTrue(contains(loadOutput, 'Selection mask loaded'), ...
                'Load should print "Selection mask loaded" message');
            testCase.verifyTrue(contains(loadOutput, 'epochs excluded'), ...
                'Load should print excluded epoch count');
        end

    end
end
