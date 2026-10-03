# Independent draft review resolution

Reviewer thread: <review-thread>. Review source note: task-6/json-adapter-independent-review.md. Review was read before final packaging.

One P2 was found: generator.seed allowed unbounded JSON integers, allowing a seed such as 9007199254740993 to round in JavaScript and change reconstruction. The draft schema now bounds numeric seeds to ±(2^53−1). Larger seeds must be canonical decimal integer strings; the contract explicitly defines those strings as encoded integers. Arbitrary text/leading-zero/fractional encodings are rejected rather than guessed.

The seed test exercises ten positive/negative/boundary/string/invalid encoding cases, checks JSON round-trip equality and type, and verifies integer-string decoding preserves the exact integer. All 25 regression methods and 11 fixture checks pass after correction. The offline validator still reads only the candidate bundle/schema, never traces or databases.

The reviewer verified all 35 source-declared DataJoint definitions and found the identity, H5 binding, missingness, tag-target, metadata-only and frozen-export contracts clear. No other findings were reported. The review did not certify production importer compatibility, live SQL state, raw verification or performance. No production change or migration was performed.
