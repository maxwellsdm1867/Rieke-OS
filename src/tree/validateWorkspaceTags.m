function [document, profiles] = validateWorkspaceTags(document)
% VALIDATEWORKSPACETAGS Validate exact typed identities in O(N log N) time.
% The optional profile map lets bulk editors check a new author without another
% whole-document scan. No label/date/index fallback is ever used.
    assert(isstruct(document) && isscalar(document) && isfield(document,'format') && ...
        strcmp(document.format,'rieke-tag-exchange') && isfield(document,'version') && ...
        isnumeric(document.version) && isscalar(document.version) && document.version==1 ...
        && isfield(document,'project_uuid') && isfield(document,'entries'), ...
        'WorkspaceTags:Format','Invalid portable tag document.');
    checkUuid(document.project_uuid);
    entries = document.entries;
    assert(isempty(entries) || isstruct(entries),'WorkspaceTags:Entries','Entries must be objects.');
    targetKeys = cell(1,numel(entries));
    profiles = containers.Map('KeyType','char','ValueType','char');
    for i=1:numel(entries)
        entry=entries(i);
        assert(isfield(entry,'target_kind') && ischar(entry.target_kind) && ...
            any(strcmp(entry.target_kind,{'cell','epoch'})) && isfield(entry,'target_uuid') && isfield(entry,'tags'), ...
            'WorkspaceTags:Target','Each entry requires a cell/epoch kind and exact UUID.');
        checkUuid(entry.target_uuid);
        targetKeys{i}=[entry.target_kind ':' entry.target_uuid];
        tags=entry.tags;
        assert(isempty(tags) || isstruct(tags),'WorkspaceTags:Tags','Tags must be authored objects.');
        tagKeys=cell(1,numel(tags)); authorIds=cell(1,numel(tags));
        for j=1:numel(tags)
            assert(all(isfield(tags(j),{'tag','profile_uuid','author_name'})), ...
                'WorkspaceTags:Author','Every tag requires its author profile UUID and name.');
            author=tags(j).profile_uuid; name=tags(j).author_name;
            checkUuid(author); checkText(tags(j).tag,255); checkText(name,120);
            if isKey(profiles,author)
                assert(strcmp(profiles(author),name),'WorkspaceTags:Author','Author profile UUID has conflicting names across targets.');
            else
                profiles(author)=name;
                assert(profiles.Count<=100,'WorkspaceTags:Limit','A tag document supports at most 100 author profiles.');
            end
            tagKeys{j}=[author ':' tags(j).tag]; authorIds{j}=author;
        end
        assert(numel(unique(tagKeys))==numel(tagKeys),'WorkspaceTags:Duplicate','Duplicate authored tag.');
        if ~isempty(authorIds)
            [~,~,groups]=unique(authorIds);
            assert(all(accumarray(groups(:),1)<=100),'WorkspaceTags:Limit','Each target/author supports at most 100 tags.');
        end
    end
    % One sorted uniqueness check replaces a growing O(N^2) membership scan.
    assert(numel(unique(targetKeys))==numel(targetKeys),'WorkspaceTags:Duplicate','Duplicate target UUID and kind.');
end
function checkUuid(value)
    assert(ischar(value) && isrow(value) && ~isempty(regexp(value,'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$','once')), ...
        'WorkspaceTags:UUID','Use an exact canonical UUID; labels, dates and positions are not identifiers.');
end
function checkText(value,maximum)
    assert(ischar(value) && isrow(value) && ~isempty(value) && strcmp(value,strtrim(value)) && numel(value)<=maximum && all(value>=32), ...
        'WorkspaceTags:Text','Use nonempty trimmed printable tag/author text.');
end
