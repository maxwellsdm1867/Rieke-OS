Disco 0.1.19 makes tagging instant and cuts repeated reads across the app.

- Tags are their own channel. Adding or removing a tag shows in the same frame, with one write and no reload, refetch or flicker. This applies to single epochs, Shift/Command multi-selections, whole Edit Tree branches, Edit Tree epoch rows and cell tags. Filters by tag work immediately afterwards.
- Clicking a cell targets cell tags; clicking an epoch targets epoch tags. Cell tags, epoch tags and effective tags stay separately filterable.
- Tag chips show only the name. Author and the time the tag was added appear in the tooltip. Filter view → Tag rules can now limit a tag to **Added after** and **Added before** a time. Tags from before this version show an approximate time.
- The tag box suggests existing tags as you type: grey completion accepted with Tab, and a dropdown with the matched text highlighted that Up/Down can navigate. New tags are suggested at once.
- Other people's tags and imported tags no longer reload or invalidate Workbench.
- Search, predicate fields and the project Overview reuse their results until something they depend on changes. Cell QC opens faster, and whole-epoch traces load in one binary read.
- The protocol Overview now matches the project Overview, with consistent storage sizes across pages.
- App-state recovery copies only what changed at each save instead of rebuilding the whole mirror.

Use **App Updates → Check for updates → Download update**, then **Restart to update** when ready. This release uses the existing unsigned Apple silicon testing channel. It is not Developer ID signed or notarized, and does not claim production or universal macOS-version qualification.
