classdef epicAnalysis
% EPICANALYSIS Static methods for receptive field analysis
%
% Ports legacy RFAnalysis, SpikeDetection.Detector, BaselineCorrectOvation,
% differenceOfGaussians, and singleGaussian to work with epicTreeTools nodes
% and epicTreeTools.getSelectedData().
%
% Usage:
%   results = epicAnalysis.RFAnalysis(node, params)
%   [times, amps] = epicAnalysis.detectSpikes(trace)
%   corrected = epicAnalysis.baselineCorrect(data, startSample, endSample)
%   fit = epicAnalysis.differenceOfGaussians(beta, x)
%   fit = epicAnalysis.singleGaussian(beta, x)
%   params = epicAnalysis.defaultParams()
%
% See also: epicTreeTools, getSelectedData

    methods (Static)

        function results = RFAnalysis(node, params)
        % RFANALYSIS Receptive field analysis with per-epoch statistics
        %
        % Computes integrated response amplitudes across leaf nodes,
        % per-epoch statistics (std, SEM), and optionally fits a
        % difference-of-Gaussians model. Plots error bars on the
        % area-summation curve.
        %
        % Inputs:
        %   node   - epicTreeTools node whose leaf nodes are conditions
        %   params - Struct from epicAnalysis.defaultParams() (optional fields override defaults)
        %
        % Outputs:
        %   results - Struct with fields:
        %       .respAmp       - [1 x nLeaves] integrated response amplitudes
        %       .respAmpStd    - [1 x nLeaves] std of response amplitudes
        %       .respAmpSem    - [1 x nLeaves] SEM of response amplitudes
        %       .numEpochs     - [1 x nLeaves] epoch count per condition
        %       .meanResponse  - [nLeaves x nSamples] mean traces
        %       .stdResponse   - [1 x nLeaves] alias for respAmpStd
        %       .semResponse   - [1 x nLeaves] alias for respAmpSem
        %       .tme           - [1 x nSamples] time vector in seconds
        %       .splitValue    - [1 x nLeaves] split values
        %       .PrePts        - Number of pre-stimulus samples
        %       .StmPts        - Number of stimulus samples
        %       .CenterSize    - Half-max RF center size (from fit or interpolation)
        %       .SurroundStrength - Surround suppression index

            if nargin < 2, params = epicAnalysis.defaultParams(); end

            if params.holdOn
                figure(params.figureNum); subplot(1, 2, 1); hold on;
            else
                figure(params.figureNum); clf; subplot(1, 2, 1); hold on;
            end

            leaves = node.leafNodes();
            firstLeaf = leaves{1};
            firstEpochs = firstLeaf.getAllEpochs(false);
            ep1 = firstEpochs{1};
            epParams = epicTreeTools.getParams(ep1);

            sampleRate = epParams.sampleRate;
            samplingInterval = 1 / sampleRate;
            PrePts = round(epParams.preTime / samplingInterval / 1000);
            StmPts = round(epParams.stimTime / samplingInterval / 1000);

            nLeaves = length(leaves);
            nColors = length(params.plotColors);

            for CurNode = 1:nLeaves
                leafNode = leaves{CurNode};
                EpochData = epicTreeTools.getSelectedData(leafNode, params.Amp);

                if isempty(EpochData)
                    continue;
                end

                if params.CellAttached
                    for epoch = 1:size(EpochData, 1)
                        [SpikeTimes, ~] = epicAnalysis.detectSpikes(EpochData(epoch, :), ...
                            'MinPeakHeight', params.minSpikeHeight);
                        EpochData(epoch, :) = 0;
                        EpochData(epoch, SpikeTimes) = sampleRate;
                    end
                else
                    EpochData = epicAnalysis.baselineCorrect(EpochData, 1, min(2000, size(EpochData, 2)));
                end

                % Filter each epoch individually for statistics
                FilteredData = zeros(size(EpochData));
                gWin = gausswin(params.DecimatePts);
                gSum = sum(gWin);
                for epoch = 1:size(EpochData, 1)
                    FilteredData(epoch, :) = filter(gWin, 1, EpochData(epoch, :)) / gSum;
                end

                if size(EpochData, 1) == 1
                    MeanResponse = FilteredData;
                else
                    MeanResponse = mean(FilteredData);
                end

                if params.baselineCorrect
                    MeanResponse = MeanResponse - mean(MeanResponse(1:PrePts));
                end

                tme = (1:length(MeanResponse)) * samplingInterval;
                results.PrePts = PrePts;
                results.StmPts = StmPts;

                % Per-epoch response amplitude statistics
                stimWindow = PrePts+1:PrePts+StmPts;
                if size(FilteredData, 1) > 1
                    epochRespAmps = zeros(size(FilteredData, 1), 1);
                    for epoch = 1:size(FilteredData, 1)
                        if params.baselineCorrect
                            corrected = FilteredData(epoch, :) - mean(FilteredData(epoch, 1:PrePts));
                            epochRespAmps(epoch) = abs(sum(corrected(stimWindow)) * samplingInterval);
                        else
                            epochRespAmps(epoch) = abs(sum(FilteredData(epoch, stimWindow)) * samplingInterval);
                        end
                    end
                    results.respAmp(CurNode) = mean(epochRespAmps);
                    results.respAmpStd(CurNode) = std(epochRespAmps);
                    results.respAmpSem(CurNode) = std(epochRespAmps) / sqrt(length(epochRespAmps));
                    results.numEpochs(CurNode) = size(FilteredData, 1);
                else
                    results.respAmp(CurNode) = abs(sum(MeanResponse(stimWindow)) * samplingInterval);
                    results.respAmpStd(CurNode) = 0;
                    results.respAmpSem(CurNode) = 0;
                    results.numEpochs(CurNode) = 1;
                end

                colorIdx = mod(CurNode - 1, nColors) + 1;
                plot(tme, MeanResponse + params.plotOffset*(CurNode-1), params.plotColors(colorIdx), 'LineWidth', 2);

                results.meanResponse(CurNode, :) = MeanResponse;
                results.stdResponse(CurNode) = results.respAmpStd(CurNode);
                results.semResponse(CurNode) = results.respAmpSem(CurNode);
                results.tme = tme;
                results.splitValue(CurNode) = leafNode.splitValue;
            end

            xlabel('sec');
            ylabel(params.yAxisLabel);

            if params.normalize
                normFactor = max(abs(results.respAmp));
                results.respAmp = results.respAmp / normFactor;
                results.stdResponse = results.stdResponse / normFactor;
                results.semResponse = results.semResponse / normFactor;
            end

            % Fit with DOG or compute half-max
            subplot(1, 2, 2); hold on;
            if params.DOGfit
                coef = [5 200 3.5 300];
                [fitcoefDOG, ~, ~, ~, DOGErr] = nlinfit(results.splitValue, results.respAmp, @epicAnalysis.differenceOfGaussians, coef);
                coef = [5 200];
                [fitcoefSingle, ~, ~, ~, SingleErr] = nlinfit(results.splitValue, results.respAmp, @epicAnalysis.singleGaussian, coef);

                if DOGErr < (SingleErr / 1.1)
                    results.DOGcoef = fitcoefDOG;
                    fitValues = epicAnalysis.differenceOfGaussians(fitcoefDOG, results.splitValue);
                else
                    results.Singlecoef = fitcoefSingle;
                    fitValues = epicAnalysis.singleGaussian(fitcoefSingle, results.splitValue);
                end

                results.CenterSize = epicAnalysis.halfMaxSize(results.splitValue, fitValues);
                results.SurroundStrength = (1 - fitValues(end)) / max(fitValues);

                errorbar(results.splitValue, results.respAmp, results.semResponse, ...
                    strcat('o', params.plotColors(1)), 'LineWidth', 2);
                hold on;
                plot(results.splitValue, fitValues, params.plotColors(1), 'LineWidth', 2);
            else
                results.CenterSize = epicAnalysis.halfMaxSize(results.splitValue, results.respAmp);
                results.SurroundStrength = (1 - results.respAmp(end)) / max(results.respAmp);

                errorbar(results.splitValue, results.respAmp, results.semResponse, ...
                    strcat('o', params.plotColors(1)), 'LineWidth', 2);
                hold on;
                plot(results.splitValue, results.respAmp, params.plotColors(1), 'LineWidth', 2);
            end

            if params.CellAttached
                ylabel('integrated resp (spikes)');
            else
                ylabel('integrated resp (pA*s)');
            end
            xlabel('split value');

            % Print statistics summary
            fprintf('\n--- Response Amplitude Statistics ---\n');
            for i = 1:length(results.splitValue)
                fprintf('Split Value %.2f: Mean=%.4f, Std=%.4f, SEM=%.4f (n=%d)\n', ...
                    results.splitValue(i), results.respAmp(i), results.stdResponse(i), ...
                    results.semResponse(i), results.numEpochs(i));
            end
        end


        function [spikeTimes, spikeAmplitudes] = detectSpikes(trace, varargin)
        % DETECTSPIKES Pure MATLAB spike detection replacing SpikeDetection.Detector
        %
        % Uses MATLAB's findpeaks() with configurable thresholds.
        %
        % Inputs:
        %   trace - 1D voltage trace (row or column vector)
        %
        % Optional Name-Value:
        %   'MinPeakHeight'   - Minimum peak amplitude (default: auto, 3*std)
        %   'MinPeakDistance'  - Minimum samples between spikes (default: 20)
        %
        % Outputs:
        %   spikeTimes      - 1-based sample indices of detected spikes
        %   spikeAmplitudes - Amplitude at each spike peak

            p = inputParser;
            p.addParameter('MinPeakHeight', 0, @isnumeric);
            p.addParameter('MinPeakDistance', 20, @isnumeric);
            p.parse(varargin{:});
            opts = p.Results;

            trace = trace(:)';  % ensure row vector

            % Auto-threshold: 3x standard deviation above mean
            if opts.MinPeakHeight <= 0
                threshold = mean(trace) + 3 * std(trace);
            else
                threshold = opts.MinPeakHeight;
            end

            [spikeAmplitudes, spikeTimes] = findpeaks(trace, ...
                'MinPeakHeight', threshold, ...
                'MinPeakDistance', opts.MinPeakDistance);
        end


        function corrected = baselineCorrect(dataMatrix, startSample, endSample)
        % BASELINECORRECT Subtract baseline mean from each epoch
        %
        % Port of BaselineCorrectOvation. Subtracts the mean of the baseline
        % region [startSample:endSample] from each row of the data matrix.
        %
        % Inputs:
        %   dataMatrix  - [nEpochs x nSamples] data matrix
        %   startSample - First sample of baseline region (1-based)
        %   endSample   - Last sample of baseline region
        %
        % Outputs:
        %   corrected   - Baseline-corrected data matrix (same size)

            corrected = zeros(size(dataMatrix));
            for epoch = 1:size(dataMatrix, 1)
                corrected(epoch, :) = dataMatrix(epoch, :) - mean(dataMatrix(epoch, startSample:endSample));
            end
        end


        function fit = differenceOfGaussians(beta, x)
        % DIFFERENCEOFGAUSSIANS Difference of Gaussians model
        %
        % fit = Ac * normcdf(x, 0, Sc) - As * normcdf(x, 0, Ss)
        %
        % beta = [Ac, Sc, As, Ss] (amplitudes and sigmas for center/surround)

            fit = abs(beta(1)) * (normcdf(x, 0, abs(beta(2))) - 0.5);
            fit = fit - abs(beta(3)) * (normcdf(x, 0, abs(beta(4))) - 0.5);
        end


        function fit = singleGaussian(beta, x)
        % SINGLEGAUSSIAN Single Gaussian model
        %
        % beta = [A, sigma]

            fit = abs(beta(1)) * (normcdf(x, 0, abs(beta(2))) - 0.5);
        end


        function centerSize = halfMaxSize(xValues, yValues)
        % HALFMAXSIZE Compute half-maximum size by interpolation
        %
        % Finds the x value where yValues first exceeds half its maximum,
        % using linear interpolation between adjacent points.
        %
        % Inputs:
        %   xValues - x coordinates (e.g., spot diameters)
        %   yValues - y coordinates (e.g., response amplitudes)
        %
        % Outputs:
        %   centerSize - Interpolated x value at half-maximum

            idx = find(yValues > max(yValues) / 2, 1, 'first');
            if isempty(idx)
                centerSize = xValues(end);
            elseif idx == 1
                centerSize = xValues(1);
            else
                lowerVal = yValues(idx-1) / max(yValues);
                upperVal = yValues(idx) / max(yValues);
                centerSize = xValues(idx-1) * (upperVal - 0.5) / (upperVal - lowerVal) ...
                           + xValues(idx) * (0.5 - lowerVal) / (upperVal - lowerVal);
            end
        end


        function params = defaultParams()
        % DEFAULTPARAMS Return default parameters for RFAnalysis
        %
        % Returns a struct with all default parameter values matching
        % the legacy dous_spike.m workflow defaults.

            params = struct();
            params.Amp = 'Amp1';
            params.figureNum = 10;
            params.holdOn = false;
            params.CellAttached = false;
            params.minSpikeHeight = 0;
            params.baselineCorrect = true;
            params.normalize = false;
            params.DOGfit = true;
            params.DecimatePts = 10;
            params.plotOffset = 0;
            params.plotColors = 'krgbcmyw';
            params.yAxisLabel = 'pA';
            params.SamplingInterval = 1/10000;
            params.saveGraphs = false;
            params.fileName = '';
        end

    end
end
