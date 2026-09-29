% Benchmark: Mask vs isSelected filtering performance
%
% Tests two approaches at different epoch counts to see where performance matters

function results = benchmark_selection_performance()
    fprintf('\n=== Selection Filtering Performance Benchmark ===\n\n');

    % Test at different scales
    epochCounts = [100, 500, 1000, 2000, 5000, 10000];
    results = struct();

    for n = epochCounts
        fprintf('Testing with %d epochs...\n', n);

        % Create synthetic epochs
        epochs = createSyntheticEpochs(n);

        % Deselect 30% randomly (typical use case)
        deselectedIndices = randperm(n, floor(n * 0.3));
        for i = 1:length(deselectedIndices)
            epochs{deselectedIndices(i)}.isSelected = false;
        end

        % Create mask from isSelected
        mask = true(n, 1);
        for i = 1:n
            mask(i) = epochs{i}.isSelected;
        end

        % Benchmark 1: Loop through isSelected (current approach)
        tic;
        for trial = 1:100
            selected1 = filterByIsSelected(epochs);
        end
        time_isSelected = toc / 100;  % Average per iteration

        % Benchmark 2: Vectorized mask (proposed approach)
        tic;
        for trial = 1:100
            selected2 = epochs(mask);
        end
        time_mask = toc / 100;

        % Verify same result
        assert(length(selected1) == length(selected2), 'Results should match');

        % Store results
        speedup = time_isSelected / time_mask;
        fprintf('  isSelected loop: %.4f ms\n', time_isSelected * 1000);
        fprintf('  Mask (vectorized): %.4f ms\n', time_mask * 1000);
        fprintf('  Speedup: %.1fx faster\n', speedup);
        fprintf('  Selected: %d/%d (%.1f%%)\n\n', length(selected1), n, 100*length(selected1)/n);

        results(end+1).n = n;
        results(end).time_isSelected = time_isSelected;
        results(end).time_mask = time_mask;
        results(end).speedup = speedup;
    end

    % Plot results
    figure;
    subplot(2,1,1);
    semilogy([results.n], [results.time_isSelected]*1000, 'o-', 'LineWidth', 2);
    hold on;
    semilogy([results.n], [results.time_mask]*1000, 's-', 'LineWidth', 2);
    xlabel('Number of Epochs');
    ylabel('Time (ms)');
    legend('isSelected Loop', 'Mask (Vectorized)');
    title('Selection Filtering Performance');
    grid on;

    subplot(2,1,2);
    plot([results.n], [results.speedup], 'o-', 'LineWidth', 2);
    xlabel('Number of Epochs');
    ylabel('Speedup Factor');
    title('Performance Improvement (Mask vs Loop)');
    grid on;

    fprintf('\n=== Summary ===\n');
    fprintf('For typical node sizes (< 1000 epochs): %.1fx speedup\n', ...
        mean([results(1:3).speedup]));
    fprintf('For large datasets (> 5000 epochs): %.1fx speedup\n', ...
        mean([results(end-1:end).speedup]));
    fprintf('\nConclusion: ');
    if mean([results(1:3).speedup]) < 2
        fprintf('Difference minimal for typical use - isSelected loop is fine!\n');
    else
        fprintf('Mask approach provides significant speedup.\n');
    end
end

function selected = filterByIsSelected(epochs)
    % Current approach: loop and check isSelected
    selected = {};
    for i = 1:length(epochs)
        ep = epochs{i};
        if isfield(ep, 'isSelected') && ep.isSelected
            selected{end+1} = ep;
        elseif ~isfield(ep, 'isSelected')
            selected{end+1} = ep;
        end
    end
    selected = selected(:);
end

function epochs = createSyntheticEpochs(n)
    % Create synthetic epoch structs for testing
    epochs = cell(n, 1);
    for i = 1:n
        epochs{i} = struct();
        epochs{i}.id = i;
        epochs{i}.isSelected = true;  % Start all selected
        epochs{i}.data = rand(1, 1000);  % Fake data
    end
end
