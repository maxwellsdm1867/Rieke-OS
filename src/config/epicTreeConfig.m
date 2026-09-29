function value = epicTreeConfig(key, newValue)
% EPICTREECONFIG Get or set epicTreeGUI configuration values
%
% This function manages configuration for epicTreeGUI, following a similar
% pattern to retinanalysis's config system.
%
% Usage:
%   value = epicTreeConfig('h5_dir')           % Get h5_dir value
%   epicTreeConfig('h5_dir', '/path/to/h5')    % Set h5_dir value
%   config = epicTreeConfig()                  % Get all config as struct
%
% Configuration Keys:
%   h5_dir      - Directory containing H5 files (default: derived from mat file)
%   analysis_dir - Directory for analysis .mat files
%   ugm_dir     - Directory for .ugm selection mask files (default: same as .mat file)
%   user        - Username for exports
%
% The configuration is stored persistently using persistent variables.
% To reset to defaults, call: epicTreeConfig('reset')
%
% Example:
%   % Set H5 directory
%   epicTreeConfig('h5_dir', '/Users/maxwellsdm/Documents/epicTreeTest/h5');
%
%   % Get H5 file path for an experiment
%   h5_dir = epicTreeConfig('h5_dir');
%   h5_file = fullfile(h5_dir, [exp_name '.h5']);
%
% See also: getH5FilePath, loadEpicTreeData

persistent config

% Initialize config if empty
if isempty(config)
    config = getDefaultConfig();
end

% No arguments - return full config
if nargin == 0
    value = config;
    return;
end

% Handle 'reset' command
if strcmp(key, 'reset')
    config = getDefaultConfig();
    value = config;
    return;
end

% Handle 'load' command - load config from file
if strcmp(key, 'load') && nargin >= 2
    configFile = newValue;
    if exist(configFile, 'file')
        loaded = load(configFile, 'epicTreeConfig');
        if isfield(loaded, 'epicTreeConfig')
            config = loaded.epicTreeConfig;
            fprintf('Loaded config from %s\n', configFile);
        end
    else
        warning('epicTreeConfig:fileNotFound', 'Config file not found: %s', configFile);
    end
    value = config;
    return;
end

% Handle 'save' command - save config to file
if strcmp(key, 'save') && nargin >= 2
    configFile = newValue;
    epicTreeConfig = config; %#ok<NASGU>
    save(configFile, 'epicTreeConfig');
    fprintf('Saved config to %s\n', configFile);
    value = config;
    return;
end

% Set value if provided
if nargin >= 2
    config.(key) = newValue;
    value = newValue;
    return;
end

% Get value
if isfield(config, key)
    value = config.(key);
else
    warning('epicTreeConfig:unknownKey', 'Unknown config key: %s', key);
    value = [];
end

end


function config = getDefaultConfig()
% GETDEFAULTCONFIG Return default configuration values
%
% These defaults can be overridden by calling epicTreeConfig(key, value)

config = struct();

% H5 file directory - where .h5 files are stored
% Default: empty, will be derived from mat file path or must be set
config.h5_dir = '';

% Analysis directory - where exported .mat files are stored
config.analysis_dir = '';

% UGM directory - where .ugm selection mask files are saved/loaded
% Default: empty (saves next to .mat file). When set, all .ugm files
% go to this directory, making them discoverable by other tools (e.g. DataJoint).
config.ugm_dir = '';

% User name for exports
config.user = getenv('USER');
if isempty(config.user)
    config.user = 'guest';
end

% Try to find common H5 directories
commonPaths = {
    '/Users/maxwellsdm/Documents/epicTreeTest/h5',
    '/Volumes/rieke-nas/data/h5',
    '/Volumes/rieke/data/h5',
    '~/Documents/H5'
};

for i = 1:length(commonPaths)
    expandedPath = strrep(commonPaths{i}, '~', getenv('HOME'));
    if exist(expandedPath, 'dir')
        config.h5_dir = expandedPath;
        break;
    end
end

end
