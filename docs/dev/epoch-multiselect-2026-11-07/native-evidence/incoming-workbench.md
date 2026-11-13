# Native incoming Workbench checks, 2026-11-07

Same owned native app/project and combined business source as
`search-and-split-tree.md`. Parent imported the separately namespaced qualified
fixture `synthetic-incoming-20261107.h5`: 63 epochs, two cells, 126 responses.
The pinned protocol had 61 incoming epochs in one cell and 61 saved Main epochs.

Native review → Inspect in Workbench → expand date/cell. Plain-click epoch 1,
Shift-click 4: four highlighted rows, Merge (0), and no selected-epoch bulk bar.
Select Highlighted explicitly produced four selected epochs, Merge (4), and the
four-epoch Tag/Exclude/Include/Clear toolbar. Plain-click epoch 5 then left only
that row highlighted while the four selected targets remained.

Exclude selected from incoming additions changed exactly epochs 1–4 to excluded;
epoch 5 stayed allowed. The banner reported four left out, not pending. Include
restored those same four; all other visible rows retained their prior state.
The Merge button continued to show the selection count (4) during exclusion;
no merge was attempted, so this check does not qualify merge-button behavior
for excluded selections.

Tag `native-incoming-four` applied to the four selected epochs despite the
separate highlight on epoch 5. Read-only annotation queries over all 63 new UUIDs
confirmed exactly the first four incoming cell-A UUIDs carried this tag and the
other 59 did not. Remove reported four removed and zero tagged; a second full
63-UUID API check confirmed the tag absent everywhere.

The saved Main protocol final API receipt is identical to the pre-Workbench
Search-final receipt: same 61 UUIDs, all included, no epoch tags. No merge or
Main inclusion write was performed. The UI was handed back in Workbench with
four selected epochs, epoch 5 highlighted, all allowed and the test tag removed.

Raw receipts: `disco-incoming-native-tagged.json`,
`disco-incoming-native-removed.json`, `disco-epoch-native-workbench-final.json`.
These are native workflow checks, not final packaged-version or performance
qualification. Parent retains ownership of the active app/project and cleanup.
