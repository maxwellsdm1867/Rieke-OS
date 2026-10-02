# Scientific dashboard UI

Disco should read like a scientific instrument: show the current scope, trustworthy measurements, and the next available actions before explanatory prose. Reuse the import view's quiet surfaces, accent line icons, thin dividers, and compact rows across Workbench, imports, data stores, and navigation.

## Measurements and navigation

- Pair every count with its unit and scope: cells, epochs, sources; main, incoming, selected, or one proposal. Use the authoritative response for that scope. Never sum overlapping proposals or infer pending counts from imported totals.
- Distinguish a reported zero from an unavailable count. Keep units visible; use tabular numerals and a consistent size hierarchy. A metric is useful only if it helps a decision or opens the corresponding scoped cell/epoch view.
- Reuse existing import summaries, sidebar badges, and source links before adding another summary. Show source context only when the current response supplies it. Do not fetch data just to decorate a header.
- Keep metric and action positions stable during refresh. Preserve the current display with a visible loading or stale notice when appropriate; do not present a retained receipt as fresh authority.

## Compact controls

Put related metrics and direct actions in a slim top bar, with selection and inspection immediately below. Use existing theme tokens and restrained separators, not a stack of summary cards. Keep primary review/explore, merge previews, export, and cancel discoverable. Wrap control groups at narrow widths without clipping labels or pushing content outside its container.

Use meaningful icons with text labels. Hide redundant decorative icons from assistive technology; icon-only controls need accessible names. Every action and disclosure must work by keyboard with a visible focus indicator. A drill-down must keep its promised scope.

Routine explanations belong in a native disclosure: count deduplication, draft behavior, shared tags, revision IDs, and provenance detail. Errors, stale authority, uncertain operations, recovery controls, and exact-scope confirmations remain visible when relevant. Reducing words must never conceal an operational risk or change an action's meaning.

## Workbench reference pattern

The earlier Needs review view stacked a page introduction, deduplication paragraph, cumulative heading, snapshot explanation, draft explanation, version line, and action rows above the inspector. The replacement uses:

1. The existing Workbench tab supplies the workspace title; do not repeat it above the data.
2. One incoming band combines a small scope badge and distinct pending cell/epoch counts alongside Review / Explore, Merge selected epochs, Merge all, Export, Merge & export, and Cancel.
3. Small selection controls and a Review details disclosure, followed immediately by the existing browser.

Merge labels map only to the existing additive acceptance route and its exact preview/confirmation. Main and incoming remain separate. Cancel leaves the draft pending; it cannot undo a submitted operation. Review decisions, shared tags, frozen cohorts, receipt recovery, and export idempotency retain their existing semantics.

Validate changes against a real rendered screen in light, dark, and narrow layouts, including keyboard disclosure/focus, zero and unavailable counts, stale/error/recovery states, and repeated navigation/loading. Visual polish must not introduce scientific mutations or extra decorative requests.
