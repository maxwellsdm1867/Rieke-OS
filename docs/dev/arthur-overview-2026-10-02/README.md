# Arthur overview UI delta

Base: published candidate `6dc6e888e992ea931c8972ead94036bea7091736`. Independent branch `codex/arthur-overview-cells` at `/tmp/rieke-arthur-overview`; active E2E checkout and manual playground stay owned by their existing tasks.

Project cells start collapsed behind a keyboard-accessible button. Date/type filters reveal and focus the list toggle, retaining the reduced-motion scrolling behavior. Collapsing preserves row details and page state. Source register and source recording availability are unchanged.

Project and protocol summaries derive exact distinct counts from authoritative `cells` DTO UUIDs. Cell labels never serve as identity, and epoch facet counts never serve as cell counts. Unknown/unclassified/missing types retain visible buckets; recorded labels are preserved. Matching scope, export participation, selection callbacks and summary request contexts stay intact.

Cell type colors use the established Wong palette from retinaSRM `analysis_exports/fit_quality_floor_distance_2026-06-02/fig_fit_quality.m` lines 43–54 (mirrored there from poster `style.typ`): OFF midget #e69f00, ON midget #d55e00, OFF parasol #56b4e9, ON parasol #0072b2. Color matching accepts RGC namespace and spacing/hyphen forms without rewriting recorded labels. Unsupported types use theme neutral ink. All color values live in `themes.css`; text/focus/surfaces continue using theme roles. Colors supplement exact labels/counts.

The existing NeuronIcon replaces people glyphs in these cell summaries and rows. The shared compact donut/legend retains an accessible text description, exact counts, type filtering on project overview, and protocol export participation counts.

[QC/import read-only findings and proposed context design](QC_IMPORT_SEAMS.md).

Validation results and rendered proof will be recorded after the E2E owner releases the serial test/render window. No package build, push, merge, live database write or import policy change is part of this task.

Dataset priority: experimental protocol overview keeps **Recordings in this protocol** first and shares the collapsed cell-list control. Its current query/view filters drive the matching infographic. Opening inspection and cell-specific inspection keep their existing callbacks and scopes.

Review-workflow design note (no semantics implemented): place new incoming/imported epochs in a temporary inspection/review workspace based on immutable pending candidate/revision mechanisms. Inspect and tag that branch, then explicitly preview the diff against the main pinned protocol and merge a reviewed selection with undo. Ordinary tag edits must not silently widen membership. Source/annotation/binding revision checks, exact acquisition identity, removal acknowledgement and audit history must remain authoritative. The separate architecture owner is investigating the safe merge contract; this UI delta only changes presentation.
