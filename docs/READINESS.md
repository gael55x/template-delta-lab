# Readiness review — 2 October 2026

Reviewer: Codex. Reviewed measured release `47f9f300dca97c1ecb9c8e00b68c4c6f155a7e98`; the codec, original tests, preregistration and raw measurements remain unchanged in this update. Claude Opus 5.5 (`claude-opus-5-5`) authored the plotting and verifier-portability changes; Codex inspected and tested them independently.

**Decision: ready as a reproducible research lab. Not ready as a deployed memory system or evidence of infrastructure savings.** Professional presentation must expose the negative controls as prominently as the favorable headline.

Priority: P1 blocks a production/business claim; P2 limits interpretation or adoption. Intentional negative results are not defects to hide.

## AI researcher perspective

**What holds:** a frozen synthetic protocol, three baselines, same corpus hashes across methods, ten paired seeds, three timing repeats, retained raw data, roundtrip checks, template-cost sensitivity and a mismatched-template control. The experiment tests a specific mechanism from section 4.2.2, not the paper's complete system.

**P1 — external validity and cost model dominate the conclusion.** The generator chooses similarity and mutation structure favorable to block deltas. Shared-template median paired improvement on sparse pages is 18.9451% of raw bytes, but charging the full template reverses it to an 8.7833% loss; zero charged wins in ten seeds. Heavy pages improve only 0.4490% in the shared case; random pages tie. [Paired results and ranges](../COMPARISON.md).

**P2 — selector benefit is not system efficiency.** Per-page selection compares candidates whose construction costs are paid in this Python experiment. Modeled stored bytes exclude working memory, Python objects, allocator/page tables and actual serialization. Fixed method order/no warmup does not support a speed claim. Three timing repeats do not create thirty independent corpora.

Next falsifiable experiment: preregister redistributable real page traces from a defined sandbox workload and a template-retention policy, then measure total resident memory, encode/decode cost and throughput against the same baselines. Include template/index/working-memory costs. Keep this frozen experiment as a separate reference.

## Business perspective

**Useful now:** an inexpensive feasibility screen for infrastructure teams deciding whether template-relative storage deserves integration work. The useful business result is the cost boundary, not the largest savings percentage.

**P1 — no evidence of customer ROI or production memory savings.** No live sandbox integration, process RSS measurement, latency/SLO evidence, cloud-cost model or customer workload has been evaluated. The charged-template scenario loses on every family, so “reduces infrastructure cost” is not an accepted claim.

Pilot gate: identify a real workload whose template is already resident or demonstrably amortized, freeze its resource/cost accounting, and set memory and tail-latency acceptance thresholds before measuring. Compare with existing compression/deduplication tooling and include engineering overhead. No dollar benefit is inferred from synthetic byte counts.

## Software engineering perspective

**What holds:** a small standard-library implementation, explicit page/template/block contracts, no network or account credentials, exact byte roundtrips, no-overwrite result paths and source/input/output hashes. No framework or package layer is needed for a local lab.

**P1 — this is not an untrusted-data codec or kernel integration.** Delta objects are trusted in-process Python representations. Modeled headers are not a production wire format; malformed input hardening, durable template identities, eviction, concurrency and storage lifecycle remain outside scope. Do not embed the decoder in an external-file service on the strength of these tests.

**P2 — portability and result discovery needed correction.** The original verifier compared complete Python build strings before checking bytes, rejecting otherwise equivalent environments. The update makes runtime strings diagnostic, retains semantic/hash checks, requires all expected hash entries and keeps checks active under optimized Python. One regression both changes runtime metadata and tampers with a measured row after recomputing its hash; only the former is accepted. CI checks tests and frozen artifacts; it is not a cross-platform compression performance claim.

This update also publishes two reproducible figures, their generator and hash manifest, embeds the graphs in the README and adopts the descriptive name **Template Delta Lab**. The underlying evaluation is unchanged.

## AI QA evaluator perspective

**Evidence:** 16 codec/accounting tests, one verifier regression, 900 primary/control rows and 340590 byte roundtrips per complete evaluation. Earlier fresh-checkout reproduction matched all non-timing fields. Corpus hashes, all 270 baseline rows per run, repeat stability, accounting identities, random-family overhead, selector bounds and paired summaries are checked by `verify_results.py`.

**P1 — passing modeled assertions does not prove a deployed benefit.** The next acceptance matrix needs real workload coverage, template invalidation/corruption handling, resource limits and actual memory/latency measurements. No API-level or agent-reliability result follows from this codec test.

**P2 — avoid misleading statistics.** Graph denominators are raw bytes; paired differences are computed per seed. Error bars show min–max across ten seeds, not inferential confidence intervals. Wrong-template encoding and decoding use the same shifted index: this tests lost similarity, not decoder corruption resistance. Full-template charging is conservative and unconditional, including when no delta is selected.

CI and artifact hashes detect regressions within this declared model. They are not independent human peer review. Codex is a separate AI reviewer from the Claude implementation lead.

## Originality and attribution

A bounded public GitHub repository/README search on 2 October 2026 for `2609.11294` found a reference collection ([agentic-engineering](https://github.com/Marontis/agentic-engineering)); no official author implementation was identified in the inspected results. An AgentZip-name search also returned unrelated/reference projects. Search does not cover private repositories, all source files or delayed indexing; it cannot prove no other implementation exists.

The defensible contribution is this original, scoped implementation and its retained paired evaluation, including negative cost/control results. The underlying template-delta idea belongs to the cited research lineage. MIT covers this repository's original code, not the separately licensed paper. No third-party implementation was copied or executed. **Do not claim exclusive invention or official author affiliation.**

## Contributing and acceptance

Run the README's unit tests and verifier before proposing a change. For codec or accounting changes, rerun both primary and wrong-template evaluations in new output directories and explain every non-timing difference. Never overwrite the frozen results or retroactively rewrite preregistration; create a new protocol/run for a new hypothesis.

For chart changes, regenerate into a new directory with `scripts/plot_results.py`, inspect both images and retain the generated source/output hash manifest. Graph generation requires optional matplotlib; the benchmark remains standard-library-only. Contributions must provide provenance/license information and synthetic or explicitly redistributable inputs. Keep credentials, private traces, full paper copies and unpublished article drafts out of commits. Use repository issues and focused pull requests for defects or proposed experiments.
