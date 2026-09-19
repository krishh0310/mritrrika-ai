"""Computer-vision model choices, in one place (§6, §64).

A base-model upgrade is a one-line change here. The inference path loads the
FINE-TUNED checkpoint below, never the base weights, so changing YOLO_MODEL has
no effect until scripts/train_layout_detector.py is run again.
"""

#: Pretrained weights the layout detector is fine-tuned from. YOLO11n over
#: YOLOv10n: its C3k2 blocks and C2PSA spatial-attention layer are what
#: Ultralytics credits for better small-object accuracy at the same size --
#: document regions such as thin header strips and table rules are small.
#: That is the vendor's claim; this project's own measurement of it is in
#: docs/ai-pipeline.md.
YOLO_MODEL = "yolo11n.pt"

#: Run name under models/checkpoints/layout/ that inference loads.
LAYOUT_CHECKPOINT = "layout-v1"
