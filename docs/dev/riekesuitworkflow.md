Riekesuite Workflow AI Manual
Quick Reference for AI Systems
Core Pattern (UPDATED)
LOAD → SPLIT → BUILD → NAVIGATE+ANALYZE+STORE → QUERY → SUMMARIZE

Essential Commands
% 1. LOAD
list = loader.loadEpochList(file, path);

% 2. BUILD TREE  
tree = riekesuite.analysis.buildTree(list, split_criteria);

% 3. STORE RESULTS (CRITICAL: Store your analysis struct directly)
% results = your elementary analysis struct (whatever you created)
target_node.custom.put('results', riekesuite.util.toJavaMap(results));

% 4. QUERY RESULTS
stored = target_node.custom.get('results');
field_data = get(stored, 'field_name');

% 5. LOG SUCCESS
log_entry.success = true;
log_entry.data_metrics = struct('n_cells', n, 'conditions', conditions);

CRITICAL AI REQUIREMENT: Understanding Tree Splitters
MANDATORY: Always Ask About Tree Splitter Structure
Before ANY tree navigation, AI MUST ask:
"I need to understand your tree splitter structure to navigate correctly. 

Looking at your tree splitters:
tree = riekesuite.analysis.buildTree(list, {
    'protocolSettings(source:type)',
    dateSplit_java,
    'cell.label', 
    'protocolSettings(epochGroup:label)',
    'protocolSettings(frequencyCutoff)',
    'protocolSettings(currentSD)'
});

Let me confirm what each level represents:
- Level 1: protocolSettings(source:type) = Cell type? (e.g., 'RGC\ON-parasol')
- Level 2: dateSplit_java = Experiment date?
- Level 3: cell.label = Individual cell? (e.g., 'Cell3')
- Level 4: protocolSettings(epochGroup:label) = Experimental group?
- Level 5: protocolSettings(frequencyCutoff) = Frequency condition?
- Level 6: protocolSettings(currentSD) = Current SD parameter?

Is this interpretation correct? Which level contains the information I need for [specific task]?"

AI Tree Splitter Analysis Process
Step 1: Splitter Type Recognition
% AI should recognize these patterns:
'protocolSettings(fieldName)'     → Protocol parameter
'cell.property'                   → Cell property  
dateSplit_java                   → Date splitting function
'stimulusSettings(parameter)'     → Stimulus parameter
cellTypeSplitter_java            → Cell type function

Step 2: Level Mapping
AI must create a level map:
% Example interpretation:
Level 1: Cell Type (from protocolSettings(source:type))
Level 2: Date (from dateSplit_java)
Level 3: Individual Cell (from cell.label)
Level 4: Experimental Group (from protocolSettings(epochGroup:label))
Level 5: Frequency Condition (from protocolSettings(frequencyCutoff))
Level 6: Analysis Parameter (from protocolSettings(currentSD))

Step 3: Navigation Planning
AI must calculate navigation paths:
% If at Level 6 (currentSD) and need Level 1 (cell type):
target_node = current_node.parent.parent.parent.parent.parent;  % Go back 5 levels

% If at Level 4 (group) and need Level 1 (cell type):
target_node = current_node.parent.parent.parent;  % Go back 3 levels

Advanced Workflow Patterns
Critical Pattern 1: Function-Generated Figure Control
Problem: Functions That Auto-Generate Figures
Many analysis functions automatically create figures when called:
% This function creates its own figure every time
[results] = some_analysis_function(data, params, true);  % true = visualize

Issues:
❌ Creates new figure window each call
❌ Can't control which figure is used
❌ Memory buildup from multiple figures
❌ Can't save systematically
Solution: Modify Functions to Accept Figure Handles
Function Modification Pattern:
function [results] = analysis_function(data, params, visualize, varargin)
    % Handle optional figure parameter
    if nargin > 3 && ~isempty(varargin{1})
        fig_handle = varargin{1};
        if visualize
            figure(fig_handle);  % Use specified figure
            clf;  % Clear previous content
        end
    else
        if visualize
            fig_handle = figure();  % Create new figure if none specified
        end
    end
    
    % Your analysis code here...
    
    if visualize
        % Your plotting code here...
        subplot(2,2,1);
        plot(data);
        % etc...
    end
end

Usage in Workflow:
% Create designated figure once
analysis_fig = figure(100);
set(analysis_fig, 'Position', [100, 100, 1200, 800]);

% Use same figure for all analyses, save immediately
for analysis_idx = 1:n_analyses
    % Run analysis with designated figure
    [results] = analysis_function(data, params, true, analysis_fig);
    
    % Save immediately with unique filename
    filename = sprintf('analysis_%d.png', analysis_idx);
    saveas(analysis_fig, [save_path filename]);
    
    fprintf('Saved: %s\n', filename);
end

Critical Pattern 2: Efficient Tree Navigation Using .parent
Understanding .parent Navigation
The .parent property provides upward tree traversal:
% Tree structure from splitters:
tree = riekesuite.analysis.buildTree(list, {
    'level1_splitter',    % Level 1: Top level
    'level2_splitter',    % Level 2: 
    'level3_splitter',    % Level 3:
    'level4_splitter',    % Level 4:
    'level5_splitter'     % Level 5: Leaf level
});

Navigation Calculation Pattern:
% If currently at Level 5 and need Level 1:
target_node = current_node.parent.parent.parent.parent;  % Go back 4 levels

% If currently at Level 3 and need Level 1:
target_node = current_node.parent.parent;  % Go back 2 levels

AI Navigation Template:
function target_value = extractFromLevel(leaf_node, target_level, current_level)
    % Calculate levels to traverse back
    levels_back = current_level - target_level;
    
    % Navigate back using .parent chain
    target_node = leaf_node;
    for i = 1:levels_back
        target_node = target_node.parent;
        if isempty(target_node)
            error('Navigation failed at level %d', i);
        end
    end
    
    % Extract value
    target_value = target_node.splitValue;
    fprintf('Extracted from level %d: %s\n', target_level, target_value);
end

Critical Pattern 3: Memory-Efficient Plotting (Single Figure Reuse)
The Single Figure Strategy
Instead of creating multiple figures, reuse one figure for all plots:
% WRONG: Creates memory buildup
for i = 1:100
    figure();  % Creates 100 figure windows
    plot(data);
    saveas(gcf, sprintf('plot_%d.png', i));
end

% RIGHT: Memory efficient
plot_fig = figure(100);  % Create once
for i = 1:100
    figure(plot_fig);     % Reuse same figure
    clf;                  % Clear previous plot
    plot(data);
    saveas(plot_fig, sprintf('plot_%d.png', i));  % Save immediately
end

Integration with Analysis Functions:
% Create designated figure for entire analysis
filter_fig = figure(100);

% Navigate tree and analyze
for each_node = analysis_nodes
    % Use same figure for each analysis
    [results] = estimate_filter(..., true, ..., filter_fig);
    
    % Save immediately after plotting
    filename = buildFilename(node_metadata);
    saveas(filter_fig, [save_path filename]);
end

% Result: One figure window + all individual saved files

Critical Pattern 4: Systematic File Organization from Tree Metadata
Extract Organization Metadata from Tree
Use tree structure to automatically organize files:
function [save_path, filename] = buildFileInfo(leaf_node, splitter_map)
    % Extract organizational metadata from tree
    cell_type_node = leaf_node.parent.parent.parent.parent.parent;  % Level 1
    cell_node = leaf_node.parent.parent.parent;                     % Level 3  
    condition_node = leaf_node.parent;                              % Level 5
    
    % Get values
    cell_type = cell_type_node.splitValue;    % e.g., 'RGC\ON-parasol'
    cell_id = cell_node.splitValue;           % e.g., 'Cell3'
    condition = condition_node.splitValue;    % e.g., '90'
    
    % Clean for file system
    cell_type_clean = strrep(cell_type, '\', '/');  % 'RGC/ON-parasol'
    
    % Build systematic path
    save_path = [base_path cell_type_clean '/'];
    
    % Build systematic filename
    date_str = extractDate(leaf_node);  % From date level
    filename = sprintf('%s-%s-condition-%s.png', date_str, lower(cell_id), condition);
end

Complete Integration Example:
%% INTEGRATED: Navigation + Analysis + Figure Control + File Organization

% Create single figure for all analyses
analysis_fig = figure(100);
set(analysis_fig, 'Position', [100, 100, 1200, 800]);

% Navigate tree and perform analyses
for each_leaf_node = target_nodes
    try
        % Extract metadata from tree structure
        [save_path, filename] = buildFileInfo(each_leaf_node, splitter_info);
        
        % Create directory if needed
        if ~exist(save_path, 'dir')
            mkdir(save_path);
        end
        
        % Run analysis with controlled figure
        [results] = analysis_function(data, params, true, analysis_fig);
        
        % Save immediately after plotting
        saveas(analysis_fig, [save_path filename]);
        fprintf('Saved: %s\n', [save_path filename]);
        
        % Store results at tree node
        each_leaf_node.custom.put('results', riekesuite.util.toJavaMap(results));
        
    catch ME
        fprintf('Failed: %s\n', ME.message);
    end
end

Key Decision Points
Situation
Selection Strategy
Code Pattern
Need robust statistics
Most epochs
max_epochs = max(epoch_counts)
Testing specific conditions
Filter by value
if strcmp(splitValue, target)
Quality control
SNR threshold
if snr > threshold
Cell type analysis
Type matching
if ismember(cell_type, target_types)

Decision Trees
Tree Structure Decision
IF drug experiment → [cell_type, drug, concentration, time]
ELSE → [source, date, cell, protocol, condition]

Analysis Level Decision
IF comparing cell types → store at cell level
ELSE IF comparing conditions → store at condition level
ELSE IF population analysis → store at protocol level

Selection Criteria Decision
IF n_epochs > 10 AND snr > threshold → PROCESS
ELSE IF n_epochs > 5 AND critical_condition → PROCESS  
ELSE IF meets_specific_filter_criteria → PROCESS
ELSE → SKIP and LOG reason

Examples of filter criteria:
- Most epochs: max(epoch_counts)
- Specific condition: splitValue == 'Control'  
- Quality filter: splitValue < 0.1 (e.g., low noise)
- Cell type match: ismember(cell_type, target_types)
- Completeness filter: node.children.length == expected_count
- Multi-condition: strcmp(splitValue,'Control') || strcmp(splitValue,'Drug')

Core Workflow Implementation
Step 1: System Setup
% Initialize
loader = edu.washington.rieke.Analysis.getEntityLoader();
params = struct('Amp', 'Amp1', 'SamplingInterval', 0.0001);
analysis_log = {};
log_counter = 1;

% Master log
master_log = struct();
master_log.analysis_type = 'YOUR_ANALYSIS_NAME';
master_log.timestamp = datetime('now');
master_log.purpose = 'ANALYSIS_PURPOSE';
analysis_log{1} = master_log;
log_counter = 2;

Step 2: Data Loading and Tree Building
% Load data
list = loader.loadEpochList([dataFolder 'file.mat'], dataFolder);

% Define splits (CUSTOMIZE FOR YOUR EXPERIMENT)
tree_splits = {
    'cell.cellType',                    % Level 1: Cell type
    'protocolSettings(condition)',      % Level 2: Experimental condition  
    'protocolSettings(parameter)'       % Level 3: Parameter value
};

% Build tree
dateSplit = @(list)splitOnExperimentDate(list);
dateSplit_java = riekesuite.util.SplitValueFunctionAdapter.buildMap(list, dateSplit);
tree = riekesuite.analysis.buildTree(list, tree_splits);

% Interactive selection
gui = epochTreeGUI(tree);
node = gui.getSelectedEpochTreeNodes();
rootNode = node{1};

Step 3: INTEGRATED Navigation + Analysis Template (UPDATED)
%% INTEGRATED NAVIGATION, SELECTION & ANALYSIS
% CRITICAL: Navigation and analysis must be combined, not separate sections

for level1_idx = 1:rootNode.children.length
    level1_Node = rootNode.children.elements(level1_idx);
    level1_value = level1_Node.splitValue;  % NO char() conversion!
    
    for level2_idx = 1:level1_Node.children.length
        level2_Node = level1_Node.children.elements(level2_idx);
        level2_value = level2_Node.splitValue;  % NO char() conversion!
        
        % Navigate to target analysis level (e.g., find best condition)
        [target_node, selection_info] = findTargetNode(level2_Node);
        
        if ~isempty(target_node)
            fprintf('>>> ANALYZING: %s | %s <<<\n', level1_value, level2_value);
            
            try
                % IMMEDIATE ANALYSIS at target node
                EpochData = getSelectedData(target_node.epochList, params.Amp);
                Stimuli = getNoiseStm(target_node);  % or getStimulus(target_node)
                
                % Perform elementary analysis HERE
                results = performElementaryAnalysis(EpochData, Stimuli, params);
                results.level1_value = level1_value;
                results.level2_value = level2_value;
                results.selection_info = selection_info;
                
                % IMMEDIATE STORAGE at target node
                target_node.custom.put('results', riekesuite.util.toJavaMap(results));
                
                fprintf('SUCCESS: Analysis stored at target node\n');
                
                % Log success
                logSuccess(level1_value, level2_value, results);
                
            catch ME
                fprintf('FAILED: %s\n', ME.message);
                logError(level1_value, level2_value, ME);
            end
        else
            fprintf('SKIP: No suitable target node found\n');
        end
    end
end

Step 4: Selection Criteria Functions (UPDATED)
function [target_node, selection_info] = findTargetNode(parent_node)
    % Find the best node for analysis (e.g., most epochs within conditions)
    
    target_node = [];
    selection_info = struct();
    
    if parent_node.children.length == 0
        return;
    end
    
    % Count epochs for each child node
    epoch_counts = [];
    child_nodes = {};
    child_values = {};
    
    for child_idx = 1:parent_node.children.length
        child_node = parent_node.children.elements(child_idx);
        child_value = child_node.splitValue;  % NO char() conversion!
        n_epochs = child_node.epochList.length;
        
        epoch_counts(end+1) = n_epochs;
        child_nodes{end+1} = child_node;
        child_values{end+1} = child_value;
    end
    
    % Find node with most epochs
    [max_epochs, max_idx] = max(epoch_counts);
    
    if max_epochs > 0
        target_node = child_nodes{max_idx};
        selection_info.selected_value = child_values{max_idx};
        selection_info.n_epochs = max_epochs;
        selection_info.total_options = length(epoch_counts);
        selection_info.all_epoch_counts = epoch_counts;
        selection_info.selection_reason = 'Most epochs';
    end
end

function should_process = shouldProcess(node)
    % Get data quality metrics
    n_epochs = node.epochList.length;
    
    % Selection logic
    should_process = false;
    
    if n_epochs >= 10
        should_process = true;
    elseif n_epochs >= 5 && isTargetCondition(node)
        should_process = true;
    end
    
    % Log decision
    if ~should_process
        logSkip(node, n_epochs, 'insufficient_data');
    end
end

function is_target = isTargetCondition(node)
    % Example: check if this is a condition of interest
    condition = node.splitValue;  % NO char() conversion!
    target_conditions = {'drug', 'control', 'baseline'};
    
    % Handle different data types
    if isnumeric(condition)
        is_target = ismember(condition, [0, 1, 10, 50]);  % numeric targets
    else
        condition_str = char(condition);  % Convert only for string operations
        is_target = any(contains(condition_str, target_conditions));
    end
end

Step 5: Elementary Analysis Template (UPDATED)
function results = performElementaryAnalysis(EpochData, Stimuli, params)
    % Get data dimensions
    [n_trials, n_timepoints] = size(Stimuli);
    dt = params.SamplingInterval;
    
    % Concatenate all trials for analysis
    I_all = reshape(Stimuli', [], 1);     % Injected current
    Vm_all = reshape(EpochData', [], 1);  % Membrane voltage
    
    % VALIDATION CHECKPOINT 1: Data dimensions
    if length(Vm_all) ~= length(I_all)
        error('Voltage and current traces have different lengths');
    end
    
    % VALIDATION CHECKPOINT 2: Data quality
    if any(isnan(Vm_all)) || any(isnan(I_all))
        error('NaN values detected in data');
    end
    
    % PERFORM YOUR SPECIFIC ANALYSIS HERE
    % Example: Enhanced spike detection
    vm_thresh = -20;    % mV
    d2v_thresh = 50;    % Second derivative threshold
    search_back_ms = 2; % ms
    plot_flag = false;  % No plots during batch processing
    
    [elbow_indices, ~, ~, avg_spike_short, diagnostic_info] = ...
        detect_spike_initiation_elbow_v2(...
        Vm_all, dt, vm_thresh, d2v_thresh, search_back_ms, plot_flag, ...
        'elbow_thresh', -65, 'spike_thresh', -10, 'min_dv_thresh', 0.1, ...
        'time_to_peak_thresh', 1.5);
    
    % Linear filter estimation
    I_preprocessed = I_all - mean(I_all);
    Vm_preprocessed = Vm_all - mean(Vm_all);
    [filt, lag, Vm_pred, r] = estimate_filter_fft_trials_regularized(...
        I_preprocessed, Vm_preprocessed, dt, 50, true, 100, 1e-4, 5);
    
    % VALIDATION CHECKPOINT 3: Analysis results
    if isempty(elbow_indices)
        warning('No spikes detected');
    end
    
    % Structure results
    results = struct();
    
    % Basic metrics
    results.n_trials = n_trials;
    results.n_timepoints = n_timepoints;
    results.dt = dt;
    results.total_duration_s = length(Vm_all) * dt;
    
    % Spike analysis
    results.spike_indices = elbow_indices;
    results.spike_times_s = elbow_indices * dt;
    results.n_spikes = length(elbow_indices);
    results.firing_rate_Hz = length(elbow_indices) / (length(Vm_all) * dt);
    results.avg_spike_waveform = avg_spike_short;
    results.spike_diagnostics = diagnostic_info;
    
    % Linear filter
    results.linear_filter = filt;
    results.filter_lag = lag;
    results.filter_correlation = r;
    
    % Quality metrics
    results.snr = std(Vm_all) / std(Vm_all - Vm_pred);
    
    % Processing info
    results.analysis_timestamp = datetime('now');
    results.success = true;
    
    fprintf('Analysis complete: %d spikes (%.2f Hz), filter r=%.3f\n', ...
        results.n_spikes, results.firing_rate_Hz, results.filter_correlation);
end

Step 6: Population Analysis (Updated for correct splitValue handling)
function population_results = queryAndAnalyze(rootNode, analysis_specs)
    % Determine analysis type based on specs
    if isfield(analysis_specs, 'treatment_conditions')
        population_results = queryTreatmentTriplets(rootNode, analysis_specs);
    elseif length(analysis_specs.protocols) > 1
        population_results = queryCrossProtocolData(rootNode, analysis_specs);
    else
        population_results = querySingleAnalysis(rootNode, analysis_specs);
    end
end

function population_results = querySingleAnalysis(rootNode, analysis_specs)
    % SINGLE ANALYSIS (most common)
    all_results = {};
    cell_types = {};
    conditions = {};
    
    % Navigate and collect
    for level1_idx = 1:rootNode.children.length
        level1_Node = rootNode.children.elements(level1_idx);
        cell_type = level1_Node.splitValue;  % NO char() conversion initially
        
        for level2_idx = 1:level1_Node.children.length
            level2_Node = level1_Node.children.elements(level2_idx);
            condition = level2_Node.splitValue;  % NO char() conversion initially
            
            % Query stored results
            stored = level2_Node.custom.get('results');
            if ~isempty(stored)
                analysis = get(stored, 'analysis');
                all_results{end+1} = analysis;
                cell_types{end+1} = cell_type;
                conditions{end+1} = condition;
                fprintf('Collected: %s | %s\n', cell_type, condition);
            end
        end
    end
    
    population_results = analyzePopulation(all_results, cell_types, conditions);
end

Logging Functions (UPDATED)
Success Logging
function logSuccess(level1_value, level2_value, results)
    global analysis_log log_counter;
    
    log_entry = struct();
    log_entry.timestamp = datetime('now');
    log_entry.level = 'SUCCESS';
    log_entry.level1_value = level1_value;  % Store raw splitValue
    log_entry.level2_value = level2_value;  % Store raw splitValue
    log_entry.n_trials = results.n_trials;
    log_entry.n_spikes = results.n_spikes;
    log_entry.firing_rate_Hz = results.firing_rate_Hz;
    log_entry.filter_correlation = results.filter_correlation;
    log_entry.success = true;
    
    analysis_log{log_counter} = log_entry;
    log_counter = log_counter + 1;
end

Error Logging
function logError(level1_value, level2_value, ME)
    global analysis_log log_counter;
    
    log_entry = struct();
    log_entry.timestamp = datetime('now');
    log_entry.level = 'ERROR';
    log_entry.level1_value = level1_value;  % Store raw splitValue
    log_entry.level2_value = level2_value;  % Store raw splitValue
    log_entry.error_message = ME.message;
    log_entry.error_id = ME.identifier;
    log_entry.success = false;
    
    analysis_log{log_counter} = log_entry;
    log_counter = log_counter + 1;
end

Skip Logging
function logSkip(node, n_epochs, reason)
    global analysis_log log_counter;
    
    log_entry = struct();
    log_entry.timestamp = datetime('now');
    log_entry.level = 'SKIP';
    log_entry.condition = node.splitValue;  % Store raw splitValue
    log_entry.n_epochs = n_epochs;
    log_entry.skip_reason = reason;
    log_entry.success = false;
    
    analysis_log{log_counter} = log_entry;
    log_counter = log_counter + 1;
end

Validation Checkpoints
Checkpoint 1: After Tree Building
% Verify tree structure
expected_levels = 3;  % Adjust based on your splits
actual_levels = getTreeDepth(tree);
if actual_levels ~= expected_levels
    warning('Tree depth mismatch: expected %d, got %d', expected_levels, actual_levels);
end

% Check node counts
total_nodes = countNodes(tree);
fprintf('Tree built: %d total nodes\n', total_nodes);

Checkpoint 2: After Data Extraction
% Validate data dimensions
assert(size(Vm_all, 1) == size(I_all, 1), 'Voltage/current length mismatch');
assert(~any(isnan(Vm_all)), 'NaN values in voltage data');
assert(length(Vm_all) > 1000, 'Insufficient data points');

Checkpoint 3: After Analysis
% Validate results structure
required_fields = {'firing_rate_Hz', 'n_spikes'};
for i = 1:length(required_fields)
    assert(isfield(results, required_fields{i}), 'Missing field: %s', required_fields{i});
end
assert(~isnan(results.firing_rate_Hz), 'Primary metric is NaN');

Checkpoint 4: After Storage
% Verify storage/retrieval using correct key
test_retrieval = node.custom.get('results');
assert(~isempty(test_retrieval), 'Failed to store/retrieve results');

% Test field access
test_field = get(test_retrieval, 'firing_rate_Hz');
assert(~isempty(test_field), 'Failed to access stored field');

Summary Generation
AI-Readable Summary
function generateAISummary(analysis_log, population_results)
    % Count outcomes by cell type
    success_entries = analysis_log([analysis_log.success] == true);
    error_entries = analysis_log([analysis_log.success] == false);
    
    % Cell type counts from successful entries (handle splitValue correctly)
    if ~isempty(success_entries)
        level1_values = {success_entries.level1_value};
        unique_values = unique(level1_values);
        value_counts = struct();
        for i = 1:length(unique_values)
            val = unique_values{i};
            count = sum(strcmp(level1_values, val));
            % Create valid field name
            field_name = matlab.lang.makeValidName(char(val));
            value_counts.(field_name) = count;
        end
    else
        value_counts = struct();
        unique_values = {};
    end
    
    % Generate summary
    summary = struct();
    summary.analysis_outcome = struct();
    summary.analysis_outcome.total_processed = length(success_entries);
    summary.analysis_outcome.total_failed = length(error_entries);
    summary.analysis_outcome.total_skipped = sum(strcmp({analysis_log.level}, 'SKIP'));
    summary.analysis_outcome.success_rate = length(success_entries) / (length(success_entries) + length(error_entries)) * 100;
    
    summary.value_summary = value_counts;
    
    if exist('population_results', 'var') && ~isempty(population_results)
        summary.key_findings = struct();
        summary.key_findings.total_analyses = length(success_entries);
        if isfield(population_results, 'overall')
            summary.key_findings.mean_firing_rate = population_results.overall.mean_metric;
            summary.key_findings.std_firing_rate = population_results.overall.std_metric;
        end
    end
    
    % Save summary
    timestamp_str = datestr(now, 'yyyymmdd_HHMMSS');
    save(sprintf('ai_analysis_summary_%s.mat', timestamp_str), 'summary', 'analysis_log');
    
    % Print summary
    fprintf('\n=== AI ANALYSIS SUMMARY ===\n');
    fprintf('Success: %d | Failed: %d | Skipped: %d\n', ...
        summary.analysis_outcome.total_processed, ...
        summary.analysis_outcome.total_failed, ...
        summary.analysis_outcome.total_skipped);
    fprintf('Success Rate: %.1f%%\n', summary.analysis_outcome.success_rate);
    
    fprintf('\nValue Distribution:\n');
    for i = 1:length(unique_values)
        val = unique_values{i};
        field_name = matlab.lang.makeValidName(char(val));
        count = value_counts.(field_name);
        fprintf('  %s: %d\n', val, count);
    end
end

Common Failure Modes and Solutions
Error
Cause
Solution
Empty results from get()
Wrong storage level or key
Check node.custom.put() location and key name
Java conversion error
Wrong data type
Use riekesuite.util.toJavaMap() for storage
Index exceeds array
Missing children
Add if node.children.length > 0 check
NaN in analysis
Bad data quality
Add data validation before analysis
Memory error
Large datasets
Process in chunks, clear variables
Garbled splitValue display
Using char() incorrectly
Use splitValue directly for display
Separate navigation/analysis sections
Wrong workflow structure
Integrate navigation + analysis in one section
Dot indexing not supported
Wrong .parent navigation
Calculate correct levels back to target
Multiple figure windows
**### Essential Commands



% 1. LOAD
list = loader.loadEpochList(file, path);

% 2. BUILD TREE  # Riekesuite Workflow AI Manual

## Quick Reference for AI Systems

### Core Pattern (UPDATED)

LOAD → SPLIT → BUILD → NAVIGATE+ANALYZE+STORE → QUERY → SUMMARIZE

### Essential Commands
```matlab
% 1. LOAD
list = loader.loadEpochList(file, path);

% 2. BUILD TREE  
tree = riekesuite.analysis.buildTree(list, split_criteria);

% 3. STORE RESULTS (CRITICAL: Store your analysis struct directly)
% results = your elementary analysis struct (whatever you created)
target_node.custom.put('results', riekesuite.util.toJavaMap(results));

% 4. QUERY RESULTS
stored = target_node.custom.get('results');
field_data = get(stored, 'field_name');

% 5. LOG SUCCESS
log_entry.success = true;
log_entry.data_metrics = struct('n_cells', n, 'conditions', conditions);

Key Decision Points
Situation
Selection Strategy
Code Pattern
Need robust statistics
Most epochs
max_epochs = max(epoch_counts)
Testing specific conditions
Filter by value
if strcmp(splitValue, target)
Quality control
SNR threshold
if snr > threshold
Cell type analysis
Type matching
if ismember(cell_type, target_types)

Decision Trees
Tree Structure Decision
IF drug experiment → [cell_type, drug, concentration, time]
ELSE → [source, date, cell, protocol, condition]

Analysis Level Decision
IF comparing cell types → store at cell level
ELSE IF comparing conditions → store at condition level
ELSE IF population analysis → store at protocol level

Selection Criteria Decision
IF n_epochs > 10 AND snr > threshold → PROCESS
ELSE IF n_epochs > 5 AND critical_condition → PROCESS  
ELSE IF meets_specific_filter_criteria → PROCESS
ELSE → SKIP and LOG reason

Examples of filter criteria:
- Most epochs: max(epoch_counts)
- Specific condition: splitValue == 'Control'  
- Quality filter: splitValue < 0.1 (e.g., low noise)
- Cell type match: ismember(cell_type, target_types)
- Completeness filter: node.children.length == expected_count
- Multi-condition: strcmp(splitValue,'Control') || strcmp(splitValue,'Drug')

Core Workflow Implementation
Step 1: System Setup
% Initialize
loader = edu.washington.rieke.Analysis.getEntityLoader();
params = struct('Amp', 'Amp1', 'SamplingInterval', 0.0001);
analysis_log = {};
log_counter = 1;

% Master log
master_log = struct();
master_log.analysis_type = 'YOUR_ANALYSIS_NAME';
master_log.timestamp = datetime('now');
master_log.purpose = 'ANALYSIS_PURPOSE';
analysis_log{1} = master_log;
log_counter = 2;

Step 2: Data Loading and Tree Building
% Load data
list = loader.loadEpochList([dataFolder 'file.mat'], dataFolder);

% Define splits (CUSTOMIZE FOR YOUR EXPERIMENT)
tree_splits = {
    'cell.cellType',                    % Level 1: Cell type
    'protocolSettings(condition)',      % Level 2: Experimental condition  
    'protocolSettings(parameter)'       % Level 3: Parameter value
};

% Build tree
dateSplit = @(list)splitOnExperimentDate(list);
dateSplit_java = riekesuite.util.SplitValueFunctionAdapter.buildMap(list, dateSplit);
tree = riekesuite.analysis.buildTree(list, tree_splits);

% Interactive selection
gui = epochTreeGUI(tree);
node = gui.getSelectedEpochTreeNodes();
rootNode = node{1};

Step 3: INTEGRATED Navigation + Analysis Template (UPDATED)
%% INTEGRATED NAVIGATION, SELECTION & ANALYSIS
% CRITICAL: Navigation and analysis must be combined, not separate sections

for level1_idx = 1:rootNode.children.length
    level1_Node = rootNode.children.elements(level1_idx);
    level1_value = level1_Node.splitValue;  % NO char() conversion!
    
    for level2_idx = 1:level1_Node.children.length
        level2_Node = level1_Node.children.elements(level2_idx);
        level2_value = level2_Node.splitValue;  % NO char() conversion!
        
        % Navigate to target analysis level (e.g., find best condition)
        [target_node, selection_info] = findTargetNode(level2_Node);
        
        if ~isempty(target_node)
            fprintf('>>> ANALYZING: %s | %s <<<\n', level1_value, level2_value);
            
            try
                % IMMEDIATE ANALYSIS at target node
                EpochData = getSelectedData(target_node.epochList, params.Amp);
                Stimuli = getNoiseStm(target_node);  % or getStimulus(target_node)
                
                % Perform elementary analysis HERE
                results = performElementaryAnalysis(EpochData, Stimuli, params);
                results.level1_value = level1_value;
                results.level2_value = level2_value;
                results.selection_info = selection_info;
                
                % IMMEDIATE STORAGE at target node - store your results struct directly
                target_node.custom.put('results', riekesuite.util.toJavaMap(results));
                
                fprintf('SUCCESS: Analysis stored at target node\n');
                
                % Log success
                logSuccess(level1_value, level2_value, results);
                
            catch ME
                fprintf('FAILED: %s\n', ME.message);
                logError(level1_value, level2_value, ME);
            end
        else
            fprintf('SKIP: No suitable target node found\n');
        end
    end
end

Step 4: Selection Criteria Functions (UPDATED)
function [target_node, selection_info] = findTargetNode(parent_node)
    % Find the best node for analysis (e.g., most epochs within conditions)
    
    target_node = [];
    selection_info = struct();
    
    if parent_node.children.length == 0
        return;
    end
    
    % Count epochs for each child node
    epoch_counts = [];
    child_nodes = {};
    child_values = {};
    
    for child_idx = 1:parent_node.children.length
        child_node = parent_node.children.elements(child_idx);
        child_value = child_node.splitValue;  % NO char() conversion!
        n_epochs = child_node.epochList.length;
        
        epoch_counts(end+1) = n_epochs;
        child_nodes{end+1} = child_node;
        child_values{end+1} = child_value;
    end
    
    % Find node with most epochs
    [max_epochs, max_idx] = max(epoch_counts);
    
    if max_epochs > 0
        target_node = child_nodes{max_idx};
        selection_info.selected_value = child_values{max_idx};
        selection_info.n_epochs = max_epochs;
        selection_info.total_options = length(epoch_counts);
        selection_info.all_epoch_counts = epoch_counts;
        selection_info.selection_reason = 'Most epochs';
    end
end

function should_process = shouldProcess(node)
    % Get data quality metrics
    n_epochs = node.epochList.length;
    
    % Selection logic
    should_process = false;
    
    if n_epochs >= 10
        should_process = true;
    elseif n_epochs >= 5 && isTargetCondition(node)
        should_process = true;
    end
    
    % Log decision
    if ~should_process
        logSkip(node, n_epochs, 'insufficient_data');
    end
end

function is_target = isTargetCondition(node)
    % Example: check if this is a condition of interest
    condition = node.splitValue;  % NO char() conversion!
    target_conditions = {'drug', 'control', 'baseline'};
    
    % Handle different data types
    if isnumeric(condition)
        is_target = ismember(condition, [0, 1, 10, 50]);  % numeric targets
    else
        condition_str = char(condition);  % Convert only for string operations
        is_target = any(contains(condition_str, target_conditions));
    end
end

Step 5: Elementary Analysis Template (UPDATED)
function results = performElementaryAnalysis(EpochData, Stimuli, params)
    % Get data dimensions
    [n_trials, n_timepoints] = size(Stimuli);
    dt = params.SamplingInterval;
    
    % Concatenate all trials for analysis
    I_all = reshape(Stimuli', [], 1);     % Injected current
    Vm_all = reshape(EpochData', [], 1);  % Membrane voltage
    
    % VALIDATION CHECKPOINT 1: Data dimensions
    if length(Vm_all) ~= length(I_all)
        error('Voltage and current traces have different lengths');
    end
    
    % VALIDATION CHECKPOINT 2: Data quality
    if any(isnan(Vm_all)) || any(isnan(I_all))
        error('NaN values detected in data');
    end
    
    % PERFORM YOUR SPECIFIC ANALYSIS HERE
    % Example: Enhanced spike detection
    vm_thresh = -20;    % mV
    d2v_thresh = 50;    % Second derivative threshold
    search_back_ms = 2; % ms
    plot_flag = false;  % No plots during batch processing
    
    [elbow_indices, ~, ~, avg_spike_short, diagnostic_info] = ...
        detect_spike_initiation_elbow_v2(...
        Vm_all, dt, vm_thresh, d2v_thresh, search_back_ms, plot_flag, ...
        'elbow_thresh', -65, 'spike_thresh', -10, 'min_dv_thresh', 0.1, ...
        'time_to_peak_thresh', 1.5);
    
    % Linear filter estimation
    I_preprocessed = I_all - mean(I_all);
    Vm_preprocessed = Vm_all - mean(Vm_all);
    [filt, lag, Vm_pred, r] = estimate_filter_fft_trials_regularized(...
        I_preprocessed, Vm_preprocessed, dt, 50, true, 100, 1e-4, 5);
    
    % VALIDATION CHECKPOINT 3: Analysis results
    if isempty(elbow_indices)
        warning('No spikes detected');
    end
    
    % Structure results
    results = struct();
    
    % Basic metrics
    results.n_trials = n_trials;
    results.n_timepoints = n_timepoints;
    results.dt = dt;
    results.total_duration_s = length(Vm_all) * dt;
    
    % Spike analysis
    results.spike_indices = elbow_indices;
    results.spike_times_s = elbow_indices * dt;
    results.n_spikes = length(elbow_indices);
    results.firing_rate_Hz = length(elbow_indices) / (length(Vm_all) * dt);
    results.avg_spike_waveform = avg_spike_short;
    results.spike_diagnostics = diagnostic_info;
    
    % Linear filter
    results.linear_filter = filt;
    results.filter_lag = lag;
    results.filter_correlation = r;
    
    % Quality metrics
    results.snr = std(Vm_all) / std(Vm_all - Vm_pred);
    
    % Processing info
    results.analysis_timestamp = datetime('now');
    results.success = true;
    
    fprintf('Analysis complete: %d spikes (%.2f Hz), filter r=%.3f\n', ...
        results.n_spikes, results.firing_rate_Hz, results.filter_correlation);
end

Step 6: Population Analysis (Updated for correct splitValue handling)
function population_results = queryAndAnalyze(rootNode, analysis_specs)
    % Determine analysis type based on specs
    if isfield(analysis_specs, 'treatment_conditions')
        population_results = queryTreatmentTriplets(rootNode, analysis_specs);
    elseif length(analysis_specs.protocols) > 1
        population_results = queryCrossProtocolData(rootNode, analysis_specs);
    else
        population_results = querySingleAnalysis(rootNode, analysis_specs);
    end
end

function population_results = querySingleAnalysis(rootNode, analysis_specs)
    % SINGLE ANALYSIS (most common)
    all_results = {};
    cell_types = {};
    conditions = {};
    
    % Navigate and collect
    for level1_idx = 1:rootNode.children.length
        level1_Node = rootNode.children.elements(level1_idx);
        cell_type = level1_Node.splitValue;  % NO char() conversion initially
        
        for level2_idx = 1:level1_Node.children.length
            level2_Node = level1_Node.children.elements(level2_idx);
            condition = level2_Node.splitValue;  % NO char() conversion initially
            
            % Query stored results using standard key
            stored = level2_Node.custom.get('results');
            if ~isempty(stored)
                analysis = get(stored, 'analysis');
                all_results{end+1} = analysis;
                cell_types{end+1} = cell_type;
                conditions{end+1} = condition;
                fprintf('Collected: %s | %s\n', cell_type, condition);
            end
        end
    end
    
    population_results = analyzePopulation(all_results, cell_types, conditions);
end

Logging Functions (UPDATED)
Success Logging
function logSuccess(level1_value, level2_value, results)
    global analysis_log log_counter;
    
    log_entry = struct();
    log_entry.timestamp = datetime('now');
    log_entry.level = 'SUCCESS';
    log_entry.level1_value = level1_value;  % Store raw splitValue
    log_entry.level2_value = level2_value;  % Store raw splitValue
    log_entry.n_trials = results.n_trials;
    log_entry.n_spikes = results.n_spikes;
    log_entry.firing_rate_Hz = results.firing_rate_Hz;
    log_entry.filter_correlation = results.filter_correlation;
    log_entry.success = true;
    
    analysis_log{log_counter} = log_entry;
    log_counter = log_counter + 1;
end

Error Logging
function logError(level1_value, level2_value, ME)
    global analysis_log log_counter;
    
    log_entry = struct();
    log_entry.timestamp = datetime('now');
    log_entry.level = 'ERROR';
    log_entry.level1_value = level1_value;  % Store raw splitValue
    log_entry.level2_value = level2_value;  % Store raw splitValue
    log_entry.error_message = ME.message;
    log_entry.error_id = ME.identifier;
    log_entry.success = false;
    
    analysis_log{log_counter} = log_entry;
    log_counter = log_counter + 1;
end

Skip Logging
function logSkip(node, n_epochs, reason)
    global analysis_log log_counter;
    
    log_entry = struct();
    log_entry.timestamp = datetime('now');
    log_entry.level = 'SKIP';
    log_entry.condition = node.splitValue;  % Store raw splitValue
    log_entry.n_epochs = n_epochs;
    log_entry.skip_reason = reason;
    log_entry.success = false;
    
    analysis_log{log_counter} = log_entry;
    log_counter = log_counter + 1;
end

Validation Checkpoints
Checkpoint 1: After Tree Building
% Verify tree structure
expected_levels = 3;  % Adjust based on your splits
actual_levels = getTreeDepth(tree);
if actual_levels ~= expected_levels
    warning('Tree depth mismatch: expected %d, got %d', expected_levels, actual_levels);
end

% Check node counts
total_nodes = countNodes(tree);
fprintf('Tree built: %d total nodes\n', total_nodes);

Checkpoint 2: After Data Extraction
% Validate data dimensions
assert(size(Vm_all, 1) == size(I_all, 1), 'Voltage/current length mismatch');
assert(~any(isnan(Vm_all)), 'NaN values in voltage data');
assert(length(Vm_all) > 1000, 'Insufficient data points');

Checkpoint 3: After Analysis
% Validate results structure
required_fields = {'firing_rate_Hz', 'n_spikes'};
for i = 1:length(required_fields)
    assert(isfield(results, required_fields{i}), 'Missing field: %s', required_fields{i});
end
assert(~isnan(results.firing_rate_Hz), 'Primary metric is NaN');

Checkpoint 4: After Storage
% Verify storage/retrieval using correct key
test_retrieval = node.custom.get('results');
assert(~isempty(test_retrieval), 'Failed to store/retrieve results');

% Test field access
test_field = get(test_retrieval, 'firing_rate_Hz');
assert(~isempty(test_field), 'Failed to access stored field');

Summary Generation
AI-Readable Summary
function generateAISummary(analysis_log, population_results)
    % Count outcomes by cell type
    success_entries = analysis_log([analysis_log.success] == true);
    error_entries = analysis_log([analysis_log.success] == false);
    
    % Cell type counts from successful entries (handle splitValue correctly)
    if ~isempty(success_entries)
        level1_values = {success_entries.level1_value};
        unique_values = unique(level1_values);
        value_counts = struct();
        for i = 1:length(unique_values)
            val = unique_values{i};
            count = sum(strcmp(level1_values, val));
            % Create valid field name
            field_name = matlab.lang.makeValidName(char(val));
            value_counts.(field_name) = count;
        end
    else
        value_counts = struct();
        unique_values = {};
    end
    
    % Generate summary
    summary = struct();
    summary.analysis_outcome = struct();
    summary.analysis_outcome.total_processed = length(success_entries);
    summary.analysis_outcome.total_failed = length(error_entries);
    summary.analysis_outcome.total_skipped = sum(strcmp({analysis_log.level}, 'SKIP'));
    summary.analysis_outcome.success_rate = length(success_entries) / (length(success_entries) + length(error_entries)) * 100;
    
    summary.value_summary = value_counts;
    
    if exist('population_results', 'var') && ~isempty(population_results)
        summary.key_findings = struct();
        summary.key_findings.total_analyses = length(success_entries);
        if isfield(population_results, 'overall')
            summary.key_findings.mean_firing_rate = population_results.overall.mean_metric;
            summary.key_findings.std_firing_rate = population_results.overall.std_metric;
        end
    end
    
    % Save summary
    timestamp_str = datestr(now, 'yyyymmdd_HHMMSS');
    save(sprintf('ai_analysis_summary_%s.mat', timestamp_str), 'summary', 'analysis_log');
    
    % Print summary
    fprintf('\n=== AI ANALYSIS SUMMARY ===\n');
    fprintf('Success: %d | Failed: %d | Skipped: %d\n', ...
        summary.analysis_outcome.total_processed, ...
        summary.analysis_outcome.total_failed, ...
        summary.analysis_outcome.total_skipped);
    fprintf('Success Rate: %.1f%%\n', summary.analysis_outcome.success_rate);
    
    fprintf('\nValue Distribution:\n');
    for i = 1:length(unique_values)
        val = unique_values{i};
        field_name = matlab.lang.makeValidName(char(val));
        count = value_counts.(field_name);
        fprintf('  %s: %d\n', val, count);
    end
end

Common Failure Modes and Solutions
Error
Cause
Solution
Empty results from get()
Wrong storage level or key
Check node.custom.put() location and key name
Java conversion error
Wrong data type
Use riekesuite.util.toJavaMap() for storage
Index exceeds array
Missing children
Add if node.children.length > 0 check
NaN in analysis
Bad data quality
Add data validation before analysis
Memory error
Large datasets
Process in chunks, clear variables
Garbled splitValue display
Using char() incorrectly
Use splitValue directly for display
Separate navigation/analysis sections
Wrong workflow structure
Integrate navigation + analysis in one section

Quick Troubleshooting
% Debug tree structure
printTreeStructure(tree, 3);  % Print first 3 levels

% Check data availability
checkDataAvailability(node);

% Verify storage
testStorage(node);

% Validate results
validateResults(results);

% Debug splitValue issues
fprintf('splitValue class: %s\n', class(node.splitValue));
disp(node.splitValue);  % Display raw value

Critical AI Configuration Questions
BEFORE STARTING: AI Must Ask These Questions
Question 1: What Are Your Tree Splitters?
User will typically provide ready-made splitters - AI just needs to implement them.
Example user input:
tree_splits = {cellTypeSplitter_java, dateSplit_java, 'cell.label', 'protocolSettings(epochGroup:label)', 'protocolSettings(stimulusTag)'};

AI Implementation:
tree = riekesuite.analysis.buildTree(list, user_provided_splits);
gui = epochTreeGUI(tree);

Question 2: What Phase Are We In?
Phase A: Elementary Analysis Development
User says: "Help me debug this analysis function"
User says: "How do I extract data from this node?"
User says: "This spike detection isn't working"
AI Role: Help with individual analysis components, no workflow integration
Phase B: Workflow Integration ("Wrapping")
User says: "Wrap this analysis into the workflow"
User says: "Apply my analysis function across all cells"
User says: "Store these results at the cell level"
AI Role: Integrate tested analysis into systematic tree navigation
Phase C: Population Analysis & Visualization
User says: "Query the stored results and make population plots"
User says: "Generate summary statistics across conditions"
User says: "Make figures comparing cell types"
AI Role: Navigate tree, collect results, generate analysis/figures
Question 3: Strategy Confirmation (MANDATORY)
Before writing ANY code, AI must:
"Let me understand what you want to accomplish..."
"Here's my proposed approach: [outline strategy]"
"Does this approach sound right to you?"
Wait for explicit approval
Then implement approved strategy
CRITICAL IMPLEMENTATION RULES (UPDATED)
Rule 1: Code in Small Sections
Never write complete scripts at once
Break into logical sections with clear section breaks
Use proper MATLAB section syntax: %% Section Title
Wait for user feedback between sections
Example Approach:
%% Initialize Analysis
% Basic setup and tree building

%% INTEGRATED Navigation, Selection & Analysis  
% COMBINED: Tree navigation with immediate analysis at target nodes

%% Query and Summarize Results
% Population analysis and visualization

Rule 2: Correct MATLAB Syntax (UPDATED)
Use proper function calls: node.children.elements(idx) not node.children(idx)
Handle splitValue correctly: Use node.splitValue directly - NEVER use char() conversion for display
Proper cell array access: epochList.elements(1) for Java collections
Correct field access: protocolSettings.get('fieldName') for Java maps
Integration requirement: Combine navigation + analysis in single workflow section
Rule 3: Section-by-Section Development
Present one section at a time
Ask "Should I continue to the next section?"
Allow user to modify current section before proceeding
Build incrementally rather than all-at-once
Question 2: What Analysis Do You Want at the Leaf Nodes?
AI MUST ASK: "What specific analysis should I perform on each data node? Provide the exact analysis function and parameters."
AI MUST ALSO ASK: "Where do you want to store the results? (leaf level, cell level, protocol level, etc.) and what key names should I use?"
User will be very specific and provide:
Exact analysis function name
All required parameters
Expected output structure
Data extraction method
Storage location and key names
Example user specification:
Analysis: detect_spike_initiation_elbow_v2
Parameters: vm_thresh=-20, d2v_thresh=50, search_back_ms=2, plot_flag=false
Data Extraction: getSelectedData(epochList, 'Amp1') + getNoiseStm(node)
Storage: cell level, key='results_spikeAnalysis'
Output Structure: spike_data.elbow_indices, spike_data.threshold_voltages, etc.

Understanding Tree Structure and .splitValue (UPDATED)
What is .splitValue?
.splitValue contains the metadata value that was used to create each node in the tree hierarchy. When you build the tree with splitting criteria, each node stores the specific value that distinguishes it from its siblings.
CRITICAL: splitValue Handling Rules
✅ CORRECT:
freq_value = freqNode.splitValue;
fprintf('Frequency: %s\n', freq_value);

cell_name = cellNode.splitValue;
protocol_name = protocolNode.splitValue;
condition = conditionNode.splitValue;

❌ WRONG:
freq_value = char(freqNode.splitValue);  % Creates garbled characters!
fprintf('Frequency: %s\n', freq_value);

Examples of .splitValue Usage:
Tree Built With:
tree = riekesuite.analysis.buildTree(list, {
    'cell.cellType',                    % Level 1 split
    dateSplit_java,                     % Level 2 split  
    'cell.label',                       % Level 3 split
    'protocolID',                       % Level 4 split
    'protocolSettings(condition)'       % Level 5 split
});

Accessing .splitValue (CORRECT WAY):
% Navigate through tree levels
cellTypeNode = rootNode.children.elements(1);
cell_type = cellTypeNode.splitValue;                    % → 'RGC\ON-parasol'

dateNode = cellTypeNode.children.elements(1);  
date_str = dateNode.splitValue;                         % → '15-Dec-2024 14:30:25'

cellNode = dateNode.children.elements(1);
cell_label = cellNode.splitValue;                       % → 'c1'

protocolNode = cellNode.children.elements(1);
protocol_name = protocolNode.splitValue;                % → 'ExpandingSpots'

conditionNode = protocolNode.children.elements(1);
condition = conditionNode.splitValue;                   % → 'Control'

Common .splitValue Patterns:
Direct Access (UPDATED - NO char() needed)
cell_type = node.splitValue;                            % 'OFF-parasol'
protocol = node.splitValue;                             % 'ExpandingGratings' 
condition = node.splitValue;                            % 'Control'
frequency = node.splitValue;                            % 500 (Hz)
concentration = node.splitValue;                        % 20 (μM)

Selection Based on .splitValue (UPDATED):
% For string comparisons, convert only when needed
if strcmp(node.splitValue, 'Control')
    % Process control condition
end

% Filter by numeric criteria  
if isnumeric(node.splitValue) && node.splitValue < 0.1
    % Process low noise conditions
end

% Cell type matching (convert only for string operations)
if contains(char(node.splitValue), 'parasol')
    % Process parasol cells
end

Key Points (UPDATED):
NEVER use char() for display - splitValue is already display-ready
Use char() only for string operations like contains(), strcmp() when needed
splitValue contains the exact metadata that created the tree split
Use for filtering and selection during tree navigation
Essential for file naming and logging to identify conditions
CRITICAL ERROR FIXES
Issue 1: splitValue Display Problems
Problem: Using char(node.splitValue) corrupts numeric and special data types Solution: Use node.splitValue directly for display
Issue 2: Separate Navigation and Analysis Sections
Problem: Old manual suggested separate sections for navigation and analysis Solution: Integrate navigation + analysis in single workflow section
WRONG Pattern:
%% Section 1: Navigate and Find Nodes
% Just navigate and collect nodes

%% Section 2: Analyze Collected Nodes  
% Analyze nodes separately

CORRECT Pattern:
%% INTEGRATED Navigation, Selection & Analysis
% Navigate → Select → Analyze → Store → Move to next

This ensures proper context preservation and immediate result storage at the correct tree level.


