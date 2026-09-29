# MATLAB tree generator: executable contract

The app does not call an LLM to build a tree or generate MATLAB code. It validates
a recorded-field recipe, groups exact typed values, and formats a fixed function
call. Protocol suggestions are explicit rules over the recorded metadata catalog.
Arbitrary analysis functions or stimulus reconstruction are not generated.

## Construction and sequencing

`workspace_tree_code.py` emits the command. `workspace_matlab.py` freezes the exact
members, semantic field mapping, sibling order and epoch sequence in `recordings.mat`.
The shipped `launchWorkspaceTree.m` validates those mappings, constructs an
`epicTreeTools` tree through its existing recursive `buildTree` implementation,
restores declared sibling order, and orders each leaf by the exported UUID sequence.
Root `allEpochs` and `epochIndex` retain their original order for mask identity.

The copied command uses real recorded field IDs. A combination is a nested cell
array, for example `{'cell', {'parameters/history1','parameters/history2',
'parameters/target'}, 'block'}`. Percent-encoded combination IDs and generated
`workspaceGrouping.gNNN` paths are implementation details. Exported display
metadata gives native tree nodes readable field names, dated cells, block times
and exact parameter values without changing their grouping identities.

The legacy equivalents of a sequencer are the epoch-tree factory, its ordered
splitters and sibling comparator, and epoch-list sorting. There is no separate
Sequencer class in this checkout. Grouping order and temporal epoch order are
distinct and are tested separately.

The audit found that MATLAB's automatic `datenum` cannot parse the source's
`MM/DD/YYYY HH:MM:SS:ffffff` timestamps. Its fallback silently kept hierarchy
order. New exports use an explicit chronological UUID sequence with a UUID
tie-break, matching the web tree without floating-point timestamp conversion.
Older exports without this sequence warn and retain legacy ordering; re-export
to obtain the new contract. Composite settings remain one exact typed grouping
key, avoiding the legacy splitter's numeric-array collapse and scalar rounding.

## Selections and source integrity

The adjacent `selection.ugm` must match the complete export UUID set. Selection
state is refreshed after constructing child nodes, so excluded branches do not
appear selected. Workspace GUI Save and close/save use the same adjacent mask;
the generated command reloads it. Saves use a temporary file and replacement,
preserve export provenance, and reject mismatched UUID membership. They do not
search global or same-basename masks. The original ZIP and H5 remain unchanged.

Workspace response references now carry SHA-256. The MATLAB lazy reader checks
the source before returning data and rejects changes during verification/read.
It caches digests for at most 32 canonical files using file identity, size and
precise timestamps. On macOS, native `stat` supplies the precision missing from
the older bundled JVM. Nonempty cached waveform fields cannot bypass verification.
Legacy non-workspace responses retain their prior behavior. GUI failures clear
the previous trace and display the integrity error instead of leaving stale data.
The first read hashes the file; subsequent unchanged-source reads reuse the digest.

## Repeating the native check

Run the CLI in the project's Python environment with MATLAB available:

```sh
python python/verify_workspace_matlab.py \
  --project-dir /path/to/managed/project \
  --protocol PROTOCOL_UUID \
  --matlab /Applications/MATLAB_R2022a.app/bin/matlab
```

Use `--splits ''` to test a flat layout, or supply a saved split order. `--output`
must name a new directory; otherwise a temporary verification directory is used.
`--prepare-only` emits the disposable bundle and oracle without launching MATLAB.
The CLI reads a starter protocol query for a generator fixture. It does not load
applied working-set bindings or current curation providers and does not publish
an export or modify project records. Separate HTTP tests cover saved query,
curation, download, and recipe reuse boundaries.

The production writer generates a ZIP, which is extracted to a path containing
spaces and an apostrophe. `tests/verify_workspace_generated_bundle.m` executes
both actual shipped scripts, unchanged, from another moved directory. It checks:

- Every ordered branch path and within-leaf UUID sequence against the web oracle.
- No omitted/duplicated epochs, extra grouping levels, or changed root mask indices.
- Shuffled mixed UUID masks, node/GUI checkboxes, and all-excluded selections.
- Visible native GUI and plotted samples/rate matching direct source H5 reads.
- Workspace GUI mask saving, reopening the generated script, and provenance.
- Invalid fields, mappings, sequence metadata and mismatched mask rejection.

Only test-owned figures and disposable masks/files are changed. The native proof
JSON and screenshots are retained alongside each moved verification bundle.

## Verified on 2026-09-27

MATLAB R2022a executed both unchanged generated scripts in three fresh cases:
history noise (101 epochs / 27 leaves), mean noise (520 / 20), and flat mean noise
(520 / one leaf). All passed exact chronological membership, friendly display
labels, GUI creation, H5 sample parity and mask save/reopen checks. The history
trace had 200,000 samples at 10 kHz; mean-noise traces had 5,000 samples. Readable
labels replace UUIDs/encoded tuple values, though long combined labels can still
extend beyond the native tree pane's width; the full text remains intact.

Fourteen native helper tests and eight integrity tests passed, including an
actual graph-selection callback that first displays a trace, detects an immediate
same-size source mutation, clears stale lines and shows the checksum error.
Python: 256 tests plus 159 subtests. React: 59 tests and production build.
Detailed retained evidence: `matlab_generator_e2e_results.json`.
