# File and folder selection

Start with [folderBrowser.js](folderBrowser.js) for absolute paths, 200-row folder pages and
`browseFolder`. It accepts the existing native bridge, request and dialog adapters.
[ui/FolderBrowserDialog.jsx](ui/FolderBrowserDialog.jsx) exports the dialog and `openFolderBrowserDialog`;
[ui/FolderPathInput.jsx](ui/FolderPathInput.jsx) binds the read-only path field to that chooser.
[ui/BrowseFilesButton.jsx](ui/BrowseFilesButton.jsx) handles browser file input. Choosing a path or files
never creates, restores, transfers or ingests them.

## Contracts and dependencies

Paths must be absolute and contain no NUL; trailing slashes normalize except root.
New names refuse empty names, dot-only names, slash/control characters and lengths
over 255. A listing needs complete typed pagination/location facts, safe counts
and a forward next offset. Native cancellation returns null; native errors remain
errors. New/create selection preserves the parent/name distinction, and incomplete
text is only an initial navigation hint. Selection is not filesystem authorization.

Dialog reads retain their existing cancellation/publication guards. Dynamic dialog
creation resolves once and releases its React root/host in a microtask. The path
input suppresses late updates after unmount and restores button focus when the
chooser finishes. Preserve the native/browser choices, purpose flags and caller
onBusyChange behavior without a new lifecycle abstraction.

Path composition is in-process; browser/native chooser controls are
local-substitutable and folder listing is remote but owned. KEEP path validation,
dialog hosting and field binding as distinct entries. Deleting path policy would
repeat validation across callers, while one combined UI/filesystem owner would
make a read-only choice appear to authorize creation. Existing injected adapters
are sufficient; no replacement port is introduced.

## Executable public examples

[folderBrowser.test.js](folderBrowser.test.js) supplies native/dialog/request adapters and checks exact
paths, cancellation, new names and incomplete listings. The retained mounted test
checks the real field lifecycle without opening a native picker.

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/file-picker/folderBrowser.test.js src/folderPathInputLifecycle.test.js
```

## Change and evidence procedure

Use the named file entries directly. Each keeps its existing exports and caller
contract; no barrel, forwarding layer or private demotion is introduced. The goal
is a clear interface with progressive disclosure of the responsibilities below,
not fewer exports or fewer lines. Co-location improves locality; moving these files
does not by itself establish deeper behavior or a performance improvement.

Read the relevant entry and executable public examples before editing. Preserve
identity, scientific meaning, errors, ordering and lifetime. Review any proposed
contract or runtime behavior change before implementation. Keep the existing tests
and their public interfaces; do not import test support into production. Root
integration owns catalog/ledger/navigation updates and aggregate frontend checks.
Run the listed commands from `workspace-app`, with `RIEKE_TEST_DOM_MODULE` unset,
only in the coordinated test lane. Native/packaged behavior, actual ingestion,
backend durability and performance remain separately qualified; these examples
use owned synthetic values and do not authorize deferred/native fixtures.
