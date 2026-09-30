import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('desktop_release', Path(__file__).resolve().parents[2] / 'tools/desktop_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class DesktopReleaseTests(unittest.TestCase):
    def evidence(self):
        return {'format': 'rieke-desktop-qualification', 'version': 1, 'application_version': '1.0.0',
                'platform': 'darwin', 'architecture': 'arm64', 'source_commit': 'a' * 40,
                'artifacts': {'app.zip': {'sha256': 'b' * 64, 'size': 10}},
                'requirements': {key: {'passed': True, 'receipts': [{'description': 'Reviewed real-artifact run', 'sha256': 'c' * 64}]} for key in release.REQUIREMENTS}}

    def test_incomplete_qualification_and_different_bytes_rejected(self):
        evidence = self.evidence()
        release.validate_evidence(evidence, evidence['artifacts'], '1.0.0')
        with self.assertRaises(ValueError):
            release.validate_evidence(evidence, {}, '1.0.0')
        for requirement in release.REQUIREMENTS:
            evidence = self.evidence()
            evidence['requirements'][requirement]['passed'] = False
            with self.assertRaises(ValueError):
                release.validate_evidence(evidence, evidence['artifacts'], '1.0.0')

    def test_mock_counts_and_unsigned_receipts_cannot_replace_requirement_evidence(self):
        evidence = self.evidence()
        evidence['requirements'] = {'tests_passed': 500}
        with self.assertRaises(ValueError):
            release.validate_evidence(evidence, evidence['artifacts'], '1.0.0')

    def test_stable_version_and_canonical_repository_required(self):
        for value in ('1.0.0-beta', 'v1.0.0', '01.0.0', None):
            with self.assertRaises(ValueError):
                release.version(value)
        with self.assertRaises(ValueError):
            release.baseline('v1.0.0', 'other/repo')


if __name__ == '__main__':
    unittest.main()
