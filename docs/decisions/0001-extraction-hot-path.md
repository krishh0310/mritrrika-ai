# ADR 0001: Reuse OCR label scores per page

Status: accepted, 2026-09-30.

The label extractor repeatedly scored each OCR block during candidate selection and neighbor scans. Profiling showed 438,430 `SequenceMatcher` calls in ten 150-block runs. Score each block/field pair once, cache repeated text/vocabulary decisions with fixed limits, and skip cross-script fuzzy matches. Preserve the existing extraction rules and fuzzy threshold. The benchmark records the before and after timings; multilingual extraction tests guard output behavior. Revisit the bounded cache size if a real workload profile shows eviction or memory pressure.
