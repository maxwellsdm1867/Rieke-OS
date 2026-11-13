# Native Search and split-tree checks, 2026-11-07

Owned native app: `org.riekeos.native-import-selection-checks` at
`/private/tmp/disco-retention-native-refresh-gELswh/Disco Native Checks.app`.
Owned project: same task root, `home/project`. Combined business source matches
parent `1ea5c1b`; test shell still identifies 0.2.10, and this is not packaged
0.2.11 qualification. UI interactions used native AX clicks and modifier keys.

Search began with epochs 1–4 selected and an annotation-stale banner from the
previous native tag-removal check. Refresh results restored action availability
and retained the four selected epochs. Exclude changed exactly epochs 1–4 to
excluded. A single Undo restored all four and displayed “Last edit undone”.
A second Exclude followed by Include restored the same four, with selection
retained throughout.

Switching to Split tree retained four selected rows and the counted toolbar.
Plain-click epoch 6 then Shift-click 11 selected six rows. Command-click epoch 8
removed only that row, yielding five. The counted toolbar Exclude changed only
6, 7, 9, 10, 11; Include restored those five. Epoch 8 and other rows stayed
included. Native view was handed back with five selected and all rows included.

A read-only API receipt after these Search-local operations confirms the saved
Main protocol still contains 61 epochs, none excluded and no epoch tags. See
`disco-epoch-native-search-final.json`. Earlier Main action receipts copied here
retain exact UUID sets for the independently completed Main tests. API reads
verified the owned process and project before using its capability internally;
no capability was written into these receipts.

Parent owns remaining import/Workbench checks and final benchmark/package
qualification. The running native app and project remain needed for those checks.
