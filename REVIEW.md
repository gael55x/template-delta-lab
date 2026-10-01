# Independent review — 2 October 2026

Reviewer: Codex. Lead selection/codec/tests: verified Claude Opus 5.5 (`claude-opus-5-5`). Reviewed implementation revision: `200739fe3be67c18da573b2f2f8173723eb505fa`.

**Disposition: suitable for publishing this bounded synthetic experiment. No unresolved correctness finding. No production or full-paper claim accepted.**

## Checks and findings

- Domain: bitmap and block order reconstruct exact bytes. Tests exercise 0/1/63/64 changed blocks, the last byte, raw admission, stable ties, wrong-template identity and hand-computed costs.
- Architecture: one stdlib codec/benchmark file; explicit delta template index; no retained original bytes inside a delta object. Trusted in-process tuples, not a decoder for untrusted files. Imperative byte assembly and timer/file side effects are appropriate here.
- Regression: generator and corpus-hash functions plus zlib store function are AST-identical to the baseline. Every prior non-timing baseline field matches on all 270 rows, in both primary/control runs.
- Evaluation: paired differences are calculated within seed; independent verifier checks 30 corpus hashes, 900 rows, costs, repeat stability, selector bounds, random-family accounting and reported paired summaries. No inputs or expectations changed after measurement.
- Reproduction: fresh local clone of the revision above passed all 16 tests and replayed primary/control. All 900 non-timing rows matched exactly; timings differed as expected. Receipts and hashes are in `results/poc/verification.json`.
- Secrets/data: source imports and I/O paths manually reviewed; no network, account access, downloaded code, subprocesses or external datasets in benchmark or verifier. Runs used a cleared environment under the normal sandbox. Pattern checks of publication files found no credentials. No strong filesystem isolation claim: code was inspected before running; environment clearing alone is not a filesystem boundary.
- Licensing: original MIT code; paper CC BY-NC-ND 4.0 cited separately. No paper prose, figures, upstream code, datasets or weights included. Private model receipts and source copies stay outside this repository.
- Claims: report modeled bytes only. Full-template charging reverses both observed shared-template advantages. Fixed method order/no warmup, excluded Python/object/allocator costs, synthetic workloads and no kernel integration preclude real-memory or speed claims.
- Developer experience: explicit no-overwrite output directories, documented Python/zlib versions, committed raw data and runnable independent verifier. Baseline manifest comparison is diagnostic; release verifier supplies the strict assertion gate.

## Resolved before release

1. Made template-index cost explicit within the fixed 8-byte header; documented its bit budget and that it is modeled rather than serialized.
2. Corrected the lead's explanation of template retention: a zero-delta corpus need not retain the template. The unconditional sensitivity charge remains the frozen conservative scenario.
3. Corrected the initial interpreter selection from system Python 3.9.6 to baseline Python 3.12.0. Diagnostic outputs were preserved privately; no generator or source adjustment. Both interpreters passed 16 tests, but release measurements/replay use 3.12.0.
4. Updated stale baseline-only README and reported the negative charged-template result as prominently as shared-template savings.

No code change by Codex was needed in the lead-authored codec or unit tests. Codex added the independent artifact verifier and wrote reports. Public claims stop at this experiment's measured scope.
