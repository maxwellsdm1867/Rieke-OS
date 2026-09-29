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
4. Run `packaging/verify_e2e.py` with a real Symphony H5 file.
5. Confirm the receipt says `passed` and includes zero Docker invocations.

The integration runner creates a temporary workspace and leaves its logs and
receipt available for inspection. Its project API and native database are stopped
at the end. The input recording is hashed before and after the run.
