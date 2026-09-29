# JAUIModel Function Inventory (Reference for MATLAB Implementation)

## Source: jenkins-jauimodel-275.jar (Rieke Lab Symphony Analysis Library)

This document catalogs all functions from the decompiled legacy JAR file. **Use this as a reference** for building equivalent MATLAB functions in the new Epic Tree GUI.

**Important**: We do NOT replicate the Java code. We build MATLAB functions that provide the same behavior. The data loading layer (EntityLoader, CoreData, JNI) is irrelevant since we use Python MAT exports instead.

---

## Table of Contents
1. [Core Interfaces](#1-core-interfaces)
2. [EpochTree System](#2-epochtree-system)
3. [EpochList System](#3-epochlist-system)
4. [Epoch Data Model](#4-epoch-data-model)
5. [Data Loading (EntityLoader)](#5-data-loading-entityloader)
6. [Analysis Entry Points](#6-analysis-entry-points)
7. [Supporting Data Types](#7-supporting-data-types)
8. [Utility Functions](#8-utility-functions)

---

## 1. Core Interfaces

### 1.1 EpochTree Interface
**Package:** `edu.washington.rieke.symphony.EpochTree`
**Extends:** `Serializable`, `HydratationNeeding`

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `splitKey()` | none | `Object` | Returns the key used to split this node (e.g., "protocolSettings.stimTime") |
| `splitValue()` | none | `Object` | Returns the value at this split (e.g., 500) |
| `splitValues()` | none | `ImmutableMap<String, Object>` | Returns all split key-value pairs from root to this node |
| `splitValues(String key)` | `String` | `Object` | Get specific split value by key |
| `custom()` | none | `Map<String, Object>` | Custom user-defined properties |
| `custom(String key)` | `String` | `Object` | Get specific custom property |
| `isLeaf()` | none | `boolean` | True if this node has no children (contains epochs) |
| `epochList()` | none | `EpochList` | Get epochs at this node (for leaf nodes) |
| `parent()` | none | `EpochTree` | Parent node in tree |
| `children()` | none | `CompatabilityList<EpochTree>` | Child nodes |
| `children(int index)` | `int` | `EpochTree` | Get specific child by index |
| `leafNodes()` | none | `CompatabilityList<EpochTree>` | All leaf nodes under this node |
| `leafNodes(int index)` | `int` | `EpochTree` | Get specific leaf by index |
| `descendentsDepthFirst()` | none | `EpochTree[]` | All descendants in depth-first order |
| `descendentsDepthFirst(int index)` | `int` | `EpochTree` | Get specific descendant |
| `insertEpochs(EpochList)` | `EpochList` | `void` | Insert epochs into tree (rebuilds structure) |
| `insertEpoch(Epoch)` | `Epoch` | `void` | Insert single epoch |
| `visualize()` | none | `void` | Opens JUNG graph visualization window |
| `saveTree(String path)` | `String` | `void` | Serialize tree to file |
| `refresh()` | none | `void` | Reload data from backing store |
| `childBySplitValue(Object value)` | `Object` | `EpochTree` | Find child by its split value |
| `splitKeyPaths()` | none | `Object[]` | Array of key paths used for splitting |
| `splitKeyPaths(int index)` | `int` | `Object` | Get specific key path |

---

### 1.2 EpochList Interface
**Package:** `edu.washington.rieke.symphony.EpochList`
**Extends:** `KeywordTaggable`, `CompatabilityList<Epoch>`, `HydratationNeeding`

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `stimuliStreamNames()` | none | `String[]` | Names of all stimulus streams (e.g., "Amp1", "LED") |
| `responseStreamNames()` | none | `String[]` | Names of all response streams |
| `stimuliByStreamName(String name)` | `String` | `double[][]` | Get stimulus data matrix for stream |
| `elements()` | none | `Epoch[]` | All epochs in list |
| `elements(int index)` | `int` | `Epoch` | Get specific epoch by index |
| `sortedBy(String keyPath)` | `String` | `EpochList` | Return new list sorted by key path |
| `append(Object, boolean)` | `Object`, `boolean` | `void` | Append epoch to list |
| `setProtocolSetting(String key, Object value)` | `String`, `Object` | `void` | Set protocol setting on all epochs |
| `removeProtocolSetting(String key)` | `String` | `void` | Remove protocol setting from all epochs |
| `refresh()` | none | `void` | Reload from backing store |

---

### 1.3 Epoch Interface
**Package:** `edu.washington.rieke.symphony.Epoch`
**Extends:** `KeywordTaggable`, `HydratationNeeding`

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `comment()` | none | `String` | User comment on epoch |
| `duration()` | none | `Double` | Duration in seconds |
| `protocolID()` | none | `String` | Protocol identifier (e.g., "edu.washington.rieke.PulseFamily") |
| `cell()` | none | `Cell` | Parent cell this epoch belongs to |
| `startDate()` | none | `double[]` | MATLAB datenum format [year, month, day, hour, min, sec] |
| `startDate(int index)` | `int` | `double` | Get specific date component |
| `isSelected()` | none | `boolean` | UI selection state |
| `setIsSelected(boolean)` | `boolean` | `void` | Set selection state |
| `includeInAnalysis()` | none | `boolean` | Whether to include in analysis |
| `setIncludeInAnalysis(boolean)` | `boolean` | `void` | Set analysis inclusion |
| `protocolSettings()` | none | `ProtocolSettingsMap` | All protocol parameters |
| `protocolSettings(String key)` | `String` | `Object` | Get specific protocol parameter |
| `setProtocolSetting(String key, Object value)` | `String`, `Object` | `void` | Set protocol parameter |
| `removeProtocolSetting(String key)` | `String` | `void` | Remove protocol parameter |
| `refresh()` | none | `void` | Reload from backing store |
| `responses()` | none | `ImmutableMap<String, Response>` | All response streams |
| `responses(String name)` | `String` | `Response` | Get specific response by stream name |
| `stimuli()` | none | `ImmutableMap<String, Stimulus>` | All stimulus streams |
| `stimuli(String name)` | `String` | `Stimulus` | Get specific stimulus by stream name |

---

### 1.4 KeywordTaggable Interface
**Package:** `edu.washington.rieke.symphony.KeywordTaggable`
**Extends:** `Serializable`

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `addKeywordTag(String tag)` | `String` | `void` | Add keyword tag |
| `removeKeywordTag(String tag)` | `String` | `void` | Remove keyword tag |
| `keywords()` | none | `Set<String>` | All keyword tags |
| `refresh()` | none | `void` | Reload from backing store |

---

## 2. EpochTree System

### 2.1 GenericEpochTree (Implementation)
**Package:** `edu.washington.rieke.symphony.generic.GenericEpochTree`
**Implements:** `EpochTree`

#### Private Fields
| Field | Type | Description |
|-------|------|-------------|
| `_splitKey` | `Object` | Key path used to split at this node |
| `_splitValue` | `Comparable` | Value at this split |
| `_custom` | `Map<String, Object>` | Custom properties (initialized as HashMap) |
| `_isLeaf` | `boolean` | Whether this is a leaf node |
| `_epochList` | `EpochList` | Epochs at this node (if leaf) |
| `_parent` | `GenericEpochTree` | Parent node |
| `_children` | `CompatabilityList<EpochTree>` | Child nodes |
| `_leafNodes` | `CompatabilityList<EpochTree>` | Cached leaf nodes |
| `_splitKeyPaths` | `Object[]` | Array of split key paths |
| `factory` | `GenericEpochTreeFactory` | Factory for tree operations (transient) |

#### Key Implementation Details
- **Visitor Pattern:** Uses `accept(GenericEpochTreeVisitor)` for tree traversal
- **Lazy Leaf Calculation:** `leafNodes()` computes and caches leaf nodes on first access
- **Serialization:** Uses Apache Commons `SerializationUtils` for `saveTree()`
- **Visualization:** Uses JUNG library for interactive graph display

---

### 2.2 GenericEpochTreeFactory
**Package:** `edu.washington.rieke.symphony.generic.GenericEpochTreeFactory`
**Implements:** `EpochTreeFactory`

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `create(EpochList, Object[])` | `EpochList`, `Object[]` | `EpochTree` | Build tree from epoch list using key paths |
| `create(Object[])` | `Object[]` | `EpochTree` | Build tree using key paths (empty list) |
| `insertEpoch(Epoch, GenericEpochTree)` | `Epoch`, `GenericEpochTree` | `void` | Insert epoch into existing tree |

#### Dependencies
- `KeyPathGetter pathGetter` - For accessing nested properties via key paths
- `EpochListFactory listFactory` - For creating new epoch lists

#### Algorithm (buildTreeHelper)
```
1. Take list of epochs and stack of key paths
2. If key paths empty: create leaf node with EpochList
3. Pop next key path
4. Group epochs by value at key path (getSplitValue)
5. For each unique value:
   a. Create child node with splitKey and splitValue
   b. Recursively build subtree with remaining key paths
6. Sort children by splitValue
```

---

### 2.3 AuiEpochTree
**Package:** `edu.washington.rieke.jauimodel.AuiEpochTree`
**Extends:** `GenericEpochTree`

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `getAttachedDataStores()` | none | `List<String>` | List of attached data store paths |
| `setAttachedDataStores(List<String>)` | `List<String>` | `void` | Set attached data stores |
| `getQualifiedProjectRoot()` | none | `String` | Root path of project |
| `setQualifiedProjectRoot(String)` | `String` | `void` | Set project root |
| `documentation()` | none | `void` | Show documentation |

---

## 3. EpochList System

### 3.1 GenericEpochList (Implementation)
**Package:** `edu.washington.rieke.symphony.generic.GenericEpochList`
**Extends:** `GenericCompatabilityList<Epoch>`
**Implements:** `EpochList`

#### Private Fields
| Field | Type | Description |
|-------|------|-------------|
| `keywordsDirty` | `boolean` | Flag for keyword cache invalidation |
| `_keywords` | `Set<String>` | Cached keyword set |
| `operationFactory` | `TransactionWrappedOperationFactory` | Transaction support (transient) |
| `listFactory` | `EpochListFactory` | Factory for creating new lists (transient) |
| `keyPathGetter` | `KeyPathGetter` | For nested property access (transient) |

#### Key Methods
| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `dataMatrix(DataGetter, String)` | `DataGetter`, `String` | `double[][]` | Extract data matrix from epochs |
| `sortedBy(String keyPath)` | `String` | `EpochList` | Return sorted copy using KeyPathComparator |
| `documentation()` | none | `void` | Show documentation |

---

### 3.2 CompatabilityList Interface
**Package:** `edu.washington.rieke.symphony.CompatabilityList<T>`
**Extends:** `Iterable<T>`, `Serializable`

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `elements()` | none | `T[]` | All elements as array |
| `elements(int index)` | `int` | `T` | Get element by index |
| `valueByIndex(int index)` | `int` | `T` | Alias for elements(index) |
| `append(T)` | `T` | `void` | Add element |
| `firstValue()` | none | `T` | First element |
| `length()` | none | `int` | Number of elements |

---

## 4. Epoch Data Model

### 4.1 AuiEpoch (Implementation)
**Package:** `edu.washington.rieke.jauimodel.AuiEpoch`
**Extends:** `RealKeywordTaggable`
**Implements:** `Epoch`, `Serializable`

#### Private Fields
| Field | Type | Description |
|-------|------|-------------|
| `_cell` | `AuiCell` | Parent cell |
| `_comment` | `String` | User comment |
| `_duration` | `Double` | Duration in seconds |
| `_includeInAnalysis` | `Boolean` | Analysis inclusion flag |
| `_isSelected` | `boolean` | UI selection state |
| `_protocolID` | `String` | Protocol identifier |
| `_responses` | `SimpleImmutableMap<String, AuiResponse>` | Response streams |
| `_stimuli` | `SimpleImmutableMap<String, AuiStimulus>` | Stimulus streams |
| `_startDate` | `double[]` | Start date as MATLAB datenum |
| `_protocolSettings` | `ProtocolSettingsMap` | Protocol parameters |

#### Native Methods (JNI to Objective-C)
| Method | Description |
|--------|-------------|
| `setIncludeInAnalysisCoreData(boolean)` | Persist to CoreData |
| `getIncludeInAnalysisCoreData()` | Read from CoreData |

---

### 4.2 Cell Interface
**Package:** `edu.washington.rieke.symphony.Cell`
**Extends:** `KeywordTaggable`, `HydratationNeeding`

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `comment()` | none | `String` | Cell comment |
| `label()` | none | `String` | Cell label (e.g., "c1", "c2") |
| `startDate()` | none | `double[]` | Start date as MATLAB datenum |
| `startDate(int index)` | `int` | `double` | Get date component |
| `experiment()` | none | `Experiment` | Parent experiment |

---

### 4.3 Experiment Interface
**Package:** `edu.washington.rieke.symphony.Experiment`
**Extends:** `KeywordTaggable`, `HydratationNeeding`

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `purpose()` | none | `String` | Experiment purpose |
| `otherNotes()` | none | `String` | Additional notes |
| `notes()` | none | `Note[]` | Time-stamped notes |
| `startDate()` | none | `double[]` | Start date |
| `startDate(int index)` | `int` | `double` | Get date component |

---

### 4.4 Stimulus Interface
**Package:** `edu.washington.rieke.symphony.Stimulus`
**Extends:** `IOBase`, `HydratationNeeding`

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `duration()` | none | `Double` | Stimulus duration |
| `stimulusID()` | none | `String` | Stimulus identifier |
| `version()` | none | `Integer` | Protocol version |
| `sampleRate()` | none | `Integer` | Sample rate in Hz |
| `data()` | none | `double[]` | Stimulus waveform data |
| `parameters()` | none | `ImmutableMap<String, Object>` | Stimulus parameters |
| `parameters(String key)` | `String` | `Object` | Get specific parameter |

---

### 4.5 Response Interface
**Package:** `edu.washington.rieke.symphony.Response`
**Extends:** `IOBase`, `HydratationNeeding`

(Inherits from IOBase - primarily provides data access)

---

### 4.6 IOBase Interface
**Package:** `edu.washington.rieke.symphony.IOBase`
**Extends:** `Serializable`

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `channelID()` | none | `Integer` | Hardware channel ID |
| `externalDeviceGain()` | none | `Integer` | External device gain |
| `externalDeviceMode()` | none | `Integer` | External device mode |
| `externalDeviceUnits()` | none | `String` | Units (e.g., "pA", "mV") |
| `streamName()` | none | `String` | Stream name (e.g., "Amp1") |

---

### 4.7 AuiIOBase (Implementation)
**Package:** `edu.washington.rieke.jauimodel.AuiIOBase`
**Extends:** `NSManagedObject`

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `data()` | none | `double[]` | Get response/stimulus data |
| `data(String key)` | `String` | `double[]` | Native method to get data by key |

---

## 5. Data Loading (EntityLoader)

### 5.1 EntityLoader Interface
**Package:** `edu.washington.rieke.symphony.internal.EntityLoader`

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `loadEpochList(String path)` | `String` | `EpochList` | Load epochs from single data store |
| `loadEpochList(String path, String cellLabel)` | `String`, `String` | `EpochList` | Load epochs for specific cell |
| `loadEpochTree(String path)` | `String` | `EpochTree` | Load as tree (default split keys) |
| `loadEpochTree(String path, String cellLabel)` | `String`, `String` | `EpochTree` | Load tree for specific cell |
| `flushCaches()` | none | `void` | Clear cached data |

---

### 5.2 AuiEntityLoader (Implementation)
**Package:** `edu.washington.rieke.jauimodel.AuiEntityLoader`

#### Dependencies
- `DataStoreProxyFactory datastoreFactory` - Creates data store proxies
- `EpochListFactory listFactory` - Creates epoch lists
- `Hydrator hydrator` - Hydrates entity objects with data

---

## 6. Analysis Entry Points

### 6.1 riekesuite.analysis (Main Entry Point)
**Package:** `riekesuite.analysis`

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `loadEpochList(String path)` | `String` | `EpochList` | Load epochs from data store path |
| `loadEpochList(String path, String cellLabel)` | `String`, `String` | `EpochList` | Load epochs for specific cell |
| `loadEpochTree(String path)` | `String` | `EpochTree` | Load as tree |
| `loadEpochTree(String path, String cellLabel)` | `String`, `String` | `EpochTree` | Load tree for cell |
| `buildTree(EpochList, Object[])` | `EpochList`, `Object[]` | `EpochTree` | Build tree from epoch list with custom split keys |
| `documentation()` | none | `void` | Show documentation |

**Usage Example (MATLAB):**
```matlab
% Load epochs
epochList = riekesuite.analysis.loadEpochList('/path/to/data.h5');

% Build tree by protocol settings
tree = riekesuite.analysis.buildTree(epochList, {'protocolSettings.stimTime', 'protocolSettings.contrast'});

% Get leaf nodes
leaves = tree.leafNodes();
for i = 1:leaves.length()
    leaf = leaves.elements(i);
    epochs = leaf.epochList();
    % Analyze epochs...
end
```

---

### 6.2 edu.washington.rieke.Analysis
**Package:** `edu.washington.rieke.Analysis`

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `getEntityLoader()` | none | `EntityLoader` | Get entity loader singleton |
| `getEpochTreeFactory()` | none | `EpochTreeFactory` | Get tree factory singleton |
| `getEpochListFactory()` | none | `EpochListFactory` | Get list factory singleton |

Uses Google Guice for dependency injection.

---

## 7. Supporting Data Types

### 7.1 ProtocolSettingsMap
**Package:** `edu.washington.rieke.symphony.ProtocolSettingsMap`
**Extends:** `Map<String, Object>`, `Serializable`, `HydratationNeeding`

Standard Map interface with `refresh()` method.

---

### 7.2 KeyValuePairMap (Implementation)
**Package:** `edu.washington.rieke.jauimodel.KeyValuePairMap`
**Implements:** `Map<String, Object>`, `Serializable`, `HydratationNeeding`

#### Private Fields
| Field | Type | Description |
|-------|------|-------------|
| `proxyInstanceId` | `String` | CoreData proxy ID (transient) |
| `operationFactory` | `TransactionWrappedOperationFactory` | Transaction support |
| `embeddedMap` | `Map<String, AuiKeyValuePair>` | Backing map |
| `_objectID` | `String` | CoreData object ID |
| `parentKVPairProperty` | `String` | Parent property name |

#### Native Methods
| Method | Description |
|--------|-------------|
| `setKeyValuePairCoreData(String, Object)` | Persist KV pair to CoreData |
| `removeKeyValuePairCoreData(String, Object, String)` | Remove from CoreData |
| `getKvPairsCoreData()` | Get all KV pairs from CoreData |

---

### 7.3 ImmutableMap Interface
**Package:** `edu.washington.rieke.symphony.ImmutableMap<T1, T2>`
**Extends:** `Map<T1, T2>`, `Serializable`

Read-only map interface.

---

## 8. Utility Functions

### 8.1 GenericUtil
**Package:** `edu.washington.rieke.symphony.generic.GenericUtil`

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `mapToYaml(Map)` | `Map` | `String` | Convert map to YAML string |
| `mapToYaml(Map, boolean)` | `Map`, `boolean` | `String` | Convert with formatting options |
| `arrayToDateString(double[])` | `double[]` | `String` | Convert MATLAB datenum to string |
| `openDocumentation(String)` | `String` | `void` | Open docs for topic |
| `openDocumentation(Class)` | `Class` | `void` | Open docs for class |
| `compare(Object, Object)` | `Object`, `Object` | `int` | Compare objects for sorting |

---

### 8.2 Util (JNI/CoreData)
**Package:** `edu.washington.rieke.jauimodel.Util`

| Method | Input | Output | Description |
|--------|-------|--------|-------------|
| `ensureNativeCodeLoaded()` | none | `void` | Load JNI library |
| `getRecurseProperties(String)` | `String` | `Map` | Get nested property definitions |
| `getExceptionIsOk(String, String)` | `String`, `String` | `boolean` | Check if exception type is acceptable |
| `getSetterTypeSig(String, String)` | `String`, `String` | `String` | Get setter type signature |
| `fromClassPath(String)` | `String` | `String` | Convert class path format |
| `dateToDateVector(Date)` | `Date` | `double[]` | Convert Java Date to MATLAB datenum |
| `initializeAuiControllers()` | none | `void` | Initialize Objective-C controllers (native) |
| `resolveTilde(String)` | `String` | `String` | Expand ~ in paths |
| `loadOvationExport(String)` | `String` | `Map` | Load Ovation export file |
| `loadOvationExportNative(String)` | `String` | `Map` | Native implementation |

---

## 9. Key Dependencies Summary

### External Libraries
- **Google Guice** - Dependency injection
- **Apache Commons Lang** - SerializationUtils
- **Apache Commons Collections** - Transformers
- **Apache Commons BeanUtils** - Property access via key paths
- **JUNG Graph Library** - Tree visualization

### Native (JNI) Dependencies
- CoreData (Objective-C) - Data persistence layer
- Mac OS X frameworks - Native UI integration

---

## 10. Implementation Priority for Epic Tree

### Critical Path (Must Have)
1. `EpochTree` interface and `GenericEpochTree` implementation
2. `EpochList` interface and `GenericEpochList` implementation
3. `Epoch` interface and data model
4. `GenericEpochTreeFactory.create()` - Tree building algorithm
5. Key path access (`KeyPathGetter`) for nested property access

### High Priority
1. `sortedBy()` for epoch list sorting
2. `childBySplitValue()` for tree navigation
3. `splitValues()` for getting all split parameters
4. Stimulus/Response data access

### Medium Priority
1. Keyword tagging system
2. `visualize()` tree visualization
3. `saveTree()` serialization

### Lower Priority (Can Defer)
1. CoreData integration (use different persistence)
2. Transaction support
3. Hydration system

---

## 11. Example Python/JavaScript Equivalents

### Tree Building (GenericEpochTreeFactory.create)
```python
def build_tree(epochs: List[Epoch], key_paths: List[str]) -> EpochTree:
    """Build hierarchical tree from flat epoch list."""
    if not key_paths:
        # Leaf node - return EpochList
        return EpochTree(is_leaf=True, epoch_list=EpochList(epochs))

    key_path = key_paths[0]
    remaining_paths = key_paths[1:]

    # Group epochs by value at key_path
    groups = defaultdict(list)
    for epoch in epochs:
        value = get_nested_value(epoch, key_path)
        groups[value].append(epoch)

    # Create child nodes for each unique value
    children = []
    for value in sorted(groups.keys()):
        child = build_tree(groups[value], remaining_paths)
        child.split_key = key_path
        child.split_value = value
        children.append(child)

    return EpochTree(is_leaf=False, children=children)
```

### Key Path Access
```python
def get_nested_value(obj, key_path: str):
    """Get nested property value using dot notation.

    Example: get_nested_value(epoch, 'protocolSettings.stimTime')
    """
    parts = key_path.split('.')
    value = obj
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            value = getattr(value, part, None)
    return value
```

---

*Document generated from decompiled jenkins-jauimodel-275.jar*
*Last updated: 2026-01-24*
