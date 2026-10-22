Disco 0.1.23 fixes incoming review becoming unusable after repeated merge and Undo cycles.

- Merge all, merge selected epochs, and Finish reviewing can each be undone repeatedly. Undo restores the pending epochs and counts so review, selection, and merging remain usable.
- Undo history validation stops at the review's actual baseline instead of incorrectly rejecting a valid restored review as unrelated.
- Finish reviewing prepares its context after pending writes settle. Lost completion replies retain the original operation for receipt recovery; retrying does not create a different completion.
- Refresh review renews an invalid candidate. Rejected requests no longer claim that draft changes may already have been saved, and the same error is not shown twice. Dismissible command errors expire; genuine uncertain operations retain recovery controls.
- Automatic renewal avoids temporary error banners. Finish reviewing preserves the local selection when the same candidate is restored by Undo, while fresh server context remains required before another action.

- Completed Undo receipts no longer keep obsolete review contexts in saved workspace history. The existing size limit remains unchanged, and unfinished merge, Finish, and export operations retain their recovery records.
- Overview renews invalidated summaries even when their identity is unchanged, preventing an indefinite Updating state after Undo. Hidden views remain paused.
- Finish reviewing reads current candidate context after preparation, so an immutable preparation receipt from before repeated Undo cannot supply stale submission fences.

Two final native rounds on the existing Single Spot data covered merge all / Undo, selecting two epochs / merge / Undo, and Finish reviewing / Undo. Exact pending counts and epoch UUIDs returned to the starting state; Finish Undo also restored the two selected rows. The user then clicked through the app and approved the behavior. Full frontend regression passed all 1,543 tests on fix commit `0ffe4f4`. These checks precede the 0.1.23 version bump; final CI, packaged archive, and updater-install evidence must remain attributed to their exact source and artifacts and are not claimed here.

This release uses the existing unsigned Apple silicon testing channel. It targets macOS 14 and later; macOS 14 runtime support remains unqualified and Intel is unsupported. It is not Developer ID signed or notarized and is not a stable production release.

The final follow-up also passed two native merge-all/Undo cycles with automatic Overview renewal, Finish/Undo through Overview and Import H5s, and orderly saved-view shutdown/restoration. The affected saved view returned below its original 2 MiB bound without changing scientific membership. Final CI and packaged qualification must identify the follow-up source rather than the superseded first candidate.

Final local frontend regression passed all 1,552 tests. The final architecture metadata, Python, JavaScript and 261-module lifecycle checks also passed before candidate packaging.
