function writeWorkspaceTags(document, filename)
% WRITEWORKSPACETAGS Explicit JSON output; no masks, raw data or SQL mutation.
    document=validateWorkspaceTags(document);
    [~,~,extension]=fileparts(filename);
    assert(strcmpi(extension,'.json'),'WorkspaceTags:Format','Write authored tags to a .json file, not .ugm.');
    assert(~isfile(filename),'WorkspaceTags:Exists','Refusing to overwrite an existing tag document.');
    % MATLAB encodes singleton struct arrays as objects. Cell wrappers preserve
    % the portable schema's list semantics for zero, one, and multiple tags.
    entries=document.entries;
    outputEntries=cell(1,numel(entries));
    for i=1:numel(entries)
        entry=entries(i); entry.tags=num2cell(entry.tags); outputEntries{i}=entry;
    end
    document.entries=outputEntries;
    raw=jsonencode(document);
    assert(numel(unicode2native(raw,'UTF-8'))<=8*1024*1024,'WorkspaceTags:Size','Tag JSON exceeds 8 MiB.');
    [handle,message]=fopen(filename,'w','n','UTF-8');
    assert(handle~=-1,'WorkspaceTags:Write','Cannot create output: %s',message);
    cleaner=onCleanup(@() fclose(handle)); %#ok<NASGU>
    written=fwrite(handle,unicode2native(raw,'UTF-8'),'uint8');
    assert(written==numel(unicode2native(raw,'UTF-8')),'WorkspaceTags:Write','Tag output was incomplete.');
end
