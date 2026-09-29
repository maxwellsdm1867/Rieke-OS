function h5_file = getH5FilePath(exp_name, h5_dir)
% GETH5FILEPATH Construct path to H5 file for an experiment
%
% This follows the retinanalysis convention where H5 files are stored
% as {exp_name}.h5 in a configured H5 directory.
%
% Usage:
%   h5_file = getH5FilePath('2025-12-02_F')
%   h5_file = getH5FilePath('2025-12-02_F', '/path/to/h5dir')
%
% Inputs:
%   exp_name - Experiment name (e.g., '2025-12-02_F')
%   h5_dir   - (Optional) H5 directory, defaults to epicTreeConfig('h5_dir')
%
% Output:
%   h5_file - Full path to H5 file
%
% Example:
%   % Using configured h5_dir
%   epicTreeConfig('h5_dir', '/Users/data/h5');
%   h5_file = getH5FilePath('2025-12-02_F');
%   % Returns: '/Users/data/h5/2025-12-02_F.h5'
%
%   % With explicit h5_dir
%   h5_file = getH5FilePath('2025-12-02_F', '/custom/path');
%   % Returns: '/custom/path/2025-12-02_F.h5'
%
% See also: epicTreeConfig, loadH5ResponseData

% Get h5_dir from config if not provided
if nargin < 2 || isempty(h5_dir)
    h5_dir = epicTreeConfig('h5_dir');
end

% Validate h5_dir
if isempty(h5_dir)
    error('getH5FilePath:noH5Dir', ...
        ['H5 directory not configured. Set it using:\n' ...
         '  epicTreeConfig(''h5_dir'', ''/path/to/h5/files'')']);
end

% Construct full path
h5_file = fullfile(h5_dir, [exp_name '.h5']);

% Warn if file doesn't exist
if ~exist(h5_file, 'file')
    warning('getH5FilePath:fileNotFound', ...
        'H5 file not found: %s\nCheck that h5_dir is set correctly.', h5_file);
end

end
