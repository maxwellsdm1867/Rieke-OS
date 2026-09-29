# Search selections and pinned protocols

From search results, **Export** offers three choices:

- **Export directly** writes SQLite or EpicTree/MATLAB output without updating a pinned dataset.
- **Update pinned protocol** compares the saved selection with an existing working dataset. Every candidate epoch must have the exact recorded acquisition Protocol ID required by that destination's original definition. Matching display names or broad `contains` predicates are not identity evidence. A matching selection may be smaller because of tags, dates, cell types, or settings. The popup shows the diff and requires acknowledgement of removals before enabling the update.
- **Create pinned protocol** names a new working dataset from the saved selection. It requires one recorded Protocol ID and at least one epoch. Mixed results must be narrowed first. The original pinned datasets are unchanged.

An update replaces working membership with the reviewed selection; it is not an automatic union. Original H5 data and shared tags are retained. Existing per-protocol curation is still addressed by epoch UUID. Creating a new protocol does not copy another protocol's inclusion mask or dataset-only tags; shared cell/epoch annotations remain linked through their exact UUIDs.

The backend independently validates acquisition identity before applying an update and again before publishing a protocol export. This protects against stale clients and previously created mismatched bindings. The normal source, annotation, query and binding revision checks also apply. A direct export has no pinned destination identity and may contain mixed acquisition protocols.

New protocol definitions are saved under `protocols/<uuid>.protocol.json`, with the exact original Protocol ID and an immutable initial selection revision. The binding and audit event commit together. Retry identity is derived from project UUID, selection revision UUID and normalized name, so retrying the same creation does not produce duplicate protocols. If publication is interrupted before the initial binding exists, that manifest cannot fall back to exporting the unrestricted base query. Repeating creation from the same selection and name repairs that incomplete creation.

Sidebar pin preferences are local to the browser; the protocol manifest, selection, binding and audit history are project data. If saving the sidebar pin fails, the UI offers a pin-only retry without reapplying the dataset.
