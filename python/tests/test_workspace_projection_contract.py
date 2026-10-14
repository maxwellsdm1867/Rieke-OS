"""Exact-vector contract admission; historical cache production is native evidence.

The temporary witnesses below test resolver behavior, not execution of an old
release. The current-source gate requires an explicit review of all five owners.
"""
import ast
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from disco.metadata import projection_contract
from disco.workbench.recipes import checksum


OWNERS = (
    'recording_workspace.py',
    'disco/metadata/projection_cache.py',
    'disco/metadata/metadata_objects.py',
    'workspace_service.py',
)


def sha(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


class ProjectionContractTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.resolver = self.root / 'projection_contract.py'
        self.resolver.write_bytes(b'reviewed resolver witness\n')
        self.receipts = self.root / 'projection_contract_receipts.py'
        self.owners = [sha('current owner ' + str(i)) for i in range(4)]
        self.legacy = [sha('legacy owner ' + str(i)) for i in range(4)]
        self.build = [*self.owners, sha(self.resolver.read_bytes())]
        self.review = {
            'id': 'synthetic-compatible-vector', 'decision': 'compatible',
            'reviewed_build': self.build, 'legacy_owners': self.legacy,
            'legacy_contract': checksum(self.legacy),
            'rationale': 'Synthetic exact-vector resolver test, not historical proof.',
            'evidence': ['This test fixture uses synthetic owner witnesses.'],
        }
        self.data = {'version': 1, 'owners': list(OWNERS), 'reviews': [self.review]}
        self.write_receipts(self.data)
        patched = patch.object(projection_contract, '__file__', str(self.resolver))
        patched.start()
        self.addCleanup(patched.stop)

    def write_receipts(self, data):
        self.receipts.write_text('COMPATIBILITY_RECEIPTS = ' + repr(data) + '\n')

    def resolve(self, owners=None):
        return projection_contract.resolve_projection_contract(self.owners if owners is None else owners)

    def fallback(self, owners=None):
        values = self.owners if owners is None else owners
        return checksum([*values, sha(self.resolver.read_bytes())])

    def test_exact_review_uses_legacy_four_owner_checksum(self):
        self.assertEqual(self.resolve(), checksum(self.legacy))
        self.assertEqual(self.resolve(tuple(self.owners)), checksum(self.legacy))
        self.assertNotEqual(checksum(self.legacy), self.fallback())

    def test_unknown_complete_vector_uses_recipes_checksum_of_all_five(self):
        unknown = [sha('unknown ' + str(i)) for i in range(4)]
        self.assertEqual(self.resolve(unknown), self.fallback(unknown))
        self.assertNotEqual(self.resolve(unknown), checksum(unknown))

    def test_each_owner_change_falls_back_without_partial_admission(self):
        for position in range(4):
            with self.subTest(owner=OWNERS[position]):
                changed = list(self.owners)
                changed[position] = sha('changed bytes ' + str(position))
                self.assertEqual(self.resolve(changed), self.fallback(changed))
                self.assertNotEqual(self.resolve(changed), checksum(self.legacy))

    def test_resolver_byte_change_falls_back_even_with_unchanged_owner_vector(self):
        self.resolver.write_bytes(self.resolver.read_bytes() + b'# one resolver change\n')
        self.assertEqual(self.resolve(), self.fallback())
        self.assertNotEqual(self.resolve(), checksum(self.legacy))

    def test_multiple_reviews_do_not_authorize_a_cartesian_mix(self):
        other = copy.deepcopy(self.review)
        other['id'] = 'second-complete-vector'
        other['reviewed_build'] = [sha('other owner ' + str(i)) for i in range(4)] + [self.build[4]]
        self.data['reviews'].append(other)
        self.write_receipts(self.data)
        self.assertEqual(self.resolve(other['reviewed_build'][:4]), checksum(self.legacy))
        mixed = [self.owners[0], other['reviewed_build'][1], self.owners[2], other['reviewed_build'][3]]
        self.assertEqual(self.resolve(mixed), self.fallback(mixed))

    def test_explicit_breaking_review_keeps_full_vector_identity(self):
        self.review.update(decision='breaking', legacy_owners=None, legacy_contract=None)
        self.write_receipts(self.data)
        self.assertEqual(self.resolve(), self.fallback())

    def test_invalid_receipt_schemas_and_reviews_are_cache_misses(self):
        cases = []

        def changed(label, mutate):
            data = copy.deepcopy(self.data)
            mutate(data)
            cases.append((label, data))

        changed('version', lambda d: d.update(version=2))
        changed('boolean version', lambda d: d.update(version=True))
        changed('extra schema field', lambda d: d.update(extra=True))
        changed('missing schema field', lambda d: d.pop('owners'))
        changed('owner order', lambda d: d.update(owners=list(reversed(OWNERS))))
        changed('empty reviews', lambda d: d.update(reviews=[]))
        changed('duplicate complete vector', lambda d: d['reviews'].append({**copy.deepcopy(d['reviews'][0]), 'id': 'other-id'}))
        changed('duplicate review id', lambda d: d['reviews'].append({**copy.deepcopy(d['reviews'][0]), 'reviewed_build': [sha('other')] * 5}))
        changed('missing review field', lambda d: d['reviews'][0].pop('evidence'))
        changed('extra review field', lambda d: d['reviews'][0].update(extra=True))
        changed('legacy checksum mismatch', lambda d: d['reviews'][0].update(legacy_contract=sha('wrong')))
        changed('incomplete build', lambda d: d['reviews'][0].update(reviewed_build=self.owners))
        changed('incomplete legacy', lambda d: d['reviews'][0].update(legacy_owners=self.legacy[:3]))
        changed('empty rationale', lambda d: d['reviews'][0].update(rationale=' '))
        changed('empty evidence', lambda d: d['reviews'][0].update(evidence=[]))
        changed('unknown decision', lambda d: d['reviews'][0].update(decision='maybe'))
        changed('breaking with legacy', lambda d: d['reviews'][0].update(decision='breaking'))
        for label, data in cases:
            with self.subTest(case=label):
                self.write_receipts(data)
                self.assertEqual(self.resolve(), self.fallback())

    def test_malformed_nonliteral_and_executable_receipts_are_not_executed(self):
        sentinel = self.root / 'must-not-exist'
        samples = [
            'COMPATIBILITY_RECEIPTS = {',
            'OTHER = ' + repr(self.data),
            'COMPATIBILITY_RECEIPTS = dict()',
            'COMPATIBILITY_RECEIPTS: dict = ' + repr(self.data),
            'COMPATIBILITY_RECEIPTS = OTHER = ' + repr(self.data),
            'import pathlib\nCOMPATIBILITY_RECEIPTS = ' + repr(self.data),
            'COMPATIBILITY_RECEIPTS = ' + repr(self.data) + '\npass',
            f'COMPATIBILITY_RECEIPTS = __import__("pathlib").Path({str(sentinel)!r}).touch()',
        ]
        for source in samples:
            with self.subTest(source=source):
                self.receipts.write_text(source)
                self.assertEqual(self.resolve(), self.fallback())
                self.assertFalse(sentinel.exists())
        self.receipts.write_bytes(b'\xff')
        self.assertEqual(self.resolve(), self.fallback())

    def test_missing_symlink_directory_and_oversize_receipts_are_misses(self):
        self.receipts.unlink()
        self.assertEqual(self.resolve(), self.fallback())
        target = self.root / 'valid-receipt.py'
        target.write_text('COMPATIBILITY_RECEIPTS = ' + repr(self.data))
        self.receipts.symlink_to(target)
        self.assertEqual(self.resolve(), self.fallback())
        self.receipts.unlink()
        self.receipts.mkdir()
        self.assertEqual(self.resolve(), self.fallback())
        self.receipts.rmdir()
        self.receipts.write_text('COMPATIBILITY_RECEIPTS = ' + repr(self.data) + '\n#' + 'x' * 131072)
        self.assertEqual(self.resolve(), self.fallback())

    def test_missing_or_invalid_owner_arguments_fail(self):
        with self.assertRaises(TypeError):
            projection_contract.resolve_projection_contract()
        invalid = [None, {}, set(self.owners), iter(self.owners), self.owners[:3],
                   self.owners + [sha('fifth')], 'a' * 64,
                   [None, *self.owners[1:]], ['A' * 64, *self.owners[1:]],
                   ['g' * 64, *self.owners[1:]], ['0' * 63, *self.owners[1:]]]
        for values in invalid:
            with self.subTest(values=repr(values)):
                with self.assertRaises(ValueError):
                    projection_contract.resolve_projection_contract(values)


class CurrentProjectionContractReviewTests(unittest.TestCase):
    def test_current_source_has_one_exact_explicit_review(self):
        # This is a source-change review gate. It does not claim that synthetic
        # fixtures were generated by an old release; native upgrade evidence
        # separately establishes historical cache production and admission.
        python_root = Path(__file__).resolve().parents[1]
        resolver_path = python_root / 'disco/metadata/projection_contract.py'
        owners = [sha((python_root / relative).read_bytes()) for relative in OWNERS]
        build = [*owners, sha(resolver_path.read_bytes())]
        path = resolver_path.with_name('projection_contract_receipts.py')
        self.assertFalse(path.is_symlink())
        source = path.read_bytes()
        self.assertLessEqual(len(source), 131072)
        statements = ast.parse(source.decode('utf-8')).body
        if (statements and isinstance(statements[0], ast.Expr)
                and isinstance(statements[0].value, ast.Constant)
                and type(statements[0].value.value) is str):
            statements = statements[1:]
        self.assertEqual(len(statements), 1)
        assignment = statements[0]
        self.assertIsInstance(assignment, ast.Assign)
        self.assertEqual(len(assignment.targets), 1)
        self.assertIsInstance(assignment.targets[0], ast.Name)
        self.assertEqual(assignment.targets[0].id, 'COMPATIBILITY_RECEIPTS')
        data = ast.literal_eval(assignment.value)
        self.assertEqual(set(data), {'version', 'owners', 'reviews'})
        self.assertIs(type(data['version']), int)
        self.assertEqual(data['version'], 1)
        self.assertEqual(tuple(data['owners']), OWNERS)
        matches = [review for review in data['reviews'] if tuple(review['reviewed_build']) == tuple(build)]
        self.assertEqual(len(matches), 1, 'Changed projection owners/resolver require one explicit compatibility or breaking review')
        review = matches[0]
        self.assertTrue(review['id'].strip())
        self.assertTrue(review['rationale'].strip())
        self.assertTrue(review['evidence'])
        self.assertTrue(all(isinstance(item, str) and item.strip() for item in review['evidence']))
        if review['decision'] == 'compatible':
            self.assertEqual(len(review['legacy_owners']), 4)
            expected = checksum(list(review['legacy_owners']))
            self.assertEqual(review['legacy_contract'], expected)
        else:
            self.assertEqual(review['decision'], 'breaking')
            self.assertIsNone(review['legacy_owners'])
            self.assertIsNone(review['legacy_contract'])
            expected = checksum(build)
        self.assertEqual(projection_contract.resolve_projection_contract(owners), expected)


if __name__ == '__main__':
    unittest.main()
