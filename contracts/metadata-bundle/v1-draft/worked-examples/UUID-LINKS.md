# Follow actual UUIDs through the synthetic collection

These are usable sample IDs, not placeholders or private experiment identifiers. UUID version is visible in the first character of the third group: `4` for the preserved cell ID, `5` for deterministic derived IDs. Version alone never proves authenticity.

| Entity | Complete UUID | Parent/reference |
|---|---|---|
| Dataset | `9f154d40-3cb1-5fe5-90c4-18e779bbebe3` | Publisher catalog, distinct from a DISCO project |
| Source | `a1bb3f6b-6198-5eee-89d0-7cbd5b74d307` | Logical acquisition, not an H5 byte hash |
| Cell1, source-native UUID4 | `7f4e8e7b-3a2d-4c91-8f12-0e9c28a40351` | source_id above |
| Second cell also labeled Cell1 | `cf1b8bd1-f76e-5cf6-b41d-b1ebeedc3d24` | Same source, different stable native key |
| Empty recorded cell | `629d15e0-2c4e-5fb8-a7df-e52cee34328a` | Retained despite having no epochs |
| First group | `d9637b23-5a7d-5437-a780-86326bb07fb5` | parent_id = preserved first cell |
| First block | `f7030d18-7df9-5881-8a8c-1e6bcd4c64cb` | parent_id = first group |
| CurrentStep protocol | `4dc6e2e1-f609-524e-8a8a-9120d0d2997a` | Referenced by first block and its epochs |
| Noise protocol | `d99c33ac-5a76-507f-8443-0fc7810c6f51` | Different protocol, same first cell |
| Epoch1, source-native UUID4 | `36f1dd9e-9201-4e7a-bd22-42f4b04d6152` | source_id, cell_id, group_id, block_id, protocol_id all explicit |
| Epoch2, UUID5 | `ed05a7fc-3447-588a-b974-670eef2b520f` | Same first block/cell/protocol |
| Epoch3, UUID5 | `359e389c-4164-5f17-b327-de6c209db051` | First cell, Noise protocol |
| Epoch4, UUID5 | `afe89e98-3bb6-5e30-ae84-8b197544c83f` | Second cell, CurrentStep protocol |
| First response stream | `efe9b820-a2cf-5a70-9926-0dab3fc999e7` | epoch_id = preserved Epoch1 |
| Claimed author profile | `ef675c7c-1bfb-4db4-bfd5-f3856825ba18` | Referenced by cell/epoch annotations |

Read `expected/identity-ledger.json` for every source key and exact UUIDv5 input string. Example:

```python
import json, uuid
namespace = uuid.UUID('5e0491e1-c451-4f91-9a6a-de7152831682')
name = json.dumps(['disco-id-v1','cell','session:synthetic-A/cell:2'],
                  ensure_ascii=False, separators=(',', ':'))
print(uuid.uuid5(namespace, name))
# cf1b8bd1-f76e-5cf6-b41d-b1ebeedc3d24
```

The namespace and immutable source keys persist across exports. Changing a label, dataset/source revision, JSON whitespace or raw locator does not change these IDs. Do not generate UUID4 anew on each import. The tutorial preserves already-recorded UUID4 strings exactly; UUID5 is for stable non-UUID keys. The fixed bundle_id/exported_at are reproducible fixture envelope values, not a recommendation to reuse transport IDs for different real exports.

The validator checks uniqueness, identity derivation, source ownership and link resolution. A matching label never creates a relationship. `frozen-selection.demo.json` selects Epoch1 and Epoch4 by exact UUID and retains revision r1; it is a separate teaching sidecar, NOT a DISCO import/export recipe. Actual production frozen packages additionally require their versioned fingerprints/receipts and existing APIs.
