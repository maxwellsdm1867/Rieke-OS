function tests = test_launch_workspace_tree
    tests = functiontests(localfunctions);
end

function setup(testCase)
    folder = tempname;
    mkdir(folder);
    testCase.TestData.folder = folder;
    testCase.TestData.path = fullfile(folder, 'recordings.mat');
    mapping = struct('field', {'date','cell','parameters/history1'}, ...
        'label', {'Recording date','Cell','History'}, ...
        'matlab_path', {'workspaceGrouping.g001','workspaceGrouping.g002','workspaceGrouping.g003'});
    epoch = struct('id', 1, 'h5_uuid', '00000000-0000-0000-0000-000000000001', ...
        'label', '', 'parameters', struct(), 'responses', [], 'stimuli', [], ...
        'workspaceGrouping', struct('g001','"2026-09-24"','g002','"Cell1"','g003','null'));
    second = epoch;
    second.id = 2;
    second.h5_uuid = '00000000-0000-0000-0000-000000000002';
    second.workspaceGrouping.g003 = '[1,2]';
    block = struct('id',1,'h5_uuid','block','protocol_name','RecordedProtocol','epochs',[epoch second]);
    group = struct('id',1,'h5_uuid','group','label','Raw group','epoch_blocks',block);
    cellData = struct('id',1,'h5_uuid','cell','label','Cell1','type','Recorded type','epoch_groups',group);
    experiment = struct('id',1,'exp_name','Fixture','is_mea',false,'cells',cellData);
    payload = struct('format_version','1.0','experiments',experiment, ...
        'metadata',struct('created_date','fixture','data_source','fixture','export_user','fixture', ...
                         'split_mapping_json',jsonencode(mapping)));
    testCase.TestData.payload = payload;
    testCase.TestData.mapping = mapping;
    writeFixture(testCase);
end

function teardown(testCase)
    rmdir(testCase.TestData.folder,'s');
end

function writeFixture(testCase)
    payload = testCase.TestData.payload;
    save(testCase.TestData.path,'-struct','payload');
end

function testDefaultReorderAndExplicitFlatPreserveIdentities(testCase)
    before = findall(groot,'Type','figure');
    [tree,gui] = launchWorkspaceTree(testCase.TestData.path,'ShowGUI',false);
    verifyEmpty(testCase,gui);
    verifyEqual(testCase,tree.children{1}.splitKey,'workspaceGrouping.g001');
    tree2 = launchWorkspaceTree(testCase.TestData.path,{'parameters/history1','date'},'ShowGUI',false);
    verifyEqual(testCase,tree2.children{1}.splitKey,'workspaceGrouping.g003');
    verifyEqual(testCase,numel(tree2.children),2); % Recorded null and array stay distinct.
    verifyEqual(testCase,tree2.allEpochs{1}.h5_uuid,tree.allEpochs{1}.h5_uuid);
    flat = launchWorkspaceTree(testCase.TestData.path,{},'ShowGUI',false);
    verifyEmpty(testCase,flat.children);
    verifyEqual(testCase,flat.epochCount(),2);
    verifyEqual(testCase,findall(groot,'Type','figure'),before);
end

function testUnavailableDuplicateAndTooManyFieldsFail(testCase)
    verifyError(testCase,@() launchWorkspaceTree(testCase.TestData.path,{'Date'},'ShowGUI',false), ...
        'launchWorkspaceTree:UnavailableField');
    verifyError(testCase,@() launchWorkspaceTree(testCase.TestData.path,{'date','date'},'ShowGUI',false), ...
        'launchWorkspaceTree:InvalidFields');
    verifyError(testCase,@() launchWorkspaceTree(testCase.TestData.path, ...
        {'a','b','c','d','e','f','g','h','i'},'ShowGUI',false),'launchWorkspaceTree:InvalidFields');
end

function testMalformedDuplicateOrMissingMappingFails(testCase)
    for variant = 1:3
        mapping = testCase.TestData.mapping;
        if variant == 1
            mapping(2).matlab_path = mapping(1).matlab_path;
        elseif variant == 2
            mapping(2).field = mapping(1).field;
        else
            mapping(2).matlab_path = 'workspaceGrouping.g001;disp(1)';
        end
        testCase.TestData.payload.metadata.split_mapping_json = jsonencode(mapping);
        writeFixture(testCase);
        verifyError(testCase,@() launchWorkspaceTree(testCase.TestData.path,'ShowGUI',false), ...
            'launchWorkspaceTree:InvalidMapping');
    end
    testCase.TestData.payload.metadata = rmfield(testCase.TestData.payload.metadata,'split_mapping_json');
    writeFixture(testCase);
    verifyError(testCase,@() launchWorkspaceTree(testCase.TestData.path,'ShowGUI',false), ...
        'launchWorkspaceTree:InvalidMapping');
end

function testExplicitBundledMaskUsesUUIDAndOtherMasksAreIgnored(testCase)
    ugm = struct('version','1.1','epoch_count',2,'epoch_h5_uuids', ...
        {{'00000000-0000-0000-0000-000000000002';'00000000-0000-0000-0000-000000000001'}}, ...
        'selection_mask',logical([false;true]));
    save(fullfile(testCase.TestData.folder,'unrelated_latest.ugm'),'ugm','-v7');
    initial = launchWorkspaceTree(testCase.TestData.path,{},'ShowGUI',false);
    verifyTrue(testCase,all(cellfun(@(epoch) epoch.isSelected,initial.allEpochs)));
    ugm.epoch_h5_uuids = cellfun(@transpose,ugm.epoch_h5_uuids,'UniformOutput',false);
    save(fullfile(testCase.TestData.folder,'selection.ugm'),'ugm','-v7');
    selected = launchWorkspaceTree(testCase.TestData.path,{},'ShowGUI',false);
    verifyTrue(testCase,selected.allEpochs{1}.isSelected);
    verifyFalse(testCase,selected.allEpochs{2}.isSelected);
    ugm.epoch_h5_uuids{1} = '00000000-0000-0000-0000-000000000099';
    save(fullfile(testCase.TestData.folder,'selection.ugm'),'ugm','-v7');
    verifyError(testCase,@() launchWorkspaceTree(testCase.TestData.path,{},'ShowGUI',false), ...
        'launchWorkspaceTree:InvalidSelection');
end

function testTypedValuesKeepEveryDistinctGrouping(testCase)
    values = {'true','1','"1"','[1,2]','[2,1]','null','<not recorded>','"<not recorded>"'};
    original = testCase.TestData.payload.experiments.cells.epoch_groups.epoch_blocks.epochs(1);
    items = repmat(original,1,numel(values));
    for i = 1:numel(values)
        items(i).id = i;
        items(i).h5_uuid = sprintf('00000000-0000-0000-0000-%012d',i);
        items(i).workspaceGrouping.g003 = values{i};
    end
    testCase.TestData.payload.experiments.cells.epoch_groups.epoch_blocks.epochs = items;
    writeFixture(testCase);
    tree = launchWorkspaceTree(testCase.TestData.path,{'parameters/history1'},'ShowGUI',false);
    verifyEqual(testCase,numel(tree.children),numel(values));
    actual = cellfun(@(child) child.splitValue,tree.children,'UniformOutput',false);
    verifyEqual(testCase,sort(actual(:)),sort(values(:)));
    verifyEqual(testCase,tree.epochCount(),numel(values));
end

function testMappedFieldMustExistOnEveryEpoch(testCase)
    testCase.TestData.payload.experiments.cells.epoch_groups.epoch_blocks.epochs(1).workspaceGrouping = struct();
    writeFixture(testCase);
    verifyError(testCase,@() launchWorkspaceTree(testCase.TestData.path,{'parameters/history1'},'ShowGUI',false), ...
        'launchWorkspaceTree:InvalidMapping');
end

function testDeclaredSiblingOrderMatchesNumericUIOrder(testCase)
    items = testCase.TestData.payload.experiments.cells.epoch_groups.epoch_blocks.epochs;
    items(1).workspaceGrouping.g003 = '100';
    items(2).workspaceGrouping.g003 = '25';
    testCase.TestData.payload.experiments.cells.epoch_groups.epoch_blocks.epochs = items;
    orders = struct('field','parameters/history1','values',{{'25','100','null','<not recorded>'}});
    testCase.TestData.payload.metadata.split_value_order_json = jsonencode(orders);
    % JSON array is explicit even for a single field.
    testCase.TestData.payload.metadata.split_value_order_json = ['[' jsonencode(orders) ']'];
    writeFixture(testCase);
    tree = launchWorkspaceTree(testCase.TestData.path,{'parameters/history1'},'ShowGUI',false);
    verifyEqual(testCase,tree.children{1}.splitValue,'25');
    verifyEqual(testCase,tree.children{2}.splitValue,'100');
    verifyEqual(testCase,tree.epochCount(),2);
    verifyEqual(testCase,tree.allEpochs{1}.h5_uuid,items(1).h5_uuid);
    verifyError(testCase,@() launchWorkspaceTree(testCase.TestData.path,{'date'},'ShowGUI',false), ...
        'launchWorkspaceTree:InvalidValueOrder');
end

function testMalformedAndUnknownSiblingOrderFails(testCase)
    cases = {{'null','null'}, {'null'}, {true,'null'}};
    for i = 1:numel(cases)
        order = struct('field','parameters/history1','values',{cases{i}});
        testCase.TestData.payload.metadata.split_value_order_json = ['[' jsonencode(order) ']'];
        writeFixture(testCase);
        verifyError(testCase,@() launchWorkspaceTree(testCase.TestData.path,{'parameters/history1'},'ShowGUI',false), ...
            'launchWorkspaceTree:InvalidValueOrder');
    end
end

function testGUIKeepsTypedDecimalAndArrayLabelsVerbatim(testCase)
    items = testCase.TestData.payload.experiments.cells.epoch_groups.epoch_blocks.epochs;
    items(1).workspaceGrouping.g003 = '1000.0';
    items(2).workspaceGrouping.g003 = '[0.0,100.0,200.0,300.0,400.0,500.0,600.0,700.0]';
    testCase.TestData.payload.experiments.cells.epoch_groups.epoch_blocks.epochs = items;
    writeFixture(testCase);
    [~, gui] = launchWorkspaceTree(testCase.TestData.path,{'parameters/history1'});
    cleanup = onCleanup(@() delete(gui.figure)); %#ok<NASGU>
    nodes = gui.treeBrowser.graphTree.nodeList;
    checked = 0;
    for i = 1:numel(nodes)
        node = nodes{i};
        if isa(node.userData,'epicTreeTools') && strcmp(node.userData.splitKey,'workspaceGrouping.g003')
            verifyEqual(testCase,node.name,sprintf('%s (%d)',node.userData.splitValue,node.userData.epochCount()));
            checked = checked + 1;
        end
    end
    verifyEqual(testCase,checked,2);
end

function testExplicitSequenceReordersLeavesWithoutChangingMaskIndices(testCase)
    ids = {'00000000-0000-0000-0000-000000000002','00000000-0000-0000-0000-000000000001'};
    testCase.TestData.payload.metadata.epoch_sequence_json = jsonencode(ids);
    writeFixture(testCase);
    tree = launchWorkspaceTree(testCase.TestData.path,{},'ShowGUI',false);
    verifyEqual(testCase,tree.epochList{1}.h5_uuid,ids{1});
    verifyEqual(testCase,tree.allEpochs{1}.h5_uuid,ids{2});
    verifyEqual(testCase,tree.epochList{1}.epochIndex,2);
    testCase.TestData.payload.metadata.epoch_sequence_json = jsonencode({ids{1},ids{1}});
    writeFixture(testCase);
    verifyError(testCase,@() launchWorkspaceTree(testCase.TestData.path,{},'ShowGUI',false), ...
        'launchWorkspaceTree:InvalidSequence');
end

function testAllExcludedMaskKeepsNewTreeNodeFlagsExcluded(testCase)
    ugm=struct('epoch_count',2,'epoch_h5_uuids',{{ ...
        '00000000-0000-0000-0000-000000000001';'00000000-0000-0000-0000-000000000002'}}, ...
        'selection_mask',false(2,1));
    save(fullfile(testCase.TestData.folder,'selection.ugm'),'ugm','-v7');
    tree=launchWorkspaceTree(testCase.TestData.path,{'date','parameters/history1'},'ShowGUI',false);
    verifyFalse(testCase,tree.custom.isSelected);
    verifyFalse(testCase,tree.children{1}.custom.isSelected);
    verifyTrue(testCase,all(cellfun(@(child) ~child.custom.isSelected,tree.children{1}.children)));
    verifyTrue(testCase,all(cellfun(@(epoch) ~epoch.isSelected,tree.allEpochs)));
end

function testGUISaveUsesExplicitMaskAndPreservesProvenance(testCase)
    path=fullfile(testCase.TestData.folder,'selection.ugm');
    ugm=struct('epoch_count',2,'epoch_h5_uuids',{{ ...
        '00000000-0000-0000-0000-000000000001';'00000000-0000-0000-0000-000000000002'}}, ...
        'selection_mask',true(2,1),'dataset_uuid','11111111-1111-1111-1111-111111111111', ...
        'recipe_sha256',repmat('a',1,64));
    save(path,'ugm','-v7');
    [tree,gui]=launchWorkspaceTree(testCase.TestData.path,{'date'});
    cleanup=onCleanup(@() delete(gui.figure)); %#ok<NASGU>
    tree.allEpochs{1}.isSelected=false;
    savedPath=gui.saveWorkspaceMask();
    [~,canonical]=fileattrib(path);
    verifyEqual(testCase,savedPath,canonical.Name);
    saved=load(path,'-mat');
    verifyEqual(testCase,saved.ugm.dataset_uuid,ugm.dataset_uuid);
    verifyEqual(testCase,saved.ugm.recipe_sha256,ugm.recipe_sha256);
    verifyEqual(testCase,saved.ugm.selection_mask,logical([0;1]));
    verifyEqual(testCase,logical(gui.loadedMask(:)),logical([0;1]));
    ugm.epoch_h5_uuids{1}='different-epoch';
    save(path,'ugm','-v7');
    before=readBytes(path);
    verifyError(testCase,@() gui.saveWorkspaceMask(),'epicTreeGUI:InvalidWorkspaceMask');
    verifyEqual(testCase,readBytes(path),before);
end

function bytes=readBytes(path)
    handle=fopen(path,'rb');
    cleanup=onCleanup(@() fclose(handle)); %#ok<NASGU>
    bytes=fread(handle,Inf,'*uint8');
end

function testNestedCompositeFieldsResolveExactMapping(testCase)
    mapping=testCase.TestData.mapping;
    for i=1:numel(mapping), mapping(i).components={}; end
    mapping(3).field='joint/parameters%2Fhistory1+parameters%2Ftarget';
    mapping(3).components={'parameters/history1','parameters/target'};
    testCase.TestData.payload.metadata.split_mapping_json=jsonencode(mapping);
    writeFixture(testCase);
    tree=launchWorkspaceTree(testCase.TestData.path,{{'parameters/history1','parameters/target'},'date'},'ShowGUI',false);
    verifyEqual(testCase,tree.children{1}.splitKey,'workspaceGrouping.g003');
    verifyEqual(testCase,tree.epochCount(),2);
    verifyError(testCase,@() launchWorkspaceTree(testCase.TestData.path,{{'parameters/target','parameters/history1'}},'ShowGUI',false), ...
        'launchWorkspaceTree:UnavailableField');
    verifyError(testCase,@() launchWorkspaceTree(testCase.TestData.path,{{'parameters/history1','parameters/history1'}},'ShowGUI',false), ...
        'launchWorkspaceTree:InvalidFields');
    mapping(3).components={'parameters/history1','parameters/history1'};
    testCase.TestData.payload.metadata.split_mapping_json=jsonencode(mapping); writeFixture(testCase);
    verifyError(testCase,@() launchWorkspaceTree(testCase.TestData.path,'ShowGUI',false),'launchWorkspaceTree:InvalidMapping');
end

function testReadableDisplayLabelsKeepUnderlyingTypedKeys(testCase)
    entries=struct('field','parameters/history1','label','History 1', ...
        'values',struct('value',{'null','[1,2]'},'label',{'Not specified','Mean 1; SD 2'}));
    testCase.TestData.payload.metadata.split_display_json=['[' jsonencode(entries) ']'];
    writeFixture(testCase);
    tree=launchWorkspaceTree(testCase.TestData.path,{'parameters/history1'},'ShowGUI',false);
    for i=1:numel(tree.children)
        node=tree.children{i};
        verifyEqual(testCase,node.getCustom('workspaceFieldLabel'),'History 1');
        index=find(strcmp({entries.values.value},node.splitValue));
        verifyEqual(testCase,node.getCustom('workspaceValueLabel'),entries.values(index).label);
    end
    entries.values(2).value='null';
    testCase.TestData.payload.metadata.split_display_json=['[' jsonencode(entries) ']']; writeFixture(testCase);
    verifyError(testCase,@() launchWorkspaceTree(testCase.TestData.path,{'parameters/history1'},'ShowGUI',false),'launchWorkspaceTree:InvalidDisplay');
    entries.values=entries.values(1);
    testCase.TestData.payload.metadata.split_display_json=['[' jsonencode(entries) ']']; writeFixture(testCase);
    verifyError(testCase,@() launchWorkspaceTree(testCase.TestData.path,{'parameters/history1'},'ShowGUI',false),'launchWorkspaceTree:InvalidDisplay');
end
