# Post-import readiness summary

The Add data store workbench now places saved protocol proposals above the next-file import form. Pinned protocol preferences are shared with the sidebar and update immediately when pinning changes.

Each proposal shows source identity, current→proposed cells, added epochs, net recorded time, affected recording dates, retained/added membership bar, and readiness state. Dates come from the bounded affected-cell detail (truncation is labeled). Counts are not summed across overlapping protocol selections.

Add matched data reuses the existing guarded comparison/apply flow. The current binding version and query revision are rechecked before any write; a changed comparison must be shown before the next click. Applied proposals retain their visual receipt with Add disabled. Stale proposals require refresh; a pinned protocol without a candidate says no pending proposal rather than inferring zero matches or a successful query check.

The headline source summary refers to the latest completed import. Individual proposals retain their own source name/time, including outstanding proposals from earlier imports. Exports remain separate protocol actions. Import-job warnings and diagnostic history remain visible.

Validation:79 frontend tests and production build passed. Live UI checked against the Sep23 source (5cells/690epochs), three pending support-protocol updates and the already-applied History update. Existing data memberships were not changed during this presentation update.
