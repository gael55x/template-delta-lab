#!/usr/bin/env python3
"""Independent artifact checks. Usage: python3 verify_results.py [primary-dir wrong-dir]."""
import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parent


def rows(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def key(r):
    return r['family'], r['seed'], r['method'], r['repeat']


def verify(primary, wrong):
    baseline = rows(ROOT / 'results/baseline/raw.csv')
    reference = json.loads((ROOT / 'results/baseline/manifest.json').read_text())
    runs = []
    for shift, directory in enumerate((primary, wrong)):
        data = rows(directory / 'raw.csv')
        manifest = json.loads((directory / 'manifest.json').read_text())
        assert manifest['python'] == reference['python'], 'use baseline Python 3.12.0'
        assert manifest['zlib_runtime_version'] == reference['zlib_runtime_version']
        assert manifest['corpora'] == reference['corpora']
        assert manifest['seeds'] == list(range(10)) and manifest['repeats'] == 3
        assert len(data) == 450 and len({key(r) for r in data}) == 450
        assert {r['family'] for r in data} == {'sparse', 'heavy', 'random'}
        assert {r['method'] for r in data} == {'raw', 'zlib', 'dedup_zlib', 'delta', 'min_page'}
        for name, digest in manifest['sha256'].items():
            path = directory / name if name.endswith('.csv') else ROOT / name
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, name
        by = {key(r): r for r in data}
        for old in baseline:
            current = by[key(old)]
            assert all(current[k] == v for k, v in old.items() if k not in ('enc_ns', 'dec_ns')), key(old)
        for r in data:
            assert int(r['template_shift']) == shift
            total = int(r['total_bytes'])
            assert total == sum(int(r[k]) for k in ('payload_bytes', 'header_bytes', 'index_bytes', 'ref_bytes'))
            assert int(r['private_pages']) * 4096 == int(r['raw_bytes'])
            charge = 262144 if r['method'] in ('delta', 'min_page') else 0
            assert int(r['template_charge_bytes']) == charge
            assert int(r['charged_total_bytes']) == total + charge
            first = by[r['family'], r['seed'], r['method'], '0']
            assert all(r[k] == v for k, v in first.items() if k not in ('enc_ns', 'dec_ns', 'repeat'))
        summary = {(r['family'], r['quantity']): r for r in rows(directory / 'summary.csv')}
        for family in ('sparse', 'heavy', 'random'):
            paired = []
            for seed in map(str, range(10)):
                sample = {m: by[family, seed, m, '0'] for m in ('raw', 'zlib', 'dedup_zlib', 'delta', 'min_page')}
                raw, z, d, delta, mp = (int(sample[m]['total_bytes']) for m in sample)
                assert mp <= min(z, delta, raw)
                if family == 'random':
                    assert mp == raw and d - mp == 40 * int(sample['raw']['private_pages'])
                paired.append((mp - min(z, d), raw))
            for prefix, charge in (('primary', 0), ('charged', 262144)):
                for unit in ('bytes', 'pct_of_raw'):
                    values = [(d + charge) * (100 / raw if unit == 'pct_of_raw' else 1) for d, raw in paired]
                    q = summary[family, prefix + '_' + unit + ':min_page-best(zlib,dedup_zlib)']
                    for field, value in (('median', statistics.median(values)), ('min', min(values)), ('max', max(values))):
                        assert abs(float(q[field]) - value) <= 0.000051
                    assert int(q['n_seeds']) == 10 and int(q['n_negative']) == sum(v < 0 for v in values)
        runs.append({'rows': len(data), 'corpora': len(manifest['corpora']),
                     'page_roundtrips': sum(int(r['private_pages']) for r in data),
                     'raw_sha256': manifest['sha256']['raw.csv'], 'template_shift': shift})
    return {'status': 'passed', 'runs': runs, 'baseline_rows_matched_per_run': len(baseline)}


if __name__ == '__main__':
    paths = [Path(p) for p in sys.argv[1:]] or [ROOT / 'results/poc', ROOT / 'results/poc-wrong-template']
    if len(paths) != 2:
        sys.exit(__doc__)
    print(json.dumps(verify(*paths), indent=2))
