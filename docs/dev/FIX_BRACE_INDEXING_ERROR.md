# Fix: "Brace Indexing is not supported" Error

If you're getting this error when clicking tree nodes:
```
Brace indexing is not supported for variables of this type.
Error in graphicalTree/fireNodesSelectedFcn (line 381)
    feval(fcn{1}, nodes);
```

This means the **OLD** `graphicalTree.m` is loaded instead of the **NEW** one.

---

## Quick Fix (Try This First)

### Step 1: Run the emergency fix script

In MATLAB command window:
```matlab
cd('/Users/maxwellsdm/Documents/GitHub/epicTreeGUI')
run fix_now.m
```

This will:
- Close all GUI windows
- Clear workspace
- Remove old code from path
- Add new code to path
- Verify correct version is loaded

If you see `✅ SUCCESS!`, you're good to go!

---

## If Quick Fix Doesn't Work

### Nuclear Option: Complete MATLAB Restart

1. **Close MATLAB completely** (File > Exit MATLAB)

2. **Restart MATLAB**

3. **In the command window, run:**
   ```matlab
   restoredefaultpath
   cd('/Users/maxwellsdm/Documents/GitHub/epicTreeGUI')
   run fix_now.m
   ```

4. **Verify it worked:**
   ```matlab
   which graphicalTree
   ```

   **Expected output:**
   ```
   /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/src/gui/graphicalTree.m
   ```

   **BAD output (if you see this, try again):**
   ```
   /Users/maxwellsdm/Documents/GitHub/epicTreeGUI/old_epochtree/.../graphicalTree.m
   ```

---

## Test After Fix

Once the fix is applied, test with:

```matlab
run test_epoch_display.m
```

**Expected behavior:**
- GUI launches without errors
- Can expand tree nodes
- Individual epochs show with pink backgrounds
- Clicking nodes works without errors

---

## Why Does This Happen?

### The Problem

There are **TWO** versions of `graphicalTree.m` in the repository:

1. **OLD version** (in `old_epochtree/`)
   - Legacy Java-based code
   - Expects callbacks as cell arrays: `fcn{1}`
   - Will cause "brace indexing" error with function handle callbacks

2. **NEW version** (in `src/gui/`)
   - Pure MATLAB implementation
   - Handles both function handles and cell arrays
   - Works correctly with `epicTreeGUI`

### Root Causes

The old version gets loaded when:

1. **MATLAB startup script** adds `old_epochtree/` to path
   - Check: `~/Documents/MATLAB/startup.m`
   - Remove any lines adding `old_epochtree`

2. **Working directory** is inside `old_epochtree/`
   - Solution: Always `cd` to project root first

3. **Path pollution** from previous sessions
   - Solution: Use `restoredefaultpath` to reset

4. **Class definition cached** in MATLAB memory
   - Solution: `clear classes` or restart MATLAB

---

## Prevention

### Option 1: Add to Your Workflow

Always start your MATLAB session with:
```matlab
cd('/Users/maxwellsdm/Documents/GitHub/epicTreeGUI')
run fix_now.m
```

### Option 2: Create Custom Launcher

Save this as `launch_epic_tree.m` in project root:
```matlab
function launch_epic_tree()
    % Safe launcher for epicTreeGUI

    % Ensure we're in the right directory
    [scriptPath, ~, ~] = fileparts(mfilename('fullpath'));
    cd(scriptPath);

    % Clear and reset paths
    close all;
    clear classes;
    warning('off', 'MATLAB:rmpath:DirNotFound');
    rmpath(genpath('old_epochtree'));
    warning('on', 'MATLAB:rmpath:DirNotFound');

    % Add correct paths
    addpath('src/gui');
    addpath('src/tree');
    addpath('src/splitters');
    addpath('src/utilities');
    addpath('src');

    % Verify
    which_result = which('graphicalTree');
    if ~contains(which_result, 'src/gui')
        error('Path setup failed. Restart MATLAB and try again.');
    end

    fprintf('✓ Paths configured correctly\n');
    fprintf('Ready to run: test_epoch_display, test_legacy_pattern, etc.\n');
end
```

Then just run:
```matlab
launch_epic_tree
```

### Option 3: Edit startup.m

Check if you have a startup script:
```matlab
which startup
```

If it exists, edit it and add at the TOP:
```matlab
% Remove epicTreeGUI old code if present
warning('off', 'MATLAB:rmpath:DirNotFound');
rmpath(genpath('old_epochtree'));
warning('on', 'MATLAB:rmpath:DirNotFound');
```

---

## Diagnostic Tools

### Check which graphicalTree is loaded
```matlab
which graphicalTree -all
```

Shows ALL versions found on path. You should see:
- `src/gui/graphicalTree.m` (GOOD)
- NOT `old_epochtree/.../graphicalTree.m` (BAD)

### Check if old_epochtree is on path
```matlab
path
```

Search output for "old_epochtree". If found, it's polluting your path.

### Run full diagnostic
```matlab
run check_paths.m
```

This script:
- Identifies which graphicalTree is loaded
- Checks for path pollution
- Attempts automatic fix
- Reports status

---

## Summary

| Issue | Solution |
|-------|----------|
| First time error | Run `fix_now.m` |
| Error persists | Restart MATLAB + `restoredefaultpath` + `fix_now.m` |
| Happens every session | Check `startup.m` for path pollution |
| Want prevention | Use `launch_epic_tree.m` launcher |
| Need diagnosis | Run `check_paths.m` |

---

## Still Not Working?

If none of the above works:

1. **Completely remove old_epochtree:**
   ```matlab
   % CAREFUL: This is destructive
   rmdir('old_epochtree', 's')
   ```
   This permanently deletes the old code. Only do this if you don't need it for reference.

2. **Check for multiple MATLAB installations:**
   - Ensure you're using the same MATLAB installation
   - Check `ver` to see MATLAB version

3. **File permissions:**
   - Ensure you have read access to `src/gui/graphicalTree.m`
   ```matlab
   ls -l src/gui/graphicalTree.m
   ```

4. **Report the issue:**
   - Include output of `which graphicalTree -all`
   - Include output of `check_paths.m`
