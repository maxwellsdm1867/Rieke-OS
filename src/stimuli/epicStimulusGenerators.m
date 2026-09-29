classdef epicStimulusGenerators
    % EPICSTIMULUSGENERATORS Pure MATLAB ports of Symphony stimulus generators
    %
    % Reconstructs stimulus waveforms from stimulusID + parameters without
    % requiring Symphony .NET classes. Each generator is a direct port of
    % the original math from the Symphony/Riekelab source code.
    %
    % Usage:
    %   [data, sampleRate] = epicStimulusGenerators.generateStimulus(stimulusID, params)
    %
    % Supported generators:
    %   symphonyui.builtin.stimuli.PulseGenerator
    %   symphonyui.builtin.stimuli.RepeatingPulseGenerator
    %   symphonyui.builtin.stimuli.PulseTrainGenerator
    %   symphonyui.builtin.stimuli.SineGenerator
    %   symphonyui.builtin.stimuli.SquareGenerator
    %   symphonyui.builtin.stimuli.RampGenerator
    %   symphonyui.builtin.stimuli.DirectCurrentGenerator
    %   symphonyui.builtin.stimuli.SumGenerator
    %   edu.washington.riekelab.stimuli.GaussianNoiseGenerator
    %   edu.washington.riekelab.stimuli.GaussianNoiseGeneratorV2
    %   edu.washington.riekelab.stimuli.BinaryNoiseGenerator

    methods (Static)

        function [data, sampleRate] = generateStimulus(stimulusID, params)
            % GENERATESTIMULUS Dispatch to the correct generator by stimulusID
            %
            % Inputs:
            %   stimulusID - Fully-qualified generator class name (string)
            %   params     - Struct of generator-specific parameters
            %
            % Outputs:
            %   data       - 1xN double waveform vector
            %   sampleRate - Sample rate in Hz

            if ischar(stimulusID)
                stimulusID = string(stimulusID);
            end

            switch stimulusID
                case 'symphonyui.builtin.stimuli.PulseGenerator'
                    [data, sampleRate] = epicStimulusGenerators.pulse(params);

                case 'symphonyui.builtin.stimuli.RepeatingPulseGenerator'
                    [data, sampleRate] = epicStimulusGenerators.repeatingPulse(params);

                case 'symphonyui.builtin.stimuli.PulseTrainGenerator'
                    [data, sampleRate] = epicStimulusGenerators.pulseTrain(params);

                case 'symphonyui.builtin.stimuli.SineGenerator'
                    [data, sampleRate] = epicStimulusGenerators.sine(params);

                case 'symphonyui.builtin.stimuli.SquareGenerator'
                    [data, sampleRate] = epicStimulusGenerators.square(params);

                case 'symphonyui.builtin.stimuli.RampGenerator'
                    [data, sampleRate] = epicStimulusGenerators.ramp(params);

                case 'symphonyui.builtin.stimuli.DirectCurrentGenerator'
                    [data, sampleRate] = epicStimulusGenerators.directCurrent(params);

                case 'symphonyui.builtin.stimuli.SumGenerator'
                    [data, sampleRate] = epicStimulusGenerators.sumGenerator(params);

                case 'edu.washington.riekelab.stimuli.GaussianNoiseGenerator'
                    [data, sampleRate] = epicStimulusGenerators.gaussianNoise(params);

                case 'edu.washington.riekelab.stimuli.GaussianNoiseGeneratorV2'
                    [data, sampleRate] = epicStimulusGenerators.gaussianNoiseV2(params);

                case 'edu.washington.riekelab.stimuli.BinaryNoiseGenerator'
                    [data, sampleRate] = epicStimulusGenerators.binaryNoise(params);

                otherwise
                    error('epicStimulusGenerators:unknownGenerator', ...
                        'Unknown stimulusID: %s', stimulusID);
            end
        end


        function [data, sampleRate] = pulse(params)
            % PULSE Rectangular pulse with pre/stim/tail segments
            %
            % Parameters:
            %   preTime    - Leading silence duration (ms)
            %   stimTime   - Pulse duration (ms)
            %   tailTime   - Trailing silence duration (ms)
            %   amplitude  - Pulse amplitude (units)
            %   mean       - Baseline value (units)
            %   sampleRate - Sample rate (Hz)

            sampleRate = epicStimulusGenerators.getParam(params, 'sampleRate');
            preTime    = epicStimulusGenerators.getParam(params, 'preTime');
            stimTime   = epicStimulusGenerators.getParam(params, 'stimTime');
            tailTime   = epicStimulusGenerators.getParam(params, 'tailTime');
            amplitude  = epicStimulusGenerators.getParam(params, 'amplitude');
            meanVal    = epicStimulusGenerators.getParam(params, 'mean', 0);

            timeToPts = @(t) round(t / 1e3 * sampleRate);

            prePts  = timeToPts(preTime);
            stimPts = timeToPts(stimTime);
            tailPts = timeToPts(tailTime);

            data = ones(1, prePts + stimPts + tailPts) * meanVal;
            data(prePts + 1 : prePts + stimPts) = amplitude + meanVal;
        end


        function [data, sampleRate] = repeatingPulse(params)
            % REPEATINGPULSE Identical math to pulse (marked indefinite in Symphony)
            [data, sampleRate] = epicStimulusGenerators.pulse(params);
        end


        function [data, sampleRate] = pulseTrain(params)
            % PULSETRAIN Train of pulses with optional per-pulse increments
            %
            % Parameters:
            %   preTime              - Leading silence (ms)
            %   pulseTime            - Base pulse duration (ms)
            %   intervalTime         - Base inter-pulse interval (ms)
            %   tailTime             - Trailing silence (ms)
            %   amplitude            - Base pulse amplitude (units)
            %   mean                 - Baseline value (units)
            %   numPulses            - Number of pulses
            %   pulseTimeIncrement   - Duration increment per pulse (ms, default 0)
            %   intervalTimeIncrement- Interval increment per pulse (ms, default 0)
            %   amplitudeIncrement   - Amplitude increment per pulse (units, default 0)
            %   sampleRate           - Sample rate (Hz)

            sampleRate = epicStimulusGenerators.getParam(params, 'sampleRate');
            preTime    = epicStimulusGenerators.getParam(params, 'preTime');
            pulseTime  = epicStimulusGenerators.getParam(params, 'pulseTime');
            intervalTime = epicStimulusGenerators.getParam(params, 'intervalTime');
            tailTime   = epicStimulusGenerators.getParam(params, 'tailTime');
            amplitude  = epicStimulusGenerators.getParam(params, 'amplitude');
            meanVal    = epicStimulusGenerators.getParam(params, 'mean', 0);
            numPulses  = epicStimulusGenerators.getParam(params, 'numPulses');
            pulseTimeInc  = epicStimulusGenerators.getParam(params, 'pulseTimeIncrement', 0);
            intervalTimeInc = epicStimulusGenerators.getParam(params, 'intervalTimeIncrement', 0);
            ampInc     = epicStimulusGenerators.getParam(params, 'amplitudeIncrement', 0);

            timeToPts = @(t) round(t / 1e3 * sampleRate);

            prePts = timeToPts(preTime);
            data = ones(1, prePts) * meanVal;

            for i = 0:numPulses-1
                pulsePts = timeToPts(pulseTimeInc * i + pulseTime);
                pulseVal = ampInc * i + amplitude + meanVal;
                data = [data, ones(1, pulsePts) * pulseVal]; %#ok<AGROW>

                if i < numPulses - 1
                    intPts = timeToPts(intervalTimeInc * i + intervalTime);
                    data = [data, ones(1, intPts) * meanVal]; %#ok<AGROW>
                end
            end

            tailPts = timeToPts(tailTime);
            data = [data, ones(1, tailPts) * meanVal];
        end


        function [data, sampleRate] = sine(params)
            % SINE Sinusoidal stimulus with pre/stim/tail segments
            %
            % Parameters:
            %   preTime    - Leading silence (ms)
            %   stimTime   - Sine wave duration (ms)
            %   tailTime   - Trailing silence (ms)
            %   amplitude  - Sine amplitude (units)
            %   period     - Sine period (ms)
            %   phase      - Phase offset (radians, default 0)
            %   mean       - Baseline value (units)
            %   sampleRate - Sample rate (Hz)

            sampleRate = epicStimulusGenerators.getParam(params, 'sampleRate');
            preTime    = epicStimulusGenerators.getParam(params, 'preTime');
            stimTime   = epicStimulusGenerators.getParam(params, 'stimTime');
            tailTime   = epicStimulusGenerators.getParam(params, 'tailTime');
            amplitude  = epicStimulusGenerators.getParam(params, 'amplitude');
            period     = epicStimulusGenerators.getParam(params, 'period');
            phase      = epicStimulusGenerators.getParam(params, 'phase', 0);
            meanVal    = epicStimulusGenerators.getParam(params, 'mean', 0);

            timeToPts = @(t) round(t / 1e3 * sampleRate);

            prePts  = timeToPts(preTime);
            stimPts = timeToPts(stimTime);
            tailPts = timeToPts(tailTime);

            data = ones(1, prePts + stimPts + tailPts) * meanVal;

            freq = 2 * pi / (period * 1e-3);
            time = (0:stimPts-1) / sampleRate;
            sineWave = meanVal + amplitude * sin(freq * time + phase);

            data(prePts + 1 : prePts + stimPts) = sineWave;
        end


        function [data, sampleRate] = square(params)
            % SQUARE Square wave derived from sine wave sign
            %
            % Parameters: same as sine()

            sampleRate = epicStimulusGenerators.getParam(params, 'sampleRate');
            preTime    = epicStimulusGenerators.getParam(params, 'preTime');
            stimTime   = epicStimulusGenerators.getParam(params, 'stimTime');
            tailTime   = epicStimulusGenerators.getParam(params, 'tailTime');
            amplitude  = epicStimulusGenerators.getParam(params, 'amplitude');
            period     = epicStimulusGenerators.getParam(params, 'period');
            phase      = epicStimulusGenerators.getParam(params, 'phase', 0);
            meanVal    = epicStimulusGenerators.getParam(params, 'mean', 0);

            timeToPts = @(t) round(t / 1e3 * sampleRate);

            prePts  = timeToPts(preTime);
            stimPts = timeToPts(stimTime);
            tailPts = timeToPts(tailTime);

            data = ones(1, prePts + stimPts + tailPts) * meanVal;

            freq = 2 * pi / (period * 1e-3);
            time = (0:stimPts-1) / sampleRate;
            sineWave = sin(freq * time + phase);

            sqWave = zeros(1, stimPts);
            sqWave(sineWave > 0) = amplitude;
            sqWave(sineWave < 0) = -amplitude;
            sqWave = sqWave + meanVal;

            data(prePts + 1 : prePts + stimPts) = sqWave;
        end


        function [data, sampleRate] = ramp(params)
            % RAMP Linear ramp from 0 to amplitude over stimTime
            %
            % Parameters:
            %   preTime    - Leading silence (ms)
            %   stimTime   - Ramp duration (ms)
            %   tailTime   - Trailing silence (ms)
            %   amplitude  - Ramp peak amplitude (units)
            %   mean       - Baseline value (units)
            %   sampleRate - Sample rate (Hz)

            sampleRate = epicStimulusGenerators.getParam(params, 'sampleRate');
            preTime    = epicStimulusGenerators.getParam(params, 'preTime');
            stimTime   = epicStimulusGenerators.getParam(params, 'stimTime');
            tailTime   = epicStimulusGenerators.getParam(params, 'tailTime');
            amplitude  = epicStimulusGenerators.getParam(params, 'amplitude');
            meanVal    = epicStimulusGenerators.getParam(params, 'mean', 0);

            timeToPts = @(t) round(t / 1e3 * sampleRate);

            prePts  = timeToPts(preTime);
            stimPts = timeToPts(stimTime);
            tailPts = timeToPts(tailTime);

            data = ones(1, prePts + stimPts + tailPts) * meanVal;
            data(prePts + 1 : prePts + stimPts) = linspace(0, amplitude, stimPts) + meanVal;
        end


        function [data, sampleRate] = directCurrent(params)
            % DIRECTCURRENT Constant DC stimulus
            %
            % Parameters:
            %   time       - Duration in SECONDS (not ms!)
            %   offset     - Constant amplitude value (units)
            %   sampleRate - Sample rate (Hz)

            sampleRate = epicStimulusGenerators.getParam(params, 'sampleRate');
            time       = epicStimulusGenerators.getParam(params, 'time');
            offset     = epicStimulusGenerators.getParam(params, 'offset');

            pts = max(round(time * sampleRate), 1);
            data = ones(1, pts) * offset;
        end


        function [data, sampleRate] = gaussianNoise(params)
            % GAUSSIANNOISE V1: FFT-filtered Gaussian noise (power-of-2 padded)
            %
            % Parameters:
            %   preTime    - Leading silence (ms)
            %   stimTime   - Noise duration (ms)
            %   tailTime   - Trailing silence (ms)
            %   stDev      - Post-filter standard deviation (units)
            %   freqCutoff - Lowpass cutoff frequency (Hz)
            %   numFilters - Number of filter cascades (default 0)
            %   mean       - Baseline value (units)
            %   seed       - RNG seed for reproducibility
            %   inverted   - Invert polarity (default false)
            %   upperLimit - Upper clip bound (default Inf)
            %   lowerLimit - Lower clip bound (default -Inf)
            %   sampleRate - Sample rate (Hz)

            sampleRate = epicStimulusGenerators.getParam(params, 'sampleRate');
            preTime    = epicStimulusGenerators.getParam(params, 'preTime');
            stimTime   = epicStimulusGenerators.getParam(params, 'stimTime');
            tailTime   = epicStimulusGenerators.getParam(params, 'tailTime');
            stDev      = epicStimulusGenerators.getParam(params, 'stDev');
            freqCutoff = epicStimulusGenerators.getParam(params, 'freqCutoff');
            numFilters = epicStimulusGenerators.getParam(params, 'numFilters', 0);
            meanVal    = epicStimulusGenerators.getParam(params, 'mean', 0);
            seed       = epicStimulusGenerators.getParam(params, 'seed');
            inverted   = epicStimulusGenerators.getParam(params, 'inverted', false);
            upperLimit = epicStimulusGenerators.getParam(params, 'upperLimit', Inf);
            lowerLimit = epicStimulusGenerators.getParam(params, 'lowerLimit', -Inf);

            timeToPts = @(t) round(t / 1e3 * sampleRate);

            prePts  = timeToPts(preTime);
            stimPts = timeToPts(stimTime);
            tailPts = timeToPts(tailTime);

            stream = RandStream('mt19937ar', 'Seed', seed);

            numFftPts = 2^nextpow2(stimPts);
            noise = stDev * stream.randn(1, numFftPts);
            noise = fft(noise);

            freqStep = sampleRate / numFftPts;
            scFact = 0;
            for i = 0:numFftPts/2 - 1
                temp = i * freqStep / freqCutoff;
                temp = 1 / (1 + temp * temp);
                temp = temp^numFilters;

                scFact = scFact + temp;

                noise(i + 1) = noise(i + 1) * temp;
                noise(end - i) = noise(end - i) * temp;
            end

            noise = ifft(noise);
            if inverted
                noise = -noise;
            end

            scFact = sqrt(numFftPts / (2 * scFact));

            data = ones(1, prePts + stimPts + tailPts) * meanVal;
            data(prePts + 1 : prePts + stimPts) = real(noise(1:stimPts)) * scFact + meanVal;

            data(data > upperLimit) = upperLimit;
            data(data < lowerLimit) = lowerLimit;
        end


        function [data, sampleRate] = gaussianNoiseV2(params)
            % GAUSSIANNOISEV2 Corrected FFT-filtered Gaussian noise
            %
            % Key differences from V1:
            %   - No zero-padding (uses exact stimPts)
            %   - DC component explicitly zeroed
            %   - Variance-based scaling factor
            %   - Handles even/odd lengths correctly
            %
            % Parameters: same as gaussianNoise()

            sampleRate = epicStimulusGenerators.getParam(params, 'sampleRate');
            preTime    = epicStimulusGenerators.getParam(params, 'preTime');
            stimTime   = epicStimulusGenerators.getParam(params, 'stimTime');
            tailTime   = epicStimulusGenerators.getParam(params, 'tailTime');
            stDev      = epicStimulusGenerators.getParam(params, 'stDev');
            freqCutoff = epicStimulusGenerators.getParam(params, 'freqCutoff');
            numFilters = epicStimulusGenerators.getParam(params, 'numFilters', 0);
            meanVal    = epicStimulusGenerators.getParam(params, 'mean', 0);
            seed       = epicStimulusGenerators.getParam(params, 'seed');
            inverted   = epicStimulusGenerators.getParam(params, 'inverted', false);
            upperLimit = epicStimulusGenerators.getParam(params, 'upperLimit', Inf);
            lowerLimit = epicStimulusGenerators.getParam(params, 'lowerLimit', -Inf);

            timeToPts = @(t) round(t / 1e3 * sampleRate);

            prePts  = timeToPts(preTime);
            stimPts = timeToPts(stimTime);
            tailPts = timeToPts(tailTime);

            stream = RandStream('mt19937ar', 'Seed', seed);

            noiseTime = stDev * stream.randn(1, stimPts);
            noiseFreq = fft(noiseTime);

            freqStep = sampleRate / stimPts;
            if mod(stimPts, 2) == 0
                frequencies = (0:stimPts/2) * freqStep;
                oneSidedFilter = 1 ./ (1 + (frequencies / freqCutoff) .^ (2 * numFilters));
                filterVec = [oneSidedFilter, fliplr(oneSidedFilter(2:end-1))];
            else
                frequencies = (0:(stimPts-1)/2) * freqStep;
                oneSidedFilter = 1 ./ (1 + (frequencies / freqCutoff) .^ (2 * numFilters));
                filterVec = [oneSidedFilter, fliplr(oneSidedFilter(2:end))];
            end

            filterFactor = sqrt(filterVec(2:end) * filterVec(2:end)' / (stimPts - 1));

            noiseFreq = noiseFreq .* filterVec;
            noiseFreq(1) = 0;  % Zero DC component
            noiseTime = ifft(noiseFreq);
            noiseTime = noiseTime / filterFactor;
            noiseTime = real(noiseTime);

            if inverted
                noiseTime = -noiseTime;
            end

            data = ones(1, prePts + stimPts + tailPts) * meanVal;
            data(prePts + 1 : prePts + stimPts) = noiseTime + meanVal;

            data(data > upperLimit) = upperLimit;
            data(data < lowerLimit) = lowerLimit;
        end


        function [data, sampleRate] = binaryNoise(params)
            % BINARYNOISE Discrete binary noise at segmentTime resolution
            %
            % Parameters:
            %   preTime     - Leading silence (ms)
            %   stimTime    - Noise duration (ms)
            %   tailTime    - Trailing silence (ms)
            %   segmentTime - Duration of each binary value (ms)
            %   amplitude   - Noise amplitude (units)
            %   mean        - Baseline value (units)
            %   seed        - RNG seed for reproducibility
            %   sampleRate  - Sample rate (Hz)

            sampleRate  = epicStimulusGenerators.getParam(params, 'sampleRate');
            preTime     = epicStimulusGenerators.getParam(params, 'preTime');
            stimTime    = epicStimulusGenerators.getParam(params, 'stimTime');
            tailTime    = epicStimulusGenerators.getParam(params, 'tailTime');
            segmentTime = epicStimulusGenerators.getParam(params, 'segmentTime');
            amplitude   = epicStimulusGenerators.getParam(params, 'amplitude');
            meanVal     = epicStimulusGenerators.getParam(params, 'mean', 0);
            seed        = epicStimulusGenerators.getParam(params, 'seed');

            timeToPts = @(t) round(t / 1e3 * sampleRate);

            prePts     = timeToPts(preTime);
            stimPts    = timeToPts(stimTime);
            tailPts    = timeToPts(tailTime);
            segmentPts = timeToPts(segmentTime);

            stream = RandStream('mt19937ar', 'Seed', seed);

            noise = zeros(1, stimPts);
            for i = 1:segmentPts:stimPts
                if stream.rand() > 0.5
                    amp = amplitude;
                else
                    amp = -amplitude;
                end
                endIdx = min(i + segmentPts - 1, stimPts);
                noise(i:endIdx) = amp;
            end

            data = ones(1, prePts + stimPts + tailPts) * meanVal;
            data(prePts + 1 : prePts + stimPts) = noise + meanVal;
        end


        function [data, sampleRate] = sumGenerator(params)
            % SUMGENERATOR Composite stimulus: element-wise sum of sub-stimuli
            %
            % Parameters are prefixed by stimulus index:
            %   stim0_stimulusID, stim0_<param>, stim0_<param>, ...
            %   stim1_stimulusID, stim1_<param>, stim1_<param>, ...
            %
            % The method reconstructs each sub-stimulus and sums them.

            % Discover how many sub-stimuli exist
            if isstruct(params)
                fnames = fieldnames(params);
            else
                error('epicStimulusGenerators:invalidParams', ...
                    'SumGenerator requires struct params');
            end

            % Find all stim indices
            indices = [];
            for k = 1:length(fnames)
                tokens = regexp(fnames{k}, '^stim(\d+)_stimulusID$', 'tokens');
                if ~isempty(tokens)
                    indices(end+1) = str2double(tokens{1}{1}); %#ok<AGROW>
                end
            end
            indices = sort(indices);

            if isempty(indices)
                error('epicStimulusGenerators:noSubStimuli', ...
                    'SumGenerator params must contain stim0_stimulusID, stim1_stimulusID, ...');
            end

            data = [];
            sampleRate = 0;

            for idx = indices
                prefix = sprintf('stim%d_', idx);
                subID = params.(sprintf('stim%d_stimulusID', idx));

                % Extract sub-params by stripping prefix
                subParams = struct();
                for k = 1:length(fnames)
                    fn = fnames{k};
                    if startsWith(fn, prefix) && ~strcmp(fn, [prefix 'stimulusID'])
                        paramName = fn(length(prefix)+1:end);
                        subParams.(paramName) = params.(fn);
                    end
                end

                [subData, subRate] = epicStimulusGenerators.generateStimulus(subID, subParams);

                if isempty(data)
                    data = subData;
                    sampleRate = subRate;
                else
                    % Pad shorter to match longer
                    maxLen = max(length(data), length(subData));
                    if length(data) < maxLen
                        data(end+1:maxLen) = 0;
                    end
                    if length(subData) < maxLen
                        subData(end+1:maxLen) = 0;
                    end
                    data = data + subData;
                end
            end
        end

    end % methods (Static)


    methods (Static, Access = private)

        function val = getParam(params, name, defaultVal)
            % GETPARAM Extract parameter from struct with optional default
            if isstruct(params) && isfield(params, name)
                val = params.(name);
                if ischar(val) || isstring(val)
                    numVal = str2double(val);
                    if ~isnan(numVal)
                        val = numVal;
                    end
                end
            elseif nargin >= 3
                val = defaultVal;
            else
                error('epicStimulusGenerators:missingParam', ...
                    'Required parameter ''%s'' not found', name);
            end
        end

    end % methods (Static, Access = private)

end
