# Navigation and startup package

This isolated assembly starts at accepted Disco 0.1.8 plus startup commit
12099185bcb5a76ed303eca5188adee298e88b4e. It incorporates the reviewed right-side
trace UI from b2e7303 and d2fc59f, the preview-tested trace-first navigation and
bounded worker/cache owners from c870e66, and progressive epoch-list scrolling.
The startup App/data activation and desktop ownership remain in place.

The shared Inspector/workbench cell list no longer has a Previous/range/Next
strip. It appends bounded pages on scrolling, retains a keyboard-accessible
Load more fallback, restores saved frontiers sequentially, and reveals keyboard
focus beyond the loaded frontier. Rows retain exact page receipts and ordinals.
Changed query/binding/total, malformed rows and duplicate IDs refuse accumulated
membership with retry. Frozen cohort refresh keeps prior row nodes inert until
new authority is ready. It does not grant curation consent.

The column tree uses full available height and places recorded traces beside
terminal epochs. Optional detailed metadata defaults off, while tags remain
independent. Existing trace buffers are bounded; background workers perform the
unchanged source-verified trace read and must exit before native database cleanup.
Partial scientific activation now closes workers before database cleanup as well.
The broader predicate/split priority scheduler remains a design, not this build.

Source checks include scrolling/membership/keyboard/frozen continuity, optional
metadata and cache lifetime, trace execution, API lock isolation, project shell,
service semantics and desktop close/startup. The original API test's reviewed
fixture AST is unchanged; inserting its encoding concurrency test moves the
reviewed selector from Call:74 to Call:111. Observer and alias owner hashes are
updated without changing their identities or reviewed ASTs. The compatibility
request owner is included; scoped predicate preference UI and imported backend
composition are outside this assembly and are not claimed by its test list.

Final build receipts and test logs are retained beside the isolated checkout in
`epoch-navigation-perf-2026-10-05`. The runtime manifest binds the exact clean
commit and packaged application files. Packaged smoke, relocated native imports,
whole-bundle audit and actual waveform/list UI evidence must refer to those bytes.

This is a local unsigned testing package for Apple silicon, not release promotion.
The host is macOS 27.0.1; macOS 14 runtime behavior and Developer ID/notarization
remain unqualified. A source test or static native audit does not establish them.
