# Retained tooling navigation

This directory owns development checks, build/release controls and qualification
evidence. Keep its existing entrypoint paths. The meaningful subfolders are
[metadata qualification](metadata_qualification/README.md) and
[UI checks](ui_checks/). Root-level tools retain their explicit command names;
there is no shared application service or new package interface here. This guide
adds navigation, not permission to run a build, benchmark, browser or native job.

For application ownership, use the [architecture map](../ARCHITECTURE.md),
[adopted contracts](../docs/architecture/0.1.8-first-port-slices.md) and
[existing ledger](../docs/architecture/core-module-ledger.json). Check the tool's
source and its linked tests before changing arguments, result formats, errors,
process lifetime or artifact identity. Preserve raw failure evidence. Do not turn
an unavailable prerequisite, partial run, skipped case or timeout into success.

## Architecture and benchmark commands

| Start here | Interface and ownership |
| --- | --- |
| [architecture_guard.py](architecture_guard.py) | `check`, `plan`, `test`; consumes the [adopted catalog](../docs/architecture/adopted-port-checks.json). `check` validates references/import rules; `plan` selects mapped contracts using explicit ancestor `--base`/`--head` or diagnostic `--all`; `test` actually runs mapped suites. JSON status, source hashes and nonzero failures are part of the interface. |
| [architecture_module_policy.py](architecture_module_policy.py) | `validate(root, catalog)`, `inputs(root, catalog)`, `check(root, catalog, node)` support the guard's frontend ownership rules. This is a syntactic review aid, not a security sandbox or scientific authority proof. |
| [benchmark.py](benchmark.py) | `run --output`, `gate RECEIPT --commit --app-version [--release]`, `compare BASELINE CANDIDATE --output`. Owns the fixed suite, receipt validation and comparable-source/environment gate; failed workers write incomplete evidence. |
| [benchmark_native.py](benchmark_native.py) | `--evidence-root` with attachment arguments or `--verify`; binds immutable native research evidence and preserves the measured commit. An attachment does not grant release qualification. |

The guard uses Python, local Git history, the existing Node import parser and
frontend dependencies for JavaScript checks. `RIEKE_TEST_DOM_MODULE` must be unset
for frontend guard/test execution. Missing catalog paths, unknown fields, invalid
ancestry, forbidden dependencies and failed mapped tests must remain failures.
Source-hash validation and a passing import guard do not establish behavior.

Existing source-checked command example, from the repository root:

```sh
python3 -B tools/architecture_guard.py check --language metadata
```

This selects catalog/reference validation; it is not the complete language/import
or behavioral check. For change selection, use `plan --base` with the actual
reviewed ancestor, inspect its mapped work, and only then use `test` within the
authorized scope. Do not use `--all` as an incidental substitute for that review.

The [guard tests](../python/tests/test_architecture_guard.py) include
`ArchitectureGuardTests.test_plan_requires_explicit_valid_ancestor_and_maps_renames_and_deleted_paths`,
`test_mapped_command_runs_behavior_and_propagates_failure` and
`test_dirty_unknown_zero_and_nonancestor_bases_never_produce_empty_green_plan`.
Frontend parser/private-import cases live in
[architectureImports.test.js](../workspace-app/src/architectureImports.test.js) and
[architectureModulePolicy.test.js](../workspace-app/src/architectureModulePolicy.test.js).

Read the canonical [benchmark guide](../docs/dev/benchmarks.md) and
[registry](../benchmarks/registry.json) for the pinned Python/Node/dependency profile,
fixture identity, serial worker limits, commands and unsupported release cases.
Do not create another registry or infer per-tool performance from relocation.
[BenchmarkTests](../python/tests/test_benchmark.py) checks missing/failed samples,
stale/dirty/tampered sources, incompatible environments and incomplete worker
receipts. [NativeTests](../python/tests/test_benchmark_native.py) checks attachment
tampering and prohibits transferring evidence by moving production into docs.
The [preload test](../python/tests/test_benchmark_preload.py) covers the existing
frontend test environment contract. These are evidence-validation tests, not
instructions to execute benchmarks or native attachments now.

## Desktop build, profile, release and diagnostics

The root names remain stable because workflows and other tools call them directly.

| Responsibility | Existing entrypoints |
| --- | --- |
| Source selection and staging | [desktop_release_plan.py](desktop_release_plan.py), [desktop_application_profile.py](desktop_application_profile.py), [build_release.py](build_release.py), [desktop_build_runtime.py](desktop_build_runtime.py) |
| Runtime inventory, audit and compatibility | [desktop_runtime_manifest.py](desktop_runtime_manifest.py), [desktop_runtime_audit.py](desktop_runtime_audit.py), [desktop_native_compatibility.py](desktop_native_compatibility.py) |
| Artifact evidence and publication controls | [desktop_release.py](desktop_release.py), [desktop_test_release.py](desktop_test_release.py), [desktop_artifact_e2e.py](desktop_artifact_e2e.py) |
| Runtime/native/scientific/startup probes | [desktop_runtime_smoke.py](desktop_runtime_smoke.py), [desktop_backend_smoke.py](desktop_backend_smoke.py), [desktop_no_docker_smoke.py](desktop_no_docker_smoke.py), [desktop_scientific_e2e.py](desktop_scientific_e2e.py), [desktop_startup_failures.py](desktop_startup_failures.py) |
| Owned lazy-startup diagnostics | [diagnose_lazy_run.cjs](diagnose_lazy_run.cjs), [diagnose_lazy_failure.cjs](diagnose_lazy_failure.cjs), [diagnose_lazy_sampler.cjs](diagnose_lazy_sampler.cjs), [analyze_lazy_diagnostic.py](analyze_lazy_diagnostic.py) |

`desktop_release_plan.plan` and its CLI inspect committed changes; `--repo`,
`--base`, `--head`, `--extended`, optional `--published-tags`, and required
`--output` control selection. Preserve explicit invalid/nonancestor refusal and
changed/deleted/renamed path handling. It produces a plan, not build qualification.
[ReleasePlanCLITests](../python/tests/test_desktop_release_plan.py) directly invokes
this CLI against disposable Git histories, including
`test_documentation_and_tests_only_do_not_build_an_application` and
`test_explicit_missing_and_nonancestor_bases_fail_closed`.

[desktop_application_profile.py](desktop_application_profile.py) exposes
`load_profile(path)`, `validate_source_closure(root, profile)`,
`copy_python_application(root, application, profile_path)` and
`audit_application(application, expected_profile)`. The
[application profile](../desktop/application-profile.json) is the explicit runtime
allowlist. Loading/closure validation rejects malformed, missing, redirected or
excluded modules; copy stages that allowlist; audit compares the actual file set.
Do not invoke copy while intending only to inspect. Its CLI `--root` checks tracked
release-source exclusions, not the entire staged runtime. The shipping profile
remains v1 with flat Python filenames; the helper also supports v2 explicit package
paths. Follow the canonical [application boundary](../desktop/README.md#application-boundary)
for package rules, source-only examples and qualification limits. Actual package
relocation still requires reviewed closure/discovery changes and separate
qualification, not a silent relaxation of the allowlist.

[DesktopPackagingTests](../python/tests/test_desktop_runtime_packaging.py) contains
these existing focused source/temporary-file checks:

- `test_current_application_closure_includes_typed_requested_summary_backend`
- `test_data_export_application_allowlist_excludes_gui_and_legacy_cli`
- `test_allowlist_rejects_excluded_imports_missing_sources_and_links`
- `test_inventory_rejects_external_and_broken_links_and_hashes_bytes`

For example, with the existing source-test Python environment available, this
names one existing case without selecting native E2E:

```sh
PYTHONPATH=python python3 -B -m unittest python.tests.test_desktop_runtime_packaging.DesktopPackagingTests.test_allowlist_rejects_excluded_imports_missing_sources_and_links
```

This command is navigation guidance, not a receipt that the case ran here. Other
build/assembly/probe tools need their own exact-candidate environment and scope.
Read the [macOS compatibility matrix](../docs/dev/macos-compatibility.md) before
assembling or auditing native runtime evidence. Pinned parser/scientific wheels,
lock files, OS/architecture and relocated imports remain material dependencies.
A manifest inventory is not runtime qualification. Lightweight startup checks and
full artifact audits have different jobs; see
[VerificationBoundaryTests](../python/tests/test_desktop_verification_boundary.py),
[runtime audit tests](../python/tests/test_desktop_runtime_audit.py),
[native compatibility tests](../python/tests/test_desktop_native_compatibility.py)
and [scientific wheel tests](../python/tests/test_desktop_scientific_wheels.py).

Promotion/testing-release behavior is covered by
[release tests](../python/tests/test_desktop_release.py),
[testing-release tests](../python/tests/test_desktop_test_release.py) and
[artifact fault tests](../python/tests/test_desktop_artifact_faults.py).
Keep artifact hashes, candidate commit, channel, clean-source checks and evidence
requirements intact. A CLI may sign, install dependencies, launch owned processes,
write databases, call GitHub or promote releases; the existence of a parser does
not make its invocation read-only. The lazy diagnostic runners additionally bind
specific local bundle/fixture/Playwright paths. Do not launch them as generic smoke
checks or substitute a live user project. The
[sampler test](diagnose_lazy_sampler.test.cjs) exercises its isolated lifecycle.

## Metadata qualification tooling

Start with the existing [README](metadata_qualification/README.md),
[qualification plan](metadata_qualification/qualification-plan.json),
[report](metadata_qualification/REPORT.md) and
[native checkpoint and open gates](metadata_qualification/NATIVE-E2E-CHECKPOINT.md).
They distinguish independent small-fixture truth, transactional doubles, native
rendered observations, capped arms and serial million-scale evidence. Historical
completion descriptions are not authorization to resume a paused fixture.

| Responsibility | Existing implementation |
| --- | --- |
| Independent small truth and adapter checks | [truth.py](metadata_qualification/truth.py), [native.py](metadata_qualification/native.py), [core_adapter.py](metadata_qualification/core_adapter.py), [checks.py](metadata_qualification/checks.py), [core_faults.py](metadata_qualification/core_faults.py), [run.py](metadata_qualification/run.py), [package initializer](metadata_qualification/__init__.py) |
| Service/publication checks | [service_checks.py](metadata_qualification/service_checks.py), [integrated_service.py](metadata_qualification/integrated_service.py) |
| Storage, bounded timing and replay gate | [storage.py](metadata_qualification/storage.py), [timing.py](metadata_qualification/timing.py), [replay_gate.py](metadata_qualification/replay_gate.py) |
| Serial million pipeline | [million_build.py](metadata_qualification/million_build.py), [million_batch.py](metadata_qualification/million_batch.py), [million_worker.py](metadata_qualification/million_worker.py), [million_controls.py](metadata_qualification/million_controls.py), [million_provenance.py](metadata_qualification/million_provenance.py), [million_storage.py](metadata_qualification/million_storage.py), [million_report.py](metadata_qualification/million_report.py) |
| Native/renderer checkpoint tools | [native_e2e_server.py](metadata_qualification/native_e2e_server.py), [native_proxy_check.py](metadata_qualification/native_proxy_check.py), [native_replay_pilot.py](metadata_qualification/native_replay_pilot.py), [render_receipts.cjs](metadata_qualification/render_receipts.cjs) |

`checks.qualify(adapter, truth)` reads the adapter's `fields` data attribute and calls
`membership`, `preview` and `detail`; `run.py` owns `adapter.close()` in its `finally`
block. The README defines their scope, cursor and truth obligations. Service checks use an isolated Flask client and explicit deterministic
worker/fault callbacks. Pending/cancelled/stale/failed results must not publish as
ready or fabricate zero summaries. `replay_gate.inventory()` is stat-only and does
not verify a seal. Verification and million commands have separate serial/fixture
requirements. Preserve their refusal paths and owned-input containment. Do not
read/hash/rebuild paused private corpus files merely to update this guidance.

The [qualification tests](metadata_qualification/test_qualification.py) include
`NativeTruthTests.test_checks_detect_corrupt_dto_facet_and_cursor`,
`ServiceSeamCheckerTests.test_summary_states_reject_zero_imputation_stale_identity_and_unready_result`
and `StorageTests.test_heavy_replay_gate_closed_and_stat_inventory_never_claims_seal`.
[Annotation tests](metadata_qualification/test_annotations.py) use transactional
doubles; [native summary I/O tests](metadata_qualification/test_native_summary_io.py)
and [rendered receipt tests](metadata_qualification/render_receipts.test.cjs)
retain their distinct evidence scopes. None converts a broad discovery invocation
into approval for native/million qualification.

## Fixture browser checks

[scoped_predicate.mjs](ui_checks/scoped_predicate.mjs) checks the real scoped editor
against intercepted API replies using Vite/React and Playwright/Chrome. Its inputs
include `SCOPED_QA_OUTPUT` and `SCOPED_QA_PORT`; installed Playwright and browser
paths are currently machine-specific. [trace_readouts.mjs](ui_checks/trace_readouts.mjs)
uses `PLAYWRIGHT_MODULE`, `TRACE_QA_OUTPUT`, `TRACE_QA_BASELINE`, `TRACE_QA_PORT` and
`TRACE_QA_BROWSER`; it reads the named Git baseline and intercepts trace replies.
Both start a server/browser and write evidence. Neither is a live backend or
native trace qualification. Missing dependencies/history, occupied ports, browser
failures or assertions must remain failures, not partial passing receipts.

Related existing behavior tests are [protocolViewFilter.test.js](../workspace-app/src/protocolViewFilter.test.js),
[scopedPredicateFilter.test.js](../workspace-app/src/scopedPredicateFilter.test.js),
[scopedPredicateLifecycle.test.js](../workspace-app/src/scopedPredicateLifecycle.test.js),
[traceGeometry.test.js](../workspace-app/src/traceGeometry.test.js) and
[traceReadContext.test.js](../workspace-app/src/traceReadContext.test.js).
These cover product behavior; they do not prove these browser scripts ran. Respect
the trace script's serialized numeric/E2E/UI window before a scoped run.

## Evidence identity and changes

Use the single [benchmark registry](../benchmarks/registry.json) and
[benchmark guide](../docs/dev/benchmarks.md). Preserve historical source commits,
fixture seals, raw samples/logs, suite/schema/runtime/OS/hardware identities and
failed/incomplete statuses. The qualification
[baseline references](metadata_qualification/baseline-references.json) index
historical evidence; do not relabel it as a candidate pass or edit a receipt to
supply a missing measurement. Native navigation/tag/ingest and export/trace/MAT
limits remain governed by the canonical registry and qualification plan.

For a change, identify the actual tool/function/CLI owner and relevant existing
assertions first. Preserve the interface and collect only authorized bounded
checks; source-link or parser inspection proves documentation accuracy, not
execution readiness. Record remaining native/paused gates explicitly. Retained
tooling already has coherent ownership; no wrappers, second framework, file moves
or new measurements follow from this navigation guide.
