# Startup presentation preference

Read the [public contract and executable examples](README.md),
[desktop navigation](../AGENTS.md), and adopted
[P07 lifecycle obligations](../../docs/architecture/0.1.8-first-port-slices.md#project-runtime-lifecycle-obligations).

The public entry is [startup-session.cjs](startup-session.cjs), retaining
StartupSession, viewNamespace and valid. Keep local tests at this seam. Dependencies
are Node fs/promises, path, crypto, root security.cjs and supervisor.cjs atomicJSON.
Do not extract a new storage facade merely to move the file.

Main retains restoration/authorization/cancellation composition and legitimately
reads value/target and updates cancelled. These are existing caller obligations;
relocation does not create language privacy. Keep single claim, compatibility/path
namespace, serialized preference writes, corrupt-byte preservation and transient
cancellation distinct from persisted chooser preference. A preference grants no
scientific readiness or process ownership. No security/protocol changes.
