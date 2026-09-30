# Computed resource-efficiency impact

Run `.venv/bin/python benchmarks/benchmark.py --output benchmarks/results.json`, then `.venv/bin/python -m impact benchmarks/results.json benchmarks/baseline.json`.

`ImpactReporter` reads the two measured, equal-workload profiles and computes the differences. For the captured 10-page, 150-block repeat workload: **5.2585 processor-wall seconds saved**, **525.85 seconds per 1,000 pages extrapolated**, **97.7% less extraction time**, and **4,156.9% more extraction throughput** (the relative throughput gain, not total system throughput). These are derived from 5.385 s before and 0.1265 s after. The code rejects unequal page counts or block counts.

The independent-page benchmark measured **31.743 ms median** and **31.33 pages/s** for the extraction stage on this machine. This is a CPU time proxy only. No electricity, carbon, material, or real-world deployment savings are inferred. OCR and storage are outside this benchmark.
