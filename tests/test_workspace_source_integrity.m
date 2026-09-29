function tests=test_workspace_source_integrity
    tests=functiontests(localfunctions);
end
function setup(testCase)
    addpath(fullfile(fileparts(fileparts(mfilename('fullpath'))),'src','tree'));
    folder=tempname;mkdir(folder);testCase.TestData.folder=folder;
    file=fullfile(folder,'source.h5');
    h5create(file,'/response/data',[4 1]);h5write(file,'/response/data',[1;2;3;4]);
    testCase.TestData.file=file;
    testCase.TestData.sha=hashFile(file);
    testCase.TestData.response=struct('device_name','Amp1','sample_rate',10000,'data',[], ...
        'h5_file',file,'h5_path','/response','source_sha256',testCase.TestData.sha);
    clear verifyWorkspaceSource
end
function teardown(testCase)
    rmdir(testCase.TestData.folder,'s');clear verifyWorkspaceSource
end
function hash=hashFile(file)
    % Independent fixture oracle via the system's streaming SHA tool.
    [status,result]=system(sprintf('/usr/bin/shasum -a 256 "%s"',file));
    assert(status==0);hash=regexp(result,'[0-9a-f]{64}(?=  )','match','once');assert(~isempty(hash));
end
function testKnownDigestAndCache(testCase)
    file=fullfile(testCase.TestData.folder,'known');f=fopen(file,'w');fwrite(f,'abc');fclose(f);
    sha='ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad';
    [first,hit]=verifyWorkspaceSource(file,sha);verifyFalse(testCase,hit);
    [second,hit]=verifyWorkspaceSource(file,sha);verifyTrue(testCase,hit);verifyEqual(testCase,first,second);
    verifyWorkspaceSource(file,sha,first);
end
function testVerifiedWaveformAndLegacy(testCase)
    data=epicTreeTools.loadH5ResponseData(testCase.TestData.response);
    verifyEqual(testCase,data,[1;2;3;4]);
    response=testCase.TestData.response;response.data=[900;901];
    verifyEqual(testCase,epicTreeTools.loadH5ResponseData(response),data);
    epoch=struct('responses',testCase.TestData.response,'isSelected',true);
    [matrix,~,rate]=epicTreeTools.getSelectedData({epoch},'Amp1');
    verifyEqual(testCase,matrix,[1 2 3 4]);verifyEqual(testCase,rate,10000);
    legacy=rmfield(testCase.TestData.response,'source_sha256');
    verifyEqual(testCase,epicTreeTools.loadH5ResponseData(legacy),data);
end
function testWrongHashPropagatesRatherThanReturningEmpty(testCase)
    response=testCase.TestData.response;response.source_sha256=repmat('0',1,64);
    verifyError(testCase,@()epicTreeTools.loadH5ResponseData(response),'workspaceSource:HashMismatch');
    epoch=struct('responses',response,'isSelected',true);
    verifyError(testCase,@()epicTreeTools.getSelectedData({epoch},'Amp1'),'workspaceSource:HashMismatch');
    response.data=[1;2];
    verifyError(testCase,@()epicTreeTools.loadH5ResponseData(response),'workspaceSource:HashMismatch');
end
function testMutationInvalidatesCacheAndReadToken(testCase)
    token=verifyWorkspaceSource(testCase.TestData.file,testCase.TestData.sha);
    h5write(testCase.TestData.file,'/response/data',[5;6;7;8]);
    verifyError(testCase,@()verifyWorkspaceSource(testCase.TestData.file,testCase.TestData.sha,token),'workspaceSource:ChangedDuringRead');
    verifyError(testCase,@()epicTreeTools.loadH5ResponseData(testCase.TestData.response),'workspaceSource:HashMismatch');
    updated=hashFile(testCase.TestData.file);
    verifyWorkspaceSource(testCase.TestData.file,updated);
end
function testRelocatedOverrideMustHaveExactSourceBytes(testCase)
    copy=fullfile(testCase.TestData.folder,'relocated.h5');copyfile(testCase.TestData.file,copy);
    verifyEqual(testCase,epicTreeTools.loadH5ResponseData(testCase.TestData.response,copy),[1;2;3;4]);
    h5write(copy,'/response/data',[0;0;0;0]);
    verifyError(testCase,@()epicTreeTools.loadH5ResponseData(testCase.TestData.response,copy),'workspaceSource:HashMismatch');
end
function testMissingSourceAndMalformedHashFailClosed(testCase)
    response=testCase.TestData.response;response.source_sha256='wrong';
    verifyError(testCase,@()epicTreeTools.loadH5ResponseData(response),'workspaceSource:InvalidHash');
    delete(testCase.TestData.file);
    verifyError(testCase,@()epicTreeTools.loadH5ResponseData(testCase.TestData.response),'workspaceSource:Unavailable');
end
function testCanonicalAliasesAndBoundedCache(testCase)
    sha='ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad';
    first=fullfile(testCase.TestData.folder,'known');f=fopen(first,'w');fwrite(f,'abc');fclose(f);
    verifyWorkspaceSource(first,sha);
    [~,hit]=verifyWorkspaceSource(fullfile(testCase.TestData.folder,'.','known'),sha);verifyTrue(testCase,hit);
    for i=1:33
        file=fullfile(testCase.TestData.folder,sprintf('other%d',i));
        f=fopen(file,'w');fwrite(f,'abc');fclose(f);verifyWorkspaceSource(file,sha);
    end
    [~,hit]=verifyWorkspaceSource(first,sha);verifyFalse(testCase,hit);
end
function testGUISelectionClearsPreviouslyValidTraceOnSourceMutation(testCase)
    root=fileparts(fileparts(mfilename('fullpath')));
    addpath(root,genpath(fullfile(root,'src')));
    epoch=struct('responses',testCase.TestData.response,'isSelected',true, ...
        'h5_file',testCase.TestData.file,'h5_uuid','disposable-integrity-epoch', ...
        'start_time','2026-09-24 12:00:00','parameters',struct(), ...
        'cellInfo',struct('label','Fixture cell'),'blockInfo',struct('protocol_name','Fixture'));
    tree=epicTreeTools();tree.allEpochs={epoch};tree.epochList={epoch};tree.isLeaf=true;
    gui=epicTreeGUI(tree);
    cleanup=onCleanup(@()delete(gui)); %#ok<NASGU> % Only this test's own figure.
    graph=gui.treeBrowser.graphTree;
    rootWidget=[];
    for i=1:numel(graph.widgetList)
        nodeKey=graph.widgetList{i}.boundNodeKey;
        if ~isempty(nodeKey)&&isa(graph.nodeList{nodeKey}.userData,'epicTreeTools')
            rootWidget=i;break;
        end
    end
    assertNotEmpty(testCase,rootWidget);
    graph.selectWidget(rootWidget);drawnow;
    ax=gui.plottingCanvas.axes;
    lines=findobj(ax,'Type','line');
    assertNotEmpty(testCase,lines,'Valid source must plot through the real tree-selection callback.');
    verifyEqual(testCase,get(lines(1),'YData'),[1 2 3 4]);
    % Same source path and dataset shape, changed bytes: no wait to hide coarse timestamps.
    h5write(testCase.TestData.file,'/response/data',[9;8;7;6]);
    graph.selectWidget(rootWidget);drawnow;
    verifyEmpty(testCase,findobj(ax,'Type','line'),'Integrity failure must remove the previously valid trace.');
    messages=get(findobj(ax,'Type','text'),'String');
    if ischar(messages),messages={messages};end
    message=strjoin(messages,' ');
    verifyTrue(testCase,contains(message,'integrity check failed'));
    verifyTrue(testCase,contains(message,'No trace displayed'));
    verifyEqual(testCase,get(get(ax,'Title'),'String'),'Data unavailable');
end
