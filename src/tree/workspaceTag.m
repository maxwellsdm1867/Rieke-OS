function document = workspaceTag(document, targetKind, targetUuid, tag, profileUuid, authorName)
% WORKSPACETAG Add an authored tag to up to 2,000 EXACT exported target UUIDs.
% targetUuid accepts one UUID, a cellstr list, or a string array. All targets are
% resolved and checked before editing. One validation covers the whole batch.
% d=readWorkspaceTags('recordings.mat');
% d=workspaceTag(d,'epoch',{epochA.h5_uuid,epochB.h5_uuid},'good',profileUuid,'A Scientist');
% writeWorkspaceTags(d,'matlab-tags.json'); % Explicitly preview/apply in RiekeOS.
% Cell tags use exact cell UUIDs. This never changes tree selection or raw H5.
    if ischar(document) || isstring(document), document=readWorkspaceTags(document); end
    [document,profiles]=validateWorkspaceTags(document);
    if isstring(targetKind) && isscalar(targetKind), targetKind=char(targetKind); end
    assert(ischar(targetKind) && isrow(targetKind) && any(strcmp(targetKind,{'cell','epoch'})), ...
        'WorkspaceTags:Target','Use an explicit cell or epoch target kind.');
    if ischar(targetUuid) && isrow(targetUuid), targetUuid={targetUuid};
    elseif isstring(targetUuid), targetUuid=cellstr(targetUuid(:)); end
    assert(iscellstr(targetUuid) && ~isempty(targetUuid) && numel(targetUuid)<=2000, ...
        'WorkspaceTags:Limit','Choose 1–2000 exact target UUIDs; split larger batches explicitly.');
    targetUuid=targetUuid(:);
    assert(numel(unique(targetUuid))==numel(targetUuid),'WorkspaceTags:Duplicate','Duplicate target UUID in this batch.');
    assert(~isempty(document.entries),'WorkspaceTags:Target','This export has no authorized targets.');
    candidates=find(strcmp({document.entries.target_kind},targetKind));
    [found,locations]=ismember(targetUuid,{document.entries(candidates).target_uuid});
    assert(all(found),'WorkspaceTags:Target','Exact target UUID/kind is absent or ambiguous in this export.');
    selected=candidates(locations);
    if isstring(tag) && isscalar(tag), tag=char(tag); end
    if isstring(profileUuid) && isscalar(profileUuid), profileUuid=char(profileUuid); end
    if isstring(authorName) && isscalar(authorName), authorName=char(authorName); end
    addition=struct('tag',tag,'profile_uuid',profileUuid,'author_name',authorName);
    probe=document;probe.entries=struct('target_kind',targetKind,'target_uuid',targetUuid{1},'tags',addition);
    validateWorkspaceTags(probe); % Validate just the new tag/profile, not N targets.
    if isKey(profiles,profileUuid)
        assert(strcmp(profiles(profileUuid),authorName),'WorkspaceTags:Author','Author profile UUID already has another name.');
    else
        assert(profiles.Count<100,'WorkspaceTags:Limit','A tag document supports at most 100 author profiles.');
    end
    needsAddition=false(1,numel(selected));
    for i=1:numel(selected)
        current=document.entries(selected(i)).tags;
        if isempty(current), needsAddition(i)=true; continue; end
        sameAuthor=strcmp({current.profile_uuid},profileUuid);
        needsAddition(i)=~any(sameAuthor & strcmp({current.tag},tag));
        assert(~needsAddition(i) || nnz(sameAuthor)<100,'WorkspaceTags:Limit','Import would exceed 100 tags for a target/author.');
    end
    for i=find(needsAddition)
        current=document.entries(selected(i)).tags;
        if isempty(current), current=addition; else, current(end+1)=addition; end
        document.entries(selected(i)).tags=current;
    end
end
