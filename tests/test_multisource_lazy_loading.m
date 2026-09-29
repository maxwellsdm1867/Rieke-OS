function tests = test_multisource_lazy_loading
% Regression: one project fallback must not replace per-recording pointers.
    tests = functiontests(localfunctions);
end

function testPerStreamPointersWinAndExplicitLowLevelOverrideRemains(testCase)
    folder = tempname;
    mkdir(folder);
    cleanup = onCleanup(@() rmdir(folder, 's')); %#ok<NASGU>
    first = fullfile(folder, 'first.h5');
    second = fullfile(folder, 'second.h5');
    h5create(first, '/response/data', [4 1]);
    h5write(first, '/response/data', (1:4)');
    h5create(second, '/response/data', [4 1]);
    h5write(second, '/response/data', (11:14)');
    response = struct('device_name', 'Amp1', 'data', [], 'h5_path', '/response', ...
                      'h5_file', first, 'sample_rate', 10000);
    one = struct('responses', response);
    response.h5_file = second;
    two = struct('responses', response);
    [matrix, rate] = epicTreeTools.getResponseMatrix({one, two}, 'Amp1', first);
    verifyEqual(testCase, matrix, [1:4; 11:14]);
    verifyEqual(testCase, rate, 10000);
    override = epicTreeTools.loadH5ResponseData(response, first);
    verifyEqual(testCase, override(:), (1:4)');
    response = rmfield(response, 'h5_file');
    fallback = epicTreeTools.getResponseFromEpoch(struct('responses', response), 'Amp1', second);
    verifyEqual(testCase, fallback, 11:14);
end
