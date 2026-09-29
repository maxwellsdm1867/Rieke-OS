# Distribution and verification

The GitHub source ZIP contains the app, installer, Python and frontend source,
locked Python dependencies, MATLAB integration, tests, and documentation.
`./install.sh` obtains the native tools and builds the parser and frontend.
`./start.sh` serves the built app using the managed Python runtime.

The distribution excludes installed runtimes, node_modules, scientific projects,
recordings, credentials, local research validation artifacts, and decompiled
third-party reference code. It is not a relocatable prebuilt desktop binary.
The supported, verified release target is Apple Silicon macOS; other installer
targets need their own native integration run before claiming support.

## Reproduce the checks

1. Extract or clone into a fresh directory without `.rieke-runtime` or node_modules.
2. Run `./install.sh` to completion.
3. Run the Python and browser tests shown in the main README.
4. Run `packaging/verify_workflows.py --source /path/to/recording.h5` using the installed Python.
5. Confirm the receipt says `passed` and includes zero Docker invocations.

The integration runner creates a temporary workspace and leaves its logs and
receipt available for inspection. Its project API and native database are stopped
at the end. The input recording is hashed before and after the run.

## Real-data validation

`stress_client.py` imports a supplied list of original Symphony H5 files into a
disposable project, records import and read timings, and checks source hashes.
`verify_catalog_source.py` independently walks the original H5 hierarchy and
compares the native SQL catalog, metadata, stream references and sampled trace
windows. Both reject legacy companion caches as test inputs.

The validation dataset contains eight original H5 recordings: 1.70 GB and
14,908 epochs. The final independent audit checked 867,468 values/relationships
with no discrepancies, including 27 cells (two without epochs), 43 groups,
454 acquisition blocks, 16,273 responses and 14,908 stimuli. Seventy-eight
HTTP trace windows matched source samples exactly. The full workflow runner
also independently checked 15 block-onset estimates and 11 trial/condition
measurements against original samples.

These are checks of import fidelity and implemented arithmetic, not independent
scientific validation of stimulus reconstruction, cell typing, or every possible
recording protocol. Waveform samples remain in the original H5, referenced by
the catalog; the application does not copy all raw samples into SQL. Keep source
files available. MATLAB bundle structure and values were read independently in
Python; executing the MATLAB GUI requires a separate MATLAB installation.

Browser control evidence and remaining configuration/edge-case coverage are
tracked in [the client validation ledger](../docs/dev/CLIENT_VALIDATION_MATRIX.md).
Local raw receipts contain private recording paths and are excluded from the
public distribution. Release summaries contain only aggregate results.
