# Application integrity

Read [public contracts and examples](README.md), [desktop navigation](../AGENTS.md)
and [P07 obligations](../../docs/architecture/0.1.8-first-port-slices.md#project-runtime-lifecycle-obligations).
The two public entries are verify-application.cjs and verification-recovery.cjs;
keep their five named exports and tests at that seam. No facade or private-state
adapter is needed. Main retains window admission, menu, restoration invalidation,
AbortController lifetime and strict replacement versus bounded Quit composition.

Preserve immutable inventory, compatibility and signed/unsigned identity rules.
Never reseal or repair user data. Block new work synchronously before awaiting
recovery. Preserve separate pause/draft/service uncertainty and reuse completed
cleanup only for services.ready === true, retaining failed-draft receipts.

Only the existing read-only audit child may receive its cancellation signals;
settle after child close. That authority does not extend to scientific writers or
E2E launcher processes. Bundle paths come from the supplied bundle, not __dirname.
Root physical-fs, updater-validation and bootstrap remain shared dependencies.
