function V = splitOnRGCSubtype(epoch)
    % SPLITONRGCSUBTYPE Split RGCs into ON-parasol, OFF-parasol, etc.
    %
    % Custom splitter that infers RGC subtype from:
    % 1. cellInfo.type (if specific)
    % 2. keywords (if present)
    % 3. RF analysis results (center size, surround, etc.)
    % 4. Response properties (transient vs sustained)
    %
    % Usage:
    %   tree.buildTreeWithSplitters({@splitOnRGCSubtype, ...});

    V = 'Unknown RGC';

    % Try cellInfo.type first
    if isfield(epoch, 'cellInfo') && isfield(epoch.cellInfo, 'type')
        cellType = epoch.cellInfo.type;
        if ~strcmp(cellType, 'RGC') % Already specific
            V = cellType;
            return;
        end
    end

    % Try keywords
    if isfield(epoch, 'keywords')
        kw = lower(strjoin(epoch.keywords, ' '));
        if contains(kw, 'onparasol') || contains(kw, 'on-parasol')
            V = 'RGC\ON-parasol';
            return;
        elseif contains(kw, 'offparasol') || contains(kw, 'off-parasol')
            V = 'RGC\OFF-parasol';
            return;
        elseif contains(kw, 'onmidget') || contains(kw, 'on-midget')
            V = 'RGC\ON-midget';
            return;
        elseif contains(kw, 'offmidget') || contains(kw, 'off-midget')
            V = 'RGC\OFF-midget';
            return;
        end
    end

    % Try RF analysis results (if you've run center/surround analysis)
    if isfield(epoch, 'rf_analysis')
        % Example: Large center diameter suggests parasol
        if isfield(epoch.rf_analysis, 'center_diameter')
            centerDiam = epoch.rf_analysis.center_diameter;
            if centerDiam > 200 % microns, adjust threshold
                % Check ON vs OFF from response polarity
                if isfield(epoch.rf_analysis, 'polarity')
                    if strcmpi(epoch.rf_analysis.polarity, 'ON')
                        V = 'RGC\ON-parasol';
                    else
                        V = 'RGC\OFF-parasol';
                    end
                    return;
                end
            else % Small center suggests midget
                if isfield(epoch.rf_analysis, 'polarity')
                    if strcmpi(epoch.rf_analysis.polarity, 'ON')
                        V = 'RGC\ON-midget';
                    else
                        V = 'RGC\OFF-midget';
                    end
                    return;
                end
            end
        end
    end

    % Try response properties
    % Example: Check if you have response analysis results
    if isfield(epoch, 'response_type')
        switch lower(epoch.response_type)
            case 'transient'
                V = 'RGC\transient';
            case 'sustained'
                V = 'RGC\sustained';
        end
        return;
    end

    % If we get here, we only know it's an RGC
    V = 'RGC\unclassified';
end
