#!/usr/bin/env python3
# Synthetic template-delta page-compression POC: raw, zlib and exact dedup + zlib baselines, plus the
# preregistered template delta and per-page min(raw, zlib, delta).
# Original stdlib-only code; not a reproduction of arXiv:2609.11294. See README.md, PREREGISTRATION.md, IMPLEMENTATION.md.
import argparse
import csv
import datetime
import hashlib
import json
import os
import platform
import random
import statistics
import sys
import time
import zlib

PAGE = 4096
BLOCK = 64
BLOCKS = PAGE // BLOCK
ZLEVEL = 9
HEADER = 8       # per encoded page: codec tag, length, location; a delta's 6-bit template index fits here too
BITMAP = BLOCKS // 8  # delta: 8 B, bit b set when 64-B block b differs from the template page
HASH_ENTRY = 32  # dedup index: sha256 digest per stored object
REFCOUNT = 8     # dedup index: refcount per stored object
REF = 8          # dedup: pointer per duplicate page

N_TEMPLATE = 64
N_SANDBOX = 8
TEMPLATE_CHARGE = N_TEMPLATE * PAGE  # sensitivity accounting: 262144 B once per family and seed
SEEDS = tuple(range(10))
REPEATS = 3
METHODS = ('raw', 'zlib', 'dedup_zlib', 'delta', 'min_page')
TEMPLATE_METHODS = ('delta', 'min_page')  # read the template during decode; only these pay TEMPLATE_CHARGE
BASELINES = ('zlib', 'dedup_zlib')        # per-seed best baseline in the primary quantity
PAIRS = (('zlib', 'raw'), ('dedup_zlib', 'zlib'), ('dedup_zlib', 'raw'),
         ('delta', 'zlib'), ('min_page', 'raw'), ('min_page', 'zlib'), ('min_page', 'dedup_zlib'))
PRIMARY = 'min_page-best(zlib,dedup_zlib)'
TEMPLATE_KINDS = (('zero', 2), ('struct', 5), ('text', 2), ('rand', 1))
WORDS = (b'agent ', b'tool ', b'call ', b'result ', b'error ', b'path ', b'step ', b'None, ', b'id=', b'0x7f3a ')

# dirty: P(a sandbox writes a template page); blocks: 64-B blocks overwritten per write;
# rewrite: P(the write stores identical bytes, so the page stays copy-on-write shared);
# shared: P(the write yields the per-page variant common to all sandboxes -> exact duplicates);
# fresh: kinds of the overwritten blocks.
FAMILIES = {
    'sparse': {'dirty': 0.5, 'blocks': 2, 'rewrite': 0.1, 'shared': 0.6, 'fresh': ('struct', 'text')},
    'heavy': {'dirty': 0.75, 'blocks': 48, 'rewrite': 0.0, 'shared': 0.0, 'fresh': ('struct', 'text', 'rand', 'rand')},
    'random': {'dirty': 1.0, 'blocks': BLOCKS, 'rewrite': 0.0, 'shared': 0.0, 'fresh': ('rand',)},
}


def _block(rng, kind):
    if kind == 'zero':
        return bytes(BLOCK)
    if kind == 'struct':  # little-endian counters with a small stride
        base, step = rng.randrange(1 << 20), rng.randrange(1, 9)
        return b''.join((base + i * step).to_bytes(4, 'little') for i in range(BLOCK // 4))
    if kind == 'text':
        out = b''
        while len(out) < BLOCK:
            out += rng.choice(WORDS)
        return out[:BLOCK]
    return rng.randbytes(BLOCK)


def _mutate(rng, page, nblocks, fresh):
    blocks = [page[i:i + BLOCK] for i in range(0, PAGE, BLOCK)]
    for i in rng.sample(range(BLOCKS), nblocks):
        blocks[i] = _block(rng, rng.choice(fresh))
    return b''.join(blocks)


def make_corpus(family, seed):
    """Return (template, private, excluded); private is a list of (template_index, page).

    A page byte-identical to its template page stays copy-on-write shared: it is counted
    in excluded and never enters the private set, for every method.
    """
    p = FAMILIES[family]
    rng = random.Random(f'{family}:{seed}')
    kinds, weights = zip(*TEMPLATE_KINDS)
    template = [b''.join(_block(rng, k) for _ in range(BLOCKS)) for k in rng.choices(kinds, weights, k=N_TEMPLATE)]
    shared = [_mutate(rng, t, p['blocks'], p['fresh']) for t in template]
    private, excluded = [], 0
    for _ in range(N_SANDBOX):
        for i, t in enumerate(template):
            if rng.random() >= p['dirty']:
                continue
            r = rng.random()
            if r < p['rewrite']:
                page = t
            elif r < p['rewrite'] + p['shared']:
                page = shared[i]
            else:
                page = _mutate(rng, t, p['blocks'], p['fresh'])
            if page == t:
                excluded += 1
            else:
                private.append((i, page))
    return template, private, excluded


def corpus_sha256(template, private):
    h = hashlib.sha256(b'w40-template-delta-corpus-v1')
    h.update(len(template).to_bytes(4, 'little'))
    for page in template:
        h.update(page)
    for i, page in private:
        h.update(i.to_bytes(4, 'little'))
        h.update(page)
    return h.hexdigest()


def store_page(page):
    """Per-page zlib with admission: keep the page resident unless compressing it saves bytes."""
    blob = zlib.compress(page, ZLEVEL)
    return ('z', blob) if len(blob) + HEADER < PAGE else ('r', page)


def delta_blob(page, base):
    """8-B little-endian bitmap of the blocks that differ from base, then those blocks verbatim in block order."""
    bitmap, changed = 0, []
    for b in range(BLOCKS):
        block = page[b * BLOCK:(b + 1) * BLOCK]
        if block != base[b * BLOCK:(b + 1) * BLOCK]:
            bitmap |= 1 << b
            changed.append(block)
    return bitmap.to_bytes(BITMAP, 'little') + b''.join(changed)


def apply_delta(base, blob):
    bitmap, pos, blocks = int.from_bytes(blob[:BITMAP], 'little'), BITMAP, []
    for b in range(BLOCKS):
        if bitmap >> b & 1:
            blocks.append(blob[pos:pos + BLOCK])
            pos += BLOCK
        else:
            blocks.append(base[b * BLOCK:(b + 1) * BLOCK])
    if pos != len(blob):
        raise AssertionError('delta length does not match its bitmap')
    return b''.join(blocks)


def store_delta(page, template, j):
    """Template delta with admission; j is the explicit template index the decoder reads from the object."""
    blob = delta_blob(page, template[j])
    return ('d', j, blob) if HEADER + len(blob) < PAGE else ('r', page)


def stored_cost(obj):
    """Stored bytes of one object: 4096 if resident, else its 8-B header plus its encoding."""
    return PAGE if obj[0] == 'r' else HEADER + len(obj[-1])


def cheapest(candidates):
    """Lowest stored cost; min() keeps the first of equal costs, so pass candidates as raw, zlib, delta."""
    return min(candidates, key=stored_cost)


def store_min(page, template, j):
    return cheapest((('r', page), store_page(page), store_delta(page, template, j)))


def load_page(obj, template=None):
    codec = obj[0]
    if codec == 'z':
        return zlib.decompress(obj[1])
    if codec == 'd':
        return apply_delta(template[obj[1]], obj[2])
    return obj[1]


def encode(method, pages, template=None, indices=None):
    """Return (objects, refs); page k decodes from objects[refs[k]].

    delta and min_page pair page k with template[indices[k]] and keep that index in the object;
    template pages are never placed in the encoded objects. Baselines ignore template and indices.
    """
    if method == 'raw':
        return [('r', p) for p in pages], list(range(len(pages)))
    if method == 'zlib':
        return [store_page(p) for p in pages], list(range(len(pages)))
    if method in TEMPLATE_METHODS:
        if len(indices) != len(pages):
            raise ValueError('need one template index per page')
        store = store_delta if method == 'delta' else store_min
        return [store(p, template, j) for p, j in zip(pages, indices)], list(range(len(pages)))
    if method != 'dedup_zlib':
        raise ValueError(f'unknown method {method!r}')
    index, firsts, objects, refs = {}, [], [], []
    for page in pages:
        digest = hashlib.sha256(page).digest()
        j = index.get(digest)
        if j is None:
            j = index[digest] = len(objects)
            firsts.append(page)
            objects.append(store_page(page))
        elif firsts[j] != page:  # full compare on hit, as a merging scanner would
            raise AssertionError('sha256 collision')
        refs.append(j)
    return objects, refs


def decode(encoded, template=None):
    objects, refs = encoded
    loaded = [load_page(obj, template) for obj in objects]
    return [loaded[j] for j in refs]


def account(method, encoded):
    """Byte accounting for one encoded corpus.

    total_bytes is the primary accounting: template pages are shared-resident and charged to no method.
    charged_total_bytes adds TEMPLATE_CHARGE to the methods that read the template during decode, even
    when admission selected no delta for any page (see IMPLEMENTATION.md).
    """
    objects, refs = encoded
    encoded_objs = [obj for obj in objects if obj[0] != 'r']
    deltas = [obj[2] for obj in objects if obj[0] == 'd']
    resident = len(objects) - len(encoded_objs)
    acct = {
        'stored_objects': len(objects),
        'compressed_objects': len(encoded_objs) - len(deltas),
        'delta_objects': len(deltas),
        'resident_objects': resident,
        'changed_blocks': sum((len(blob) - BITMAP) // BLOCK for blob in deltas),
        'duplicate_pages': len(refs) - len(objects),
        'payload_bytes': sum(len(obj[-1]) for obj in encoded_objs) + resident * PAGE,
        'header_bytes': len(encoded_objs) * HEADER,
        'index_bytes': len(objects) * (HASH_ENTRY + REFCOUNT) if method == 'dedup_zlib' else 0,
        'ref_bytes': (len(refs) - len(objects)) * REF,
    }
    acct['total_bytes'] = acct['payload_bytes'] + acct['header_bytes'] + acct['index_bytes'] + acct['ref_bytes']
    acct['template_charge_bytes'] = TEMPLATE_CHARGE if method in TEMPLATE_METHODS else 0
    acct['charged_total_bytes'] = acct['total_bytes'] + acct['template_charge_bytes']
    return acct


def _saving(total, raw):
    return 100.0 * (1 - total / raw) if raw else 0.0


def run(seeds, families, repeats, wrong_template=False):
    """Benchmark every method on identical corpora; returns (rows, corpora). Aborts on any invariant failure.

    With wrong_template, delta and min_page pair a page of template i with template (i + 1) mod 64 in both
    encode and decode; baselines and corpus hashes are unchanged.
    """
    shift = 1 if wrong_template else 0
    rows, corpora = [], []
    for family in families:
        for seed in seeds:
            template, private, excluded = make_corpus(family, seed)
            pages = [page for _, page in private]
            indices = [(i + shift) % len(template) for i, _ in private]
            corpus = {
                'corpus_sha256': corpus_sha256(template, private),
                'template_pages': len(template),
                'template_bytes': len(template) * PAGE,
                'private_pages': len(pages),
                'excluded_cow_pages': excluded,
                'raw_bytes': len(pages) * PAGE,
            }
            corpora.append({'family': family, 'seed': seed, **corpus})
            first = {}
            for rep in range(repeats):
                encs = {}
                for method in METHODS:
                    t0 = time.perf_counter_ns()
                    enc = encs[method] = encode(method, pages, template, indices)
                    t1 = time.perf_counter_ns()
                    out = decode(enc, template)
                    t2 = time.perf_counter_ns()
                    where = f'{family} seed={seed} {method} repeat={rep}'
                    if out != pages:
                        raise AssertionError('round-trip failed: ' + where)
                    acct = account(method, enc)
                    if first.setdefault(method, acct) != acct:
                        raise AssertionError('sizes differ between repeats: ' + where)
                    if method != 'dedup_zlib' and acct['total_bytes'] > corpus['raw_bytes']:
                        raise AssertionError('admission violated: ' + where)
                    rows.append({'family': family, 'seed': seed, 'method': method, 'repeat': rep, 'template_shift': shift,
                                 **corpus, **acct,
                                 'saving_pct': round(_saving(acct['total_bytes'], corpus['raw_bytes']), 4),
                                 'charged_saving_pct': round(_saving(acct['charged_total_bytes'], corpus['raw_bytes']), 4),
                                 'enc_ns': t1 - t0, 'dec_ns': t2 - t1})
                costs = {m: [stored_cost(obj) for obj in encs[m][0]] for m in ('raw', 'zlib', 'delta', 'min_page')}
                for k, cost in enumerate(costs['min_page']):
                    if cost != min(costs['raw'][k], costs['zlib'][k], costs['delta'][k]):
                        raise AssertionError(f'min_page bound violated: {family} seed={seed} page={k} repeat={rep}')
    return rows, corpora


def _pct_of_raw(d, raws):
    return [100.0 * x / r if r else 0.0 for x, r in zip(d, raws)]


def summarize(rows):
    """Median and [min, max] across seeds, per family, plus the number of seeds below zero.

    Sizes come from repeat 0 (run() asserts they are identical across repeats); timings use
    the per-seed median over repeats. delta_* is first method minus second, so a negative
    value means the first method stores fewer bytes. The primary quantity is paired per seed,
    total(min_page) - min(total(zlib), total(dedup_zlib)); its charged twin uses min_page's
    charged total. Family medians are never subtracted from each other.
    """
    size, enc, dec = {}, {}, {}
    for r in rows:
        key = (r['family'], int(r['seed']), r['method'])
        if int(r['repeat']) == 0:
            size[key] = (int(r['total_bytes']), int(r['raw_bytes']), int(r['charged_total_bytes']))
        enc.setdefault(key, []).append(int(r['enc_ns']))
        dec.setdefault(key, []).append(int(r['dec_ns']))
    out = []
    for family in dict.fromkeys(k[0] for k in size):
        seeds = sorted({k[1] for k in size if k[0] == family})
        raws = [size[family, s, 'raw'][1] for s in seeds]
        series = {}
        for m in METHODS:
            series['saving_pct:' + m] = [_saving(*size[family, s, m][:2]) for s in seeds]
        for m in TEMPLATE_METHODS:
            series['charged_saving_pct:' + m] = [_saving(size[family, s, m][2], size[family, s, m][1]) for s in seeds]
        for a, b in PAIRS:
            d = [size[family, s, a][0] - size[family, s, b][0] for s in seeds]
            series[f'delta_bytes:{a}-{b}'] = d
            series[f'delta_pct_of_raw:{a}-{b}'] = _pct_of_raw(d, raws)
        best = [min(size[family, s, m][0] for m in BASELINES) for s in seeds]  # baselines pay no template charge
        primary = [size[family, s, 'min_page'][0] - x for s, x in zip(seeds, best)]
        charged = [size[family, s, 'min_page'][2] - x for s, x in zip(seeds, best)]
        series['primary_bytes:' + PRIMARY] = primary
        series['primary_pct_of_raw:' + PRIMARY] = _pct_of_raw(primary, raws)
        series['charged_bytes:' + PRIMARY] = charged
        series['charged_pct_of_raw:' + PRIMARY] = _pct_of_raw(charged, raws)
        series['per_page_bytes:dedup_zlib-min_page'] = [
            (size[family, s, 'dedup_zlib'][0] - size[family, s, 'min_page'][0]) / (r // PAGE) if r else 0.0
            for s, r in zip(seeds, raws)]
        for m in METHODS:
            series['enc_ms:' + m] = [statistics.median(enc[family, s, m]) / 1e6 for s in seeds]
            series['dec_ms:' + m] = [statistics.median(dec[family, s, m]) / 1e6 for s in seeds]
        for quantity, v in series.items():
            out.append({'family': family, 'quantity': quantity, 'n_seeds': len(v),
                        'median': round(float(statistics.median(v)), 4),
                        'min': round(float(min(v)), 4), 'max': round(float(max(v)), 4),
                        'n_negative': sum(1 for x in v if x < 0)})
    return out


def parse_seeds(text):
    try:
        seeds = tuple(int(s) for s in text.split(','))
    except ValueError:
        raise argparse.ArgumentTypeError(f'seeds must be comma-separated integers, got {text!r}') from None
    if any(not 0 <= s < 2 ** 32 for s in seeds):
        raise argparse.ArgumentTypeError('seeds must be in [0, 2**32)')
    if len(set(seeds)) != len(seeds):
        raise argparse.ArgumentTypeError('seeds must not repeat')
    return seeds


def parse_families(text):
    names = tuple(text.split(','))
    if any(n not in FAMILIES for n in names) or len(set(names)) != len(names):
        raise argparse.ArgumentTypeError('families must be distinct names from ' + ','.join(FAMILIES) + f', got {text!r}')
    return names


def parse_repeats(text):
    try:
        n = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f'repeats must be an integer, got {text!r}') from None
    if not 1 <= n <= 20:
        raise argparse.ArgumentTypeError('repeats must be in 1..20')
    return n


def check_out_dir(path, root):
    """Resolve an output directory that lies strictly inside root and is absent or empty."""
    out, root = os.path.realpath(path), os.path.realpath(root)
    if out == root or os.path.commonpath([out, root]) != root:
        raise ValueError(f'--out must be a subdirectory of {root}, got {out}')
    if os.path.exists(out) and (not os.path.isdir(out) or os.listdir(out)):
        raise ValueError(f'--out {out} exists and is not an empty directory')
    return out


def file_sha256(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def write_csv(path, rows):
    with open(path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def baseline_check(root, corpora, rows):
    """Compare corpus hashes, baseline totals and the PREREGISTRATION.md hash with results/baseline, if present.

    The result is recorded in the manifest and printed; it does not abort, so a mismatch stays next to the results.
    """
    base = os.path.join(root, 'results', 'baseline')
    manifest_path = os.path.join(base, 'manifest.json')
    if not os.path.exists(manifest_path):
        return {'baseline_manifest': None}
    with open(manifest_path) as f:
        manifest = json.load(f)
    hashes = {(c['family'], int(c['seed'])): c['corpus_sha256'] for c in manifest.get('corpora', [])}
    seen = [c for c in corpora if (c['family'], int(c['seed'])) in hashes]
    prereg = os.path.join(root, 'PREREGISTRATION.md')
    check = {
        'baseline_manifest': 'results/baseline/manifest.json',
        'baseline_manifest_sha256': file_sha256(manifest_path),
        'same_python_version': manifest.get('python') == sys.version,
        'preregistration_sha256_matches': os.path.exists(prereg)
        and manifest.get('sha256', {}).get('PREREGISTRATION.md') == file_sha256(prereg),
        'corpora_compared': len(seen),
        'corpus_sha256_mismatches': ['%s:%s' % (c['family'], c['seed']) for c in seen
                                     if hashes[c['family'], int(c['seed'])] != c['corpus_sha256']],
    }
    raw_path = os.path.join(base, 'raw.csv')
    if os.path.exists(raw_path):
        with open(raw_path, newline='') as f:
            totals = {(r['family'], int(r['seed']), r['method']): int(r['total_bytes'])
                      for r in csv.DictReader(f) if int(r['repeat']) == 0}
        seen = [r for r in rows if int(r['repeat']) == 0 and (r['family'], int(r['seed']), r['method']) in totals]
        check['baseline_totals_compared'] = len(seen)
        check['baseline_total_mismatches'] = ['%s:%s:%s' % (r['family'], r['seed'], r['method']) for r in seen
                                              if totals[r['family'], int(r['seed']), r['method']] != int(r['total_bytes'])]
    return check


def main(argv=None):
    if sys.version_info < (3, 9):
        sys.exit('poc.py needs Python 3.9+ (random.randbytes)')
    root = os.path.dirname(os.path.realpath(__file__))
    ap = argparse.ArgumentParser(description='Run raw, zlib, dedup+zlib, template delta and min_page on synthetic sandbox pages.')
    ap.add_argument('--seeds', type=parse_seeds, default=SEEDS, help='comma-separated integers in [0, 2**32); default 0..9')
    ap.add_argument('--families', type=parse_families, default=tuple(FAMILIES),
                    help='comma-separated subset of ' + ','.join(FAMILIES))
    ap.add_argument('--repeats', type=parse_repeats, default=REPEATS, help='timing repeats, 1..20; default 3')
    ap.add_argument('--wrong-template', action='store_true',
                    help='descriptive run: delta and min_page pair template i pages with template (i + 1) mod 64; '
                         'baselines unchanged')
    ap.add_argument('--out', default=None,
                    help='new or empty directory inside this experiment directory; default results/poc '
                         '(results/poc-wrong-template with --wrong-template)')
    args = ap.parse_args(argv)
    default_out = os.path.join(root, 'results', 'poc-wrong-template' if args.wrong_template else 'poc')
    try:
        out = check_out_dir(default_out if args.out is None else args.out, root)
    except ValueError as e:
        ap.error(str(e))

    started = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')
    rows, corpora = run(args.seeds, args.families, args.repeats, args.wrong_template)
    os.makedirs(out, exist_ok=True)
    raw_path, summary_path = os.path.join(out, 'raw.csv'), os.path.join(out, 'summary.csv')
    write_csv(raw_path, rows)
    with open(raw_path, newline='') as f:
        summary = summarize(list(csv.DictReader(f)))  # recomputed from the file, not from memory
    write_csv(summary_path, summary)
    check = baseline_check(root, corpora, rows)

    manifest = {
        'command': ['poc.py'] + list(sys.argv[1:] if argv is None else argv),
        'started_utc': started,
        'python': sys.version,
        'implementation': platform.python_implementation(),
        'platform': platform.platform(),
        'machine': platform.machine(),
        'zlib_version': zlib.ZLIB_VERSION,
        'zlib_runtime_version': zlib.ZLIB_RUNTIME_VERSION,
        'seeds': list(args.seeds),
        'families': list(args.families),
        'repeats': args.repeats,
        'methods': list(METHODS),
        'wrong_template': args.wrong_template,
        'template_lookup': ('delta and min_page read template (i + 1) mod 64 for a page of template i; baselines unchanged'
                            if args.wrong_template else 'each page reads its own template index i'),
        'constants': {'PAGE': PAGE, 'BLOCK': BLOCK, 'ZLEVEL': ZLEVEL, 'HEADER': HEADER, 'BITMAP': BITMAP,
                      'HASH_ENTRY': HASH_ENTRY, 'REFCOUNT': REFCOUNT, 'REF': REF, 'N_TEMPLATE': N_TEMPLATE,
                      'N_SANDBOX': N_SANDBOX, 'TEMPLATE_CHARGE': TEMPLATE_CHARGE},
        'family_params': {f: FAMILIES[f] for f in args.families},
        'header_model': '8 B per encoded page: codec tag, encoded length, location and, for delta, the template '
                        'index (6 bits for 64 templates); a modeled charge, not a wire format',
        'template_accounting': {
            'primary': 'total_bytes: shared-resident, template bytes charged to no method (see PREREGISTRATION.md)',
            'sensitivity': 'charged_total_bytes: 64 x 4096 = 262144 B once per family and seed, to delta and '
                           'min_page only, even when admission selects zero deltas'},
        'timing_note': 'perf_counter_ns wall time of Python-level whole-corpus encode/decode; nondeterministic',
        'baseline_check': check,
        'corpora': corpora,
        'sha256': {name: file_sha256(path) for name, path in (
            ('poc.py', os.path.join(root, 'poc.py')),
            ('test_poc.py', os.path.join(root, 'test_poc.py')),
            ('PREREGISTRATION.md', os.path.join(root, 'PREREGISTRATION.md')),
            ('IMPLEMENTATION.md', os.path.join(root, 'IMPLEMENTATION.md')),
            ('raw.csv', raw_path),
            ('summary.csv', summary_path)) if os.path.exists(path)},
    }
    with open(os.path.join(out, 'manifest.json'), 'w') as f:
        json.dump(manifest, f, indent=2)

    for q in summary:
        print('%-7s %-52s median %14.4f  range [%.4f, %.4f]  negative %d/%d' % (
            q['family'], q['quantity'], q['median'], q['min'], q['max'], q['n_negative'], q['n_seeds']))
    print('baseline check: ' + json.dumps(check, sort_keys=True))
    print('wrote ' + out)


if __name__ == '__main__':
    main()
