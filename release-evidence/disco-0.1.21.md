Disco 0.1.21 combines the robustness and decoupling work into one release.

- Ordinary navigation, tagging, curation and Workbench reads reuse target-scoped state instead of repeatedly rebuilding whole-project state. Traces retain their source identity through unrelated edits, and Edit Tree keeps its presentation when focus changes.
- Workbench merge and undo use membership deltas. Left-out epochs remain excluded, failed merges preserve the prior decision, and undone additions cannot be exported as accepted.
- Query building no longer launches previews or statistics. Run shows results first, followed by one background summary; cell lists are paged and pending totals are shown explicitly.
- Project recovery, draft ownership, export staging and preference-save retries receive correctness fixes. Batch curation writes preserve exact membership and avoid no-op revisions.
- Electron 44.9.2 and updated certificate bundles retain the eMudhra security changes from the local 0.1.20 candidate. The Python backend uses the bundled certificate trust store.

This uses the existing unsigned Apple silicon testing channel. It is not Developer ID signed or notarized and does not claim production or universal macOS-version qualification. Exact-source regression, performance and packaged checks must pass before this draft is published.
