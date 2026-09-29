classdef epicTreeGUI < handle
    % EPICTREEGUI Interactive GUI for visualizing and analyzing epoch data
    %
    % Main GUI controller that integrates:
    %   - epicTreeTools (data organization)
    %   - epicGraphicalTree (tree visualization)
    %   - singleEpoch (epoch viewer)
    %
    % Usage:
    %   % Load data and build tree
    %   [data, ~] = loadEpicTreeData('data.mat');
    %   tree = epicTreeTools(data);
    %   tree.buildTreeWithSplitters({
    %       @epicTreeTools.splitOnCellType,
    %       @epicTreeTools.splitOnExperimentDate,
    %       'cellInfo.id'
    %   });
    %
    %   % Launch GUI with pre-built tree
    %   gui = epicTreeGUI(tree);
    %   gui = epicTreeGUI(tree, 'noEpochs');  % Hide individual epochs
    %
    % Layout:
    %   [40% Tree Browser] | [60% Viewer/Plotting]
    %
    % See also: epicTreeTools, epicGraphicalTree, getSelectedData, loadEpicTreeData

    properties
        % Data
        tree                    % epicTreeTools root node
        allEpochs               % Flat epoch list (cell array)
        h5File                  % H5 file path for lazy loading
        matFilePath = ''        % Path to source .mat file (for .ugm file discovery)
        loadedMask = []         % Selection mask loaded at startup (for close comparison)
        workspaceTags = []       % Validated UUID-based annotation exchange document
        workspaceTagsDirty = false
        workspaceTagProfile = ''
        workspaceTagAuthor = ''
        workspaceMaskPath = '' % Explicit bundle mask; never use global latest-file discovery

        % UI Components
        figure                  % Main figure handle
        treeBrowser             % struct: panel, graphTree
        plottingCanvas          % struct: panel, axes, infoTable

        % State
        showEpochs = true       % Show individual epochs in tree
        isBusy = false          % Busy flag
    end

    properties (Hidden = true)
        title = 'Epic Tree GUI'
        fontSize = 12
        xDivLeft = 0.4          % Tree panel width (40%)
    end

    methods
        function self = epicTreeGUI(treeObj, varargin)
            % Constructor - Accepts pre-built epicTreeTools object only
            %
            % Usage:
            %   % Build tree first
            %   [data, ~] = loadEpicTreeData('data.mat');
            %   tree = epicTreeTools(data);
            %   tree.buildTreeWithSplitters({@epicTreeTools.splitOnCellType, ...});
            %
            %   % Launch GUI
            %   gui = epicTreeGUI(tree);
            %   gui = epicTreeGUI(tree, 'noEpochs');  % Hide individual epochs
            %
            % This matches the legacy epochTreeGUI pattern.

            % Parse options
            if any(strcmpi(varargin, 'noEpochs'))
                self.showEpochs = false;
            end

            % Create figure
            self.figure = figure(...
                'Name', self.title, ...
                'NumberTitle', 'off', ...
                'MenuBar', 'none', ...
                'ToolBar', 'none', ...
                'Position', [100 100 1200 700], ...
                'CloseRequestFcn', @(src,evt) self.onClose(), ...
                'Visible', 'off');

            % Build UI components
            self.buildUIComponents();

            % Validate and set tree
            if nargin >= 1 && ~isempty(treeObj)
                if isa(treeObj, 'epicTreeTools')
                    % Pre-built tree passed in
                    self.tree = treeObj;
                    self.allEpochs = self.tree.allEpochs;

                    % Store .mat file path for .ugm file persistence
                    if ~isempty(self.tree.sourceFile)
                        self.matFilePath = self.tree.sourceFile;
                    end

                    % Store loaded mask for close comparison (build from current isSelected state)
                    self.loadedMask = self.buildCurrentMask();

                    % Exported epochs retain their own acquisition files. A
                    % legacy global directory must not override these paths
                    % or emit a false "data will not load" warning.
                    hasEpochSources = ~isempty(self.allEpochs) && all(cellfun(@(ep) ...
                        isfield(ep, 'h5_file') && ~isempty(ep.h5_file), self.allEpochs));
                    self.h5File = '';
                    if ~hasEpochSources
                        try
                            config = epicTreeConfig();
                            if isfield(config, 'h5_dir') && ~isempty(config.h5_dir)
                                % Get experiment name from first epoch
                                if ~isempty(self.allEpochs)
                                    ep = self.allEpochs{1};
                                    if isfield(ep, 'expInfo') && isfield(ep.expInfo, 'exp_name')
                                        expName = ep.expInfo.exp_name;
                                        self.h5File = fullfile(config.h5_dir, [expName '.h5']);

                                        % Verify H5 file exists
                                        if ~exist(self.h5File, 'file')
                                            warning('epicTreeGUI:H5NotFound', ...
                                                'H5 file not found: %s\nData will not load!', self.h5File);
                                            self.h5File = '';
                                        else
                                            fprintf('✓ H5 file found: %s\n', self.h5File);
                                        end
                                    end
                                end
                            else
                                warning('epicTreeGUI:NoH5Config', ...
                                    'H5 directory not configured! Run: epicTreeConfig(''h5_dir'', ''/path/to/h5'')');
                            end
                        catch ME
                            warning('epicTreeGUI:ConfigError', ...
                                'Error getting H5 config: %s', ME.message);
                        end
                    end

                    % Update tree browser
                    self.initTreeBrowser();

                    % Update title
                    nEpochs = length(self.allEpochs);
                    set(self.figure, 'Name', sprintf('%s - %d epochs', self.title, nEpochs));
                else
                    error('Input must be an epicTreeTools object. Use loadEpicTreeData() then build tree with buildTreeWithSplitters().');
                end
            end

            % Show figure
            set(self.figure, 'Visible', 'on');
        end

        function delete(self)
            % Destructor
            if ~isempty(self.figure) && ishandle(self.figure)
                delete(self.figure);
            end
        end


        function nodes = getSelectedEpochTreeNodes(self)
            % GETSELECTEDEPOCHTREENODES Get selected tree nodes
            %
            % Returns cell array of epicTreeTools nodes

            if isempty(self.treeBrowser) || isempty(self.treeBrowser.graphTree)
                nodes = {};
                return;
            end

            % Get selected epicGraphicalTreeNodes
            [graphNodes, ~] = self.treeBrowser.graphTree.getSelectedNodes();

            % Extract epicTreeTools nodes from userData
            nodes = cell(size(graphNodes));
            for ii = 1:length(graphNodes)
                if ~isempty(graphNodes{ii}) && ~isempty(graphNodes{ii}.userData)
                    nodes{ii} = graphNodes{ii}.userData;
                end
            end
        end

        function epochs = getSelectedEpochs(self)
            % GETSELECTEDEPOCHS Get epochs from selected tree nodes
            %
            % Returns cell array of epoch structs

            nodes = self.getSelectedEpochTreeNodes();

            epochs = {};
            for ii = 1:length(nodes)
                if ~isempty(nodes{ii})
                    nodeEpochs = nodes{ii}.getAllEpochs(true);  % Only selected
                    epochs = [epochs; nodeEpochs(:)];
                end
            end
        end
        function filepath = saveWorkspaceMask(self)
            % Save the working bundle mask that the generated command reloads.
            filepath = self.workspaceMaskPath;
            if isempty(filepath) || isempty(self.matFilePath) || ...
                    ~strcmp(filepath,fullfile(fileparts(self.matFilePath),'selection.ugm'))
                error('epicTreeGUI:InvalidWorkspaceMask','Workspace mask must be adjacent to its recordings.mat.');
            end
            ids=cellfun(@(epoch) epoch.h5_uuid,self.tree.allEpochs,'UniformOutput',false);
            previous=struct();
            if isfile(filepath)
                saved=load(filepath,'-mat');
                if ~isfield(saved,'ugm') || ~isstruct(saved.ugm) || ~isscalar(saved.ugm) || ...
                        ~isfield(saved.ugm,'epoch_h5_uuids') || ~iscellstr(saved.ugm.epoch_h5_uuids)
                    error('epicTreeGUI:InvalidWorkspaceMask','Existing workspace mask has no valid UUID membership.');
                end
                oldIds=cellfun(@(id) reshape(id,1,[]),saved.ugm.epoch_h5_uuids,'UniformOutput',false);
                if numel(oldIds)~=numel(ids) || numel(unique(oldIds))~=numel(ids) || ~isequal(sort(oldIds(:)),sort(ids(:)))
                    error('epicTreeGUI:InvalidWorkspaceMask','Existing mask belongs to different epochs; it was not overwritten.');
                end
                previous=saved.ugm;
            end
            temporary=[tempname(fileparts(filepath)) '.ugm'];
            try
                self.tree.saveUserMetadata(temporary);
                saved=load(temporary,'-mat'); ugm=saved.ugm;
                provenance={'project_uuid','protocol_uuid','dataset_uuid','export_uuid', ...
                    'query_sha256','recipe_sha256','source_scope_revision'};
                for i=1:numel(provenance)
                    key=provenance{i}; if isfield(previous,key),ugm.(key)=previous.(key);end
                end
                save(temporary,'ugm','-v7.3');
                [ok,message]=movefile(temporary,filepath,'f');
                if ~ok,error('epicTreeGUI:MaskSaveFailed','%s',message);end
            catch cause
                if isfile(temporary),delete(temporary);end
                rethrow(cause);
            end
            self.loadedMask=self.buildCurrentMask();
        end
    end

    methods
        function loadWorkspaceTags(self, path)
            % Validate against actual loaded identities, never labels or ordinals.
            if self.workspaceTagsDirty
                error('epicTreeGUI:UnsavedTags','Save current tag edits before loading another file.');
            end
            document = readWorkspaceTags(path);
            entries = document.entries;
            cellIds = self.workspaceTagIds('cell',self.allEpochs);
            epochIds = self.workspaceTagIds('epoch',self.allEpochs);
            keys = [strcat('cell:',cellIds);strcat('epoch:',epochIds)];
            known = containers.Map(keys,true(size(keys)));
            for k = 1:numel(entries)
                if iscell(entries), entry = entries{k}; else, entry = entries(k); end
                if ~isKey(known,[char(entry.target_kind) ':' char(entry.target_uuid)])
                    error('epicTreeGUI:UnknownTagTarget','Tag file contains a %s UUID outside this loaded tree: %s',entry.target_kind,entry.target_uuid);
                end
            end
            self.workspaceTags = document;
        end

        function count = tagWorkspaceIds(self, kind, identities, tag, profileUuid, authorName)
            % Public/scriptable counterpart of Tags > Tag selected epochs/cells.
            if isempty(self.workspaceTags)
                error('epicTreeGUI:NoTagRegistry','Load the exported annotations.json through the Tags menu first.');
            end
            known = self.workspaceTagIds(kind, self.allEpochs);
            if ischar(identities) || isstring(identities), identities = cellstr(identities); end
            if ~iscell(identities) || isempty(identities) || any(~ismember(identities,known))
                error('epicTreeGUI:UnknownTagTarget','Every target must be an exact UUID of the requested kind in this loaded tree.');
            end
            identities = unique(identities,'stable');
            document = workspaceTag(self.workspaceTags,kind,identities,tag,profileUuid,authorName);
            self.workspaceTags = document;
            self.workspaceTagsDirty = true;
            count = numel(identities);
        end

        function saveWorkspaceTags(self, path)
            if isempty(self.workspaceTags), error('epicTreeGUI:NoTagRegistry','Load a tag document first.'); end
            writeWorkspaceTags(self.workspaceTags,path);
            self.workspaceTagsDirty = false;
        end
    end

    %% Private Methods - UI Building
    methods (Access = private)
        function buildUIComponents(self)
            % Build all UI components

            % Initialize structs
            self.treeBrowser = struct();
            self.plottingCanvas = struct();

            % Create tree browser panel (left)
            self.buildTreeBrowserPanel();

            % Create plotting canvas (right)
            self.buildPlottingCanvas();

            % Create menu bar
            self.buildMenuBar();
        end

        function buildTreeBrowserPanel(self)
            % Build the tree browser panel (left side)

            % Main panel
            self.treeBrowser.panel = uipanel(self.figure, ...
                'Title', 'Epoch Tree', ...
                'FontSize', self.fontSize, ...
                'Units', 'normalized', ...
                'Position', [0 0 self.xDivLeft 1]);

            % Tree axes (takes up most of the panel)
            self.treeBrowser.treeAxes = axes('Parent', self.treeBrowser.panel, ...
                'Units', 'normalized', ...
                'Position', [0.02 0.12 0.96 0.87]);

            % Initialize epicGraphicalTree
            self.treeBrowser.graphTree = epicGraphicalTree(self.treeBrowser.treeAxes, 'Epochs');
            self.treeBrowser.graphTree.nodesSelectedFcn = @(tree) self.onTreeSelectionChanged(tree);
            self.treeBrowser.graphTree.nodesCheckedFcn = @(tree) self.onTreeCheckChanged(tree);

            % Button panel (bottom)
            self.treeBrowser.buttonPanel = uipanel(self.treeBrowser.panel, ...
                'Title', '', ...
                'BorderType', 'none', ...
                'Units', 'normalized', ...
                'Position', [0.02 0.01 0.96 0.10]);

            % Set Example button
            self.treeBrowser.setExampleBtn = uicontrol(self.treeBrowser.buttonPanel, ...
                'Style', 'pushbutton', ...
                'String', 'Set Example', ...
                'Units', 'normalized', ...
                'Position', [0.02 0.3 0.3 0.6], ...
                'Callback', @(src,evt) self.onSetExample());

            % Select All button
            self.treeBrowser.selectAllBtn = uicontrol(self.treeBrowser.buttonPanel, ...
                'Style', 'pushbutton', ...
                'String', 'Select All', ...
                'Units', 'normalized', ...
                'Position', [0.35 0.3 0.3 0.6], ...
                'Callback', @(src,evt) self.onSelectAll());

            % Clear Selection button
            self.treeBrowser.clearSelBtn = uicontrol(self.treeBrowser.buttonPanel, ...
                'Style', 'pushbutton', ...
                'String', 'Clear Sel', ...
                'Units', 'normalized', ...
                'Position', [0.68 0.3 0.3 0.6], ...
                'Callback', @(src,evt) self.onClearSelection());
        end

        function buildPlottingCanvas(self)
            % Build the plotting canvas (right side)

            % Main panel
            self.plottingCanvas.panel = uipanel(self.figure, ...
                'Title', 'Data Viewer', ...
                'FontSize', self.fontSize, ...
                'Units', 'normalized', ...
                'Position', [self.xDivLeft 0 (1 - self.xDivLeft) 1]);

            % Info table (top)
            self.plottingCanvas.infoTable = uitable(self.plottingCanvas.panel, ...
                'Units', 'normalized', ...
                'Position', [0.02 0.85 0.96 0.13], ...
                'ColumnName', {'Property', 'Value'}, ...
                'ColumnWidth', {120, 200}, ...
                'Data', {'Node', ''; 'Epochs', ''; 'Selected', ''});

            % Plot axes (bottom)
            self.plottingCanvas.axes = axes('Parent', self.plottingCanvas.panel, ...
                'Units', 'normalized', ...
                'Position', [0.1 0.1 0.85 0.70]);

            xlabel(self.plottingCanvas.axes, 'Time (ms)');
            ylabel(self.plottingCanvas.axes, 'Response');
        end

        function buildMenuBar(self)
            % Build menu bar

            % File menu
            fileMenu = uimenu(self.figure, 'Label', 'File');
            uimenu(fileMenu, 'Label', 'Export Selection...', 'Callback', @(src,evt) self.onExportSelection());
            uimenu(fileMenu, 'Label', 'Save Epoch Mask...', 'Callback', @(src,evt) self.onSaveEpochMask());
            uimenu(fileMenu, 'Label', 'Close', 'Callback', @(src,evt) self.onClose(), 'Separator', 'on');

            % Analysis menu
            tagsMenu = uimenu(self.figure,'Label','Tags');
            uimenu(tagsMenu,'Label','Load tag JSON...','Callback',@(src,evt) self.onLoadWorkspaceTags());
            uimenu(tagsMenu,'Label','Tag selected epochs...','Callback',@(src,evt) self.onTagWorkspaceSelection('epoch'));
            uimenu(tagsMenu,'Label','Tag cells of selected epochs...','Callback',@(src,evt) self.onTagWorkspaceSelection('cell'));
            uimenu(tagsMenu,'Label','Save tag JSON...','Callback',@(src,evt) self.onSaveWorkspaceTags());

            analysisMenu = uimenu(self.figure, 'Label', 'Analysis');
            uimenu(analysisMenu, 'Label', 'Mean Response Trace', 'Callback', @(src,evt) self.onAnalysisMeanTrace());
            uimenu(analysisMenu, 'Label', 'Response Amplitude', 'Callback', @(src,evt) self.onAnalysisAmplitude());

            % Help menu
            helpMenu = uimenu(self.figure, 'Label', 'Help');
            uimenu(helpMenu, 'Label', 'Keyboard Shortcuts', 'Callback', @(src,evt) self.showKeyboardHelp());
            uimenu(helpMenu, 'Label', 'About', 'Callback', @(src,evt) self.showAbout());
        end

        function initTreeBrowser(self)
            % Initialize tree browser from epicTreeTools

            if isempty(self.tree)
                return;
            end

            % Delete existing epicGraphicalTree (cleans up all widgets)
            if ~isempty(self.treeBrowser.graphTree)
                delete(self.treeBrowser.graphTree);
            end

            % Recreate epicGraphicalTree
            self.treeBrowser.graphTree = epicGraphicalTree(self.treeBrowser.treeAxes, 'Epochs');
            gTree = self.treeBrowser.graphTree;
            gTree.nodesSelectedFcn = @(tree) self.onTreeSelectionChanged(tree);
            gTree.nodesCheckedFcn = @(tree) self.onTreeCheckChanged(tree);

            % Build graphical tree from epicTreeTools
            self.marryEpochNodesToWidgets(self.tree, gTree.trunk);

            % Draw
            gTree.trunk.isExpanded = true;
            gTree.draw();
        end

        function marryEpochNodesToWidgets(self, epochNode, browserNode)
            % Recursively create epicGraphicalTreeNodes for epicTreeTools nodes

            gTree = self.treeBrowser.graphTree;

            % Set browser node properties
            browserNode.userData = epochNode;

            % Get display name
            if epochNode.hasCustom('workspaceValueLabel') && epochNode.hasCustom('workspaceFieldLabel')
                browserNode.name = sprintf('%s: %s',epochNode.getCustom('workspaceFieldLabel'),epochNode.getCustom('workspaceValueLabel'));
            elseif ~isempty(epochNode.splitValue)
                if isnumeric(epochNode.splitValue)
                    browserNode.name = sprintf('%s = %g', epochNode.splitKey, epochNode.splitValue);
                elseif ischar(epochNode.splitValue)
                    if startsWith(epochNode.splitKey, 'workspaceGrouping.')
                        % Canonical JSON is a typed value, not a dotted class name.
                        % Preserve decimals, arrays and quoted strings verbatim.
                        displayValue = epochNode.splitValue;
                    else
                        displayValue = self.abbreviateProtocolName(epochNode.splitValue);
                    end
                    browserNode.name = sprintf('%s', displayValue);
                else
                    displayValue = self.abbreviateProtocolName(char(string(epochNode.splitValue)));
                    browserNode.name = displayValue;
                end
            else
                browserNode.name = 'Root';
            end

            % Add epoch count
            nEpochs = epochNode.epochCount();
            browserNode.name = sprintf('%s (%d)', browserNode.name, nEpochs);

            % Set check state from custom property
            browserNode.isChecked = epochNode.custom.isSelected;

            % Handle example nodes (red background)
            if epochNode.custom.isExample
                browserNode.textBackgroundColor = [1 0.8 0.8];
            end

            % Recurse on children OR create individual epoch nodes
            if ~epochNode.isLeaf
                % Internal node - recurse on children
                for ii = 1:length(epochNode.children)
                    childEpoch = epochNode.children{ii};
                    childBrowser = gTree.newNode(browserNode, '');
                    self.marryEpochNodesToWidgets(childEpoch, childBrowser);
                end
            elseif self.showEpochs && ~isempty(epochNode.epochList)
                % Leaf node - create individual epoch widgets (legacy behavior)
                epochs = epochNode.epochList;
                for ii = 1:length(epochs)
                    ep = epochs{ii};

                    % Create epoch widget
                    epochWidget = gTree.newNode(browserNode, '');
                    epochWidget.userData = ep;  % Store epoch struct directly, not tree node

                    % Set selection state
                    if isfield(ep, 'isSelected') && ~isempty(ep.isSelected)
                        epochWidget.isChecked = ep.isSelected;
                    else
                        epochWidget.isChecked = true;
                    end

                    % Format name: "#N: date/time"
                    epochWidget.name = self.formatEpochName(ii, ep);

                    % Pink background for individual epochs
                    epochWidget.textColor = [0 0 0];
                    epochWidget.textBackgroundColor = [1 .85 .85];
                end
            end
        end
    end

    %% Private Methods - Callbacks
    methods (Access = private)
        function onClose(self)
            if self.workspaceTagsDirty
                choice = questdlg('Save edited tags as a JSON for import back into the workspace?', 'Unsaved tags', 'Save', 'Discard', 'Cancel', 'Save');
                if strcmp(choice,'Save')
                    if ~self.onSaveWorkspaceTags(), return; end
                elseif ~strcmp(choice,'Discard')
                    return;
                end
            end
            % Close handler: compare current selection to loaded mask, prompt to save changes
            try
                % Build current mask from isSelected flags (one-time)
                currentMask = self.buildCurrentMask();

                % Compare to loaded mask
                if ~isempty(self.loadedMask) && ~isempty(currentMask)
                    % Check if masks differ
                    if length(currentMask) == length(self.loadedMask)
                        if ~isequal(currentMask, self.loadedMask)
                            % Selection changed - prompt user
                            choice = questdlg(...
                                'Selection state has changed since loading. Update mask with session changes?', ...
                                'Save Changes?', ...
                                'Update Mask', 'Discard Changes', 'Cancel', ...
                                'Update Mask');

                            switch choice
                                case 'Update Mask'
                                    % Save to latest .ugm or create new if none exists
                                    if ~isempty(self.workspaceMaskPath)
                                        self.saveWorkspaceMask();
                                    elseif ~isempty(self.matFilePath)
                                        latestUGM = epicTreeTools.findLatestUGM(self.matFilePath);
                                        if isempty(latestUGM)
                                            % Create new
                                            filepath = epicTreeTools.generateUGMFilename(self.matFilePath);
                                            self.tree.saveUserMetadata(filepath);
                                        else
                                            % Update latest
                                            self.tree.saveUserMetadata(latestUGM);
                                        end
                                    end
                                    % Continue closing
                                case 'Discard Changes'
                                    % Continue closing without saving
                                case {'Cancel',''}
                                    % Don't close
                                    return;
                            end
                        end
                    end
                end
            catch ME
                if ~isempty(self.workspaceMaskPath)
                    errordlg(sprintf('Mask could not be saved. The window remains open.\n%s',ME.message),'Save mask failed');
                    return;
                end
                warning('epicTreeGUI:onClose', ...
                    'Error during close handler: %s. Closing without saving.', ME.message);
            end

            % Always close figure, even if save logic failed
            delete(self.figure);
        end



        function onTreeSelectionChanged(self, ~)
            % Handle tree node selection change

            % Get selected graphical nodes
            if isempty(self.treeBrowser) || isempty(self.treeBrowser.graphTree)
                return;
            end

            [graphNodes, ~] = self.treeBrowser.graphTree.getSelectedNodes();
            if isempty(graphNodes) || isempty(graphNodes{1})
                return;
            end

            % Check userData type
            userData = graphNodes{1}.userData;

            if isa(userData, 'epicTreeTools')
                % Tree node clicked

                % Performance optimization: Navigate to first single epoch
                % Find first leaf node
                leaves = userData.leafNodes();
                if ~isempty(leaves)
                    firstLeaf = leaves{1};
                    % Get first epoch from that leaf
                    if ~isempty(firstLeaf.epochList)
                        firstEpoch = firstLeaf.epochList{1};
                        fprintf('Note: Showing first epoch from node "%s"\n', ...
                            string(userData.splitValue));
                        % Plot single epoch
                        self.updateInfoTableForEpoch(firstEpoch);
                        self.plotSingleEpoch(firstEpoch);
                        return;
                    end
                end

                % Fallback: if no epochs found, show node info
                self.updateInfoTable(userData);
                self.plotNodeData(userData);

            elseif isstruct(userData)
                % Individual epoch - display single epoch
                self.updateInfoTableForEpoch(userData);
                self.plotSingleEpoch(userData);
            end
        end

        function onTreeCheckChanged(self, ~)
            % Handle check/selection change

            % Sync check state to epicTreeTools nodes or individual epochs
            gTree = self.treeBrowser.graphTree;
            for ii = 1:length(gTree.nodeList)
                gNode = gTree.nodeList{ii};
                if ~isempty(gNode.userData)
                    if isa(gNode.userData, 'epicTreeTools')
                        % Tree node - update custom flag
                        gNode.userData.custom.isSelected = gNode.isChecked;
                        % Also update epochs if leaf
                        if gNode.userData.isLeaf
                            gNode.userData.setSelected(gNode.isChecked, false);
                        end
                    elseif isstruct(gNode.userData)
                        % Individual epoch - update isSelected field
                        gNode.userData.isSelected = gNode.isChecked;
                    end
                end
            end
        end

        function onSetExample(self)
            % Toggle example flag on selected nodes

            nodes = self.getSelectedEpochTreeNodes();
            for ii = 1:length(nodes)
                if ~isempty(nodes{ii})
                    nodes{ii}.custom.isExample = ~nodes{ii}.custom.isExample;
                end
            end
            self.initTreeBrowser();
        end

        function onSelectAll(self)
            % Select all epochs

            if ~isempty(self.tree)
                self.tree.setSelected(true, true);
                self.initTreeBrowser();
            end
        end

        function onClearSelection(self)
            % Clear all selections

            if ~isempty(self.tree)
                self.tree.setSelected(false, true);
                self.initTreeBrowser();
            end
        end

        function identities = workspaceTagIds(~,kind,epochs)
            identities = cell(numel(epochs),1);
            for k = 1:numel(epochs)
                ep = epochs{k};
                if strcmp(kind,'epoch') && isfield(ep,'h5_uuid')
                    value = ep.h5_uuid;
                elseif strcmp(kind,'cell') && isfield(ep,'cellInfo') && isfield(ep.cellInfo,'h5_uuid')
                    value = ep.cellInfo.h5_uuid;
                else
                    error('epicTreeGUI:MissingTagIdentity','Loaded epochs need exact cell and epoch H5 UUIDs; labels and positions cannot be used.');
                end
                value = char(string(value));
                if isempty(regexp(value,'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$','once'))
                    error('epicTreeGUI:InvalidTagIdentity','Loaded data contains a noncanonical tag identity.');
                end
                identities{k} = value;
            end
            identities = unique(identities,'stable');
        end

        function onLoadWorkspaceTags(self)
            [file,path] = uigetfile('*.json','Load exported tag JSON');
            if isequal(file,0),return;end
            try
                self.loadWorkspaceTags(fullfile(path,file));
                msgbox('Tag identities verified against this loaded tree. Use Tags to edit or save annotations.','Tags loaded');
            catch cause
                errordlg(cause.message,'Tag import failed');
            end
        end

        function onTagWorkspaceSelection(self,kind)
            try
                if isempty(self.workspaceTags)
                    adjacent = fullfile(fileparts(self.matFilePath),'annotations.json');
                    if isfile(adjacent),self.loadWorkspaceTags(adjacent);else,self.onLoadWorkspaceTags();end
                    if isempty(self.workspaceTags),return;end
                end
                identities = self.workspaceTagIds(kind,self.getSelectedEpochs());
                if isempty(identities),msgbox('Select epochs in the tree first.','Tag selection');return;end
                answer = inputdlg({'Tag text','Author name'},sprintf('Tag %d exact %s UUIDs',numel(identities),kind),[1 65],{'',self.workspaceTagAuthor});
                if isempty(answer),return;end
                tag = strtrim(answer{1});author = strtrim(answer{2});
                if isempty(tag)||isempty(author),error('epicTreeGUI:MissingTagText','Tag and author name are required.');end
                if isempty(self.workspaceTagProfile)||~strcmp(author,self.workspaceTagAuthor)
                    profile = char(java.util.UUID.randomUUID());
                else
                    profile = self.workspaceTagProfile;
                end
                count = self.tagWorkspaceIds(kind,identities,tag,profile,author);
                self.workspaceTagProfile = profile;self.workspaceTagAuthor = author;
                msgbox(sprintf('Added tag to %d %s identities. Save tag JSON, then import it into the web workspace.',count,kind),'Tags updated');
            catch cause
                errordlg(cause.message,'Tag update failed');
            end
        end

        function saved = onSaveWorkspaceTags(self)
            saved = false;
            if isempty(self.workspaceTags),errordlg('Load an exported tag document first.','No tags loaded');return;end
            [file,path] = uiputfile('*.json','Save reviewed tags','tags-reviewed.json');
            if isequal(file,0),return;end
            try
                self.saveWorkspaceTags(fullfile(path,file));
                saved=true;
            catch cause
                errordlg(cause.message,'Tag save failed');
            end
        end

        function onExportSelection(self)
            % Export selected epochs

            epochs = self.getSelectedEpochs();
            if isempty(epochs)
                msgbox('No epochs selected', 'Export');
                return;
            end

            [file, path] = uiputfile('*.mat', 'Export Selected Epochs');
            if file ~= 0
                selectedEpochs = epochs;
                save(fullfile(path, file), 'selectedEpochs');
                msgbox(sprintf('Exported %d epochs', length(epochs)), 'Export');
            end
        end

        function onSaveEpochMask(self)
            % Save current selection state to .ugm file

            if ~isempty(self.workspaceMaskPath)
                try
                    filepath=self.saveWorkspaceMask();
                    msgbox(sprintf('Workspace mask saved to:\n%s\nThe generated command will reload these selections.',filepath),'Epoch Mask Saved');
                catch cause
                    errordlg(cause.message,'Save mask failed');
                end
                return;
            end

            % Validate we have data and path
            if isempty(self.tree) || isempty(self.tree.allEpochs)
                errordlg('No data loaded.', 'Save Epoch Mask');
                return;
            end

            if isempty(self.matFilePath)
                % Ask user to specify the .mat file path
                [file, path] = uigetfile('*.mat', 'Select the source .mat file for this dataset');
                if file == 0
                    return;  % User cancelled
                end
                self.matFilePath = fullfile(path, file);
                self.tree.sourceFile = self.matFilePath;
            end

            % Find existing .ugm files
            latestUGM = epicTreeTools.findLatestUGM(self.matFilePath);

            if isempty(latestUGM)
                % No existing files - create new
                filepath = epicTreeTools.generateUGMFilename(self.matFilePath);
                self.tree.saveUserMetadata(filepath);

                % Update loadedMask to current state (for close comparison)
                self.loadedMask = self.buildCurrentMask();

                msgbox(sprintf('Selection mask saved to:\n%s', filepath), 'Epoch Mask Saved');
            else
                % Existing files found - ask user
                % Use questdlg for broader MATLAB compatibility (works pre-R2020a too)
                choice = questdlg(...
                    sprintf('Found existing selection file:\n%s\n\nReplace it or create a new one?', latestUGM), ...
                    'Save Epoch Mask', ...
                    'Replace Latest', 'Create New', 'Cancel', ...
                    'Create New');

                switch choice
                    case 'Replace Latest'
                        self.tree.saveUserMetadata(latestUGM);

                        % Update loadedMask to current state
                        self.loadedMask = self.buildCurrentMask();

                        msgbox(sprintf('Selection mask updated:\n%s', latestUGM), 'Epoch Mask Saved');
                    case 'Create New'
                        filepath = epicTreeTools.generateUGMFilename(self.matFilePath);
                        self.tree.saveUserMetadata(filepath);

                        % Update loadedMask to current state
                        self.loadedMask = self.buildCurrentMask();

                        msgbox(sprintf('Selection mask saved to:\n%s', filepath), 'Epoch Mask Saved');
                    case 'Cancel'
                        % Do nothing
                end
            end
        end

        function onAnalysisMeanTrace(self)
            % Compute and plot mean response trace

            nodes = self.getSelectedEpochTreeNodes();
            if isempty(nodes) || isempty(nodes{1})
                msgbox('Select a tree node first', 'Analysis');
                return;
            end

            node = nodes{1};
            try
                [data, ~, fs] = epicTreeTools.getSelectedData(node, 'Amp1', self.h5File);
            catch cause
                self.showDataError(cause); return;
            end

            if isempty(data)
                msgbox('No response data available', 'Analysis');
                return;
            end

            % Convert to double and ensure fs is valid
            data = double(data);
            fs = double(fs);
            if isempty(fs) || fs == 0
                fs = 10000;  % Default sample rate
            end

            % Compute mean and SEM
            meanTrace = mean(data, 1);
            semTrace = std(data, [], 1) / sqrt(size(data, 1));
            t = (0:length(meanTrace)-1) / fs * 1000;

            % Plot
            ax = self.plottingCanvas.axes;
            cla(ax);
            hold(ax, 'on');
            fill(ax, [t fliplr(t)], [meanTrace-semTrace fliplr(meanTrace+semTrace)], ...
                [0.8 0.8 1], 'EdgeColor', 'none', 'FaceAlpha', 0.5);
            plot(ax, t, meanTrace, 'b', 'LineWidth', 2);
            hold(ax, 'off');
            xlabel(ax, 'Time (ms)');
            ylabel(ax, 'Response');
            title(ax, sprintf('Mean Response (n=%d)', size(data,1)));
        end

        function onAnalysisAmplitude(self)
            msgbox('Amplitude analysis not yet implemented', 'Analysis');
        end

        function updateInfoTable(self, node)
            % Update info table for selected tree node

            nEpochs = node.epochCount();
            nSelected = node.selectedCount();

            % Convert splitValue to char (table requires char, not string objects)
            if isempty(node.splitValue)
                valueStr = '';
            elseif isnumeric(node.splitValue)
                valueStr = sprintf('%g', node.splitValue);
            elseif ischar(node.splitValue)
                valueStr = node.splitValue;
            else
                valueStr = char(string(node.splitValue));
            end

            fieldName=node.splitKey;
            if node.hasCustom('workspaceFieldLabel'),fieldName=node.getCustom('workspaceFieldLabel');end
            if node.hasCustom('workspaceValueLabel'),valueStr=node.getCustom('workspaceValueLabel');end
            data = {
                'Node', fieldName;
                'Value', valueStr;
                'Epochs', sprintf('%d', nEpochs);
                'Selected', sprintf('%d', nSelected)
            };

            set(self.plottingCanvas.infoTable, 'Data', data);
        end

        function updateInfoTableForEpoch(self, epoch)
            % Update info table for selected individual epoch

            % Extract epoch metadata
            if isfield(epoch, 'start_time') && ~isempty(epoch.start_time)
                dateStr = char(epoch.start_time);
            elseif isfield(epoch, 'startTime') && ~isempty(epoch.startTime)
                dateStr = char(epoch.startTime);
            elseif isfield(epoch, 'expInfo') && isfield(epoch.expInfo, 'date')
                dateStr = epoch.expInfo.date;
            else
                dateStr = 'Unknown';
            end

            if isfield(epoch, 'isSelected')
                isSelected = logical(epoch.isSelected);
            else
                isSelected = true;
            end

            % Get protocol name
            if isfield(epoch, 'blockInfo') && isfield(epoch.blockInfo, 'protocol_name') && ~isempty(epoch.blockInfo.protocol_name)
                protocol = epoch.blockInfo.protocol_name;
            elseif isfield(epoch, 'protocolSettings') && isfield(epoch.protocolSettings, 'protocolID')
                protocol = epoch.protocolSettings.protocolID;
            elseif isfield(epoch, 'parameters') && isfield(epoch.parameters, 'protocol')
                protocol = epoch.parameters.protocol;
            else
                protocol = 'Unknown';
            end

            data = {
                'Type', 'Single Epoch';
                'Date', dateStr;
                'Protocol', char(protocol);
                'Selected', char(string(isSelected))
            };

            set(self.plottingCanvas.infoTable, 'Data', data);
        end

        function showDataError(self,cause)
            ax=self.plottingCanvas.axes;
            cla(ax); hold(ax,'off'); title(ax,'Data unavailable');
            text(ax,0.02,0.5,sprintf('No trace displayed.\n%s',cause.message), ...
                'Units','normalized','Interpreter','none','HorizontalAlignment','left');
        end

        function plotNodeData(self, node)
            % Plot data for selected tree node (aggregated epochs)

            ax = self.plottingCanvas.axes;

            % Get selected data (pass H5 file for lazy loading)
            try
                [data, ~, fs] = epicTreeTools.getSelectedData(node, 'Amp1', self.h5File);
            catch cause
                self.showDataError(cause); return;
            end

            if isempty(data)
                cla(ax);
                text(ax, 0.5, 0.5, 'No response data', ...
                    'HorizontalAlignment', 'center', 'Units', 'normalized');
                return;
            end

            % Convert to double and ensure fs is valid
            data = double(data);
            fs = double(fs);
            if isempty(fs) || fs == 0
                fs = 10000;  % Default sample rate
            end

            % Plot all traces
            cla(ax);
            hold(ax, 'on');
            t = (0:size(data,2)-1) / fs * 1000;
            for ii = 1:min(size(data,1), 20)  % Limit to 20 traces
                plot(ax, t, data(ii,:), 'Color', [0.7 0.7 0.7]);
            end
            plot(ax, t, mean(data,1), 'k', 'LineWidth', 2);
            hold(ax, 'off');

            xlabel(ax, 'Time (ms)');
            ylabel(ax, 'Response');
            title(ax, sprintf('%d epochs', size(data,1)));
        end

        function plotSingleEpoch(self, epoch)
            % Plot data for a single epoch (lazy loaded from H5)

            ax = self.plottingCanvas.axes;
            cla(ax);

            try
                % Use getSelectedData for single epoch (lazy loads from H5)
                epochList = {epoch};
                [data, ~, fs] = epicTreeTools.getSelectedData(epochList, 'Amp1', self.h5File);

                if isempty(data)
                    text(ax, 0.5, 0.5, 'No response data', ...
                        'HorizontalAlignment', 'center', 'Units', 'normalized');
                    return;
                end

                % Convert to double and ensure fs is valid
                data = double(data(:)');  % Ensure row vector of doubles
                fs = double(fs);
                if isempty(fs) || fs == 0
                    fs = 10000;  % Default sample rate
                end

                % Plot single trace
                t = (0:length(data)-1) / fs * 1000;  % Convert to ms
                plot(ax, t, data, 'b', 'LineWidth', 1.5);

                xlabel(ax, 'Time (ms)');
                responseLabel = 'Amp1';
                if isfield(epoch, 'responses')
                    responses = epoch.responses;
                    if isstruct(responses), responses = num2cell(responses); end
                    for ii = 1:numel(responses)
                        response = responses{ii};
                        if isfield(response, 'device_name') && strcmp(response.device_name, 'Amp1') && ...
                                isfield(response, 'units') && ~isempty(response.units)
                            responseLabel = sprintf('Amp1 (%s)', char(response.units));
                            break;
                        end
                    end
                end
                ylabel(ax, responseLabel);
                title(ax, 'Single Epoch');

            catch ME
                self.showDataError(ME);
            end
        end

        function showKeyboardHelp(self)
            msg = sprintf([...
                'Keyboard Shortcuts:\n\n' ...
                'Up/Down Arrow - Navigate tree\n' ...
                'Left Arrow - Collapse node\n' ...
                'Right Arrow - Expand node\n' ...
                'F or Space - Toggle selection\n']);
            msgbox(msg, 'Keyboard Shortcuts');
        end

        function showAbout(self)
            msg = sprintf([...
                'Epic Tree GUI v2.0\n\n' ...
                'Pure MATLAB epoch tree browser.\n\n' ...
                'Based on legacy Rieke Lab tools.']);
            msgbox(msg, 'About');
        end

        function shortName = abbreviateProtocolName(~, fullName)
            % ABBREVIATEPROTOCOLNAME Shorten long protocol names for display
            %
            % Converts:
            %   'edu.washington.riekelab.protocols.SingleSpot'  -> 'SingleSpot'
            %   'edu.washington.riekelab.turner.protocols.Foo'  -> 'Foo'
            %
            % Max length: 40 characters (truncate with '...')

            if ~ischar(fullName) && ~isstring(fullName)
                shortName = char(fullName);
                return;
            end

            fullName = char(fullName);

            % Only a protocol namespace is eligible. Decimal values and other
            % metadata strings must not be mistaken for Java class names.
            shortName = fullName;
            if contains(fullName, '.protocols.') && ...
                    ~isempty(regexp(fullName, '^[A-Za-z_]\w*(\.[A-Za-z_]\w*)+$', 'once'))
                parts = strsplit(fullName, '.');
                shortName = parts{end};
            end

            % Truncate if still too long
            maxLen = 40;
            if length(shortName) > maxLen
                shortName = [shortName(1:maxLen-3) '...'];
            end
        end

        function name = formatEpochName(~, index, epoch)
            % FORMATEPOCHNAME Format epoch display name
            %
            % Legacy format: "#N: YYYY-MM-DD HH:MM:SS"
            % Example: "  1: 2025-12-02 10:15:30"

            % Try to extract date/time from epoch
            if isfield(epoch, 'start_time') && ~isempty(epoch.start_time)
                dateStr = char(epoch.start_time);
            elseif isfield(epoch, 'expInfo') && isfield(epoch.expInfo, 'date')
                dateStr = epoch.expInfo.date;
            elseif isfield(epoch, 'startTime')
                dateStr = epoch.startTime;
            else
                dateStr = '';
            end

            % Format name
            if ~isempty(dateStr)
                name = sprintf('%3d: %s', index, dateStr);
            else
                name = sprintf('%3d', index);
            end
        end

        function h5Path = getH5FilePath(~, metadata, matPath)
            % GETH5FILEPATH Get H5 file path for lazy loading
            %
            % Tries multiple strategies to find the H5 file

            % Strategy 1: Check epicTreeConfig
            try
                config = epicTreeConfig();
                if isfield(config, 'h5_dir') && ~isempty(config.h5_dir)
                    h5Dir = config.h5_dir;
                    % Look for H5 file in this directory
                    if isfield(metadata, 'exp_name')
                        h5Path = fullfile(h5Dir, [metadata.exp_name '.h5']);
                        if exist(h5Path, 'file')
                            return;
                        end
                    end
                end
            catch
                % Config not available
            end

            % Strategy 2: Look for h5 directory next to .mat file
            [matDir, matName, ~] = fileparts(matPath);
            h5Dir = fullfile(fileparts(matDir), 'h5');
            if exist(h5Dir, 'dir')
                % Extract experiment name from mat file
                if isfield(metadata, 'exp_name')
                    expName = metadata.exp_name;
                else
                    % Use mat filename as experiment name
                    expName = matName;
                end

                h5Path = fullfile(h5Dir, [expName '.h5']);
                if exist(h5Path, 'file')
                    return;
                end
            end

            % Strategy 3: Return empty (will use in-memory data if available)
            h5Path = '';
        end

        function mask = buildCurrentMask(self)
            % Build selection mask from current isSelected flags (one-time)
            if isempty(self.tree) || isempty(self.tree.allEpochs)
                mask = [];
                return;
            end

            allEps = self.tree.allEpochs;
            mask = false(length(allEps), 1);
            for i = 1:length(allEps)
                if isfield(allEps{i}, 'isSelected') && allEps{i}.isSelected
                    mask(i) = true;
                end
            end
        end
    end
end
