#!/usr/bin/env python3
"""Verifier portability: runtime strings are diagnostic, measurements are not."""
import csv
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_results as vr  # noqa: E402

OTHER_RUNTIME = {'python': '3.13.1 (main, Jan 1 2026, 00:00:00) [GCC 14.2.0]', 'platform': 'Linux-6.8.0-x86_64',
                 'zlib_version': '1.3.1', 'zlib_runtime_version': '1.3.1.zlib-ng'}


def stage(tmp):
    """Copy only the committed per-run artifacts, then rewrite runtime strings in each manifest."""
    dirs = []
    for name in ('poc', 'poc-wrong-template'):
        out = Path(tmp) / name
        out.mkdir()
        for f in ('raw.csv', 'summary.csv', 'manifest.json'):
            shutil.copyfile(vr.ROOT / 'results' / name / f, out / f)
        manifest = json.loads((out / 'manifest.json').read_text())
        manifest.update(OTHER_RUNTIME)
        (out / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        dirs.append(out)
    return dirs


class RuntimePortability(unittest.TestCase):
    def test_runtime_strings_diagnostic_measurements_authoritative(self):
        with tempfile.TemporaryDirectory() as tmp:
            primary, wrong = stage(tmp)
            report = vr.verify(primary, wrong)
            self.assertEqual(report['status'], 'passed')
            self.assertIn('zlib_runtime_version', report['runs'][0]['runtime_differs_from_baseline'])

            # Consistent tamper (accounting still sums) with the raw hash updated to defeat hash-only checks.
            path = primary / 'raw.csv'
            with path.open(newline='') as f:
                reader = csv.DictReader(f)
                fields, data = reader.fieldnames, list(reader)
            row = next(r for r in data if (r['family'], r['seed'], r['method'], r['repeat']) == ('sparse', '3', 'min_page', '2'))
            for k in ('payload_bytes', 'total_bytes', 'charged_total_bytes'):
                row[k] = str(int(row[k]) - 1)
            with path.open('w', newline='') as f:
                writer = csv.DictWriter(f, fields, lineterminator='\n')
                writer.writeheader()
                writer.writerows(data)
            manifest = json.loads((primary / 'manifest.json').read_text())
            manifest['sha256']['raw.csv'] = hashlib.sha256(path.read_bytes()).hexdigest()
            (primary / 'manifest.json').write_text(json.dumps(manifest, indent=2))

            with self.assertRaises(vr.VerificationError) as caught:
                vr.verify(primary, wrong)
            self.assertNotIn('sha256', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
