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
              'rationale': 'Relative to add33d153ae8f533d5c4a68c50690764323c4336, recording_workspace '
                           'only adds recording_location during NEW import CLI handling. '
                           'Existing-project projection construction, codecs and verification are '
                           'unchanged. WorkspaceService only delegates its contract selection to this '
                           'exact reviewed resolver. Native index, typed index and scientific-input '
                           'witnesses remain unchanged.',
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
                           'construction, codecs, scientific input checks and all other vector owners '
                           'are unchanged. Independently reviewed as additive display metadata; no '
                           'reads, membership or authority changes.',
              'evidence': ('git:6b81372',
                           'docs/dev/cell-identity-placement-2026-10-14.md',
                           'python/tests/test_workspace_projection_contract.py',
                           'python/tests/test_workspace_tree_pages.py',
                           'python/tests/test_workspace_refresh_cache.py')})}
