# w40-agentzip-template-delta-poc

This is a synthetic benchmark scaffold that uses only the Python standard library. It targets one idea from AgentZip (arXiv:2609.11294v1, https://arxiv.org/abs/2609.11294): template-delta encoding of sandbox memory pages, described in section 4.2.2 of the paper.

**Today (2026-10-01) the baseline is implemented, tested and measured; see [BASELINE.md](BASELINE.md).** The template-delta POC is planned for Friday 2026-10-02 and is not implemented yet.

This is original code, not a reproduction of the paper. It runs on synthetic pages, not real memory dumps. It makes no claims about OS RSS, restore latency, speedups or LLM behaviour.

## Isolation

- This directory sits beneath a parent git repository that has uncommitted changes. Nothing here reads or writes parent files.
- `poc.py` refuses any `--out` that resolves outside this directory. It also refuses an `--out` that already exists and is not empty.
- This directory has its own Git repository. Run Git commands here only; preserve the parent checkout and all its existing changes.

## Requirements

Python 3.9 or later (for `random.randbytes`), standard library only. The benchmark uses no network access and no paid APIs.

## Commands

```sh
cd w40-agentzip-template-delta-poc
python3 test_poc.py      # stdlib unittest
python3 poc.py --seeds 0 --families sparse --repeats 1 --out results/smoke   # quick smoke run
python3 poc.py           # preregistered baseline: seeds 0..9, all families, 3 repeats -> results/baseline/
python3 poc.py --help
```

A relative `--out` resolves against the current directory, so run these commands from inside this directory.

Runtime is estimated, not measured: seconds to a few minutes on a laptop. Each corpus has 64 template pages and at most 512 private pages, about 2.25 MiB in total. Corpora are regenerated from their seeds rather than stored, and are identified by sha256.

## Outputs

Each run directory contains three files.

- **`raw.csv`**: one row per family x seed x method x repeat. Each row has:
  - the corpus sha256
  - page counts: private, COW-excluded and template
  - byte accounting: payload, header, index, ref and total
  - saving %
  - encode and decode wall-clock ns
- **`summary.csv`**: recomputed by reading `raw.csv` back after it is written. For each family it gives the median and [min, max] across seeds of:
  - saving %
  - paired per-seed size deltas, in bytes and as % of private bytes
  - per-seed median timings
- **`manifest.json`**: provenance for the run:
  - command and UTC start time
  - Python, platform and zlib (compile and runtime) versions
  - seeds, repeats, constants and family parameters
  - per-corpus sha256
  - sha256 of `poc.py`, `PREREGISTRATION.md`, `raw.csv` and `summary.csv`

## Baseline methods

| method | cost charged per private page |
|---|---|
| raw | 4096 B resident |
| zlib | zlib level 9 output plus an 8 B header. If that is not smaller than 4096 B, the page is admitted resident at 4096 B with no header. |
| dedup_zlib | Exact match by sha256, with a full byte comparison on every hash hit. Each stored object pays the zlib-with-admission cost plus 32 B hash and 8 B refcount. Each duplicate page pays an 8 B reference. |

Some rules apply to every method:

- Template pages are treated as shared-resident and are charged to no method.
- A page that is byte-identical to its template page counts as copy-on-write shared. It is excluded from the private set for every method.

The sparse family deliberately contains cross-sandbox exact duplicates, so that dedup is a real competitor and not a straw man.

## Reproducibility

- The same family and seed always give the same corpus sha256. The tests check this.
- Byte sizes are asserted to be identical across repeats within a run.
- Compressed sizes depend on the zlib build, which the manifest records. Only compare sizes across machines when their zlib versions match.
- Wall-clock times are nondeterministic, Python-level measurements. Compare them only within a single run.

## Friday plan (2026-10-02, bounded)

Resume this repository through the due comparison milestone; checkpoint each verified transition. Hold only concretely blocked work.

1. Hash `PREREGISTRATION.md` and compare the result with `results/baseline/manifest.json`. Record any edit, with its reason and the new hash, in `DEVIATIONS.md`.
2. Add two methods to `poc.py`, exactly as defined in PREREGISTRATION.md:
   - `delta`: a bitmap plus the changed blocks, with admission.
   - `min_page`: the per-page minimum of delta, zlib and raw.
   Do not add dictionaries, RLE or portfolios.
3. Rerun the same seeds, families and repeats into `results/poc/`, and check that the corpus sha256s match today's baseline.
4. Write `COMPARISON.md` with:
   - the paired per-seed deltas against the best baseline for each seed
   - median/range
   - the template-charged sensitivity
   - the descriptive wrong-template run

Out of scope: UFFD, prefetching, schedulers, real sandboxes, zstd and statistical tests.

## Costs

- **Benchmark:** API spend is $0. No network or paid service is used, and compute is local CPU.
- **Authoring and review:** the AI models used to write and review these files have their own costs. Claude CLI reports list-price estimates totaling $2.1829618 for the identity probe, research selection and baseline authoring. These are not subscription invoices. Codex review cost is unavailable; local electricity is unmeasured.

## Citation and licensing

- **Paper:** AgentZip, arXiv:2609.11294v1, https://arxiv.org/abs/2609.11294. Codex verified the exact version, date (10 September 2026) and CC BY-NC-ND 4.0 license against the primary arXiv HTML on 1 October 2026.
- **Paper content:** no text, figures, code or data from the paper are copied. Descriptions here are paraphrases.
- **Code in this directory:** MIT License, Copyright (c) 2026 Gaille Amolong (see LICENSE). That license does not cover the paper.
