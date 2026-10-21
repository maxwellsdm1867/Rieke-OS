Disco 0.1.23 fixes incoming review becoming unusable after repeated merge and Undo cycles.

- Merge all, merge selected epochs, and Finish reviewing can each be undone repeatedly. Undo restores the pending epochs and counts so review, selection, and merging remain usable.
- Undo history validation stops at the review's actual baseline instead of incorrectly rejecting a valid restored review as unrelated.
- Finish reviewing prepares its context after pending writes settle. Lost completion replies retain the original operation for receipt recovery; retrying does not create a different completion.
- Refresh review renews an invalid candidate. Rejected requests no longer claim that draft changes may already have been saved, and the same error is not shown twice. Dismissible command errors expire; genuine uncertain operations retain recovery controls.
- Automatic renewal avoids temporary error banners. Finish reviewing preserves the local selection when the same candidate is restored by Undo, while fresh server context remains required before another action.

Two final native rounds on the existing Single Spot data covered merge all / Undo, selecting two epochs / merge / Undo, and Finish reviewing / Undo. Exact pending counts and epoch UUIDs returned to the starting state; Finish Undo also restored the two selected rows. The user then clicked through the app and approved the behavior. Full frontend regression passed all 1,543 tests on fix commit `0ffe4f4`. These checks precede the 0.1.23 version bump; final CI, packaged archive, and updater-install evidence must remain attributed to their exact source and artifacts and are not claimed here.

This release uses the existing unsigned Apple silicon testing channel. It targets macOS 14 and later; macOS 14 runtime support remains unqualified and Intel is unsupported. It is not Developer ID signed or notarized and is not a stable production release.
