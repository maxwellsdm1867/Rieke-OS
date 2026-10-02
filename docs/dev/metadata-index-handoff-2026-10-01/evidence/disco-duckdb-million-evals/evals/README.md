# Disco million-epoch evaluation

Read [RESULTS.md](RESULTS.md) for findings, [SCORECARD.md](SCORECARD.md) for all nine original actions, and [EXPERIMENT.md](EXPERIMENT.md) for scope. All additions are isolated experiment tooling; production source is unchanged.

## Replay

Use the existing Python runtime read only. Install the tested dependency into an owned directory with `uv pip install --python /path/to/existing/python --target /private/tmp/disco-duckdb-deps-20261001 duckdb==1.5.6`. The included drivers add that dependency path; adjust it if using another directory. See each harness README for browser and native MySQL commands. These timings must run serially.

Example from this branch (use fresh owned output directories):

```sh
/path/to/python -B docs/dev/duckdb-million-evals-2026-10-01/evaluate.py --mode fixture --epochs 1000000 --csv /private/tmp/owned-run/million.csv --out /private/tmp/owned-run/fixture --cap 300
/path/to/python -B docs/dev/duckdb-million-evals-2026-10-01/evaluate.py --mode sqlite --epochs 1000000 --csv /private/tmp/owned-run/million.csv --out /private/tmp/owned-run/sqlite --cap 300
/path/to/python -B docs/dev/duckdb-million-evals-2026-10-01/evaluate.py --mode duckdb --epochs 1000000 --csv /private/tmp/owned-run/million.csv --out /private/tmp/owned-run/duckdb --cap 300
/path/to/python -B docs/dev/duckdb-million-evals-2026-10-01/verify_results.py
```

`guard.py --out FRESH_GUARD_DIRECTORY --seconds 300 -- COMMAND ARGS...` wraps an owned experiment and records its resources. Process enumeration permission is required; preflight failure prevents launch. It is intended for these non-daemonizing workers, not a general service manager. `adjust_sqlite.py --database ORIGINAL_TYPED_SQLITE --csv CSV --baseline-receipt ORIGINAL_QUERY_RECEIPT --out FRESH_DIRECTORY` copies the database, adds covering indexes, records plans and replays all queries. The source database hash is checked before/after.

Stored receipts deliberately retain initial failures and explicitly unresolved production qualification. The shared corpus is reproducible; large CSV/database files are not checked into Git. Raw source runtimes, binary database files and installed application are not part of this branch.
