# Measured comparison — 2 October 2026

Original synthetic codec experiment inspired by [AgentZip, arXiv:2609.11294v1](https://arxiv.org/html/2609.11294v1), section 4.2.2. This is modeled stored bytes, not RSS or a paper reproduction.

## Result

The page selector wins on the sparse and heavy families when the template is already resident. Charging its full 256 KiB template reverses that advantage in every seed. On the fixed random corpora the selector stores raw pages; dedup adds exactly 40 B per page. These conditional and negative results are the outcome, not an experiment to tune away.

## Primary savings

Percentage of raw private bytes saved; median [min, max] across 10 seeds. Positive saves bytes. Each seed uses the same input for every method. A family median difference is not a paired result.

| Family | zlib | dedup + zlib | delta | min_page |
|---|---:|---:|---:|---:|
| sparse | 65.0306 [57.9646, 69.5732] | 77.6488 [72.2982, 82.5817] | 96.4844 [96.4844, 96.4844] | 96.6005 [96.5386, 96.6229] |
| heavy | 35.6466 [35.0542, 36.2054] | 34.6701 [34.0777, 35.2288] | 24.6094 [24.6094, 24.6094] | 36.0656 [35.6617, 36.6891] |
| random | 0 [0, 0] | -0.9766 [-0.9766, -0.9766] | 0 [0, 0] | 0 [0, 0] |

## Paired comparison against the best baseline

For each seed: total(min_page) minus min(total(zlib), total(dedup_zlib)). Negative favors the POC. The percentage denominator is that seed's raw private bytes, not baseline bytes. Full-template sensitivity adds 262144 bytes once to the POC and zero to baselines, even when it selects no delta.

| Family | Shared: byte delta median [range] | Shared: % raw delta median [range] | Wins | Charged: byte delta median [range] | Charged: % raw delta median [range] | Wins |
|---|---:|---:|---:|---:|---:|---:|
| sparse | -180,016.5 [-212,997, -139,083] | -18.9451 [-24.2404, -14.0313] | 10/10 | 82,127.5 [49,147, 123,061] | 8.7833 [4.9995, 12.415] | 0/10 |
| heavy | -7,151 [-10,069, -4,783] | -0.449 [-0.6271, -0.3106] | 10/10 | 254,993 [252,075, 257,361] | 15.9071 [14.9857, 16.7107] | 0/10 |
| random | 0 [0, 0] | 0 [0, 0] | 0/10 | 262,144 [262,144, 262,144] | 12.5 [12.5, 12.5] | 0/10 |

Sparse's predeclared 10/10 shared-template wins were observed. Heavy had no direction claimed; it wins shared-template by only a median 0.4490% of raw bytes. Random's exact raw-size and 40 B/page overhead checks passed for all ten fixed seeds. No hypothesis tests or real-workload generalization.

## Wrong-template descriptive run

Both encoder and decoder use index (i+1) mod 64; input pages and corpus hashes stay the same. All roundtrips pass. This is a different reference choice, not a corrupted decoder.

| Family | min_page savings % median [range] | Paired delta % raw median [range] | Wins |
|---|---:|---:|---:|
| sparse | 65.0306 [57.9646, 69.5732] | 12.8556 [11.5502, 15.4991] | 0/10 |
| heavy | 35.6466 [35.0542, 36.2054] | 0 [0, 0] | 0/10 |
| random | 0 [0, 0] | 0 [0, 0] | 0/10 |

The selector equals zlib in the wrong-template run. Sparse therefore loses against dedup+zlib; heavy and random tie their best baseline. Some wrong-template delta pages still save bytes, as expected from possible shared zero blocks.

## Reproduce and verify

Python 3.12.0, macOS 15.6.1 arm64, zlib 1.2.12. See both manifests for exact environment, command, hashes, seeds and repeats. Run from repository root into new empty directories:

```sh
python3 test_poc.py
python3 poc.py --out results/replay/primary
python3 poc.py --wrong-template --out results/replay/wrong
python3 verify_results.py results/replay/primary results/replay/wrong
```

Use Python 3.12.0 and zlib 1.2.12 to compare with committed measurements. The independent verifier requires these versions and asserts all 270 prior baseline rows' non-timing fields, 30 corpus hashes, full byte accounting, repeat stability and paired summaries. Each full run has 450 rows and 170295 page roundtrips; primary plus wrong-template total 900 rows and 340590 page roundtrips. Sixteen unit tests pass. Raw timings are retained and expected to vary.

## Costs and limits

- Local benchmark API spend: $0. Claude research and code authoring list-price estimates through this run: $3.3712318; these are not subscription invoices. Codex review and electricity are unmeasured.
- Synthetic families were frozen before the first baseline. Sparse explicitly changes two blocks and contains exact duplicates; its large delta saving follows from that construction. Real-workload validity is untested.
- Headers, indexes, reference counts and template costs are modeled. Python objects, retained encoder buffers, page tables and allocator overhead are excluded. The 8-byte header has a documented bit budget, not a binary serialization.
- Full-template sensitivity is intentionally conservative: when no delta is selected, a decoder would not actually require that template. It remains charged here by preregistration.
- min_page performs both zlib and delta encoding. In this run sparse whole-corpus encode medians were 25.4842 ms for min_page, 21.7359 ms for zlib, and 14.1304 ms for dedup+zlib. This is no speed claim: method order is fixed, with no explicit warmup, interpreter overhead, and a shared laptop.
- No kernel integration, real sandbox traces, dictionaries, delta-plus-dedup, or zlib-compressed delta. No result supports a deployment recommendation.
- Original implementation MIT; paper CC BY-NC-ND 4.0 separately. No paper text, figures, upstream source, data or weights are included.
