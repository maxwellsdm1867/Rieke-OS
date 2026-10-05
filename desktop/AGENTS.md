# Desktop navigation

Start with [architecture](../ARCHITECTURE.md) and the adopted
[P07 lifecycle obligations](../docs/architecture/0.1.8-first-port-slices.md#project-runtime-lifecycle-obligations).
[Close coordination](close/AGENTS.md) is the first responsibility folder.
Its [contracts, errors, dependencies and executable examples](close/README.md)
are beside the public entries and tests.

`main.cjs` retains Electron window/IPC, restoration and lifecycle composition;
`preload.cjs` and `security.cjs` retain the renderer capability and admission rules.
[Draft storage](drafts/AGENTS.md) and [startup preferences](startup/AGENTS.md)
remain separate owners with nearby contracts and public examples. ServiceSupervisor owns
exact root identity/readiness; Python `workspace_desktop.py` owns project children
and native cleanup. Renderer draft/lifecycle files stay in `workspace-app/src`.
[Application integrity](integrity/AGENTS.md) owns explicit read-only auditing and
recovery ordering; main retains admission and Quit composition.
[Update coordination](updates/AGENTS.md) keeps signed and unsigned-testing owners
separate; the shared root validator remains an installation/integrity dependency.
[Installation and rollback](INSTALLATION.md) explains the retained installed helper
paths and signed/testing readiness distinctions. [Retained startup and state owners](RETAINED_OWNERS.md)
explains supervisor, restoration, profile/path and location-index contracts and
public examples. No universal lifecycle facade exists.

Preserve strict replacement versus bounded explicit Quit. Project UUID/canonical
path and PID/creation time are separate proofs. Preference restoration grants no
scientific readiness. Do not widen IPC, disable sandbox/security checks or replace
uncertain stop with a clean receipt.

Root `tests/` retains cross-owner composition. `close/tests/`, `drafts/tests/`, `startup/tests/` and `integrity/tests/` contain local public
seam tests; `updates/tests/` retains updater contracts and controlled public examples. `e2e/` and host/native inspection
are separate qualification. Root installation and retained-owner public examples
remain mapped separately from native/helper execution. Never use indiscriminate
recursive test discovery.

From repository root, with existing provisioned dependencies:

```sh
node --test desktop/close/tests/*.test.cjs desktop/tests/close-packaging.test.cjs
python tools/architecture_guard.py check
python tools/architecture_guard.py plan --base <pre-change-ancestor>
python tools/architecture_guard.py test --base <pre-change-ancestor> --language desktop
```

The mapped supervisor tests may bind owned loopback sockets. The full npm desktop
suite also contains Electron/host-specific tests; a source move does not require
launching them silently. Follow the [benchmark guide](../docs/dev/benchmarks.md)
and [macOS compatibility policy](../docs/dev/macos-compatibility.md) for separately
scoped packaging/native work. Source packaging assertions do not establish actual
ASAR contents, packaged IPC or native exit qualification.
