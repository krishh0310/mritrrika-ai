# Declared concept → code artifact

This table covers the working capabilities declared in the README and design docs. Limits explicitly identified as prototype exclusions are listed below the table and are not presented as working features. The prior audit's 67-term list was not provided, so this is a fresh artifact-level inventory, not a claim to have matched that unavailable list.

| Declared concept | Code artifact (file : class/function) |
|---|---|
| PDF and image intake | `services/ai-worker/ingest/rasterize.py : decode_pages` |
| Scan quality gate | `services/ai-worker/quality/assessment.py : assess` |
| Deskew, denoise, contrast | `services/ai-worker/preprocessing/enhance.py : enhance` |
| Multilingual OCR | `services/ai-worker/ocr/provider.py : build_default_engine` |
| Script routing | `services/ai-worker/ocr/scripts.py : detect_script` |
| Handwriting detection | `services/ai-worker/ocr/handwriting_model.py : HandwritingDetector` |
| Hindi handwriting reading | `services/ai-worker/ocr/handwriting_model.py : HandwritingReader` |
| Nine Indic script field labels | `services/ai-worker/extraction/labels.py : LABELS_BY_LANGUAGE` |
| English field labels | `services/ai-worker/extraction/labels.py : LABELS_BY_LANGUAGE["en"]` |
| Label anchored field extraction | `services/ai-worker/extraction/field_extractor.py : extract` |
| Owner and share table extraction | `services/ai-worker/extraction/field_extractor.py : extract_table_rows` |
| Normalization | `services/ai-worker/normalization/normalizers.py : normalize_field` |
| Field validation | `services/ai-worker/validation/rules.py : run_all` |
| Confidence fusion | `packages/domain/mrittika_domain/confidence.py : fuse` |
| Anomaly scoring | `services/ai-worker/anomaly/engine.py : analyse` |
| Exact and near duplicate checks | `apps/api/app/services/duplicate_service.py : find_exact_duplicate, find_near_duplicates` |
| Cadastral cross reference | `apps/api/app/services/cross_reference_service.py : cross_reference` |
| PostGIS parcel model | `apps/api/app/models/geography.py : Parcel` |
| Map viewport retrieval | `apps/api/app/services/search_service.py : parcels_in_bounds` |
| Ownership history | `apps/api/app/services/citizen_service.py : ownership_history` |
| Verification queue and correction | `apps/api/app/routers/workflow.py : list_queue, correct_extraction` |
| Tehsildar approval | `apps/api/app/routers/workflow.py : approve_document` |
| Feedback export and retraining | `apps/api/app/services/feedback_service.py : training_pages`; `apps/api/app/tasks/retrain_scheduler.py : run_cycle` |
| Mock LRMS delivery | `apps/api/app/integrations/lrms.py : build_adapter` |
| Mock DILRMP delivery | `apps/api/app/integrations/dilrmp_connector.py : push_record` |
| Hash chained audit | `apps/api/app/services/audit_service.py : record, verify_chain` |
| QR certificate | `apps/api/app/services/certificate_service.py : issue, verify` |
| Citizen scoped records | `apps/api/app/services/citizen_service.py : my_holdings` |
| Public approved record search | `apps/api/app/services/search_service.py : search_public_records` |
| Grounded assistant | `apps/api/app/services/rag_service.py : answer_question` |
| Dashboards | `apps/api/app/services/dashboard_service.py : analytics` |
| Operational metrics | `apps/api/app/services/metrics_service.py : render` |
| Notification channels | `apps/api/app/services/notification_service.py : Dispatcher` |
| Synthetic dataset | `scripts/generate_dataset.py : main` |
| Benchmark and impact calculation | `benchmarks/benchmark.py : run`; `impact/reporter.py : ImpactReporter.report` |

Explicit exclusions: live NIC/DILRMP connection, event broker publication, and accuracy on real citizen records. They require external access or data and are not claimed as implemented. See the limits section of the README.
