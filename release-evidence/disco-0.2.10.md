# Disco 0.2.10 testing

This unsigned Apple silicon testing prerelease includes the Cell QC updates from
local builds 0.2.8–0.2.10 and strengthens shutdown evidence.

- Bath temperature readings display in Celsius, with warnings below 25 °C.
- Cell QC has a compact identity header and protocol/trial navigation.
- Searching a cell UUID opens Cell QC. Searching an epoch UUID opens its owning
  cell with that exact epoch, protocol and page selected and visible. Tagging is
  available there; Back/Forward restores each visit.
- Shutdown requires a positive stop acknowledgement and normal exit of the owned
  backend before releasing its session or authorizing replacement. Failed stops,
  crashes and signal exits preserve recovery evidence. An exited backend's former
  port is no longer used for control requests.
- Quitting during startup cancels any not-yet-started backend, preventing a late
  spawn after the app has closed.
- The shutdown hardening adds no waiting period and leaves existing deadlines
  unchanged. It does not force-stop scientific writers or unrelated sessions.

Publication uses the exact immutable candidate archive after full regression,
million-row comparisons and packaged native qualification. The published
qualification summary records the source, run IDs, archive hashes and outcomes.

This remains an unsigned, unnotarized macOS arm64 testing prerelease. Intel,
signed-updater and universal macOS support are not qualified. Use the in-app
App Updates workflow to download, verify and restart into the published build.
