# Frontend module navigation

Start in the module folder for the responsibility you are changing:

- [Presentation sessions](presentation/AGENTS.md): route snapshots, destination
  fallbacks, checkpoints and deletion pruning; public session factory and tests
  live together. App composes navigation, persistence and scientific owners.

Other frontend owners retain their existing named files. This is one folder
pilot, not a declaration that each ledger record is a separate module. See the
[architecture map](../../ARCHITECTURE.md) for other adopted interfaces.

Run `npm test` from `workspace-app` for recursive `.test.js` discovery with the
React preload, or use a module's explicit command. Do not import test support into
production. The [catalog](../../docs/architecture/adopted-port-checks.json) guards
public entry/import rules; run `python3 -B tools/architecture_guard.py check
--language javascript` from the repository root. Tests and the guard require
`RIEKE_TEST_DOM_MODULE` to be unset. No native qualification follows from these
frontend checks.
