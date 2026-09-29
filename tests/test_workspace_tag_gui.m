% Native GUI tagging uses loaded typed UUIDs, independently of tree order.
repo=fileparts(fileparts(mfilename('fullpath')));addpath(genpath(fullfile(repo,'src')));addpath(repo);
project='10000000-0000-4000-8000-000000000001';
cellA='20000000-0000-4000-8000-000000000001';cellB='20000000-0000-4000-8000-000000000002';
epochA='30000000-0000-4000-8000-000000000001';epochB='30000000-0000-4000-8000-000000000002';
profile='40000000-0000-4000-8000-000000000001';
entries=struct('target_kind',{'cell','cell','epoch','epoch'},'target_uuid',{cellA,cellB,epochA,epochB},'tags',{[],[],[],[]});
doc=struct('format','rieke-tag-exchange','version',1,'project_uuid',project,'entries',entries);
inputFile=[tempname '.json'];outputFile=[tempname '.json'];badFile=[tempname '.json'];writeWorkspaceTags(doc,inputFile);
ep=struct('h5_uuid',epochA,'cellInfo',struct('h5_uuid',cellA,'label','Cell1','type','test'), ...
    'isSelected',true,'responses',[],'protocolSettings',struct(),'protocolID','test');
ep2=ep;ep2.h5_uuid=epochB;ep2.cellInfo.h5_uuid=cellB;
tree=epicTreeTools();tree.allEpochs={ep2;ep};tree.buildTreeWithSplitters({'cellInfo.h5_uuid'});
gui=epicTreeGUI(tree);cleanupGui=onCleanup(@() delete(gui));
assert(~isempty(findall(gui.figure,'Type','uimenu','Label','Tags')),'Native Tags menu missing');
gui.loadWorkspaceTags(inputFile);
assert(gui.tagWorkspaceIds('epoch',{epochA},'matlab-reviewed',profile,'MATLAB tester')==1);
assert(gui.tagWorkspaceIds('cell',{cellB},'cell-type',profile,'MATLAB tester')==1);
gui.saveWorkspaceTags(outputFile);saved=readWorkspaceTags(outputFile);
assert(strcmp(saved.entries(3).tags.tag,'matlab-reviewed'));
assert(isempty(saved.entries(4).tags),'Tag leaked to another epoch after tree reorder');
assert(isempty(saved.entries(1).tags),'Same cell label cross-tagged wrong cell');
assert(strcmp(saved.entries(2).tags.tag,'cell-type'));
failed=false;before=gui.workspaceTags;
try,gui.tagWorkspaceIds('cell',{epochA},'wrong-kind',profile,'MATLAB tester');catch,failed=true;end
assert(failed && isequaln(before,gui.workspaceTags),'Wrong-kind UUID was accepted or partially mutated');
failed=false;
try,gui.tagWorkspaceIds('epoch',{epochA,'30000000-0000-4000-8000-000000000099'},'partial',profile,'MATLAB tester');catch,failed=true;end
assert(failed && isequaln(before,gui.workspaceTags),'Unknown mixed batch partially mutated');
bad=doc;bad.entries(3).target_uuid='30000000-0000-4000-8000-000000000099';writeWorkspaceTags(bad,badFile);
failed=false;try,gui.loadWorkspaceTags(badFile);catch,failed=true;end
assert(failed && isequaln(before,gui.workspaceTags),'Foreign registry replaced loaded tags');
delete(inputFile);delete(outputFile);delete(badFile);clear cleanupGui;
fprintf('Native tag GUI exact-UUID round trip passed: reordered epochs, same-named cells, typed IDs, atomic rejection.\n');
