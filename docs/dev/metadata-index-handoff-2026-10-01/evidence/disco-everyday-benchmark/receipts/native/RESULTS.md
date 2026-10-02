# Native everyday actions — actual current app routes

Source: `a8fac2c293ccf4fa73a4eb5e93673b41620b1d13`. Run2026-10-01UTC. MySQL8.4.2, Python3.11, macOSAppleSilicon. Both disposable runs passed18 exactness checks; all product Python imports loaded from the chosen source; source and harness inventories unchanged; owned native databases shut down normally.

Times below are five-sample **median / observed maximum**, in milliseconds. They are local backend API times, not browser paint or network latency. Dense synthetic metadata/tags; no scientific waveform data.

| Everyday action | 10,000 epochs | 100,000 epochs |
|---|---:|---:|
| Add tag to ten selected epochs (read revisions + commit) | 24.4 / 62.9 | 52.2 / 78.1 |
| Add tag to another ten selected epochs | 24.1 / 25.0 | 23.5 / 26.6 |
| Filter to those twenty epochs | 28.2 / 41.5 | 131.5 / 214.2 |
| Tag one cell and filter its hundred epochs | 52.4 / 53.2 | 155.0 / 159.4 |
| Filter by cell tag AND epoch tag | 24.7 / 25.7 | 122.0 / 132.5 |
| Remove tag from ten epochs (commit only) | 18.0 / 18.4 | 18.1 / 20.0 |
| Tag ten + tag another ten + filter twenty | 76.7 / 129.2 | 190.6 / 318.9 |

Single-sample autocomplete diagnostics: 10k cold17.3ms, warm16.4ms, empty18.5ms; 100k cold27.7ms, warm24.0ms, empty26.5ms. These do not establish a latency distribution.

| Setup phase (seconds) | 10,000 epochs | 100,000 epochs |
|---|---:|---:|
| Synthetic canonical annotation/curation seed | 1.31 | 14.21 |
| First populated app startup / native lookup migration | 7.36 | 146.34 |
| Entire fixture setup, actions, oracles, cleanup | 20.38 | 218.37 |

Python process peak RSS: 228.5MiB at10k; 971.3MiB at100k. This excludes the MySQL server and browser.

The slow startup here is a deliberately seeded **first populated migration**, with no derived native tag tables present at seeding. It is not a measurement of reopening an already-prepared normal project. Native annotation preparation alone reports5.40s/124.09s at10k/100k, with protocol-read preparation0.19s/1.51s respectively. The benchmark strongly identifies initialization work worth investigating, but does not prove which subphase dominates without more profiling.

Fixture:100epochs/cell;3authors ×5shared tags/epoch and/cell;2protocols ×5curation tags/epoch;10source identities;4scalar parameters perepoch. SQL triggers active throughout timed writes. Exact case, Unicode normalization distinctions, hierarchical inherited tags, independent protocol curation, saved revisions and removals all verified. No SQLite membership-cache queries were used.

No million-epoch dense annotation run: the eight-minute experiment cap intentionally avoids extrapolating that cost into a long run. No packaging or installer checks were used.

## Receipts

- `native-10k-permitted.json` SHA256 `0d6f452e532cbbd41cff4245209ba98b08c4c4db0aa3b1ce956933856c4561db`
- `native-100k.json` SHA256 `a169eeb32636e57a6186a975e1cfed2054ac2712fc9778346b6542cc62352327`
- `capped_runner.py` SHA256 `cb494e227d847f94b7820573b66ad09316b45feae963949edcb3b891aec776cf`

Reproducible command and scope: `REPRODUCE.md`. Failed sandbox loopback attempt remains `native-10k.json`; it is excluded from performance results.
