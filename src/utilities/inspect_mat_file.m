%% Inspect MAT File Structure
% Quick inspection of the test data file

clear all; clc;

file_path = '/Users/maxwellsdm/Documents/epicTreeTest/analysis/2025-12-02_F.mat';

fprintf('=== Inspecting MAT File ===\n');
fprintf('File: %s\n\n', file_path);

try
    % Load and display contents
    data = load(file_path);
    
    fprintf('Top-level fields:\n');
    fields = fieldnames(data);
    for i = 1:length(fields)
        fname = fields{i};
        fval = data.(fname);
        fprintf('  %s: ', fname);
        
        if isstruct(fval)
            fprintf('[struct with %d fields]\n', length(fieldnames(fval)));
            if length(fieldnames(fval)) < 10
                subfields = fieldnames(fval);
                for j = 1:length(subfields)
                    fprintf('    - %s\n', subfields{j});
                end
            end
        elseif iscell(fval)
            fprintf('[cell array %s]\n', mat2str(size(fval)));
            % Show first element if it exists
            if ~isempty(fval)
                fprintf('    First element type: %s\n', class(fval{1}));
            end
        elseif isnumeric(fval) || islogical(fval)
            fprintf('[%s %s]\n', class(fval), mat2str(size(fval)));
        elseif ischar(fval)
            if length(fval) < 50
                fprintf('[string]: "%s"\n', fval);
            else
                fprintf('[string]: "%s..."\n', fval(1:50));
            end
        else
            fprintf('[%s]\n', class(fval));
        end
    end
    
    % Check for standard format fields
    fprintf('\n=== Format Check ===\n');
    if isfield(data, 'format_version')
        fprintf('✓ Has format_version: %s\n', data.format_version);
    else
        fprintf('✗ Missing format_version (this is OK for custom formats)\n');
    end
    
    if isfield(data, 'metadata')
        fprintf('✓ Has metadata\n');
    else
        fprintf('✗ Missing metadata\n');
    end
    
    if isfield(data, 'experiments')
        fprintf('✓ Has experiments\n');
        if isstruct(data.experiments)
            fprintf('  Number of experiments: %d\n', length(data.experiments));
            if length(data.experiments) > 0
                fprintf('\n  First experiment fields:\n');
                exp_fields = fieldnames(data.experiments(1));
                for i = 1:min(10, length(exp_fields))
                    fprintf('    - %s\n', exp_fields{i});
                end
            end
        end
    else
        fprintf('✗ Missing experiments field\n');
        fprintf('\n=== Checking for alternative data structures ===\n');
        
        % Check for epoch data
        if isfield(data, 'epochs')
            fprintf('Found "epochs" field\n');
            if isstruct(data.epochs) && length(data.epochs) > 0
                fprintf('  First epoch fields:\n');
                e_fields = fieldnames(data.epochs(1));
                for i = 1:length(e_fields)
                    fprintf('    - %s\n', e_fields{i});
                end
            end
        end
        
        % Check for responses
        if isfield(data, 'responses')
            fprintf('Found "responses" field\n');
        end
        
        % Check for raw traces
        if isfield(data, 'amp_data') || isfield(data, 'trace')
            fprintf('Found raw data field\n');
        end
    end
    
catch ME
    fprintf('ERROR: %s\n', ME.message);
    fprintf('\nStack trace:\n');
    for i = 1:length(ME.stack)
        fprintf('  %s (line %d)\n', ME.stack(i).name, ME.stack(i).line);
    end
end

