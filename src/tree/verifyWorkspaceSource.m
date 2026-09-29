function [token, cacheHit] = verifyWorkspaceSource(filename, expectedSHA256, previous)
%VERIFYWORKSPACESOURCE Verify a workspace H5 reference without loading it in RAM.
% token = verifyWorkspaceSource(path, sha) verifies a source before reading.
% verifyWorkspaceSource(path, sha, token) rejects changes during that read.
% Cached digests are scoped to canonical path and precise filesystem identity.
    persistent cache
    if isempty(cache)
        cache = struct('path',{},'signature',{},'sha',{});
    end
    cacheHit = false;
    if ~((ischar(expectedSHA256) && isrow(expectedSHA256)) || (isstring(expectedSHA256) && isscalar(expectedSHA256)))
        error('workspaceSource:InvalidHash','Workspace source SHA-256 must be one hexadecimal string.');
    end
    expectedSHA256 = lower(char(expectedSHA256));
    if isempty(regexp(expectedSHA256,'^[0-9a-f]{64}$','once'))
        error('workspaceSource:InvalidHash','Workspace source SHA-256 is missing or malformed.');
    end
    [canonical, signature] = sourceSignature(filename);
    if nargin >= 3
        if ~isstruct(previous) || ~strcmp(previous.path,canonical) || ...
                ~isequal(previous.signature,signature) || ~strcmp(previous.sha,expectedSHA256)
            error('workspaceSource:ChangedDuringRead', ...
                'Workspace H5 source changed during reading. No waveform was returned: %s',canonical);
        end
        token = previous;
        return;
    end
    hit = find(strcmp({cache.path},canonical),1);
    if ~isempty(hit) && isequal(cache(hit).signature,signature)
        actual = cache(hit).sha;
        cacheHit = true;
    else
        try
            digest = java.security.MessageDigest.getInstance('SHA-256');
            stream = java.io.FileInputStream(canonical);
            cleanup = onCleanup(@() stream.close()); %#ok<NASGU>
            channel = stream.getChannel();
            buffer = java.nio.ByteBuffer.allocate(1024*1024);
            while true
                count = channel.read(buffer);
                if count < 0, break; end
                buffer.flip();
                digest.update(buffer);
                buffer.clear();
            end
            bytes = typecast(digest.digest(),'uint8');
            actual = lower(reshape(dec2hex(bytes,2).',1,[]));
        catch cause
            error('workspaceSource:ReadFailed','Cannot verify workspace H5 source %s: %s',canonical,cause.message);
        end
        [afterPath, afterSignature] = sourceSignature(filename);
        if ~strcmp(canonical,afterPath) || ~isequal(signature,afterSignature)
            error('workspaceSource:ChangedDuringVerification', ...
                'Workspace H5 source changed while its checksum was being verified: %s',canonical);
        end
        if ~isempty(hit), cache(hit)=[]; end
        cache(end+1)=struct('path',canonical,'signature',{signature},'sha',actual);
        if numel(cache)>32, cache=cache(end-31:end); end
    end
    if ~strcmp(actual,expectedSHA256)
        error('workspaceSource:HashMismatch', ...
            'Workspace H5 integrity check failed. Expected SHA-256 %s, found %s. No waveform was returned: %s', ...
            expectedSHA256,actual,canonical);
    end
    token=struct('path',canonical,'signature',{signature},'sha',actual);
end

function [canonical, signature] = sourceSignature(filename)
    try
        file=java.io.File(char(filename));
        canonical=char(file.getCanonicalPath());
        path=file.toPath();
        options=javaArray('java.nio.file.LinkOption',0);
        attributes=java.nio.file.Files.readAttributes(path,'basic:*',options);
        modified=attributes.get('lastModifiedTime');
        created=attributes.get('creationTime');
        key=attributes.get('fileKey');
        keyText='';if ~isempty(key),keyText=char(key.toString());end
        signature={sprintf('%.0f',double(attributes.get('size'))),char(modified.toString()),char(created.toString()),keyText};
        % Older MATLAB JVMs truncate macOS NIO times to seconds. Native stat
        % exposes subsecond mtime/ctime; pass arguments directly, never a shell.
        if ismac
            args=javaArray('java.lang.String',4);
            args(1)=java.lang.String('/usr/bin/stat');
            args(2)=java.lang.String('-f');
            args(3)=java.lang.String('%z|%.9Fm|%.9Fc|%i|%d');
            args(4)=java.lang.String(canonical);
            builder=java.lang.ProcessBuilder(args);
            process=builder.start();
            reader=java.io.BufferedReader(java.io.InputStreamReader(process.getInputStream()));
            readerCleanup=onCleanup(@() reader.close()); %#ok<NASGU>
            line=reader.readLine();
            status=process.waitFor();
            if status~=0 || isempty(line)
                error('workspaceSource:StatFailed','Cannot obtain precise source timestamps.');
            end
            signature{end+1}=char(line);
        end
        % Unix ctime also catches in-place edits whose mtime was restored.
        try
            changed=java.nio.file.Files.getAttribute(path,'unix:ctime',options);
            signature{end+1}=char(changed.toString());
        catch
            % Other filesystems retain the precise basic timestamps and file key.
        end
    catch cause
        error('workspaceSource:Unavailable','Cannot inspect workspace H5 source %s: %s',char(filename),cause.message);
    end
end
