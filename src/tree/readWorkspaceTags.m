function document = readWorkspaceTags(filename)
% READWORKSPACETAGS Read authored tags from portable JSON or a workspace MAT.
% Mask (.ugm) files carry selection only and are deliberately not accepted.
    [~,~,extension] = fileparts(filename);
    if strcmpi(extension,'.mat')
        data = load(filename,'metadata');
        assert(isfield(data,'metadata') && isfield(data.metadata,'workspace_tags_json'), ...
            'WorkspaceTags:MissingSnapshot','MAT export has no shared-tag snapshot.');
        document = jsondecode(data.metadata.workspace_tags_json);
    elseif strcmpi(extension,'.json')
        info = dir(filename);
        assert(~isempty(info) && info.bytes <= 8*1024*1024,'WorkspaceTags:Size','Tag JSON exceeds 8 MiB.');
        document = jsondecode(fileread(filename));
    else
        error('WorkspaceTags:Format','Use portable tag JSON or an exported recordings.mat; UGM is selection only.');
    end
    document = validateWorkspaceTags(document);
end
