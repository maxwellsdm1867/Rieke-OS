# Native everyday action experiments

Source: `/private/tmp/rieke-os-issues-20260930/repo` at `a8fac2c293ccf4fa73a4eb5e93673b41620b1d13`.
Run on local macOS with Python3.11 (the existing Disco development virtualenv) and bundled native MySQL8.4.2. Existing runtimes are read only; canonical source and all scientific data are read only. Each project/datadir and author preferences path is disposable. The first sandboxed10k attempt could not bind loopback and is retained as failed environment evidence, not a performance result.

For each size:

```sh
PYTHONDONTWRITEBYTECODE=1 \
RIEKE_PREFERENCES_DIR=/private/tmp/disco-everyday-bench-20261001/native/preferences-100k \
/PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/.rieke-runtime/venv/bin/python \
/private/tmp/disco-everyday-bench-20261001/native/capped_runner.py \
/private/tmp/rieke-os-issues-20260930/repo/docs/dev/scale-audit-2026-09-29/benchmark_native_tag_sequence.py \
--source-root /private/tmp/rieke-os-issues-20260930/repo \
--mysql-runtime-root /PATH/TO/LOCAL_HOME/Documents/GitHub/epicTreeGUI/.rieke-runtime/mysql \
--epochs 100000 --samples 5 \
--output /private/tmp/disco-everyday-bench-20261001/native/native-100k.json
```

Use unused output paths. The10k run used10000 and native-10k-permitted.json. The cap wrapper raises TimeoutError at480 seconds; the reviewed unchanged harness flushes/closes its stores and normally stops its owned native database in finally. No user databases/apps are killed.

Dense fixture:100epochs per cell,3 authors and5 tags per shared annotation,2 independent protocol curations with5 tags each per epoch,10 synthetic H5 source identities,4 scalar metadata parameters per epoch. No private H5 files or waveform bytes. Seed/setup/startup/oracles are separate from action timings. API action times use Flask test client plus serialization/JSON decode; exclude browser rendering/network. Bundle times sum sequential measured requests and exclude oracle work. Five samples support median and maximum, not a robust tail percentile. Autocomplete cold/warm/empty diagnostics each have one sample.

All exactness oracles and source inventory checks must pass; the receipt records whether owned MySQL shut down normally. Existing harness itself reports nearest-rankp95/p99 for five samples; summarize median/max instead.
