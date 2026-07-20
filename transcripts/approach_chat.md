# Approach-Phase AI Chat Transcript — Suryaa Consumer Products Multi-Agent Assistant

## Session Overview
Building a production-grade multi-agent assistant for FMCG sales analytics.

## Transcript

**User**: Build a production-grade multi-agent assistant that answers What / Why / What-to-do questions over the provided structured and unstructured data.

**Assistant**: Let me start by understanding the data. I'll explore the data folder to understand what datasets we're working with.

**Action**: Read data directory → found 8 CSV files, 1 markdown data dictionary, and a docs/ folder with 30 text files.

**Action**: Read all CSVs and data dictionary:

Key findings:
- `fact_primary_sales.csv` — weekly primary sales (61,955 rows), columns: week_start, sku_code, territory, distributor_id, primary_sales_units, primary_sales_value
- `fact_targets.csv` — monthly targets, columns: month, material_no, area, target_value (note: column names differ from sales table)
- `dim_sku.csv` — product master (137 rows, 2 duplicates)
- `dim_geo.csv` — geography master (12 territories → 4 regions)
- `dim_distributor.csv` — distributor master (24 distributors)
- `dim_rep.csv` — sales officer master (12 reps, 1 missing name)
- `stockouts.csv` — 2 stockout events
- `promotions.csv` — 2 promotions
- 30 unstructured docs including circulars, emails, notes

**User**: Data quality issues discovered:
1. Date format inconsistency (ISO, US MM/DD/YY, Indian DD-MM-YYYY, text formats)
2. Territory naming: BLR→Bengaluru, Bombay→Mumbai
3. Leading zeros in distributor IDs: 0DEL-D1→DEL-D1
4. Bad units: 9999, -1, #N/A, empty
5. Currency symbols in values: "Rs 4,792"
6. Column name mismatches across tables
7. Duplicate SKU rows (lowercase, trailing spaces)
8. Inconsistent tier casing (Mainstream, mainstream, Mainstream)
9. PII in 4 documents (phone numbers)

**Assistant**: Building the solution architecture:
- Python FastAPI with POST /ask endpoint
- Multi-agent system: Intent Classifier → Query Engine → Reasoner → Response Builder
- Rule-based (deterministic) approach for production reliability
- Data cleaning pipeline with multi-pass date parsing

**Action**: Building data_loader.py with:
- Multi-format date parser (ISO, US, Indian, text)
- Territory alias normalization
- Distributor ID cleaning (strip leading zeros)
- Numeric value sanitization (strip Rs, commas, quotes)
- Bad value handling (9999→NaN, -1→NaN)

**Action**: Building agents.py with:
- IntentClassifier: keyword-based WHAT/WHY/WHAT_TO_DO/OOD detection
- QueryEngine: brand→SKU lookup, region→territory mapping, monthly/weekly aggregation
- Reasoner: cross-references promotions, stockouts, docs for WHY analysis
- ResponseBuilder: formats answer, computes confidence, sets status

**User**: Testing with the two business questions:

Q1: "Why did SparkClean 1kg primary sales spike in Mumbai in the week of 16 Sep 2025?"
- Intent: WHY, Status: OK, Confidence: 0.85
- Found: 15% PriceOff promotion on SC-004 in Mumbai, confirmed by promo_circular_01.txt
- Baseline: ~INR 30,600 → spike: INR 42,903.75 (+40.2%)
- Citations: docs/promo_circular_01.txt (non-empty ✓)

Q2: "What were GlucoJoy monthly primary sales vs target in the North region in November 2025?"
- Intent: WHAT, Status: OK, Confidence: 0.95
- Sales: INR 861,938.25 | Target: INR 1,026,116.06 | Achievement: 84%

Q3: "What is the weather today?"
- OUT_OF_DOMAIN, Status: ABSTAINED ✓

Q4: "What should we do about GlucoJoy stockouts in Delhi?"
- WHAT_TO_DO, Status: PENDING_APPROVAL ✓
- Found: GJ-003 stockout in Delhi for 5 days, supplier delay confirmed

**Assistant**: Building APPROACH.md, RECONCILIATION.md, and deployment docs.
