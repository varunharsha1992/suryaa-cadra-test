# Build-Phase AI Chat Transcript — Suryaa Consumer Products Multi-Agent Assistant

## Session Overview
Building the solution code, testing, and fixing issues.

## Transcript

**User**: Build the full solution with FastAPI, multi-agent system, data cleaning, and all required endpoints.

**Action**: Created project structure:
- `requirements.txt` — FastAPI, uvicorn, pandas, python-dateutil, pydantic
- `data_loader.py` — Data loading, cleaning, schema normalization
- `agents.py` — Multi-agent system (IntentClassifier, QueryEngine, Reasoner, ResponseBuilder)
- `app.py` — FastAPI application with POST /ask, GET /health, GET /schema

**Issue 1**: Date parsing ambiguity. `01-07-2025` was being parsed as Jan 7 instead of July 1.
**Fix**: Implemented 4-pass date parsing with format-specific strptime:
1. ISO match (`YYYY-MM-DD`)
2. US format (`MM/DD/YY`)
3. Indian format (`DD-MM-YYYY`)
4. Text fallback with dayfirst=True

**Issue 2**: `Bgl` territory not being cleaned. `BGL` was missing from the aliases map.
**Fix**: Added `"BGL": "Bengaluru"` to `TERRITORY_ALIASES`.

**Issue 3**: `get_weekly_sales()` returning nested dict with MultiIndex keys.
**Fix**: Changed from pandas `.agg().to_dict()` to manual sum/count with flat dict.

**Issue 4**: Baseline calculation multiplying instead of dividing by week count.
**Fix**: Changed `baseline_avg = sum / len(baseline) * 4` to `sum / weeks_count`.

**Issue 5**: Baseline being calculated over wrong SKU set (all 3 SparkClean 1kg SKUs instead of just SC-004 which had data in Mumbai).
**Fix**: Added logic to determine which SKUs actually have data in the spike week, then compute baseline over only those SKUs.

**Test Results**:
```
Q1: WHY SparkClean → Status: OK, Conf: 0.85, Citations: 1
Q2: WHAT GlucoJoy → Status: OK, Conf: 0.95, Achievement: 84%
Q3: OOD weather → Status: ABSTAINED, Conf: 0.0
Q4: WTD stockouts → Status: PENDING_APPROVAL, Conf: 0.7
```

**Final Verification**:
- 52 unique weeks confirmed (2025-07-01 to 2026-06-23)
- Total primary sales: INR 1,525,676,586.94
- All 61,955 rows retained after cleaning (values cleaned in-place)
- 0 rows excluded (all dates parseable, all values parseable)

**PII Handling**: 4 documents contain Indian mobile numbers. Cited by reference key only, phone numbers not surfaced in answers.