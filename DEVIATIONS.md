# Evaluation deviations and implementation clarifications

2026-10-02, before POC measurements. Frozen PREREGISTRATION.md remains SHA-256 543e0b0a3a9eb8e179329814f7e45b36146103471644133efa72bef1b0c785ee. No change to generator, seeds, families, methods, repeats, accounting costs, expectations or scope.

The 8-byte modeled header now explicitly budgets a delta template index: 2 tag bits + 12 length bits + 6 template-index bits + 44 location bits. This is an accounting assumption, not serialized storage. Full-template sensitivity is unconditionally charged even when no delta is selected, as preregistered; it is not actual memory retention. Additional CSV columns expose delta counts, charge and pairing. The CLI defaults now write POC results, preserving the original baseline directory.

Codex reviewed Claude-authored source and tests before execution; only documentation was clarified. No code was downloaded from the paper authors. Baseline checks embedded in the manifest are diagnostic, so independent release verification also asserts complete baseline equality and result hashes.

Execution correction: the first cleared-environment invocation resolved the system Python 3.9.6 rather than baseline Python 3.12.0. Its 16 tests passed and raw outputs were retained privately as Python 3.9 diagnostics. The authoritative run is rerun with the absolute Python 3.12.0 interpreter; inputs, source and preregistration are unchanged. Do not use the diagnostic run for the main comparison.
