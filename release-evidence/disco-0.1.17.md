Disco 0.1.17 improves large-trace inspection and protects the improvement with regression checks.

- Whole-epoch traces display through bounded geometry while cursor and zoom retain exact recorded samples.
- Foreground trace work receives appropriate worker scheduling, reducing intermittent stalls during epoch changes.
- Trace loading and prepared-view handling avoid redundant requests and stale empty displays.
- Successfully opening a project closes the completed setup dialog in its originating view, including when returning to a retained project.
- Saving tags preserves Workbench rows, highlights and navigation while scientific read authority refreshes. Hidden selected views defer renewal until reopened.
- macOS and Linux regression checks verify exact geometry and cursor values, foreground execution, and draw/frame latency. The macOS comparison prepares both versions before alternating samples between independent pre-started browsers, retaining the existing correctness and timing limits. Publication requires the matching successful trace proof.

Use **App Updates → Check for updates → Download update**, then **Restart to update** when ready. This release uses the existing unsigned Apple silicon testing channel. It is not Developer ID signed or notarized, and does not claim production or universal macOS-version qualification.

The local installed-app measurements demonstrated million-sample drawing below 50 ms. Hosted browser checks enforce matched relative regression limits; they do not establish an absolute 50 ms guarantee across machines.
