#!/usr/bin/env python3
# Stdlib-only checks for poc.py: baselines, template delta and min_page. Run: python3 test_poc.py
import argparse
import json
import os
import random
import statistics
import tempfile
import unittest
import zlib

import poc

BASELINES = ('raw', 'zlib', 'dedup_zlib')


def flip_blocks(base, blocks):
    """Return base with every byte of the listed 64-B blocks inverted, so each listed block differs."""
    page = bytearray(base)
    for b in blocks:
        lo = b * poc.BLOCK
        page[lo:lo + poc.BLOCK] = bytes(x ^ 0xFF for x in base[lo:lo + poc.BLOCK])
    return bytes(page)


class CodecTest(unittest.TestCase):
    def test_admission_and_roundtrip(self):
        zero = bytes(poc.PAGE)
        noise = random.Random(1).randbytes(poc.PAGE)
        last_byte = zero[:-1] + bytes([1])
        self.assertEqual(poc.store_page(zero)[0], 'z')
        self.assertEqual(poc.store_page(noise), ('r', noise))  # zlib expands random data: stays resident
        for page in (zero, noise, last_byte):
            self.assertEqual(poc.load_page(poc.store_page(page)), page)


class DeltaTest(unittest.TestCase):
    template = [random.Random(3).randbytes(poc.PAGE), bytes(poc.PAGE)]

    def test_changed_block_counts_and_admission(self):
        base, last = self.template[0], poc.BLOCKS - 1
        cases = {0: (), 1: (last,), 63: tuple(range(1, poc.BLOCKS)), 64: tuple(range(poc.BLOCKS))}
        costs = {0: 16, 1: 80, 63: 4048, 64: 4096}  # 8 header + 8 bitmap + 64 per block; 4112 is not < 4096
        for k, blocks in cases.items():
            page = flip_blocks(base, blocks)
            blob = poc.delta_blob(page, base)
            self.assertEqual(len(blob), poc.BITMAP + k * poc.BLOCK, k)
            self.assertEqual(int.from_bytes(blob[:poc.BITMAP], 'little'), sum(1 << b for b in blocks), k)
            self.assertEqual(poc.apply_delta(base, blob), page, k)
            obj = poc.store_delta(page, self.template, 0)
            self.assertEqual(obj, ('d', 0, blob) if k < 64 else ('r', page), k)
            self.assertEqual(poc.stored_cost(obj), costs[k], k)
            self.assertEqual(poc.load_page(obj, self.template), page, k)

    def test_last_byte_change_selects_last_block(self):
        base = self.template[1]
        page = base[:-1] + bytes([1])
        blob = poc.delta_blob(page, base)
        self.assertEqual(blob, (1 << 63).to_bytes(8, 'little') + page[-poc.BLOCK:])
        self.assertEqual(poc.apply_delta(base, blob), page)

    def test_min_page_choice_and_tie_order(self):
        zero, noise = bytes(poc.PAGE), random.Random(4).randbytes(poc.PAGE)
        one_block = flip_blocks(self.template[0], (5,))
        self.assertEqual(poc.store_min(one_block, self.template, 0), poc.store_delta(one_block, self.template, 0))
        self.assertEqual(poc.store_min(zero, self.template, 0), poc.store_page(zero))  # delta has 64 blocks: resident
        self.assertEqual(poc.store_min(noise, self.template, 0), ('r', noise))  # every candidate costs 4096
        raw = ('r', zero)
        z_full, d_full = ('z', bytes(4088)), ('d', 0, bytes(4088))  # 8 + 4088 = 4096, tied with raw
        self.assertIs(poc.cheapest((raw, z_full, d_full)), raw)
        z, d = ('z', bytes(100)), ('d', 0, bytes(100))
        self.assertIs(poc.cheapest((raw, z, d)), z)

    def test_wrong_template_index_roundtrip(self):
        page = flip_blocks(self.template[1], (poc.BLOCKS - 1,))
        enc = poc.encode('delta', [page], self.template, [1])  # own index 0 shifted by one
        obj = enc[0][0]
        self.assertEqual(obj[:2], ('d', 1))
        self.assertEqual(poc.decode(enc, self.template), [page])
        self.assertNotEqual(poc.load_page(('d', 0, obj[2]), self.template), page)  # the stored index selects the base
        template, private, _ = poc.make_corpus('sparse', 0)
        pages = [p for _, p in private]
        indices = [(i + 1) % poc.N_TEMPLATE for i, _ in private]
        for method in ('delta', 'min_page'):
            enc = poc.encode(method, pages, template, indices)
            self.assertEqual(poc.decode(enc, template), pages, method)
            for obj, j in zip(enc[0], indices):
                if obj[0] == 'd':
                    self.assertEqual(obj[1], j, method)


class AccountingTest(unittest.TestCase):
    def test_hand_computed_costs(self):
        a, b = bytes(poc.PAGE), random.Random(2).randbytes(poc.PAGE)
        pages = [a, b, a]
        za = len(zlib.compress(a, poc.ZLEVEL))
        fields = ('payload_bytes', 'header_bytes', 'index_bytes', 'ref_bytes', 'duplicate_pages')
        expected = {
            'raw': (3 * poc.PAGE, 0, 0, 0, 0),
            'zlib': (2 * za + poc.PAGE, 2 * poc.HEADER, 0, 0, 0),
            'dedup_zlib': (za + poc.PAGE, poc.HEADER, 2 * (poc.HASH_ENTRY + poc.REFCOUNT), poc.REF, 1),
        }
        for method in BASELINES:
            enc = poc.encode(method, pages)
            acct = poc.account(method, enc)
            self.assertEqual(tuple(acct[f] for f in fields), expected[method], method)
            self.assertEqual(acct['total_bytes'], sum(expected[method][:4]), method)
            self.assertEqual((acct['template_charge_bytes'], acct['charged_total_bytes']), (0, acct['total_bytes']), method)
            self.assertEqual(poc.decode(enc), pages, method)

    def test_delta_and_min_page_hand_computed(self):
        template = [random.Random(3).randbytes(poc.PAGE)]
        zero, noise = bytes(poc.PAGE), random.Random(2).randbytes(poc.PAGE)
        pages = [flip_blocks(template[0], (0, poc.BLOCKS - 1)), noise, zero]
        za = len(zlib.compress(zero, poc.ZLEVEL))
        fields = ('payload_bytes', 'header_bytes', 'resident_objects', 'compressed_objects', 'delta_objects', 'changed_blocks')
        expected = {  # the 2-block delta is 8 + 2 * 64 = 136 B; noise and zero differ from the template in all 64 blocks
            'delta': (136 + 2 * poc.PAGE, 8, 2, 0, 1, 2),
            'min_page': (136 + poc.PAGE + za, 16, 1, 1, 1, 2),
        }
        for method, exp in expected.items():
            enc = poc.encode(method, pages, template, [0, 0, 0])
            acct = poc.account(method, enc)
            self.assertEqual(tuple(acct[f] for f in fields), exp, method)
            self.assertEqual(acct['total_bytes'], exp[0] + exp[1], method)
            self.assertEqual(acct['template_charge_bytes'], 262144, method)
            self.assertEqual(acct['charged_total_bytes'], acct['total_bytes'] + 262144, method)
            self.assertEqual(poc.decode(enc, template), pages, method)
        no_delta = poc.account('min_page', poc.encode('min_page', [noise], template, [0]))
        self.assertEqual((no_delta['delta_objects'], no_delta['charged_total_bytes']), (0, poc.PAGE + 262144))

    def test_random_family_pays_index_without_duplicates(self):
        _, private, _ = poc.make_corpus('random', 0)
        pages = [p for _, p in private]
        z = poc.account('zlib', poc.encode('zlib', pages))
        d = poc.account('dedup_zlib', poc.encode('dedup_zlib', pages))
        self.assertEqual((z['compressed_objects'], d['duplicate_pages']), (0, 0))
        self.assertEqual(z['total_bytes'], len(pages) * poc.PAGE)
        self.assertEqual(d['total_bytes'] - z['total_bytes'], len(pages) * (poc.HASH_ENTRY + poc.REFCOUNT))


class SummaryTest(unittest.TestCase):
    def test_primary_and_charged_quantities_are_paired_per_seed(self):
        totals = {0: {'raw': 40960, 'zlib': 20000, 'dedup_zlib': 18000, 'delta': 30000, 'min_page': 15000},
                  1: {'raw': 40960, 'zlib': 20000, 'dedup_zlib': 21000, 'delta': 30000, 'min_page': 20500},
                  2: {'raw': 40960, 'zlib': 30000, 'dedup_zlib': 32000, 'delta': 30000, 'min_page': 10000}}
        rows = []
        for seed, by_method in totals.items():
            for method, total in by_method.items():
                charge = 262144 if method in ('delta', 'min_page') else 0
                rows.append({'family': 'f', 'seed': seed, 'method': method, 'repeat': 0, 'total_bytes': total,
                             'raw_bytes': 40960, 'charged_total_bytes': total + charge, 'enc_ns': 1, 'dec_ns': 1})
        summary = {q['quantity']: q for q in poc.summarize(rows)}
        q = summary['primary_bytes:' + poc.PRIMARY]  # per seed: -3000, 500, -20000
        self.assertEqual((q['n_seeds'], q['median'], q['min'], q['max'], q['n_negative']), (3, -3000, -20000, 500, 2))
        self.assertNotEqual(q['median'], 15000 - 20000)  # not the difference of family medians
        q = summary['primary_pct_of_raw:' + poc.PRIMARY]
        self.assertEqual((q['median'], q['min'], q['max']), (-7.3242, -48.8281, 1.2207))
        q = summary['charged_bytes:' + poc.PRIMARY]  # per seed: 259144, 262644, 242144
        self.assertEqual((q['median'], q['min'], q['max'], q['n_negative']), (259144, 242144, 262644, 0))
        q = summary['per_page_bytes:dedup_zlib-min_page']  # 10 private pages: 300, 50, 2200
        self.assertEqual((q['median'], q['min'], q['max']), (300, 50, 2200))


class GeneratorTest(unittest.TestCase):
    def test_cow_invariant_and_sparse_duplicates(self):
        template, private, excluded = poc.make_corpus('sparse', 0)
        self.assertGreater(excluded, 0)  # the invariant is exercised, not vacuous
        for i, page in private:
            self.assertEqual(len(page), poc.PAGE)
            self.assertNotEqual(page, template[i])
        pages = [p for _, p in private]
        self.assertGreater(len(pages) - len(set(pages)), 0)  # dedup has real work in sparse

    def test_corpus_is_deterministic(self):
        def digest(family, seed):
            template, private, _ = poc.make_corpus(family, seed)
            return poc.corpus_sha256(template, private)
        self.assertEqual(digest('heavy', 3), digest('heavy', 3))
        self.assertNotEqual(digest('heavy', 3), digest('heavy', 4))
        self.assertNotEqual(digest('heavy', 3), digest('sparse', 3))


class RunTest(unittest.TestCase):
    def test_run_invariants_and_summary(self):
        rows, corpora = poc.run((0, 1), ('sparse', 'random'), 2)
        self.assertEqual(len(corpora), 4)
        self.assertEqual(len(rows), 4 * len(poc.METHODS) * 2)
        by = {(r['family'], r['seed'], r['method'], r['repeat']): r for r in rows}
        for r in rows:
            parts = r['payload_bytes'] + r['header_bytes'] + r['index_bytes'] + r['ref_bytes']
            self.assertEqual(r['total_bytes'], parts)
            self.assertEqual(r['raw_bytes'], r['private_pages'] * poc.PAGE)
            self.assertEqual(r['total_bytes'], by[r['family'], r['seed'], r['method'], 0]['total_bytes'])
            self.assertEqual(r['template_shift'], 0)
            charge = 262144 if r['method'] in ('delta', 'min_page') else 0
            self.assertEqual((r['template_charge_bytes'], r['charged_total_bytes']), (charge, r['total_bytes'] + charge))
        for c in corpora:
            raw, z, d, dl, mp = (by[c['family'], c['seed'], m, 0] for m in ('raw', 'zlib', 'dedup_zlib', 'delta', 'min_page'))
            self.assertEqual(raw['total_bytes'], raw['raw_bytes'])
            self.assertLessEqual(z['total_bytes'], raw['total_bytes'])
            self.assertLessEqual(d['payload_bytes'] + d['header_bytes'], z['payload_bytes'] + z['header_bytes'])
            self.assertLessEqual(dl['total_bytes'], raw['total_bytes'])
            self.assertLessEqual(mp['total_bytes'], min(z['total_bytes'], dl['total_bytes']))
        summary = {(q['family'], q['quantity']): q for q in poc.summarize(rows)}
        deltas = [by['sparse', s, 'dedup_zlib', 0]['total_bytes'] - by['sparse', s, 'zlib', 0]['total_bytes'] for s in (0, 1)]
        q = summary['sparse', 'delta_bytes:dedup_zlib-zlib']
        self.assertEqual((q['n_seeds'], q['median'], q['min'], q['max']),
                         (2, statistics.median(deltas), min(deltas), max(deltas)))
        primary = [by['sparse', s, 'min_page', 0]['total_bytes']
                   - min(by['sparse', s, m, 0]['total_bytes'] for m in ('zlib', 'dedup_zlib')) for s in (0, 1)]
        q = summary['sparse', 'primary_bytes:' + poc.PRIMARY]
        self.assertEqual((q['median'], q['n_negative']), (statistics.median(primary), sum(1 for x in primary if x < 0)))

    def test_wrong_template_changes_only_template_methods(self):
        primary, corpora = poc.run((0,), ('sparse',), 1)
        shifted, corpora_shifted = poc.run((0,), ('sparse',), 1, wrong_template=True)
        self.assertEqual(corpora_shifted, corpora)  # corpus hashes use the true template indices
        a = {r['method']: r['total_bytes'] for r in primary}
        b = {r['method']: r['total_bytes'] for r in shifted}
        self.assertEqual({m: a[m] for m in BASELINES}, {m: b[m] for m in BASELINES})
        self.assertEqual({r['template_shift'] for r in shifted}, {1})


class BaselineCheckTest(unittest.TestCase):
    def test_compares_preregistration_corpora_and_totals(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(poc.baseline_check(root, [], []), {'baseline_manifest': None})
            base = os.path.join(root, 'results', 'baseline')
            os.makedirs(base)
            prereg = os.path.join(root, 'PREREGISTRATION.md')
            with open(prereg, 'w') as f:
                f.write('frozen')
            manifest = {'python': 'other', 'sha256': {'PREREGISTRATION.md': poc.file_sha256(prereg)},
                        'corpora': [{'family': 'sparse', 'seed': 0, 'corpus_sha256': 'aa'},
                                    {'family': 'sparse', 'seed': 1, 'corpus_sha256': 'bb'}]}
            with open(os.path.join(base, 'manifest.json'), 'w') as f:
                json.dump(manifest, f)
            poc.write_csv(os.path.join(base, 'raw.csv'), [
                {'family': 'sparse', 'seed': 0, 'method': 'zlib', 'repeat': 0, 'total_bytes': 5},
                {'family': 'sparse', 'seed': 1, 'method': 'zlib', 'repeat': 0, 'total_bytes': 7}])
            corpora = [{'family': 'sparse', 'seed': 0, 'corpus_sha256': 'aa'},
                       {'family': 'sparse', 'seed': 1, 'corpus_sha256': 'cc'}]
            rows = [{'family': 'sparse', 'seed': 0, 'method': 'zlib', 'repeat': 0, 'total_bytes': 5},
                    {'family': 'sparse', 'seed': 1, 'method': 'zlib', 'repeat': 0, 'total_bytes': 8},
                    {'family': 'sparse', 'seed': 1, 'method': 'delta', 'repeat': 0, 'total_bytes': 1}]
            check = poc.baseline_check(root, corpora, rows)
            self.assertEqual((check['preregistration_sha256_matches'], check['same_python_version']), (True, False))
            self.assertEqual((check['corpora_compared'], check['corpus_sha256_mismatches']), (2, ['sparse:1']))
            self.assertEqual((check['baseline_totals_compared'], check['baseline_total_mismatches']), (2, ['sparse:1:zlib']))


class CliTest(unittest.TestCase):
    def test_parsers(self):
        self.assertEqual(poc.parse_seeds('0,3'), (0, 3))
        for bad in ('', 'a', '-1', '1,1', str(2 ** 32)):
            with self.assertRaises(argparse.ArgumentTypeError):
                poc.parse_seeds(bad)
        self.assertEqual(poc.parse_families('random,sparse'), ('random', 'sparse'))
        for bad in ('', 'dense', 'sparse,sparse'):
            with self.assertRaises(argparse.ArgumentTypeError):
                poc.parse_families(bad)
        self.assertEqual(poc.parse_repeats('3'), 3)
        for bad in ('0', '21', 'x'):
            with self.assertRaises(argparse.ArgumentTypeError):
                poc.parse_repeats(bad)

    def test_out_dir_stays_inside_experiment(self):
        with tempfile.TemporaryDirectory() as root:
            target = os.path.join(root, 'results', 'r1')
            self.assertEqual(poc.check_out_dir(target, root), os.path.realpath(target))
            full = os.path.join(root, 'full')
            os.makedirs(full)
            open(os.path.join(full, 'x'), 'w').close()
            for bad in (root, os.path.dirname(root), os.path.join(root, '..', 'sibling'), full):
                with self.assertRaises(ValueError):
                    poc.check_out_dir(bad, root)


if __name__ == '__main__':
    unittest.main()
