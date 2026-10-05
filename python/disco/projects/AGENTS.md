# Project storage and provisioning owners

Choose the responsibility in the [canonical contract](CONTRACT.md), then import
its named public module. `disco.projects` initializes nothing and is not a facade.
Existing functions/classes/constants and necessary cross-owner helpers retain their
capabilities. Do not infer privacy from underscore spelling or add forwarding shims.

Read [backend navigation](../../AGENTS.md) and the contract before changing identity,
filesystem ordering, retention, provisioning, migration or partial completion.
The source-only public examples use owned temporary bytes and explicit upstream
stand-ins; they do not load scientific libraries, start a database or transfer data.
Native/HTTP/app and export qualification remain separately deferred. The integration
owner serializes catalog, application-profile, CI, ledger and path-companion updates.
