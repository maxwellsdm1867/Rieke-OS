# Update coordination

Read [public contracts and examples](README.md), [desktop navigation](../AGENTS.md)
and [architecture](../../ARCHITECTURE.md). Three public entries preserve signed
coordination, unsigned-testing coordination and testing-specific validation.
No facade merges their trust policies. Root updater-validation remains shared by
installation, integrity and packaging; main retains channel/quit composition.

Preserve explicit download intent, provenance and cache checks, revalidation after
drain, helper readiness identity and exact quit authorization/revocation. A Ready
hint is not install authority. Testing stop-during-drain refusal is an existing
testing-coordinator behavior; signed coordination does not have that guard. Do
not add it as part of this move or claim a testing fault qualifies signed behavior.

Do not run broad test globs silently: original suites include Darwin host/archive
and installed-interpreter cases. Local public examples use injected transport,
validation and helper ports; they do not qualify actual installs or signing.
Preserve real receipt-rename fences in signed fixtures and flushReceipts in testing.
