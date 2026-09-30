# Computed resource-efficiency impact

Run `.venv/bin/python benchmarks/benchmark.py --output benchmarks/results.json`, then `.venv/bin/python -m impact benchmarks/results.json benchmarks/baseline.json`.

`ImpactReporter` reads the two measured, equal-workload profiles and computes the differences. For the captured 10-page, 150-block repeat workload: **5.2585 processor-wall seconds saved**, **525.85 seconds per 1,000 pages extrapolated**, **97.7% less extraction time**, and **4,156.9% more extraction throughput** (the relative throughput gain, not total system throughput). These are derived from 5.385 s before and 0.1265 s after. The code rejects unequal page counts or block counts.

The independent-page benchmark measured **31.743 ms median** and **31.33 pages/s** for the extraction stage on this machine. This is a CPU time proxy only. No electricity, carbon, material, or real-world deployment savings are inferred. OCR and storage are outside this benchmark.

## Actual local pipeline outputs

`python -m impact benchmarks/document-pipeline/mobile-after.json --pipeline` computes the committed `benchmarks/document-pipeline/impact.json`: four successful documents, 9.555545 seconds summed processing time, 0.418605 documents/s, 24 extracted fields, all 24 flagged for review, and 1964.3125 MiB measured peak process RSS. Human review time saved and energy saved are explicitly null. A review flag count does not measure reviewer effort saved.

The official [UN Target 9.4](https://sdgs.un.org/goals/goal9) concerns sustainable infrastructure/industrial retrofits, resource efficiency and cleaner technologies. Its indicator concerns CO₂ per unit of value added. The evaluator's computational-algorithm wording is a project interpretation, not an official quotation. Our measured processing throughput and memory can inform resource planning; no energy, emissions, financial savings or citizen outcomes were measured.
