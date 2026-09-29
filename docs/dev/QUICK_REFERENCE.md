# Quick Reference - EpicTreeGUI

## 🚀 Fastest Way to Start

**Just run this:**
```matlab
run START_HERE.m
```

This does everything for you:
1. Adds all paths
2. Configures H5 directory
3. Loads data
4. Builds tree
5. Launches GUI

---

## ⚙️ Manual Setup (If You Need Custom Paths)

### Step 1: Configure H5 Directory (MUST DO THIS FIRST!)

```matlab
% Set where your H5 files are located
epicTreeConfig('h5_dir', '/Users/maxwellsdm/Documents/epicTreeTest/h5');
```

**This tells the GUI where to find your actual response data!**

### Step 2: Add Paths

```matlab
addpath('src/gui');
addpath('src/tree');
addpath('src/splitters');
addpath('src/utilities');
addpath('src/config');
addpath('src');
```

### Step 3: Load Data and Build Tree

```matlab
[data, ~] = loadEpicTreeData('your_data.mat');

tree = epicTreeTools(data);
tree.buildTreeWithSplitters({
    @epicTreeTools.splitOnCellType,
    @epicTreeTools.splitOnProtocol
});
```

### Step 4: Launch GUI

```matlab
gui = epicTreeGUI(tree);
```

---

## 🔍 Troubleshooting

### No data shows when clicking nodes

**Problem:** H5 directory not configured

**Solution:**
```matlab
epicTreeConfig('h5_dir', '/path/to/your/h5/files');
```

**Check if it worked:**
```matlab
gui.h5File
% Should show: '/path/to/your/h5/files/2025-12-02_F.h5'
```

### Warning: "H5 directory not configured"

You forgot to run `epicTreeConfig` before launching the GUI.

**Fix:**
```matlab
close all
epicTreeConfig('h5_dir', '/Users/maxwellsdm/Documents/epicTreeTest/h5');
run START_HERE.m
```

### Warning: "H5 file not found"

The H5 file doesn't exist at the configured path.

**Check what the GUI is looking for:**
```matlab
gui.h5File
```

**Make sure the file exists:**
```matlab
ls /Users/maxwellsdm/Documents/epicTreeTest/h5/
% Should show: 2025-12-02_F.h5
```

---

## 📂 Expected Directory Structure

```
/Users/maxwellsdm/Documents/epicTreeTest/
├── analysis/
│   └── 2025-12-02_F.mat     ← Metadata (loads fast)
└── h5/
    └── 2025-12-02_F.h5      ← Actual data (lazy loaded)
```

---

## 💡 How It Works

### Startup (Fast!)
```
Load .mat file → Parse structure → Build tree
                 (NO data loaded - just metadata!)
```

### Click Node (On-Demand Loading)
```
Click "SingleSpot" → Find epochs → Load from H5 → Plot
                     (ONLY those epochs loaded)
```

### Result
- ✅ Fast startup (< 1 sec)
- ✅ Snappy clicks (~0.1 sec per node)
- ✅ Low memory usage
- ✅ Works with huge datasets

---

## 🎯 Common Workflows

### Quick Exploration
```matlab
run START_HERE.m
% Click around the tree to explore your data
```

### Analysis Session
```matlab
% 1. Setup
epicTreeConfig('h5_dir', '/path/to/h5');

% 2. Build custom tree
[data, ~] = loadEpicTreeData('data.mat');
tree = epicTreeTools(data);
tree.buildTreeWithSplitters({
    @epicTreeTools.splitOnCellType,
    'parameters.contrast',
    @epicTreeTools.splitOnProtocol
});

% 3. Launch GUI
gui = epicTreeGUI(tree);

% 4. Use GUI to select epochs (checkboxes)

% 5. Export selected epochs
% File > Export Selection
```

### Get Data for Custom Analysis
```matlab
% After selecting epochs in GUI
selectedEpochs = gui.getSelectedEpochs();

% Get data matrix
h5File = gui.h5File;
[data, epochs, fs] = getSelectedData(selectedEpochs, 'Amp1', h5File);

% Your analysis
meanResponse = mean(data, 1);
plot((1:length(meanResponse))/fs*1000, meanResponse);
```

---

## 📋 Remember

**ALWAYS set H5 directory BEFORE launching GUI:**

```matlab
epicTreeConfig('h5_dir', '/your/h5/directory');
```

**Or just use:**
```matlab
run START_HERE.m  % Does everything automatically
```
