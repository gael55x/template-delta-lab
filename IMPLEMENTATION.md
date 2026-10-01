# Implementation notes: template delta and min_page

This is the Friday POC defined in PREREGISTRATION.md. That file is unchanged, and every manifest records its sha256. The code is original, stdlib-only Python run on synthetic pages. It makes no claims about OS memory, RSS, latency or speedups.

## Encoded objects

Encoded objects are trusted in-process tuples. Only `poc.py` produces and consumes them, and they are not a binary format.

| object | meaning | stored cost |
|---|---|---|
| `('r', page)` | resident page | 4096 B, no header |
| `('z', blob)` | zlib level 9 | 8 B header + `len(blob)` |
| `('d', j, blob)` | template delta against `template[j]` | 8 B header + 8 B bitmap + 64 B per changed block |

The delta `blob` is an 8 B little-endian bitmap followed by the differing 64 B blocks, verbatim and in block order. Bit b of the bitmap is set when block b differs from `template[j]`. Decode rebuilds the page from `template[j]` plus those blocks, and asserts that the blob length matches the bitmap.

Template pages are passed to `decode` separately. They are never stored inside objects. Raw objects hold the original page only when that page is charged 4096 B.

## Template index charge

The preregistered 8 B header holds the codec tag, length and location. A delta also needs its template index `j`, and 64 templates need 6 bits for it. The modeled budget for the 64 header bits is:

- 2 bits: codec tag
- 12 bits: length (every admitted encoding is at most 4087 B)
- 6 bits: template index
- 44 bits: location

The index therefore costs no bytes beyond the existing header. This is an accounting model, not a wire format. This clarification retains the frozen 8 B charge; see DEVIATIONS.md.

## Admission, min_page and bounds

- **Delta admission:** a delta is admitted only when 8 + `len(blob)` < 4096. That allows at most 63 changed blocks, costing 4048 B. With 64 changed blocks the delta would cost 4112 B, so the page stays resident at 4096 B.
- **min_page:** builds three candidates in the order raw, zlib-with-admission, delta-with-admission, and keeps the lowest stored cost. On ties, `min()` keeps the first candidate, which gives the preregistered raw, zlib, delta order. The object tag is the codec tag.
- **Bound checks in `run()`:**
  - Per page, it asserts min_page cost == min(raw, zlib, delta), with the same lookup.
  - It asserts that the delta and min_page totals are <= raw.
  - Round-trip and repeat-size checks are unchanged and abort on failure.

## Template accounting

- **`total_bytes` (primary):** template pages are shared-resident and charged to no method.
- **`charged_total_bytes` (sensitivity):** adds 64 x 4096 = 262144 B once per family and seed, to delta and min_page only. Baselines get 0.

The charge applies even when admission selects zero deltas for a corpus. This is conservative on purpose. It follows the frozen whole-template scenario, not a measured retention requirement. A corpus that selects zero deltas does not actually require a template for decoding; charging it anyway is a deliberately conservative sensitivity.

## Wrong-template run

`--wrong-template` pairs each page of template i with template (i + 1) mod 64 for delta and min_page only. Its default output directory is `results/poc-wrong-template`.

- The shifted index is stored in each delta object, and decode reads that same index.
- Round-trip against the original bytes is asserted.
- Baselines are unchanged.
- Corpus hashes use the true indices.

This run is descriptive only.

## Summary quantities (summary.csv)

Each quantity is reported per family as median, [min, max] and `n_negative`, which counts the seeds below zero.

- `saving_pct:<method>` for all five methods, and `charged_saving_pct:` for delta and min_page.
- `delta_bytes` and `delta_pct_of_raw` for each pair listed in PAIRS.
- `primary_bytes:min_page-best(zlib,dedup_zlib)`: per seed, total(min_page) - min(total(zlib), total(dedup_zlib)). Also reported as `primary_pct_of_raw:`.
- `charged_bytes:min_page-best(zlib,dedup_zlib)`: the same, with min_page charged for the template. Also reported as `charged_pct_of_raw:`.
- `per_page_bytes:dedup_zlib-min_page`: makes the random-family check (exactly 40 B per page) directly readable.
- `enc_ms` and `dec_ms`.

Everything is paired per seed. Family medians are never subtracted from each other. No expectation is asserted at run time; the predeclared expectations are read from the output.

## Baseline check

The manifest field `baseline_check` compares this run with `results/baseline/manifest.json` and `results/baseline/raw.csv`:

- the PREREGISTRATION.md hash
- the Python version
- per-corpus sha256
- repeat-0 totals for raw, zlib and dedup_zlib

The check is recorded and printed. It does not abort the run.

## Style

- **Byte assembly:** `delta_blob` and `apply_delta` are plain imperative loops over 64 blocks because ordered bitmap and payload assembly is clearest as a bounded traversal.
- **Timing:** `perf_counter_ns` times whole-corpus Python-level encode and decode. The min_page encode time includes running zlib and building a delta for every page. Timers and output file I/O are inherently side effects. Timings are relative and nondeterministic; method order is fixed with no explicit warmup.

## Commands

- `python3 test_poc.py`
- `python3 poc.py` writes the primary run, all five methods, to `results/poc/`.
- `python3 poc.py --wrong-template` writes the descriptive run to `results/poc-wrong-template/`.
