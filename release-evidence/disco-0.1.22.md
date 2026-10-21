Disco 0.1.22 improves incoming-data review, merge recovery, and metadata refresh.

- Overview and Import Review use the same pending-data card, merge action, and Undo controller. Hold to merge all merges directly in place; only Inspect in Workbench opens Workbench.
- Finish reviewing uses a shared confirmation across Overview, Import Review, and Workbench. Undo restores the completed pending review without undoing earlier Main merges.
- Import Review closes after a confirmed merge or review completion so Undo is immediately usable. Hidden review dialogs release their modal state when navigation changes.
- Workbench confirms selected merges, handles empty and partially merged queues, restores pending counts after Undo, and keeps recovery and saved review sessions associated with their original author.
- Delayed startup prefetch preserves freshly loaded protocol summaries and avoids an unnecessary read or stale presentation.
- Metadata refresh is explicit, and stale epoch lists renew through their read owner. Cleared or already-merged epoch focus does not reopen obsolete review data.

Native click-through covered direct import and Overview merges, Finish reviewing, Undo, explicit Workbench navigation, and the all-merged empty state. Final release qualification is tied to the exact tagged source and packaged archive; local predecessor checks are not substituted for those receipts.

This release uses the existing unsigned Apple silicon testing channel. It targets macOS 14 and later; macOS 14 runtime support remains unqualified and Intel is unsupported. It is not Developer ID signed or notarized and is not a stable production release.
