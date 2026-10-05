# HTTP mutation recovery owner

Read the [canonical public contract](CONTRACT.md) before editing. It defines the
single public interface, adapters, ordering, errors and executable HTTP examples.
Use [backend navigation](../../AGENTS.md) for adjacent owners and the
[adoption record](../../../docs/architecture/0.1.8-first-port-slices.md#mutation-recovery-completion)
for cross-owner obligations.

Callers and conformance tests import `disco.recovery`; implementation imports
stay inside this folder. Keep ancestor initialization inert. Do not add a shim,
eager registration, private-test exceptions or new transaction authority. Preserve
all existing 13 local case identities and both central integration suites.
