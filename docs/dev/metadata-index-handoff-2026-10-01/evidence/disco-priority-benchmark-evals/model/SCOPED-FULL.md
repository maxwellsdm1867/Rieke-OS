# Full-field scoped query routing

`scoped_full.FullScopedSidecar` retains the full previous 140-field sidecar and changes only predicate compilation when the caller supplies an explicit cell, block or group scope. Generic scientific leaves use a correlated `EXISTS` query that point-reads the current epoch's field entry, then its typed dictionary value. A `CROSS JOIN` fixes this loop order. Previously the same leaf built a project-wide epoch-ID membership set before applying the small structural scope.

Missing uses `NOT EXISTS` against native epoch/field membership; exists uses `EXISTS`. Native epoch IDs are non-null primary identities. Recorded null remains a present value and is tested through the unchanged typed-null selector. Core-safe direct field predicates retain their previous SQL. Compound all, any and not retain their original Boolean structure. Global and protocol-only queries retain the prior SQL exactly.

The new class inherits the earlier bounded DTO paging, exact counts, requested facet output, all-field validation, chronology cursor, groups, detail decoding and reconstruction data. It requires no new database build and does not modify the input files. The full auxiliary storage remains 1.107 GB.

`scoped-fixture-smoke.json` verifies 1,185 valid predicate cases across all 140 fields against independently read native values, five matching validation rejections, 15 compound cases, all-140-field facet payloads for cell/block/group scopes and unchanged global/protocol SQL. Source and full-sidecar generation identities remain unchanged. Performance qualification is a separate root-owned million-row A/B run.
