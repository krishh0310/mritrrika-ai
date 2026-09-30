# Measured implementation choices

"Novel" here means a project-specific algorithmic choice, not a claim of a new research method. Both components run in `services/ai-worker/extraction/field_extractor.py`.

## 1. One classification per OCR block

The extractor scores every block against the multilingual label vocabulary once and reuses those scores when selecting a field and looking for its value. A naive neighbor scan reclassified every candidate against every label, including unrelated scripts. On the same 150-block page, ten profiled calls fell from **5.385 s to 3.614 s** after this change alone, a **32.9%** reduction. The owner/share headings and page furniture are also marked once per page.

## 2. Bounded multilingual label memoization and script gate

Forms repeat printed labels across documents. `_cached_label_score` retains 8,192 recent text/vocabulary scores; `_chrome_text` retains 4,096 page-furniture decisions. `_different_scripts` avoids fuzzy comparisons between Unicode scripts that cannot be the same printed label. This preserves fuzzy matching *within* a script for imperfect OCR. After these changes, the ten-call profile measured **0.1265 s**, a **96.5%** reduction from the intermediate 3.614 s. For **30 distinct pages**, median extraction latency was **31.743 ms**; this is the more conservative operating figure because most body text cannot reuse the cache.

The measurements are CPU-only and use synthetic OCR blocks. See [performance.md](performance.md), `benchmarks/baseline.json`, and `benchmarks/results.json` for method and limits.

## 3. Measured, budget-constrained OCR operating point

`services/ai-worker/optimization/multi_objective.py` computes a Pareto frontier over field F1, document latency and peak memory. `benchmarks/compare_pipeline.py` consumes matching real pipeline reports and selects the fastest configuration satisfying explicit quality and memory budgets, returning no recommendation if none qualify. Unlike choosing the fastest detector alone, accuracy and memory remain hard constraints. Behavioral checks are in `tests/ai/test_multi_objective.py`.

On the four-document Hindi development corpus, server and mobile remain Pareto alternatives: server F1 1.0000 at 10577.812 ms median and 15386.47 MiB; mobile F1 0.9167 at 2393.768 ms and 1964.31 MiB. A 0.90 minimum F1 / 4096 MiB budget selects mobile. These measurements expose a trade-off rather than proving general improvement. Selection is offline and does not alter production settings or human approval.

The repository also includes a bounded two-hidden-layer evolutionary search in `services/ai-worker/optimization/deep_evolutionary_network.py`. It evolves architecture and training hyperparameters against validation accuracy, parameter cost, and worst-group calibration error. `benchmarks/evolutionary_search.py` records deterministic generation evidence, Pareto candidates, equal-budget random-search comparison, regularization ablation, shifted held-out evaluation, and per-group calibration. This is evidence on synthetic nonstationary data, not a claim of real-register generalization or a new research method.
