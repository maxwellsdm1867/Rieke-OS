% Native portable tag editing and exact-identity validation. No research writes.
root=fileparts(fileparts(mfilename('fullpath')));
addpath(fullfile(root,'src','tree'));
folder=tempname; mkdir(folder);
cleaner=onCleanup(@() rmdir(folder,'s')); %#ok<NASGU>
project='11111111-1111-4111-8111-111111111111';
author='22222222-2222-4222-8222-222222222222';
first='33333333-3333-4333-8333-333333333333';
second='44444444-4444-4444-8444-444444444444';
cellUuid='55555555-5555-4555-8555-555555555555';
entry=struct('target_kind','epoch','target_uuid',first,'source_sha256',repmat('a',1,64),'tags',[]);
entries=[entry entry entry];entries(2).target_uuid=second;entries(3).target_kind='cell';entries(3).target_uuid=cellUuid;
doc=struct('format','rieke-tag-exchange','version',1,'project_uuid',project,'entries',entries);
initial=fullfile(folder,'input.json');writeWorkspaceTags(doc,initial);doc=readWorkspaceTags(initial);
doc.entries=doc.entries([3 2 1]); % Tree/export ordering is irrelevant.
doc=workspaceTag(doc,'epoch',second,'selected epoch',author,'Scientist A');
doc=workspaceTag(doc,'cell',cellUuid,'whole cell',author,'Scientist A');
assert(isempty(doc.entries(3).tags));assert(strcmp(doc.entries(2).tags.tag,'selected epoch'));
again=workspaceTag(doc,'epoch',second,'selected epoch',author,'Scientist A');assert(numel(again.entries(2).tags)==1);
output=fullfile(folder,'returned.json');writeWorkspaceTags(doc,output);returned=readWorkspaceTags(output);
assert(strcmp(returned.entries(1).target_uuid,cellUuid));assert(strcmp(returned.entries(2).target_uuid,second));
for args={{'cell',first},{'epoch',cellUuid},{'epoch','Cell1'},{'epoch','66666666-6666-4666-8666-666666666666'}}
    failed=false;
    try,workspaceTag(doc,args{1}{1},args{1}{2},'bad',author,'Scientist A');catch err,failed=strcmp(err.identifier,'WorkspaceTags:Target');end
    assert(failed,'Wrong kind/unknown/label target did not fail closed.');
end
subset=doc;subset.entries=subset.entries(2);writeWorkspaceTags(subset,fullfile(folder,'subset.json'));
assert(numel(readWorkspaceTags(fullfile(folder,'subset.json')).entries)==1);
duplicate=doc;duplicate.entries(end+1)=duplicate.entries(1);failed=false;
try,validateWorkspaceTags(duplicate);catch err,failed=strcmp(err.identifier,'WorkspaceTags:Duplicate');end
assert(failed);
metadata=struct('workspace_tags_json',fileread(output));save(fullfile(folder,'recordings.mat'),'metadata');
assert(strcmp(readWorkspaceTags(fullfile(folder,'recordings.mat')).entries(2).tags.tag,'selected epoch'));
bulk=workspaceTag(doc,'epoch',{first,second},'batch',author,'Scientist A');
assert(all(arrayfun(@(e) any(strcmp({e.tags.tag},'batch')),bulk.entries(2:3))));
assert(~any(strcmp({bulk.entries(1).tags.tag},'batch')),'Batch leaked into cell tags.');
failed=false;try,workspaceTag(doc,'epoch',repmat({first},1,2001),'too many',author,'Scientist A');catch err,failed=strcmp(err.identifier,'WorkspaceTags:Limit');end
assert(failed,'Oversized batch did not fail explicitly.');
conflicting=doc;conflicting.entries(2).tags.author_name='Different author';failed=false;
try,validateWorkspaceTags(conflicting);catch err,failed=strcmp(err.identifier,'WorkspaceTags:Author');end
assert(failed,'One author UUID accepted conflicting names on different targets.');
disp('PASS: exact typed UUID targets, shuffled order, subset, author, JSON/MAT roundtrip, duplicate/foreign rejection.');
