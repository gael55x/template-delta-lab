#!/usr/bin/env python3
"""Independent artifact checks. Usage: python3 verify_results.py [primary-dir wrong-dir]

Authoritative: SHA-256 of code and CSVs, full corpus identity, baseline byte fields,
byte accounting, repeat stability, bounds and paired summaries. Python build and zlib
runtime strings are returned as diagnostics; byte identity is enforced by the checks above.
"""
import csv
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys

ROOT = Path(__file__).resolve().parent
FAMILIES = ('sparse', 'heavy', 'random')
METHODS = ('raw', 'zlib', 'dedup_zlib', 'delta', 'min_page')
HASHED = ('poc.py', 'test_poc.py', 'PREREGISTRATION.md', 'IMPLEMENTATION.md', 'raw.csv', 'summary.csv')
RUNTIME = ('python', 'implementation', 'platform', 'machine', 'zlib_version', 'zlib_runtime_version')


class VerificationError(Exception):
    pass


def need(condition, message):
    # Explicit raise rather than assert so every check also runs under python -O.
    if not condition:
        raise VerificationError(message)


def rows(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))


def key(r):
    return r['family'], r['seed'], r['method'], r['repeat']


def verify(primary, wrong):
    baseline = rows(ROOT / 'results/baseline/raw.csv')
    reference = json.loads((ROOT / 'results/baseline/manifest.json').read_text())
    runs = []
    for shift, directory in enumerate((Path(primary), Path(wrong))):
        data = rows(directory / 'raw.csv')
        manifest = json.loads((directory / 'manifest.json').read_text())
        need(manifest['corpora'] == reference['corpora'], 'corpus identity differs from baseline')
        need(manifest['seeds'] == list(range(10)) and manifest['repeats'] == 3, 'seeds/repeats differ from protocol')
        need(len(data) == 450 and len({key(r) for r in data}) == 450, 'expected 450 unique rows')
        need({r['family'] for r in data} == set(FAMILIES), 'unexpected families')
        need({r['method'] for r in data} == set(METHODS), 'unexpected methods')
        need({r['seed'] for r in data} == set(map(str, range(10))) and {r['repeat'] for r in data} == {'0', '1', '2'},
             'incomplete seed/repeat grid')
        need(set(HASHED) <= set(manifest['sha256']), 'manifest omits a required sha256')
        for name, digest in manifest['sha256'].items():
            path = directory / name if name.endswith('.csv') else ROOT / name
            need(hashlib.sha256(path.read_bytes()).hexdigest() == digest, f'sha256 mismatch: {name}')
        by = {key(r): r for r in data}
        for old in baseline:
            current = by.get(key(old))
            need(current is not None and all(current[k] == v for k, v in old.items() if k not in ('enc_ns', 'dec_ns')),
                 f'baseline field mismatch: {key(old)}')
        for r in data:
            need(int(r['template_shift']) == shift, f'template_shift: {key(r)}')
            total = int(r['total_bytes'])
            need(total == sum(int(r[k]) for k in ('payload_bytes', 'header_bytes', 'index_bytes', 'ref_bytes')),
                 f'byte accounting: {key(r)}')
            need(int(r['private_pages']) * 4096 == int(r['raw_bytes']), f'raw_bytes != private_pages*4096: {key(r)}')
            charge = 262144 if r['method'] in ('delta', 'min_page') else 0
            need(int(r['template_charge_bytes']) == charge, f'template charge: {key(r)}')
            need(int(r['charged_total_bytes']) == total + charge, f'charged total: {key(r)}')
            first = by[r['family'], r['seed'], r['method'], '0']
            need(all(r[k] == v for k, v in first.items() if k not in ('enc_ns', 'dec_ns', 'repeat')),
                 f'repeat differs from repeat 0: {key(r)}')
        summary = {(r['family'], r['quantity']): r for r in rows(directory / 'summary.csv')}
        for family in FAMILIES:
            paired = []
            for seed in map(str, range(10)):
                sample = {m: by[family, seed, m, '0'] for m in METHODS}
                raw, z, d, delta, mp = (int(sample[m]['total_bytes']) for m in METHODS)
                need(mp <= min(z, delta, raw), f'min_page bound: {family} seed {seed}')
                if family == 'random':
                    need(mp == raw and d - mp == 40 * int(sample['raw']['private_pages']),
                         f'random-family expectation: seed {seed}')
                paired.append((mp - min(z, d), raw))
            for prefix, charge in (('primary', 0), ('charged', 262144)):
                for unit in ('bytes', 'pct_of_raw'):
                    values = [(d + charge) * (100 / raw if unit == 'pct_of_raw' else 1) for d, raw in paired]
                    name = prefix + '_' + unit + ':min_page-best(zlib,dedup_zlib)'
                    q = summary.get((family, name))
                    need(q is not None, f'summary missing: {family} {name}')
                    for field, value in (('median', statistics.median(values)), ('min', min(values)), ('max', max(values))):
                        need(abs(float(q[field]) - value) <= 0.000051, f'summary {field}: {family} {name}')
                    need(int(q['n_seeds']) == 10 and int(q['n_negative']) == sum(v < 0 for v in values),
                         f'summary counts: {family} {name}')
        runtime = {k: manifest.get(k) for k in RUNTIME}
        runs.append({'rows': len(data), 'corpora': len(manifest['corpora']),
                     'page_roundtrips': sum(int(r['private_pages']) for r in data),
                     'raw_sha256': manifest['sha256']['raw.csv'], 'template_shift': shift,
                     'runtime': runtime,
                     'runtime_differs_from_baseline': [k for k in RUNTIME if runtime[k] != reference.get(k)]})
    return {'status': 'passed', 'runs': runs, 'baseline_rows_matched_per_run': len(baseline),
            'baseline_runtime': {k: reference.get(k) for k in RUNTIME},
            'verifier_python': platform.python_version(),
            'runtime_policy': 'diagnostic only; not a pass/fail criterion'}


if __name__ == '__main__':
    paths = [Path(p) for p in sys.argv[1:]] or [ROOT / 'results/poc', ROOT / 'results/poc-wrong-template']
    if len(paths) != 2:
        sys.exit(__doc__)
    try:
        report = verify(*paths)
    except (VerificationError, KeyError, ValueError, OSError) as e:
        sys.exit(f'verification failed: {e!r}')
    print(json.dumps(report, indent=2))
