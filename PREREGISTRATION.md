# Preregistration: synthetic template-delta baselines and Friday POC

Version 1, written 2026-10-01, before any run.

**Freeze.** Every `manifest.json` records the sha256 of this file. The Friday run must either match today's hash or list every change in `DEVIATIONS.md`.

## Source and scope

- **Source:** AgentZip, arXiv:2609.11294v1 (https://arxiv.org/abs/2609.11294), CC BY-NC-ND 4.0.
- **What is in scope:** only section 4.2.2, which encodes a sandbox's private page as a block delta against its immutable template page. It is paraphrased here, and nothing is copied.
- **Nature of this work:** original stdlib Python run on synthetic pages. It is not a reproduction, and it makes no claims about:
  - the paper's numbers
  - OS RSS
  - latency or speedups
  - LLMs
- **Dropped from the earlier draft:**
  - cohort dictionaries and RLE
  - portfolios and validation gates
  - sign tests and bootstrap CIs

## Question

On synthetic sandbox pages, how many bytes does per-page min(template-delta, zlib, raw) store, compared with strong baselines that do not use the template? We ask this for three kinds of private set:

- **sparse:** contains meaningful exact duplicates
- **heavy:** consists of mostly rewritten pages
- **random:** consists of independent random pages

## Inputs (fixed)

- **Page geometry:** 4096 B pages split into 64 B blocks, so 64 blocks per page.
- **Corpus size:** each family and seed has 64 template pages and 8 sandboxes.
- **RNG:** `random.Random('<family>:<seed>')`, with seeds 0..9.
- **Template page kinds**, drawn with these weights:
  - zero: 2
  - struct (small-stride LE counters): 5
  - text (word tokens): 2
  - random: 1
- **Writes:** each sandbox writes each template page with probability `dirty`. A write does exactly one of the following:
  - stores identical bytes (probability `rewrite`)
  - produces that page's shared variant, which is identical across sandboxes and is the source of the exact duplicates (probability `shared`)
  - overwrites `blocks` randomly chosen blocks with fresh content (otherwise)

| family | dirty | blocks | rewrite | shared | fresh block kinds |
|---|---|---|---|---|---|
| sparse | 0.5 | 2 | 0.1 | 0.6 | struct, text |
| heavy | 0.75 | 48 | 0 | 0 | struct, text, random x2 |
| random | 1.0 | 64 | 0 | 0 | random |

- **Copy-on-write invariant (a synthetic rule):** a page byte-identical to its template page is shared. It is excluded from the private set for all methods and reported as `excluded_cow_pages`. The sparse family exercises this rule through `rewrite`. Dedup gets no credit for these pages.
- **Identical inputs:** every method sees the same private pages in the same order.
- **Corpus identity:** each corpus is identified by a sha256 over its template pages and its (template index, page) records.

## Accounting (fixed)

- **Private bytes** = 4096 x the number of private pages.
- **Saving %** = 100 x (1 - total / private bytes).
- **Admission:** if a page's encoding plus its 8 B header is not smaller than 4096 B, the page stays resident at 4096 B and pays no header.
- **Header:** 8 B per encoded page, holding the codec tag, length and location.
- **dedup_zlib:**
  - Pages are matched exactly, by sha256 plus a full byte comparison.
  - Every stored object pays 32 B for its hash and 8 B for its refcount. This applies to all stored objects, including those that are never duplicated and those that were not admitted.
  - Every duplicate page pays an 8 B reference.
  - On the random family, this index overhead is expected to make dedup_zlib larger than zlib. That result is reported, not hidden.
- **Template bytes, primary run:** shared-resident, charged to no method. The template is already needed for copy-on-write.
- **Template bytes, sensitivity run (Friday):** the template could otherwise be evictable or compressible. To cover that case, charge all 64 x 4096 template bytes once per family and seed. The charge goes only to the methods that read the template during decode: delta and min_page.
- **Nothing else is charged:** no page tables, allocator slack or process overhead.

## Methods

**Today (baselines):**
- raw
- zlib: level 9, per page, with admission
- dedup_zlib

**Friday (POC):**
- **delta:** an 8 B bitmap marking which blocks differ from the page's template, followed by those differing blocks verbatim. Cost = 8 B header + 8 B bitmap + 64 B per changed block, with admission.
- **min_page:** for each page, the cheapest stored cost among raw, zlib and delta. Ties go to raw, then zlib, then delta. The codec tag is stored in the header.

**Not planned:** delta combined with dedup, and zlib-compressed deltas. If either is added, it is recorded as a deviation and reported separately.

## Measurements

- **Rows:** one per family x seed x method x repeat, with 3 repeats.
- **Timing:** wall-clock time for encoding and for decoding the whole corpus, measured with `time.perf_counter_ns`. Each row also carries the accounting above.
- **Abort conditions:** the run aborts if sizes differ between repeats, or if any page fails to round-trip bitwise.
- **Recorded provenance:**
  - Python and platform versions
  - zlib compile and runtime versions
  - seeds, repeats and constants
  - corpus hashes and file hashes

## Reporting (no hypothesis tests)

- **Per family:** across the 10 seeds, the median and [min, max] of:
  - saving % for each method
  - paired per-seed deltas, in bytes and as % of private bytes
- **Friday primary quantity:** for each seed, total(min_page) - min(total(zlib), total(dedup_zlib)), which compares against the best baseline for that seed. Report its median/range and the number of seeds where it is negative.
- **Predeclared expectations.** These are descriptive and are reported whichever way they come out.
  - **sparse:** negative in 10 of 10 seeds under shared-resident accounting. Note that dedup exploits sparse's exact duplicates and min_page does not.
  - **heavy:** no direction is claimed.
  - **random:** in every seed, min_page total equals private bytes, and dedup_zlib exceeds it by exactly 40 B per page. These are predeclared checks for the fixed pseudorandom corpora, not a mathematical guarantee that all random byte strings are incompressible.
  - **template-charged sensitivity:** reported with the same median/range. No expectation.
- **Wrong-template run (Friday, descriptive only):** delta and min_page are run with each page paired to template index (i + 1) mod 64. This is not a pass/fail control, for two reasons:
  - min_page can still win through within-page redundancy captured by zlib.
  - delta can still match zero blocks or unchanged blocks.
- **Timing:** medians and ranges of the per-seed median encode and decode ms. These are labelled as Python-level relative measurements, with no speedup claims.

## Validity checks

- The round-trip and repeat-size assertions described above.
- The same seed gives the same corpus sha256. Friday's corpora must hash-match today's baseline when run on the same Python.
- Asserted size bounds:
  - zlib total <= raw total
  - min_page per-page cost <= its zlib and raw costs, which holds by construction

## Costs

- **Benchmark:** $0 API spend and no network. It runs on local CPU in seconds to minutes (an estimate).
- **Authoring and review by AI models:** a separate cost. It is not measured here and is not claimed to be zero.

## Limitations

- The synthetic generator largely determines the results. The three families explore synthetic scenarios; they neither represent nor establish bounds for real workloads.
- Compressed sizes depend on the zlib build.
- Python timings include interpreter overhead.

## Deviations

- Any change after the freeze goes in DEVIATIONS.md, with its reason and the new file hash.
- Families, parameters and expectations are not tuned after seeing results.
