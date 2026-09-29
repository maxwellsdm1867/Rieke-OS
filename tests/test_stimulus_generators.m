function tests = test_stimulus_generators
    tests = functiontests(localfunctions);
end

function setupOnce(testCase)
    addpath(fullfile(fileparts(fileparts(mfilename('fullpath'))), 'src', 'stimuli'));
    addpath(fullfile(fileparts(fileparts(mfilename('fullpath'))), 'src', 'tree'));
    addpath(fullfile(fileparts(fileparts(mfilename('fullpath'))), 'src'));
end

function testPulseGenerator(testCase)
    params = struct('preTime', 100, 'stimTime', 200, 'tailTime', 100, ...
        'amplitude', 5, 'mean', 1, 'sampleRate', 10000);
    [data, sr] = epicStimulusGenerators.pulse(params);

    verifyEqual(testCase, sr, 10000);
    verifyEqual(testCase, length(data), 4000);  % (100+200+100)/1000 * 10000

    % Pre region should be mean
    verifyEqual(testCase, data(1), 1, 'AbsTol', 1e-10);
    verifyEqual(testCase, data(1000), 1, 'AbsTol', 1e-10);

    % Stim region should be amplitude + mean
    verifyEqual(testCase, data(1001), 6, 'AbsTol', 1e-10);
    verifyEqual(testCase, data(3000), 6, 'AbsTol', 1e-10);

    % Tail region should be mean
    verifyEqual(testCase, data(3001), 1, 'AbsTol', 1e-10);
    verifyEqual(testCase, data(4000), 1, 'AbsTol', 1e-10);
end

function testRepeatingPulseIdentical(testCase)
    params = struct('preTime', 50, 'stimTime', 100, 'tailTime', 50, ...
        'amplitude', 3, 'mean', 0, 'sampleRate', 10000);
    [d1, ~] = epicStimulusGenerators.pulse(params);
    [d2, ~] = epicStimulusGenerators.repeatingPulse(params);
    verifyEqual(testCase, d1, d2);
end

function testSineGenerator(testCase)
    params = struct('preTime', 0, 'stimTime', 100, 'tailTime', 0, ...
        'amplitude', 1, 'period', 10, 'phase', 0, 'mean', 0, 'sampleRate', 10000);
    [data, sr] = epicStimulusGenerators.sine(params);

    verifyEqual(testCase, sr, 10000);
    verifyEqual(testCase, length(data), 1000);

    % At t=0, sin(0)=0 so value should be mean=0
    verifyEqual(testCase, data(1), 0, 'AbsTol', 1e-10);

    % At t = period/4 = 2.5ms = 25 samples, sin(pi/2) = 1
    verifyEqual(testCase, data(26), 1, 'AbsTol', 1e-6);
end

function testSquareGenerator(testCase)
    params = struct('preTime', 0, 'stimTime', 100, 'tailTime', 0, ...
        'amplitude', 2, 'period', 20, 'phase', 0, 'mean', 0, 'sampleRate', 10000);
    [data, ~] = epicStimulusGenerators.square(params);

    verifyEqual(testCase, length(data), 1000);

    % First quarter cycle (sine > 0): should be +amplitude
    verifyEqual(testCase, data(10), 2, 'AbsTol', 1e-10);

    % Third quarter cycle (sine < 0): should be -amplitude
    verifyEqual(testCase, data(160), -2, 'AbsTol', 1e-10);
end

function testRampGenerator(testCase)
    params = struct('preTime', 100, 'stimTime', 200, 'tailTime', 100, ...
        'amplitude', 10, 'mean', 5, 'sampleRate', 10000);
    [data, ~] = epicStimulusGenerators.ramp(params);

    verifyEqual(testCase, length(data), 4000);

    % Pre = mean
    verifyEqual(testCase, data(500), 5, 'AbsTol', 1e-10);

    % Start of ramp = 0 + mean = 5
    verifyEqual(testCase, data(1001), 5, 'AbsTol', 0.01);

    % End of ramp = amplitude + mean = 15
    verifyEqual(testCase, data(3000), 15, 'AbsTol', 0.01);
end

function testDirectCurrentGenerator(testCase)
    params = struct('time', 0.75, 'offset', 120, 'sampleRate', 10000);
    [data, sr] = epicStimulusGenerators.directCurrent(params);

    verifyEqual(testCase, sr, 10000);
    verifyEqual(testCase, length(data), 7500);
    verifyEqual(testCase, data(1), 120, 'AbsTol', 1e-10);
    verifyEqual(testCase, data(7500), 120, 'AbsTol', 1e-10);
end

function testPulseTrainGenerator(testCase)
    params = struct('preTime', 50, 'pulseTime', 20, 'intervalTime', 10, ...
        'tailTime', 50, 'amplitude', 3, 'mean', 1, 'numPulses', 3, ...
        'pulseTimeIncrement', 0, 'intervalTimeIncrement', 0, ...
        'amplitudeIncrement', 0, 'sampleRate', 10000);
    [data, sr] = epicStimulusGenerators.pulseTrain(params);

    verifyEqual(testCase, sr, 10000);

    % Expected: 500 pre + 3*200 pulse + 2*100 interval + 500 tail = 1800
    verifyEqual(testCase, length(data), 1800);

    % Pre region = mean
    verifyEqual(testCase, data(250), 1, 'AbsTol', 1e-10);

    % First pulse = amplitude + mean = 4
    verifyEqual(testCase, data(600), 4, 'AbsTol', 1e-10);
end

function testPulseTrainWithIncrements(testCase)
    params = struct('preTime', 0, 'pulseTime', 10, 'intervalTime', 10, ...
        'tailTime', 0, 'amplitude', 1, 'mean', 0, 'numPulses', 3, ...
        'pulseTimeIncrement', 0, 'intervalTimeIncrement', 0, ...
        'amplitudeIncrement', 1, 'sampleRate', 10000);
    [data, ~] = epicStimulusGenerators.pulseTrain(params);

    % Pulse 0: amplitude=1, Pulse 1: amplitude=2, Pulse 2: amplitude=3
    verifyEqual(testCase, data(50), 1, 'AbsTol', 1e-10);   % First pulse
    verifyEqual(testCase, data(250), 2, 'AbsTol', 1e-10);  % Second pulse
    verifyEqual(testCase, data(450), 3, 'AbsTol', 1e-10);  % Third pulse
end

function testGaussianNoiseReproducibility(testCase)
    params = struct('preTime', 0, 'stimTime', 500, 'tailTime', 0, ...
        'stDev', 1, 'freqCutoff', 500, 'numFilters', 1, ...
        'mean', 0, 'seed', 42, 'inverted', false, ...
        'upperLimit', Inf, 'lowerLimit', -Inf, 'sampleRate', 10000);

    [d1, ~] = epicStimulusGenerators.gaussianNoise(params);
    [d2, ~] = epicStimulusGenerators.gaussianNoise(params);

    verifyEqual(testCase, d1, d2, 'Same seed should produce identical output');
end

function testGaussianNoiseV2Reproducibility(testCase)
    params = struct('preTime', 100, 'stimTime', 500, 'tailTime', 100, ...
        'stDev', 0.3, 'freqCutoff', 300, 'numFilters', 1, ...
        'mean', 0, 'seed', 123, 'inverted', false, ...
        'upperLimit', Inf, 'lowerLimit', -Inf, 'sampleRate', 10000);

    [d1, ~] = epicStimulusGenerators.gaussianNoiseV2(params);
    [d2, ~] = epicStimulusGenerators.gaussianNoiseV2(params);

    verifyEqual(testCase, d1, d2, 'Same seed should produce identical output');

    % Pre/tail should be mean (0)
    verifyEqual(testCase, d1(1), 0, 'AbsTol', 1e-10);
    verifyEqual(testCase, d1(end), 0, 'AbsTol', 1e-10);

    % Stimulus portion should have variability
    stimPortion = d1(1001:6000);
    verifyGreaterThan(testCase, std(stimPortion), 0.1);
end

function testGaussianNoiseV2Inverted(testCase)
    params = struct('preTime', 0, 'stimTime', 200, 'tailTime', 0, ...
        'stDev', 1, 'freqCutoff', 500, 'numFilters', 1, ...
        'mean', 0, 'seed', 99, 'inverted', false, ...
        'upperLimit', Inf, 'lowerLimit', -Inf, 'sampleRate', 10000);

    [d1, ~] = epicStimulusGenerators.gaussianNoiseV2(params);

    params.inverted = true;
    [d2, ~] = epicStimulusGenerators.gaussianNoiseV2(params);

    verifyEqual(testCase, d1, -d2, 'AbsTol', 1e-10, 'Inverted should negate');
end

function testBinaryNoiseReproducibility(testCase)
    params = struct('preTime', 50, 'stimTime', 500, 'tailTime', 50, ...
        'segmentTime', 10, 'amplitude', 1, 'mean', 0, ...
        'seed', 7, 'sampleRate', 10000);

    [d1, ~] = epicStimulusGenerators.binaryNoise(params);
    [d2, ~] = epicStimulusGenerators.binaryNoise(params);

    verifyEqual(testCase, d1, d2, 'Same seed should produce identical output');

    % Pre/tail should be mean (0)
    verifyEqual(testCase, d1(1), 0, 'AbsTol', 1e-10);
    verifyEqual(testCase, d1(end), 0, 'AbsTol', 1e-10);

    % Stimulus portion should be +/- amplitude + mean
    stimPortion = d1(501:5500);
    uniqueVals = unique(stimPortion);
    verifyEqual(testCase, sort(uniqueVals(:)'), [-1, 1], 'AbsTol', 1e-10);
end

function testBinaryNoiseSegments(testCase)
    params = struct('preTime', 0, 'stimTime', 100, 'tailTime', 0, ...
        'segmentTime', 10, 'amplitude', 5, 'mean', 2, ...
        'seed', 1, 'sampleRate', 10000);

    [data, ~] = epicStimulusGenerators.binaryNoise(params);

    % Each segment (100 samples) should be constant
    seg1 = data(1:100);
    verifyEqual(testCase, min(seg1), max(seg1), 'AbsTol', 1e-10, ...
        'Each segment should be constant');
end

function testDispatcherMapping(testCase)
    % Test that dispatcher correctly routes to each generator
    dcParams = struct('time', 0.1, 'offset', 5, 'sampleRate', 1000);
    [data, sr] = epicStimulusGenerators.generateStimulus( ...
        'symphonyui.builtin.stimuli.DirectCurrentGenerator', dcParams);
    verifyEqual(testCase, sr, 1000);
    verifyEqual(testCase, length(data), 100);
    verifyEqual(testCase, data(50), 5, 'AbsTol', 1e-10);
end

function testDispatcherUnknownID(testCase)
    params = struct('sampleRate', 1000);
    verifyError(testCase, ...
        @() epicStimulusGenerators.generateStimulus('unknown.generator', params), ...
        'epicStimulusGenerators:unknownGenerator');
end

function testReconstructionIntegration(testCase)
    % Create a fake epoch with empty data but stimulus_id + parameters
    epoch = struct();
    epoch.stimuli = {struct( ...
        'device_name', 'LED', ...
        'stimulus_id', 'symphonyui.builtin.stimuli.DirectCurrentGenerator', ...
        'stimulus_parameters', struct('time', 0.5, 'offset', 100, 'sampleRate', 10000), ...
        'data', [], ...
        'sample_rate', 10000, ...
        'units', 'normalized' ...
    )};

    stim = epicTreeTools.getStimulusByName(epoch, 'LED');

    verifyFalse(testCase, isempty(stim), 'Should find stimulus');
    verifyFalse(testCase, isempty(stim.data), 'Should auto-reconstruct data');
    verifyEqual(testCase, length(stim.data), 5000);
    verifyEqual(testCase, stim.data(1), 100, 'AbsTol', 1e-10);
end

function testGetStimulusFromEpoch(testCase)
    epoch = struct();
    epoch.stimuli = {struct( ...
        'device_name', 'Stage', ...
        'stimulus_id', 'symphonyui.builtin.stimuli.PulseGenerator', ...
        'stimulus_parameters', struct( ...
            'preTime', 100, 'stimTime', 200, 'tailTime', 100, ...
            'amplitude', 3, 'mean', 0, 'sampleRate', 10000), ...
        'data', [], ...
        'sample_rate', 10000, ...
        'units', 'normalized' ...
    )};

    [data, sr] = epicTreeTools.getStimulusFromEpoch(epoch, 'Stage');

    verifyEqual(testCase, sr, 10000);
    verifyEqual(testCase, length(data), 4000);
    verifyEqual(testCase, data(500), 0, 'AbsTol', 1e-10);   % Pre = mean
    verifyEqual(testCase, data(2000), 3, 'AbsTol', 1e-10);  % Stim = amplitude
end

function testGetStimulusMatrix(testCase)
    makeEpoch = @(seed) struct( ...
        'stimuli', {{struct( ...
            'device_name', 'LED', ...
            'stimulus_id', 'edu.washington.riekelab.stimuli.GaussianNoiseGeneratorV2', ...
            'stimulus_parameters', struct( ...
                'preTime', 0, 'stimTime', 100, 'tailTime', 0, ...
                'stDev', 1, 'freqCutoff', 500, 'numFilters', 1, ...
                'mean', 0, 'seed', seed, 'inverted', false, ...
                'upperLimit', Inf, 'lowerLimit', -Inf, 'sampleRate', 10000), ...
            'data', [], 'sample_rate', 10000, 'units', 'norm')}});

    epochs = {makeEpoch(1), makeEpoch(2), makeEpoch(3)};

    [mat, sr] = epicTreeTools.getStimulusMatrix(epochs, 'LED');

    verifyEqual(testCase, sr, 10000);
    verifyEqual(testCase, size(mat), [3, 1000]);

    % Each row should differ (different seeds)
    verifyGreaterThan(testCase, norm(mat(1,:) - mat(2,:)), 0.1);
end

function testSumGenerator(testCase)
    params = struct();
    params.stim0_stimulusID = 'symphonyui.builtin.stimuli.DirectCurrentGenerator';
    params.stim0_time = 0.1;
    params.stim0_offset = 5;
    params.stim0_sampleRate = 10000;
    params.stim1_stimulusID = 'symphonyui.builtin.stimuli.DirectCurrentGenerator';
    params.stim1_time = 0.1;
    params.stim1_offset = 3;
    params.stim1_sampleRate = 10000;

    [data, sr] = epicStimulusGenerators.sumGenerator(params);

    verifyEqual(testCase, sr, 10000);
    verifyEqual(testCase, length(data), 1000);
    verifyEqual(testCase, data(500), 8, 'AbsTol', 1e-10);  % 5 + 3
end
