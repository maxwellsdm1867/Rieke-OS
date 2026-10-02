# Draft classification of all 140 observed query fields

Draft only. Importance, queryability, indexing, default display, and reconstruction requirements are separate. No source values or application policies changed.

Counts of field paths (aliases included): {'common-navigation': 9, 'on-demand': 83, 'protocol-specific': 41, 'common-scientific': 7}

| Source field | Owner | Proposed query priority | Possible reconstruction dependency | Present / null / missing in 2,781 real epochs |
|---|---|---|---|---|
| `epoch` | epoch | common-navigation  | Review generator dependencies | 2781 / 0 / 0 |
| `date` | epoch | common-navigation  | Review generator dependencies | 2781 / 0 / 0 |
| `cell` | cell | common-navigation  | Review generator dependencies | 2781 / 0 / 0 |
| `block` | block | common-navigation  | Review generator dependencies | 2781 / 0 / 0 |
| `block time` | block | common-navigation  | Review generator dependencies | 2781 / 0 / 0 |
| `cell type` | cell | common-navigation  | Review generator dependencies | 2781 / 0 / 0 |
| `group label` | group | common-navigation  | Review generator dependencies | 2781 / 0 / 0 |
| `group` | group | common-navigation  | Review generator dependencies | 2781 / 0 / 0 |
| `protocol` | epoch | common-navigation  | Review generator dependencies | 2781 / 0 / 0 |
| `parameters/NDF` | epoch | on-demand  | Protocol-dependent | 2781 / 0 / 0 |
| `parameters/amp` | epoch | on-demand  | Protocol-dependent | 2781 / 0 / 0 |
| `parameters/backgroundIntensity` | epoch | protocol-specific visual | Protocol-dependent | 1932 / 0 / 849 |
| `parameters/canvasSize` | epoch | on-demand  | Protocol-dependent | 2781 / 0 / 0 |
| `parameters/centerOffset` | epoch | protocol-specific visual | Protocol-dependent | 2781 / 0 / 0 |
| `parameters/contrast` | epoch | protocol-specific visual | Protocol-dependent | 52 / 0 / 2729 |
| `parameters/gain` | epoch | on-demand  | Protocol-dependent | 2781 / 2781 / 0 |
| `parameters/lightPath` | epoch | on-demand  | Protocol-dependent | 2781 / 0 / 0 |
| `parameters/maskDiameter` | epoch | protocol-specific visual | Protocol-dependent | 52 / 0 / 2729 |
| `parameters/microdisplayBrightness` | epoch | on-demand  | Protocol-dependent | 2781 / 0 / 0 |
| `parameters/microdisplayBrightnessValue` | epoch | on-demand  | Protocol-dependent | 2781 / 0 / 0 |
| `parameters/micronsPerPixel` | epoch | on-demand  | Protocol-dependent | 2781 / 0 / 0 |
| `parameters/monitorRefreshRate` | epoch | on-demand  | Protocol-dependent | 2781 / 0 / 0 |
| `parameters/ndfs` | epoch | on-demand  | Protocol-dependent | 2781 / 0 / 0 |
| `parameters/numberOfAverages` | epoch | on-demand  | Protocol-dependent | 2472 / 0 / 309 |
| `parameters/onlineAnalysis` | epoch | on-demand  | Review generator dependencies | 1909 / 0 / 872 |
| `parameters/preTime` | epoch | on-demand  | Protocol-dependent | 1932 / 0 / 849 |
| `parameters/prerender` | epoch | on-demand  | Protocol-dependent | 2781 / 0 / 0 |
| `parameters/rotation` | epoch | protocol-specific visual | Protocol-dependent | 52 / 0 / 2729 |
| `parameters/sampleRate` | epoch | on-demand  | Protocol-dependent | 2781 / 0 / 0 |
| `parameters/splitField` | epoch | protocol-specific visual | Protocol-dependent | 52 / 0 / 2729 |
| `parameters/spotDiameter` | epoch | protocol-specific visual | Protocol-dependent | 75 / 0 / 2706 |
| `parameters/stimTime` | epoch | on-demand  | Protocol-dependent | 2472 / 0 / 309 |
| `parameters/tailTime` | epoch | on-demand  | Protocol-dependent | 1932 / 0 / 849 |
| `parameters/temporalFrequency` | epoch | protocol-specific visual | Protocol-dependent | 52 / 0 / 2729 |
| `parameters/trueCanvasSize` | epoch | on-demand  | Protocol-dependent | 2781 / 0 / 0 |
| `properties/bathTemperature` | epoch | common-scientific  | Review generator dependencies | 2781 / 0 / 0 |
| `metadata/cell/properties/type` | cell | common-scientific  | Review generator dependencies | 2781 / 0 / 0 |
| `metadata/group/properties/externalSolutionAdditions` | group | common-scientific  | Review generator dependencies | 2781 / 0 / 0 |
| `metadata/group/properties/internalSolutionAdditions` | group | common-scientific  | Review generator dependencies | 2781 / 2781 / 0 |
| `metadata/group/properties/pipetteSolution` | group | common-scientific  | Review generator dependencies | 2781 / 2781 / 0 |
| `metadata/group/properties/recordingTechnique` | group | common-scientific  | Review generator dependencies | 2781 / 2781 / 0 |
| `metadata/group/properties/seriesResistanceCompensation` | group | common-scientific  | Review generator dependencies | 2781 / 0 / 0 |
| `metadata/experiment/attributes/purpose` | experiment | on-demand  | Review generator dependencies | 2781 / 2091 / 0 |
| `metadata/experiment/label` | experiment | on-demand  | Review generator dependencies | 2781 / 0 / 0 |
| `metadata/experiment/notes` | experiment | on-demand  | Review generator dependencies | 2781 / 0 / 0 |
| `metadata/experiment/start_time` | experiment | on-demand  | Review generator dependencies | 2781 / 0 / 0 |
| `metadata/cell/label` | cell | on-demand  | Review generator dependencies | 2781 / 0 / 0 |
| `metadata/cell/notes` | cell | on-demand  | Review generator dependencies | 2781 / 0 / 0 |
| `metadata/cell/start_time` | cell | on-demand  | Review generator dependencies | 2781 / 0 / 0 |
| `metadata/group/end_time` | group | on-demand  | Review generator dependencies | 2781 / 0 / 0 |
| `metadata/group/label` | group | on-demand  | Review generator dependencies | 2781 / 0 / 0 |
| `metadata/group/notes` | group | on-demand  | Review generator dependencies | 2781 / 0 / 0 |
| `metadata/group/start_time` | group | on-demand  | Review generator dependencies | 2781 / 0 / 0 |
| `metadata/block/end_time` | block | on-demand  | Review generator dependencies | 2781 / 0 / 0 |
| `metadata/block/protocolID` | block | on-demand  | Review generator dependencies | 2781 / 0 / 0 |
| `metadata/block/start_time` | block | on-demand  | Review generator dependencies | 2781 / 0 / 0 |
| `metadata/epoch/end_time` | epoch | on-demand  | Review generator dependencies | 2781 / 0 / 0 |
| `metadata/epoch/label` | epoch | on-demand  | Review generator dependencies | 2781 / 2781 / 0 |
| `metadata/epoch/protocolID` | epoch | on-demand  | Review generator dependencies | 2781 / 2781 / 0 |
| `metadata/epoch/start_time` | epoch | on-demand  | Review generator dependencies | 2781 / 0 / 0 |
| `metadata/experiment/properties/experimenter` | experiment | on-demand  | Review generator dependencies | 2781 / 2091 / 0 |
| `metadata/experiment/properties/institution` | experiment | on-demand  | Review generator dependencies | 2781 / 0 / 0 |
| `metadata/experiment/properties/lab` | experiment | on-demand  | Review generator dependencies | 2781 / 0 / 0 |
| `metadata/experiment/properties/project` | experiment | on-demand  | Review generator dependencies | 2781 / 2781 / 0 |
| `metadata/experiment/properties/rig` | experiment | on-demand  | Review generator dependencies | 2781 / 0 / 0 |
| `metadata/block/parameters/amp` | block | on-demand  | Protocol-dependent | 2781 / 0 / 0 |
| `metadata/block/parameters/backgroundIntensity` | block | protocol-specific visual | Protocol-dependent | 1932 / 0 / 849 |
| `metadata/block/parameters/contrast` | block | protocol-specific visual | Protocol-dependent | 52 / 0 / 2729 |
| `metadata/block/parameters/maskDiameter` | block | protocol-specific visual | Protocol-dependent | 52 / 0 / 2729 |
| `metadata/block/parameters/numberOfAverages` | block | on-demand  | Protocol-dependent | 2472 / 0 / 309 |
| `metadata/block/parameters/onlineAnalysis` | block | on-demand  | Review generator dependencies | 1909 / 0 / 872 |
| `metadata/block/parameters/preTime` | block | on-demand  | Protocol-dependent | 1932 / 0 / 849 |
| `metadata/block/parameters/rotation` | block | protocol-specific visual | Protocol-dependent | 52 / 0 / 2729 |
| `metadata/block/parameters/sampleRate` | block | on-demand  | Protocol-dependent | 2781 / 0 / 0 |
| `metadata/block/parameters/splitField` | block | protocol-specific visual | Protocol-dependent | 52 / 0 / 2729 |
| `metadata/block/parameters/spotDiameter` | block | protocol-specific visual | Protocol-dependent | 75 / 0 / 2706 |
| `metadata/block/parameters/stimTime` | block | on-demand  | Protocol-dependent | 2472 / 0 / 309 |
| `metadata/block/parameters/tailTime` | block | on-demand  | Protocol-dependent | 1932 / 0 / 849 |
| `metadata/block/parameters/temporalFrequency` | block | protocol-specific visual | Protocol-dependent | 52 / 0 / 2729 |
| `parameters/currentSpotSize` | epoch | protocol-specific visual | Review generator dependencies | 1857 / 0 / 924 |
| `parameters/randomizeOrder` | epoch | on-demand  | Protocol-dependent | 1857 / 0 / 924 |
| `parameters/spotIntensity` | epoch | protocol-specific visual | Protocol-dependent | 1880 / 0 / 901 |
| `parameters/spotSizes` | epoch | on-demand  | Protocol-dependent | 1857 / 0 / 924 |
| `metadata/block/parameters/randomizeOrder` | block | on-demand  | Protocol-dependent | 1857 / 0 / 924 |
| `metadata/block/parameters/spotIntensity` | block | protocol-specific visual | Protocol-dependent | 1880 / 0 / 901 |
| `metadata/block/parameters/spotSizes` | block | on-demand  | Protocol-dependent | 1857 / 0 / 924 |
| `parameters/blockRepeatCount` | epoch | on-demand  | Review generator dependencies | 309 / 0 / 2472 |
| `parameters/controlMode` | epoch | on-demand  | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/firstHistoryID` | epoch | on-demand  | Protocol-dependent | 292 / 0 / 2489 |
| `parameters/frequencyCutoff` | epoch | protocol-specific mean-noise, history-noise | Protocol-dependent | 849 / 0 / 1932 |
| `parameters/history1` | epoch | protocol-specific history-noise | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/history1Mean` | epoch | protocol-specific history-noise | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/history1SD` | epoch | protocol-specific history-noise | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/history1Seed` | epoch | on-demand  | Protocol-dependent | 292 / 0 / 2489 |
| `parameters/history2` | epoch | protocol-specific history-noise | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/history2Mean` | epoch | protocol-specific history-noise | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/history2SD` | epoch | protocol-specific history-noise | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/history2Seed` | epoch | on-demand  | Protocol-dependent | 292 / 0 / 2489 |
| `parameters/historyNoiseVersion` | epoch | on-demand  | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/isControl` | epoch | protocol-specific history-noise | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/numberOfFilters` | epoch | on-demand  | Protocol-dependent | 849 / 0 / 1932 |
| `parameters/numberOfTrials` | epoch | on-demand  | Review generator dependencies | 309 / 0 / 2472 |
| `parameters/numberOfTrialsInRun` | epoch | on-demand  | Review generator dependencies | 309 / 0 / 2472 |
| `parameters/repeatsPerTrial` | epoch | on-demand  | Review generator dependencies | 309 / 0 / 2472 |
| `parameters/samplesPerBlock` | epoch | on-demand  | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/samplesPerSegment` | epoch | on-demand  | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/segmentTime` | epoch | protocol-specific history-noise | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/sequenceShuffleSeed` | epoch | on-demand  | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/shuffleSequence` | epoch | on-demand  | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/stimulusGenerator` | epoch | on-demand  | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/stimulusGeneratorVersion` | epoch | on-demand  | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/stimulusSampleRate` | epoch | on-demand  | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/target` | epoch | protocol-specific history-noise | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/targetMean` | epoch | protocol-specific history-noise | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/targetSD` | epoch | protocol-specific history-noise | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/targetSeed` | epoch | on-demand  | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/totalDurationMs` | epoch | on-demand  | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/trialNumber` | epoch | on-demand  | Protocol-dependent | 309 / 0 / 2472 |
| `parameters/useRandomSeed` | epoch | protocol-specific mean-noise, history-noise | Protocol-dependent | 849 / 0 / 1932 |
| `properties/frameTimesMs` | epoch | on-demand  | Protocol-dependent | 849 / 849 / 1932 |
| `metadata/block/properties/frameTimesMs` | block | on-demand  | Protocol-dependent | 483 / 0 / 2298 |
| `metadata/block/parameters/controlMode` | block | on-demand  | Protocol-dependent | 309 / 0 / 2472 |
| `metadata/block/parameters/frequencyCutoff` | block | protocol-specific mean-noise, history-noise | Protocol-dependent | 849 / 0 / 1932 |
| `metadata/block/parameters/history1` | block | protocol-specific history-noise | Protocol-dependent | 309 / 0 / 2472 |
| `metadata/block/parameters/history2` | block | protocol-specific history-noise | Protocol-dependent | 309 / 0 / 2472 |
| `metadata/block/parameters/numberOfFilters` | block | on-demand  | Protocol-dependent | 849 / 0 / 1932 |
| `metadata/block/parameters/numberOfTrials` | block | on-demand  | Review generator dependencies | 309 / 0 / 2472 |
| `metadata/block/parameters/repeatsPerTrial` | block | on-demand  | Review generator dependencies | 309 / 0 / 2472 |
| `metadata/block/parameters/segmentTime` | block | protocol-specific history-noise | Protocol-dependent | 309 / 0 / 2472 |
| `metadata/block/parameters/shuffleSequence` | block | on-demand  | Protocol-dependent | 309 / 0 / 2472 |
| `metadata/block/parameters/target` | block | protocol-specific history-noise | Protocol-dependent | 309 / 0 / 2472 |
| `metadata/block/parameters/useRandomSeed` | block | protocol-specific mean-noise, history-noise | Protocol-dependent | 849 / 0 / 1932 |
| `parameters/currentMean` | epoch | protocol-specific mean-noise | Protocol-dependent | 540 / 0 / 2241 |
| `parameters/currentSD` | epoch | protocol-specific mean-noise | Protocol-dependent | 540 / 0 / 2241 |
| `parameters/interpulseInterval` | epoch | on-demand  | Protocol-dependent | 563 / 0 / 2218 |
| `parameters/seed` | epoch | on-demand  | Protocol-dependent | 540 / 0 / 2241 |
| `parameters/stdv` | epoch | on-demand  | Protocol-dependent | 540 / 0 / 2241 |
| `metadata/block/parameters/currentMean` | block | protocol-specific mean-noise | Protocol-dependent | 540 / 0 / 2241 |
| `metadata/block/parameters/currentSD` | block | protocol-specific mean-noise | Protocol-dependent | 540 / 0 / 2241 |
| `metadata/block/parameters/interpulseInterval` | block | on-demand  | Protocol-dependent | 563 / 0 / 2218 |
