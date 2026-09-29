function proof = verify_workspace_generated_bundle(bundlePath, oraclePath)
% VERIFY_WORKSPACE_GENERATED_BUNDLE Test shipped scripts as executable artifacts.
%
% proof = verify_workspace_generated_bundle(bundlePath [, oraclePath])
% Oracle JSON: {epoch_count, fields:[semantic IDs], leaves:[{path:[canonical
% grouping strings], epochs:[UUIDs in exact UI chronological order]}]}.
% The default oracle is bundlePath/expected-tree.json. Scripts are trusted
% artifacts produced by this repository, not arbitrary uploaded MATLAB code.
%
% Copies into a fresh directory containing spaces and an apostrophe. Executes
% the unchanged launch_epictree.m and tree_layout.m, tests grouping/sequence,
% shuffled mixed UUID masks, visible GUI and real lazy response data, native
% mask round trips, all-excluded flags, and invalid mappings. Raw H5 files are
% read only. Only figures created by this test are deleted. Proof JSON, PNGs,
% and the moved copy remain under proof.output_directory for inspection.

    if nargin < 2
        oraclePath=fullfile(bundlePath,'expected-tree.json');
    end
    expected=jsondecode(fileread(oraclePath));
    required={'recordings.mat','launch_epictree.m','tree_layout.m','launchWorkspaceTree.m'};
    for i=1:numel(required)
        assert(isfile(fullfile(bundlePath,required{i})),'Missing generated artifact: %s',required{i});
    end
    root=tempname;
    mkdir(root);
    folder=fullfile(root,'moved bundle''s files');
    copyfile(bundlePath,folder);
    [resolved,canonical]=fileattrib(folder); assert(resolved); folder=canonical.Name;
    oldDirectory=pwd; oldPath=path;
    restore=onCleanup(@() restoreEnvironment(oldDirectory,oldPath)); %#ok<NASGU>
    repo=fileparts(fileparts(mfilename('fullpath')));
    addpath(genpath(repo)); addpath(folder,'-begin'); cd(folder);
    [data,metadata]=loadEpicTreeData(fullfile(folder,'recordings.mat'));
    assert(isfield(metadata,'epoch_sequence_json'),'New generated exports must include exact epoch sequence metadata.');
    baseline=epicTreeTools(data,'LoadUserMetadata','none');
    ids=cellfun(@(epoch) epoch.h5_uuid,baseline.allEpochs,'UniformOutput',false);
    n=numel(ids);
    assert(n==expected.epoch_count && n>1,'Artifact requires at least two exported epochs for mixed-mask testing.');
    selected=mod((1:n)',3)~=0;
    selected(1)=true; selected(end)=false;
    permutation=[2:2:n,1:2:n];
    writeMask(fullfile(folder,'selection.ugm'),ids(permutation),selected(permutation));
    flags=containers.Map(ids,num2cell(selected));
    mapping=jsondecode(metadata.split_mapping_json);
    fields=textList(expected.fields);
    paths=cell(1,numel(fields));
    for i=1:numel(fields)
        index=find(strcmp({mapping.field},fields{i}));
        assert(isscalar(index),'Oracle field must resolve exactly once in mapping.');
        paths{i}=mapping(index).matlab_path;
    end
    results=cell(1,2);
    activeSelection=selected;
    scripts={'launch_epictree.m','tree_layout.m'};
    for index=1:numel(scripts)
        previous=findall(groot,'Type','figure');
        cleanup=onCleanup(@() deleteNewFigures(previous));
        [tree,gui]=executeGenerated(fullfile(folder,scripts{index}));
        assert(isa(tree,'epicTreeTools') && isa(gui,'epicTreeGUI'),'Generated script did not return its tree and GUI.');
        assert(isgraphics(gui.figure,'figure') && strcmp(get(gui.figure,'Visible'),'on'),'Generated GUI is not visible.');
        verifyTree(tree,expected,paths,flags);
        verifyGraphFlags(gui);
        verifyDisplayLabels(gui,metadata);
        traceProof=selectAndVerifyTrace(gui,tree,flags);
        reversed=~activeSelection;
        for i=1:n
            tree.allEpochs{i}.isSelected=reversed(i);
        end
        tree.propagateSelectionToLeaves(); tree.refreshNodeSelectionState();
        assert(ismethod(gui,'saveWorkspaceMask'),'Workspace GUI must provide its explicit bundle-mask save method.');
        returned=gui.saveWorkspaceMask();
        assert(strcmp(returned,fullfile(folder,'selection.ugm')),'GUI save escaped this bundle or used a latest-mask filename.');
        assert(isequal(logical(gui.loadedMask(:)),reversed(:)),'GUI did not acknowledge its saved mask revision.');
        savedMask=load(returned,'-mat');
        assert(isfield(savedMask.ugm,'dataset_uuid') && strcmp(reshape(savedMask.ugm.dataset_uuid,1,[]),reshape(metadata.dataset_uuid,1,[])), ...
            'GUI save lost the original dataset provenance.');
        roundtrip=epicTreeTools(data,'LoadUserMetadata','none');
        assert(roundtrip.loadUserMetadata(returned),'MATLAB-saved mask failed to reload.');
        for i=1:n
            assert(roundtrip.allEpochs{i}.isSelected==reversed(i),'Mask round trip changed UUID-associated selection.');
        end
        drawnow;
        imagePath=fullfile(folder,sprintf('generated-script-%d.png',index));
        saveas(gui.figure,imagePath);
        results{index}=struct('script',scripts{index},'executed_unchanged',true, ...
            'epochs',n,'ordered_leaves',numel(expected.leaves),'exact_epoch_sequence',true, ...
            'mixed_mask_by_uuid',true,'gui_created',true,'roundtrip_mask_by_uuid',true, ...
            'friendly_display_labels',isfield(metadata,'split_display_json'), ...
            'gui_save_path',returned,'reopened_saved_mask',index==2, ...
            'trace',traceProof,'screenshot',imagePath); %#ok<AGROW>
        activeSelection=reversed;
        flags=containers.Map(ids,num2cell(activeSelection));
        delete(gui.figure);
        clear cleanup;
    end
    % A fully excluded mask must remain unchecked after new tree nodes form.
    writeMask(fullfile(folder,'selection.ugm'),ids,false(n,1));
    previous=findall(groot,'Type','figure');
    cleanup=onCleanup(@() deleteNewFigures(previous));
    [excluded,excludedGUI]=executeGenerated(fullfile(folder,'tree_layout.m'));
    falseFlags=containers.Map(ids,num2cell(false(n,1)));
    verifyTree(excluded,expected,paths,falseFlags); verifyGraphFlags(excludedGUI);
    assert(~excluded.custom.isSelected,'All-excluded root incorrectly appears selected.');
    delete(excludedGUI.figure); clear cleanup;
    writeMask(fullfile(folder,'selection.ugm'),ids(permutation),selected(permutation));
    expectFailure(@() launchWorkspaceTree(fullfile(folder,'recordings.mat'),{'unavailable/field'},'ShowGUI',false), ...
                  'launchWorkspaceTree:UnavailableField');
    bad=load(fullfile(folder,'recordings.mat'));
    badMapping=jsondecode(bad.metadata.split_mapping_json);
    if isempty(badMapping)
        badMapping=struct('field','date','label','Date','matlab_path','workspaceGrouping.invalid;system');
        bad.metadata.split_mapping_json=['[' jsonencode(badMapping) ']'];
    else
        badMapping(1).matlab_path='workspaceGrouping.invalid;system';
        bad.metadata.split_mapping_json=jsonencode(badMapping);
    end
    invalid=fullfile(folder,'invalid-mapping.mat'); save(invalid,'-struct','bad');
    expectFailure(@() launchWorkspaceTree(invalid,fields,'ShowGUI',false),'launchWorkspaceTree:InvalidMapping');
    delete(invalid);
    sequence=jsondecode(metadata.epoch_sequence_json);
    sequence{end}=sequence{1};
    bad=load(fullfile(folder,'recordings.mat'));
    bad.metadata.epoch_sequence_json=jsonencode(sequence);
    invalid=fullfile(folder,'invalid-sequence.mat'); save(invalid,'-struct','bad');
    expectFailure(@() launchWorkspaceTree(invalid,fields,'ShowGUI',false),'launchWorkspaceTree:InvalidSequence');
    delete(invalid);
    proof=struct('output_directory',folder,'epoch_count',n,'fields',{fields}, ...
        'scripts',[results{:}],'all_excluded_nodes_and_gui_flags',true,'invalid_mapping_rejected',true, ...
        'unavailable_field_rejected',true,'invalid_sequence_rejected',true, ...
        'source_files_modified',false,'project_database_modified',false);
    handle=fopen(fullfile(folder,'generated-bundle-proof.json'),'w');
    fprintf(handle,'%s\n',jsonencode(proof)); fclose(handle);
    fprintf('GENERATED_BUNDLE_E2E_PASS %d epochs %d ordered leaves: %s\n',n,numel(expected.leaves),folder);
end

function [tree,gui]=executeGenerated(script)
    run(script); % Execute the exact trusted generated artifact, not an equivalent call.
end

function verifyTree(tree,expected,paths,flags)
    assert(tree.epochCount()==expected.epoch_count,'Epoch count changed.');
    actual=collect(tree,{},paths,1,flags);
    assert(numel(actual)==numel(expected.leaves),'Leaf count differs from the UI oracle.');
    allIds={};
    for i=1:numel(actual)
        assert(isequal(actual{i}.path(:),textList(expected.leaves(i).path)), 'Ordered branch path differs at leaf %d.',i);
        assert(isequal(actual{i}.epochs(:),textList(expected.leaves(i).epochs)), 'Within-leaf epoch sequence differs at leaf %d.',i);
        allIds=[allIds;actual{i}.epochs(:)]; %#ok<AGROW>
    end
    assert(numel(unique(allIds))==expected.epoch_count,'Leaf membership duplicated or missing.');
    for i=1:numel(tree.allEpochs)
        epoch=tree.allEpochs{i};
        assert(epoch.isSelected==flags(epoch.h5_uuid),'Root UUID selection changed.');
        assert(epoch.epochIndex==i,'Root mask identity/index was reordered.');
    end
end

function leaves=collect(node,path,paths,depth,flags)
    if isempty(node.children)
        assert(depth==numel(paths)+1,'Tree grouping gained or lost a level.');
        ids=cellfun(@(epoch) epoch.h5_uuid,node.epochList,'UniformOutput',false);
        for i=1:numel(node.epochList)
            assert(node.epochList{i}.isSelected==flags(ids{i}),'Leaf UUID selection changed.');
        end
        assert(node.custom.isSelected==any(cellfun(@(id) flags(id),ids)),'Leaf checkbox state differs from epoch flags.');
        leaves={struct('path',{path},'epochs',{ids})}; return;
    end
    assert(depth<=numel(paths),'Unexpected nested grouping level.');
    leaves={};
    for i=1:numel(node.children)
        child=node.children{i};
        assert(strcmp(child.splitKey,paths{depth}),'Grouping field order differs from emitted recipe.');
        leaves=[leaves collect(child,[path {child.splitValue}],paths,depth+1,flags)]; %#ok<AGROW>
    end
    assert(node.custom.isSelected==any(cellfun(@(child) child.custom.isSelected,node.children)), ...
        'Parent checkbox state differs from selected children.');
end

function verifyGraphFlags(gui)
    for i=1:numel(gui.treeBrowser.graphTree.nodeList)
        node=gui.treeBrowser.graphTree.nodeList{i};
        if isa(node.userData,'epicTreeTools')
            assert(node.isChecked==node.userData.custom.isSelected,'Rendered tree checkbox differs from selection state.');
        elseif isstruct(node.userData) && isfield(node.userData,'isSelected')
            assert(node.isChecked==node.userData.isSelected,'Rendered epoch checkbox differs from selection state.');
        end
    end
end

function proof=selectAndVerifyTrace(gui,tree,flags)
    graph=gui.treeBrowser.graphTree; target=[];
    for i=1:numel(graph.nodeList)
        node=graph.nodeList{i}; epoch=node.userData;
        if isstruct(epoch) && isfield(epoch,'h5_uuid') && flags(epoch.h5_uuid)
            target=node; break;
        end
    end
    assert(~isempty(target),'No selectable exported epoch widget.');
    ancestor=target;
    while ~isempty(ancestor.parentKey)
        ancestor=graph.nodeList{ancestor.parentKey}; ancestor.isExpanded=true;
    end
    graph.draw();
    selected=false;
    for i=1:numel(graph.widgetList)
        if isequal(graph.widgetList{i}.boundNodeKey,target.selfKey)
            graph.selectWidget(i); selected=true; break;
        end
    end
    assert(selected,'Selected epoch was not rendered.'); drawnow;
    epoch=target.userData; response=epicTreeTools.getResponseByName(epoch,'Amp1');
    assert(~isempty(response) && isempty(response.data),'Test requires a lazy Amp1 response pointer.');
    raw=h5read(response.h5_file,[response.h5_path '/data']);
    assert(isstruct(raw) && isfield(raw,'quantity'),'Expected recorded quantity/unit H5 representation.');
    expected=double(raw.quantity(:));
    traces=findobj(gui.plottingCanvas.axes,'Type','line');
    assert(~isempty(traces),'Generated GUI did not display a lazy response.');
    plotted=get(traces(1),'YData'); assert(isequal(plotted(:),expected),'GUI trace differs from direct H5 quantities.');
    [loaded,rate]=epicTreeTools.getResponseFromEpoch(epoch,'Amp1');
    assert(isequal(loaded(:),expected) && rate==response.sample_rate,'Loader trace or sample rate differs.');
    proof=struct('epoch_uuid',epoch.h5_uuid,'samples',numel(expected),'sample_rate',rate, ...
        'units',response.units,'gui_equals_direct_h5',true,'loader_equals_direct_h5',true);
end

function writeMask(filename,ids,selected)
    ugm=struct('version','1.1','epoch_count',numel(ids),'epoch_h5_uuids',{ids(:)}, ...
               'selection_mask',logical(selected(:)),'mat_file_basename','recordings');
    if isfile(filename)
        previous=load(filename,'-mat');
        scope={'project_uuid','protocol_uuid','dataset_uuid','export_uuid','query_sha256','recipe_sha256','source_scope_revision'};
        for i=1:numel(scope)
            if isfield(previous.ugm,scope{i}),ugm.(scope{i})=previous.ugm.(scope{i});end
        end
    end
    save(filename,'ugm','-v7.3');
end

function values=textList(value)
    if isempty(value), values=cell(0,1); else, values=cellfun(@(item) reshape(item,1,[]),value(:),'UniformOutput',false); end
end

function expectFailure(callback,identifier)
    caught=false;
    try, callback(); catch error, caught=strcmp(error.identifier,identifier); end
    assert(caught,'Expected fail-closed error %s.',identifier);
end

function deleteNewFigures(previous)
    current=findall(groot,'Type','figure');
    for i=1:numel(current)
        if ~any(current(i)==previous), delete(current(i)); end
    end
end

function restoreEnvironment(directory,oldPath)
    cd(directory); path(oldPath);
end

function verifyDisplayLabels(gui,metadata)
    if ~isfield(metadata,'split_display_json'), return; end
    entries=jsondecode(metadata.split_display_json);
    mapping=jsondecode(metadata.split_mapping_json);
    for i=1:numel(gui.treeBrowser.graphTree.nodeList)
        graphNode=gui.treeBrowser.graphTree.nodeList{i};
        node=graphNode.userData;
        if ~isa(node,'epicTreeTools') || isempty(node.splitKey), continue; end
        field=mapping(find(strcmp({mapping.matlab_path},node.splitKey),1)).field;
        entry=entries(find(strcmp({entries.field},field),1));
        value=entry.values(find(strcmp({entry.values.value},node.splitValue),1));
        assert(strcmp(node.getCustom('workspaceFieldLabel'),entry.label),'Semantic field label changed.');
        assert(strcmp(node.getCustom('workspaceValueLabel'),value.label),'Readable value label changed.');
        prefix=[entry.label ': ' value.label];
        assert(startsWith(graphNode.name,prefix),'GUI exposes internal grouping keys instead of exported readable labels.');
    end
end
