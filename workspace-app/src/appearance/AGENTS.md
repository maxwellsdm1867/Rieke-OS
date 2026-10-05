# App appearance

[appearanceThemes.js](appearanceThemes.js) owns the named theme choices, normalization/cache, system
scheme subscription and DOM application. [appAppearance.js](appAppearance.js) exposes
`useAppAppearance`, `iconSource` and `applyBrowserIcon`. [ui/AppAppearance.jsx](ui/AppAppearance.jsx)
exports the dialog, `ThemePicker` and `AppearanceButton`. The server preference,
browser appearance and desktop icon remain distinct outcomes.

## Contracts and dependencies

Retain system/light/dark/fred identities and the legacy bright/icon normalization.
Browser cache failure does not replace the server preference. System appearance
attaches/removes its change listener; DOM changes preserve theme/appearance data,
color scheme, theme-color and existing appearance event behavior. Icon source
paths remain the existing packaged assets.

The hook gates choices while loading/writing. It publishes a tentative choice,
rolls back failed persistence, and retains a successfully saved theme when only
the desktop icon fails. Load, save and icon error phases remain distinct. Preserve
its current mounted load fence, request injection and writing serialization; this
move adds no new cancellation guarantee or preference lifetime.

Normalization is in-process, DOM/storage/media are local-substitutable, and owned
appearance/desktop bridge calls use their existing adapters. KEEP these entries:
one controller for all effects would make theme-only consumers learn persistence
and desktop icon error semantics. Removing normalization repeats compatibility
policy rather than eliminating complexity.

## Executable public example

The colocated test mounts the real hook with controlled request/bridge adapters and
checks saved preference versus desktop icon failure, browser cache and load gating.

```sh
node --import ./src/test-support/reactTestEnvironment.js --test src/appearance/appAppearancePersistence.test.js
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
