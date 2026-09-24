# models

- `registry/model_versions.json`: tracked record of which model versions are live.
- `checkpoints/`: trained weights (layout, handwriting, base `yolo11n.pt`). Gitignored.

Weights are not distributed. Reproduce them with `scripts/train_layout_detector.py` and `scripts/train_handwriting.py`. Ultralytics downloads base weights into the current directory; to reuse the local copy, pass `--model models/checkpoints/base/yolo11n.pt`.
