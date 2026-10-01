# Template deltas: savings depend on what you charge

A small, original Python experiment inspired by [AgentZip's template-delta mechanism](https://arxiv.org/html/2609.11294v1). **Synthetic stored-byte accounting only; not OS memory savings or a reproduction of the paper.**

On the frozen sparse family, min(raw, zlib, delta) saves a median **96.6005%** of private bytes versus **77.6488%** for exact dedup+zlib. But charge the full 256 KiB template to the POC and **it loses to the best baseline in all 10 seeds**. Heavy pages show a small shared-template advantage; random pages show none.

| Family | zlib saving | dedup+zlib saving | min_page saving | min_page saving with template charged |
|---|---:|---:|---:|---:|
| Sparse | 65.0306% | 77.6488% | 96.6005% | 69.6062% |
| Heavy | 35.6466% | 34.6701% | 36.0656% | 19.5472% |
| Random | 0% | -0.9766% | 0% | -12.5% |

Each cell is a median across 10 fixed seeds. Read [COMPARISON.md](COMPARISON.md) for paired deltas, ranges, wrong-template results, costs and limitations. Differences between these medians are not the paired statistics.

## Run

Standard library only. Python 3.9+ runs the benchmark; **Python 3.12.0 / zlib 1.2.12** reproduces the recorded environment. No network, dataset download or API key.

```sh
python3 test_poc.py
python3 poc.py --out results/replay/primary
python3 poc.py --wrong-template --out results/replay/wrong
python3 verify_results.py results/replay/primary results/replay/wrong
```

Output directories must be new or empty and inside this repository. A second identical command refuses to overwrite results. Timings vary; compare byte counts and corpus hashes. `verify_results.py` also checks committed results with no arguments. It is an independent assertion-based release check, not the codec implementation.

## Design

4096-byte pages, 64-byte blocks, 64 template pages, eight synthetic sandboxes; 10 seeds and three timing repeats. Copy-on-write identical pages are excluded equally. Five methods see the same input: raw, per-page zlib with admission, exact dedup+zlib with index/reference costs, bitmap+verbatim-block delta, and per-page minimum of raw/zlib/delta. Wrong-template tests shift the reference for encoding and decoding together. No candidate is tuned after measurement.

A delta with two changed blocks costs 8 bytes of header + 8 bytes of bitmap + 128 bytes of changed blocks = 144 bytes. If an encoding does not save space, the page stays raw. [IMPLEMENTATION.md](IMPLEMENTATION.md) specifies template identity, tie order and modeled metadata. The template is free in the shared-resident scenario; the sensitivity charges all 262144 bytes to delta/min_page, including runs that select no deltas.

## Evidence

- [PREREGISTRATION.md](PREREGISTRATION.md): frozen before baseline measurements; hash retained unchanged.
- [DEVIATIONS.md](DEVIATIONS.md): header clarification and corrected interpreter invocation.
- [BASELINE.md](BASELINE.md) and [results/baseline](results/baseline): original three-method results.
- [results/poc](results/poc) and [results/poc-wrong-template](results/poc-wrong-template): 900 raw rows, paired summaries and provenance.
- [REVIEW.md](REVIEW.md): independent review and reproduction evidence.

Sixteen tests; 340590 page roundtrips per complete primary+control evaluation. The generator drives these results; none establish real memory usage, latency, sandbox capacity or a production benefit.

## Authorship, cost and license

Claude Opus 5.5 led paper selection and authored the codec and tests. Codex independently reviewed source, evaluation, claims, licensing and secrets, executed the experiment, and wrote the artifact verifier and reports. Local benchmark API spend is $0; Claude's cumulative list-price estimate is $3.3712318, not an invoice. Codex review/electricity are unmeasured.

Original code is [MIT](LICENSE), copyright 2026 Gaille Amolong. The referenced paper, arXiv:2609.11294v1, 10 September 2026, has its own CC BY-NC-ND 4.0 license. No paper prose, figures, upstream code, dataset or weights are redistributed.
