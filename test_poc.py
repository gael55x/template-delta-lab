#!/usr/bin/env python3
# Stdlib-only checks for the poc.py baselines. Run: python3 test_poc.py
import argparse
import os
import random
import statistics
import tempfile
import unittest
import zlib

import poc


class CodecTest(unittest.TestCase):
    def test_admission_and_roundtrip(self):
        zero = bytes(poc.PAGE)
        noise = random.Random(1).randbytes(poc.PAGE)
        last_byte = zero[:-1] + bytes([1])
        self.assertEqual(poc.store_page(zero)[0], 'z')
        self.assertEqual(poc.store_page(noise), ('r', noise))  # zlib expands random data: stays resident
        for page in (zero, noise, last_byte):
            self.assertEqual(poc.load_page(poc.store_page(page)), page)


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
        for method in poc.METHODS:
            enc = poc.encode(method, pages)
            acct = poc.account(method, enc)
            self.assertEqual(tuple(acct[f] for f in fields), expected[method], method)
            self.assertEqual(acct['total_bytes'], sum(expected[method][:4]), method)
            self.assertEqual(poc.decode(enc), pages, method)

    def test_random_family_pays_index_without_duplicates(self):
        _, private, _ = poc.make_corpus('random', 0)
        pages = [p for _, p in private]
        z = poc.account('zlib', poc.encode('zlib', pages))
        d = poc.account('dedup_zlib', poc.encode('dedup_zlib', pages))
        self.assertEqual((z['compressed_objects'], d['duplicate_pages']), (0, 0))
        self.assertEqual(z['total_bytes'], len(pages) * poc.PAGE)
        self.assertEqual(d['total_bytes'] - z['total_bytes'], len(pages) * (poc.HASH_ENTRY + poc.REFCOUNT))


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
        for c in corpora:
            raw, z, d = (by[c['family'], c['seed'], m, 0] for m in poc.METHODS)
            self.assertEqual(raw['total_bytes'], raw['raw_bytes'])
            self.assertLessEqual(z['total_bytes'], raw['total_bytes'])
            self.assertLessEqual(d['payload_bytes'] + d['header_bytes'], z['payload_bytes'] + z['header_bytes'])
        summary = {(q['family'], q['quantity']): q for q in poc.summarize(rows)}
        deltas = [by['sparse', s, 'dedup_zlib', 0]['total_bytes'] - by['sparse', s, 'zlib', 0]['total_bytes'] for s in (0, 1)]
        q = summary['sparse', 'delta_bytes:dedup_zlib-zlib']
        self.assertEqual((q['n_seeds'], q['median'], q['min'], q['max']),
                         (2, statistics.median(deltas), min(deltas), max(deltas)))


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
