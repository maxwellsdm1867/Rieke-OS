# Mutation recovery public contract

[`disco.recovery`](__init__.py) exports only
`register_mutation_recovery(app, scheduler, *, desktop_mode)`. It registers one
Flask `after_request` callback and returns `None`. The private implementation is
[`mutation_outcomes.py`](mutation_outcomes.py); import the public package.

## Ownership and adapters

This module translates existing HTTP mutation completion into backup status or a
backup checkpoint. It does not establish SQL commits, own annotation/group
transactions, create a scheduler, roll back a committed write or guarantee native
durability. The caller owns the Flask app and scheduler lifetimes.

Register once, during app construction, at the existing composition position:
after the response-header callback. Flask executes after-request callbacks in
reverse order, so replacement 507 responses still receive security headers.
`scheduler.status()` returns independent backup state; `scheduler.flush()`
synchronously checkpoints or raises. `desktop_mode` is a zero-argument boolean
callable evaluated per request. It must not be replaced by a cached boolean.
The only implementation dependency is Flask.

## Why this organization

This slice organizes an existing module; it does not claim new depth from a
folder or a smaller export count. Deleting its implementation would return the
route-specific completion policy to app composition, where callers would again
need to understand backup failure translation. Locality improves because the
public contract and existing conformance tests now sit beside that policy.

Flask request/response handling is in-process. The scheduler is an existing
local-substitutable dependency: production backup scheduling and disposable
observable test adapters already satisfy the same `status`/`flush` interface.
No remote owned service or new external-service port is introduced. Tests cross
the same public registration seam as callers and observe HTTP results; the moved
test replaces its former central file instead of layering duplicate tests.

## Results, failures and exclusions

Successful annotation-update/undo replies keep the existing receipt and add the
committed-database/current-backup status without synchronous flush. Status errors
retain existing exception propagation. Successful other writes checkpoint once,
including no-op or replay replies. Existing read-only POST endpoint exemptions,
exact close/unmount paths and desktop-control prefix/mode exclusions stay exact;
other verbs on read POST routes remain writes.

A flush failure returns HTTP 507 with `saved: true` and the existing backup-failure
message. Group apply/undo failures also retain the request's exact operation UUID,
`recovery_unconfirmed` and committed-database/degraded-backup status. This response
must never imply rollback or encourage minting a new operation identity.
Non-success replies and non-write methods retain their existing behavior.
There is no cancellation or background-work owner here. Synchronous flush latency
belongs to request completion; no per-module performance measurements are claimed.

## Public usage and executable checks

```python
from flask import Flask
from disco.recovery import register_mutation_recovery

app = Flask(__name__)
# Register the application's response headers first.
register_mutation_recovery(app, scheduler, desktop_mode=lambda: False)
```

`scheduler` is the caller-owned adapter described above. The complete executable
examples are the [13 local HTTP cases](tests/test_workspace_mutation_outcomes.py):
`MutationRecoveryTests` constructs a disposable Flask app and scheduler adapter,
uses actual test-client requests and observes callback results. Its
`ApplicationRecoveryRegistrationTests` exercises real app composition through
existing disposable fixtures. The central
[group recovery tests](../../tests/test_workspace_group_recovery.py)
and [registered-route policy tests](../../tests/test_workspace_registered_recovery_policy.py)
retain six and seven cross-owner cases respectively.

From repository root, with the selected source-test Python and dependencies:

```sh
PYTHONPATH=python:python/tests "$TEST_PYTHON" -B -m unittest -v \
  disco.recovery.tests.test_workspace_mutation_outcomes \
  python.tests.test_workspace_group_recovery \
  python.tests.test_workspace_registered_recovery_policy
```

Owner-local CI discovery uses `-s python/disco/recovery/tests -t python`, preserving
all 13 cases. Compare exact pre/post collected IDs, replacing only the moved module
prefix. Do not substitute full scientific/native discovery for this scoped lane.
An unavailable interpreter/dependency, skipped case or failed import is not a pass.

The [adoption record](../../../docs/architecture/0.1.8-first-port-slices.md#mutation-recovery-completion)
records cross-owner behavior and historical evidence. The
[fixed benchmark guide](../../../docs/dev/benchmarks.md) and
[registry](../../../benchmarks/registry.json) retain their existing identities;
this relocation creates no benchmark or native qualification. Source staging must
verify all 92 explicit profile files and an isolated public import from the staged
package. Full app/ASAR/native import and ordinary-quit acceptance remain separate.
