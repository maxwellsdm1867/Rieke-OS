# Metadata reads and disposable generations

Start with the [canonical contract](CONTRACT.md). Import the named leaf module
for the responsibility you need; this package initializer is inert. There is no
combined metadata facade, new factory or export demotion. The existing reader,
query, object encoding and lease interfaces retain separate lifetimes.

[Shared authority and trace KEEP decisions](KEEP.md) explain why state generation,
protocol-state proof and source-verified trace composition stay outside this folder.
[Backend navigation](../../AGENTS.md) locates adjacent scientific owners.

Preserve scientific types/order/units, exact scope and revision identity, source
witness ordering and paired native/typed leases. Tests never replace server/native
proof. Read the contract's scoped checks before running anything; native, HTTP,
crash/process, qualification and aggregate lanes remain separate.
