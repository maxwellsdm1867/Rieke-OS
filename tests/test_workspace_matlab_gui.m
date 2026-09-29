function gui = test_workspace_matlab_gui(exportFolder)
% Native GUI regression for a temporary workspace export with expected.json.
% No SQL writes, source changes, global config edits, or unrelated figure closes.
% expected.json contains independently read epoch UUID/count and source samples.
    expected = jsondecode(fileread(fullfile(exportFolder, 'expected.json')));
    lastwarn('');
    run(fullfile(exportFolder, 'launch_epictree.m'));
    [~, warningId] = lastwarn;
    assert(~ismember(warningId, {'epicTreeGUI:H5NotFound', 'epicTreeGUI:NoH5Config'}));
    assert(ishghandle(gui.figure) && strcmp(get(gui.figure, 'Visible'), 'on'));
    assert(numel(gui.allEpochs) == expected.epoch_count);
    g = gui.treeBrowser.graphTree;
    target = [];
    for k = 1:numel(g.nodeList)
        candidate = g.nodeList{k};
        if isstruct(candidate.userData) && isfield(candidate.userData, 'h5_uuid') && strcmp(candidate.userData.h5_uuid, expected.first_uuid)
            target = candidate;
            break;
        end
    end
    assert(~isempty(target), 'Epoch UUID missing from graphical tree');
    assert(contains(target.name, target.userData.start_time), 'Epoch label lost recorded timestamp');
    parent = target.getParent();
    while ~isempty(parent)
        parent.isExpanded = true;
        parent = parent.getParent();
    end
    g.draw();
    selected = false;
    for k = 1:numel(g.widgetList)
        if isequal(g.widgetList{k}.boundNodeKey, target.selfKey)
            g.selectWidget(k);
            selected = true;
            break;
        end
    end
    assert(selected, 'Epoch widget was not drawn');
    drawnow;
    info = get(gui.plottingCanvas.infoTable, 'Data');
    assert(strcmp(info{2,2}, target.userData.start_time));
    assert(strcmp(info{3,2}, target.userData.blockInfo.protocol_name));
    lines = findobj(gui.plottingCanvas.axes, 'Type', 'line');
    assert(~isempty(lines), 'GUI callback did not create a raw trace');
    y = get(lines(1), 'YData');
    x = get(lines(1), 'XData');
    assert(numel(y) == expected.first_trace.total_samples);
    assert(max(abs(y(1:10) - expected.first_trace.values(:)')) < 1e-10);
    assert(abs(x(2) - 1000/expected.first_trace.sample_rate) < 1e-10);
    assert(contains(get(get(gui.plottingCanvas.axes, 'YLabel'), 'String'), expected.first_trace.units));
    assert(all(cellfun(@(ep) ep.isSelected, tree.allEpochs)));
    mask = true(numel(tree.allEpochs), 1);
    mask(1) = false;
    tree.setSelectedByMask(mask);
    returned = fullfile(exportFolder, 'native_returned.ugm');
    tree.saveUserMetadata(returned);
    tree.setSelectedByMask(true(size(mask)));
    assert(tree.loadUserMetadata(returned));
    assert(~tree.allEpochs{1}.isSelected && all(cellfun(@(ep) ep.isSelected, tree.allEpochs(2:end))));
    tree.setSelectedByMask(true(size(mask)));
    gui.loadedMask = true(size(mask));
    report = struct('visible_figure', true, 'epoch_count', numel(tree.allEpochs), ...
        'graphical_nodes', numel(g.nodeList), 'visible_widgets', g.drawCount, ...
        'trace_samples', numel(y), 'trace_matches_source', true, 'sample_rate', expected.first_trace.sample_rate, ...
        'ugm_roundtrip', true, 'first_epoch_uuid', expected.first_uuid, 'metadata_visible', true);
    f = fopen(fullfile(exportFolder, 'native-gui-proof.json'), 'w');
    fprintf(f, '%s', jsonencode(report));
    fclose(f);
    set(gui.figure, 'Name', sprintf('Rieke OS validation — %d VMN epochs (temporary export)', expected.epoch_count));
    drawnow;
    frame = getframe(gui.figure);
    imwrite(frame.cdata, fullfile(exportFolder, 'native-gui-figure.png'));
    disp('NATIVE_GUI_VALIDATION_PASS');
end
