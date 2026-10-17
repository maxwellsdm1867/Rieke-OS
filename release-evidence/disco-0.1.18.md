Disco 0.1.18 makes merging newly imported data simple, reliable and fast.

- New data is the difference between your newest imports and a protocol's main dataset. Only recordings main has not seen are offered; epochs you reviewed and left out earlier are never offered again. Re-running a search predicate remains the explicit way to compare everything.
- The Review imported data dialog, the protocol Overview card and Workbench show the same pending data for each protocol. Everything shown can be merged.
- **Hold to merge all** on the Overview card or in the import review merges every pending epoch of a protocol in one step. Workbench still lets you pick individual epochs, and **Finish review** leaves the rest out.
- A corner **Undo** restores main exactly after a merge, while main has not changed since.
- Fixed merges that were refused with "Merge was not submitted" because the saved view grew too large, proposals stuck at "Conflict requires review" after a query was saved again, and the Overview merge button opening Workbench instead of merging.
- Protocol entries accept the same protocol name recorded by another lab; pinned protocols keep every protocol they span.
- Merging is much faster: on a 755-epoch real project, merge all went from about 7 s to under 1.5 s, undo to about 0.15 s, and pending counts read in about 0.2–0.3 s.

Use **App Updates → Check for updates → Download update**, then **Restart to update** when ready. This release uses the existing unsigned Apple silicon testing channel. It is not Developer ID signed or notarized, and does not claim production or universal macOS-version qualification.
