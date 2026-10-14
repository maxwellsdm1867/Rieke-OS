# Cell identity placement

Approved after the standalone QC, column and hierarchy previews. Built on local
combined source `6b81372`; live main was checked at `8cd6182`. This is source work,
not an installed app or 0.1.13 package.

CellTypeIcon appears in Cell QC beside the recorded type, and on exact `cell` and
`cell type` branch levels in columns, hierarchy, Edit Tree and full-tree preview.
Other grouping levels and combined-field nodes retain existing presentation.
Missing type uses the approved neutral unknown glyph. Labels never infer identity.

The shared TreeBranchIcon uses 22px tree icons; QC uses 28px. Existing text, arrows,
selection fill, exact UUIDs, membership and freshness remain authoritative.
The backend carries optional recorded cell_type through the existing representative
rendering; no extra requests, full-project scans, H5 reads or summary work are added.

Independent source review found no blocking issues: the backend adds display-only
metadata in the existing row loop, and renderer changes add no hooks/effects or
request/selection ownership. The lifetime receipt checks unchanged effect sites.
A new exact projection compatibility vector preserves the prior reviewed legacy
contract; the historical receipt remains intact. Cache contents are not resealed.

Focused checks cover exact level restriction, label non-inference, neutral unknown,
mounted browsing/Edit Tree/QC, paged/ancestor/counts-only metadata and existing
navigation/selection behavior. Final source gates and their exact receipts are
reported separately after the implementation commit.
