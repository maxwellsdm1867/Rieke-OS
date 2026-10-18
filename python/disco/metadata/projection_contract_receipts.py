"""Reviewed whole-build compatibility decisions; literal data only."""

COMPATIBILITY_RECEIPTS = {'version': 1,
 'owners': ('recording_workspace.py',
            'disco/metadata/projection_cache.py',
            'disco/metadata/metadata_objects.py',
            'workspace_service.py'),
 'reviews': ({'id': 'release-0.1.12-projection-compatibility-2026-10-14',
              'decision': 'compatible',
              'reviewed_build': ('6f8a583c021153c373ddc90e5f68aef1be8d690ed2882cbfb43eb814cb240230',
                                 'a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9',
                                 '8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd',
                                 'c7e3038863a63144ca2faaa3a2ed5733916759f58570df86c340ef554b1c96db',
                                 '04faa42a70bbd6f63044df7b1e67640b4a0f49b919b8f8c86294557f5a2ba024'),
              'legacy_owners': ('7dbf2d4d17fb0f06f084b0fd74a9e2376899afe07cba8257eb3c8fd803e55139',
                                'a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9',
                                '8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd',
                                '1f7da71b300a2c617cc6f67cf70a2790d609f3d115828e1b092a518003178be8'),
              'legacy_contract': 'd612c67e1297f3f64eb96339150a9b9a007d55003e8c5d38f21a8aa695d55f37',
              'rationale': 'Relative to add33d153ae8f533d5c4a68c50690764323c4336, recording_workspace only '
                           'adds recording_location during NEW import CLI handling. Existing-project '
                           'projection construction, codecs and verification are unchanged. WorkspaceService '
                           'only delegates its contract selection to this exact reviewed resolver. Native '
                           'index, typed index and scientific-input witnesses remain unchanged.',
              'evidence': ('git:add33d153ae8f533d5c4a68c50690764323c4336',
                           'docs/dev/project-version-first-open-2026-10-14.md',
                           'python/tests/test_workspace_projection_contract.py',
                           'python/tests/test_workspace_refresh_cache.py')},
             {'id': 'cell-identity-presentation-compatibility-2026-10-14',
              'decision': 'compatible',
              'reviewed_build': ('6f8a583c021153c373ddc90e5f68aef1be8d690ed2882cbfb43eb814cb240230',
                                 'a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9',
                                 '8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd',
                                 '28fea6b5d8fe45378159f7c6888346990c750e3a72f0b900c28af0474e211f4f',
                                 '04faa42a70bbd6f63044df7b1e67640b4a0f49b919b8f8c86294557f5a2ba024'),
              'legacy_owners': ('7dbf2d4d17fb0f06f084b0fd74a9e2376899afe07cba8257eb3c8fd803e55139',
                                'a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9',
                                '8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd',
                                '1f7da71b300a2c617cc6f67cf70a2790d609f3d115828e1b092a518003178be8'),
              'legacy_contract': 'd612c67e1297f3f64eb96339150a9b9a007d55003e8c5d38f21a8aa695d55f37',
              'rationale': 'Relative to 6b81372, workspace_service only adds recorded cell_type to '
                           'cell-level tree presentation inside the existing row loop. Projection '
                           'construction, codecs, scientific input checks and all other vector owners are '
                           'unchanged. Independently reviewed as additive display metadata; no reads, '
                           'membership or authority changes.',
              'evidence': ('git:6b81372',
                           'docs/dev/cell-identity-placement-2026-10-14.md',
                           'python/tests/test_workspace_projection_contract.py',
                           'python/tests/test_workspace_tree_pages.py',
                           'python/tests/test_workspace_refresh_cache.py')},
             {'id': 'dedicated-project-heap-compatibility-2026-10-14',
              'decision': 'compatible',
              'reviewed_build': ('6f8a583c021153c373ddc90e5f68aef1be8d690ed2882cbfb43eb814cb240230',
                                 'a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9',
                                 '8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd',
                                 '5ff4111053048cf5e3907fa3dc58184e9f9b76c3632c79198ea603dfaee40017',
                                 '04faa42a70bbd6f63044df7b1e67640b4a0f49b919b8f8c86294557f5a2ba024'),
              'legacy_owners': ('7dbf2d4d17fb0f06f084b0fd74a9e2376899afe07cba8257eb3c8fd803e55139',
                                'a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9',
                                '8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd',
                                '1f7da71b300a2c617cc6f67cf70a2790d609f3d115828e1b092a518003178be8'),
              'legacy_contract': 'd612c67e1297f3f64eb96339150a9b9a007d55003e8c5d38f21a8aa695d55f37',
              'rationale': 'Relative to b82de83, WorkspaceService only wraps refresh in the explicitly '
                           'installed dedicated-process heap lifetime. Removing that wrapper and its '
                           'contextlib import produces an identical whole-file AST. Projection construction, '
                           'codecs, source verification, recorded values and all other vector owners are '
                           'unchanged. Collector state grants no scientific authority.',
              'evidence': ('git:b82de83c3ea388e326288e3356770edc9518616f',
                           'docs/dev/process-heap-performance-2026-10-14.md',
                           'python/tests/test_workspace_process_heap.py',
                           'python/tests/test_workspace_projection_contract.py',
                           'python/tests/test_workspace_refresh_cache.py')},
             {'id': 'whole-trace-batch-compatibility-2026-10-14',
              'decision': 'compatible',
              'reviewed_build': ('6f8a583c021153c373ddc90e5f68aef1be8d690ed2882cbfb43eb814cb240230',
                                 'a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9',
                                 '8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd',
                                 '86606d41763c9b745cf303c50efbed3b13d3e7255ac6e9667d24fd7237a5420b',
                                 '04faa42a70bbd6f63044df7b1e67640b4a0f49b919b8f8c86294557f5a2ba024'),
              'legacy_owners': ('7dbf2d4d17fb0f06f084b0fd74a9e2376899afe07cba8257eb3c8fd803e55139',
                                'a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9',
                                '8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd',
                                '1f7da71b300a2c617cc6f67cf70a2790d609f3d115828e1b092a518003178be8'),
              'legacy_contract': 'd612c67e1297f3f64eb96339150a9b9a007d55003e8c5d38f21a8aa695d55f37',
              'rationale': 'Relative to installed source82d541e, removing only the new trace_batch method '
                           'and its canonical trace-reader identity capture yields an identical '
                           'WorkspaceService AST. All other projection owners and the resolver are '
                           'byte-identical. The batch is a foreground sample-read API; projection '
                           'construction, codecs, metadata values, scientific source verification and cache '
                           'formats are unchanged. Independently reviewed by the integration owner. Typed '
                           'lifecycle recovery separately reopens fully verified sidecars when old live '
                           'witnesses become stale; it grants no projection compatibility or authority.',
              'evidence': ('git:82d541e8300eb1b6930ff7f1bd35f974a6ca343e',
                           'docs/dev/trace-click-latency-2026-10-15.md',
                           'python/tests/test_workspace_projection_contract.py',
                           'python/tests/test_workspace_refresh_cache.py',
                           'python/tests/test_workspace_explore_queries.py')},
             {'id': 'direct-trace-read-compatibility-2026-10-15',
              'decision': 'compatible',
              'reviewed_build': ('6f8a583c021153c373ddc90e5f68aef1be8d690ed2882cbfb43eb814cb240230',
                                 'a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9',
                                 '8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd',
                                 '5c1934805538f2852c9d5ca43f7ecf46d9413a97fc21c18c1708611e8a16d008',
                                 '04faa42a70bbd6f63044df7b1e67640b4a0f49b919b8f8c86294557f5a2ba024'),
              'legacy_owners': ('7dbf2d4d17fb0f06f084b0fd74a9e2376899afe07cba8257eb3c8fd803e55139',
                                'a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9',
                                '8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd',
                                '1f7da71b300a2c617cc6f67cf70a2790d609f3d115828e1b092a518003178be8'),
              'legacy_contract': 'd612c67e1297f3f64eb96339150a9b9a007d55003e8c5d38f21a8aa695d55f37',
              'rationale': 'Relative to bf5064d, changes in workspace_service are restricted to exact '
                           'foreground H5 sample readers, trace_batch and their canonical identity captures. '
                           'Removing these trace-only nodes produces an identical whole-file AST. Other '
                           'projection owners and resolver are byte-identical. Metadata construction, '
                           'codecs, source projections and cache formats are unchanged. The direct reader '
                           'separately preserves identity, units, finite values, per-window and closing '
                           'source witnesses; it grants no projection authority.',
              'evidence': ('git:bf5064d7ad9ef4f6541395496bcd56c4c39a9003',
                           'docs/dev/trace-direct-read-2026-10-15.md',
                           'python/tests/test_workspace_projection_contract.py',
                           'python/tests/test_workspace_refresh_cache.py',
                           'python/tests/test_workspace_service.py')},
             {'id': 'native-trace-read-compatibility-2026-10-15',
              'decision': 'compatible',
              'reviewed_build': ('6f8a583c021153c373ddc90e5f68aef1be8d690ed2882cbfb43eb814cb240230',
                                 'a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9',
                                 '8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd',
                                 '4465a19b6a350561c0fd2c2bb8cc289fddce632cda1b56ee8f20fb9f12db1e71',
                                 '04faa42a70bbd6f63044df7b1e67640b4a0f49b919b8f8c86294557f5a2ba024'),
              'legacy_owners': ('7dbf2d4d17fb0f06f084b0fd74a9e2376899afe07cba8257eb3c8fd803e55139',
                                'a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9',
                                '8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd',
                                '1f7da71b300a2c617cc6f67cf70a2790d609f3d115828e1b092a518003178be8'),
              'legacy_contract': 'd612c67e1297f3f64eb96339150a9b9a007d55003e8c5d38f21a8aa695d55f37',
              'rationale': 'Relative to bf5064d, removing only foreground trace sample readers, trace_batch '
                           'and their canonical identity captures yields an identical whole-file AST. Other '
                           'projection owners and resolver are byte-identical. Native decompression affects '
                           'only exact trace sample reading, with separate type, filter, unit, finite and '
                           'closing source checks. No metadata projection, codec, membership or cache '
                           'authority changes.',
              'evidence': ('git:bf5064d7ad9ef4f6541395496bcd56c4c39a9003',
                           'docs/architecture/trace-worker-execution.md',
                           'python/tests/test_trace_native.py',
                           'python/tests/test_workspace_projection_contract.py',
                           'python/tests/test_workspace_service.py')},
             {'id': 'prepared-display-compatibility-2026-10-15',
              'decision': 'compatible',
              'reviewed_build': ('6f8a583c021153c373ddc90e5f68aef1be8d690ed2882cbfb43eb814cb240230',
                                 'a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9',
                                 '8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd',
                                 'f74371e38102b31877092bd8a82d4ce6f61bfa0148c09707c711cf24a4e5e200',
                                 '04faa42a70bbd6f63044df7b1e67640b4a0f49b919b8f8c86294557f5a2ba024'),
              'legacy_owners': ('7dbf2d4d17fb0f06f084b0fd74a9e2376899afe07cba8257eb3c8fd803e55139',
                                'a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9',
                                '8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd',
                                '1f7da71b300a2c617cc6f67cf70a2790d609f3d115828e1b092a518003178be8'),
              'legacy_contract': 'd612c67e1297f3f64eb96339150a9b9a007d55003e8c5d38f21a8aa695d55f37',
              'rationale': 'Relative to 8c77785, removing only WorkspaceService.trace_batch yields an '
                           'identical whole-file AST. Its changes add optional diagnostic stage clocks only. '
                           'Other projection owners and resolver are byte-identical. Prepared display reads '
                           'are separate from metadata projection, codec, membership and cache authority.',
              'evidence': ('git:8c77785cec23a4e804ddd6d199259bfcd30707bf',
                           'docs/architecture/trace-worker-execution.md',
                           'python/tests/test_trace_native.py',
                           'python/tests/test_workspace_projection_contract.py',
                           'python/tests/test_workspace_service.py')},
             {'id': 'geometry-display-compatibility-2026-10-15',
              'decision': 'compatible',
              'reviewed_build': ('6f8a583c021153c373ddc90e5f68aef1be8d690ed2882cbfb43eb814cb240230',
                                 'a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9',
                                 '8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd',
                                 '3c9fc897975c3345b6290e33c8b10fa63f4b93386642eefed112ae29fcb29121',
                                 '04faa42a70bbd6f63044df7b1e67640b4a0f49b919b8f8c86294557f5a2ba024'),
              'legacy_owners': ('7dbf2d4d17fb0f06f084b0fd74a9e2376899afe07cba8257eb3c8fd803e55139',
                                'a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9',
                                '8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd',
                                '1f7da71b300a2c617cc6f67cf70a2790d609f3d115828e1b092a518003178be8'),
              'legacy_contract': 'd612c67e1297f3f64eb96339150a9b9a007d55003e8c5d38f21a8aa695d55f37',
              'rationale': 'Relative to 9097d52, removing only _response_window_reader yields an identical '
                           'whole-file AST. The function consumes optional native unit-checked finite f64 '
                           'values instead of compound records; the generic reader retains its validations. '
                           'Other projection owners and resolver are byte-identical. Display geometry is a '
                           'separate response representation and changes no metadata projection, codec, '
                           'membership or cache authority.',
              'evidence': ('git:9097d5245deea6dc594a9ae17e63158804e6190b',
                           'docs/architecture/trace-worker-execution.md',
                           'python/tests/test_trace_native.py',
                           'python/tests/test_workspace_projection_contract.py',
                           'python/tests/test_workspace_service.py')},
             {'id': 'foreground-trace-qos-projection-compatibility-2026-10-15',
              'decision': 'compatible',
              'reviewed_build': ('6f8a583c021153c373ddc90e5f68aef1be8d690ed2882cbfb43eb814cb240230',
                                 'a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9',
                                 '8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd',
                                 'a15fe9699c8fdd5134ddc4e8a6640e0de630af784d0c116cb601da4899eb181c',
                                 '04faa42a70bbd6f63044df7b1e67640b4a0f49b919b8f8c86294557f5a2ba024'),
              'legacy_owners': ('7dbf2d4d17fb0f06f084b0fd74a9e2376899afe07cba8257eb3c8fd803e55139',
                                'a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9',
                                '8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd',
                                '1f7da71b300a2c617cc6f67cf70a2790d609f3d115828e1b092a518003178be8'),
              'legacy_contract': 'd612c67e1297f3f64eb96339150a9b9a007d55003e8c5d38f21a8aa695d55f37',
              'rationale': 'Relative to clean 5c78fd689c0c9c725272a7a7bdde359fe8b93e0e, workspace_service only '
                           'adds foreground=False keyword defaults to _response_window_reader and '
                           'WorkspaceService.trace_batch plus one conditional foreground=True forwarding '
                           'expression in each. Removing exactly those four AST edits yields an identical '
                           'whole-file AST; no method bodies are excluded. All other ordered projection owners '
                           'and resolver are byte-identical. Optional foreground scheduling changes no metadata '
                           'projection, codec, membership, source validation or cache authority.',
              'evidence': ('git:5c78fd689c0c9c725272a7a7bdde359fe8b93e0e',
                           'docs/dev/foreground-trace-qos-projection-compatibility-2026-10-15.md',
                           'docs/architecture/trace-worker-execution.md',
                           'python/tests/test_workspace_projection_contract.py',
                           'python/tests/test_workspace_refresh_cache.py',
                           'python/tests/test_trace_native.py',
                           'python/tests/test_trace_views.py')},
             {'id': 'metadata-digest-signature-cache-projection-compatibility-2026-10-16',
              'decision': 'compatible',
              'reviewed_build': ('6f8a583c021153c373ddc90e5f68aef1be8d690ed2882cbfb43eb814cb240230',
                                 'a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9',
                                 '8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd',
                                 'abf29bafbe61f61de2aa730c500680568632ceec6f89f0c72098f1069c8d6dc1',
                                 '04faa42a70bbd6f63044df7b1e67640b4a0f49b919b8f8c86294557f5a2ba024'),
              'legacy_owners': ('7dbf2d4d17fb0f06f084b0fd74a9e2376899afe07cba8257eb3c8fd803e55139',
                                'a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9',
                                '8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd',
                                '1f7da71b300a2c617cc6f67cf70a2790d609f3d115828e1b092a518003178be8'),
              'legacy_contract': 'd612c67e1297f3f64eb96339150a9b9a007d55003e8c5d38f21a8aa695d55f37',
              'rationale': 'Relative to clean 2fe57feee58a95247aef8612e0af31b4617cf8af, workspace_service only lets '
                           'refresh reuse a metadata file digest verified earlier in this process when the file signature '
                           '(path, device, inode, size, mtime and ctime) is unchanged, mirroring the existing recording '
                           'signature cache, and still compares that digest with the manifest. Projection keys, codecs, '
                           'membership, source validation and cache authority are unchanged; all other ordered owners and '
                           'the resolver are byte-identical.',
              'evidence': ('git:2fe57feee58a95247aef8612e0af31b4617cf8af',
                           'python/tests/test_workspace_projection_contract.py',
                           'python/tests/test_workspace_refresh_cache.py')},
             {'id': 'tag-time-filter-and-catalog-memo-projection-compatibility-2026-10-17',
              'decision': 'compatible',
              'reviewed_build': ('6f8a583c021153c373ddc90e5f68aef1be8d690ed2882cbfb43eb814cb240230',
                                 'a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9',
                                 '8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd',
                                 'cd48922db39a9089d177ed680af2ea04ab079655eea8925a493cb6db4784f570',
                                 '04faa42a70bbd6f63044df7b1e67640b4a0f49b919b8f8c86294557f5a2ba024'),
              'legacy_owners': ('7dbf2d4d17fb0f06f084b0fd74a9e2376899afe07cba8257eb3c8fd803e55139',
                                'a49da9dbddefd6fb8d617e13e4956bcf07a9110c8bbf8f9d82207f3281942ae9',
                                '8cb62575cf0fc6198a7e2d4d51e20d7ff14ad6172200bc917d13b3b2b9a372cd',
                                '1f7da71b300a2c617cc6f67cf70a2790d609f3d115828e1b092a518003178be8'),
              'legacy_contract': 'd612c67e1297f3f64eb96339150a9b9a007d55003e8c5d38f21a8aa695d55f37',
              'rationale': 'Relative to clean 9c462df72c5e755dd76637fe2b45ec5974a8f8a0, workspace_service only admits '
                           'shared tag-time fields in validate_tag_filter_predicate and annotation predicate validation '
                           '(object samples plus check_time_nodes), and lets the canonical shared-tag filter fallback '
                           'evaluate tag-time leaves against hydrated chip times. Projection keys, codecs, membership, '
                           'source validation and cache authority are unchanged; all other ordered owners and the '
                           'resolver are byte-identical. '
                           'Merged with the catalog memo (whose memo keys omit filter-only tag-time fields): '
                           'Relative to clean 9c462df, workspace_service only changes the body of '
                           'WorkspaceService._with_annotation_fields: annotation catalog fields are memoized per '
                           'field under an app-supplied native generation witness and recomputed otherwise. '
                           'Restoring that one method body yields the clean file byte for byte. Projection keys, '
                           'codecs, membership, source validation and cache authority are unchanged; all other '
                           'ordered owners and the resolver are byte-identical.',
              'evidence': ('git:9c462df72c5e755dd76637fe2b45ec5974a8f8a0',
                           'python/tests/test_workspace_tag_times.py',
                           'docs/dev/request-decoupling-audit.md',
                           'python/tests/test_workspace_slow_read_memos.py',
                           'python/tests/test_workspace_projection_contract.py',
                           'python/tests/test_workspace_refresh_cache.py')})}
