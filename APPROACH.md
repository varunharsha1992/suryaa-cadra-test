# Approach Document — Suryaa Consumer Products Multi-Agent Assistant

## Section A — Problem Decomposition

### Supported Analytical Question Types

| Intent | Question Pattern | Structured Output |
|---|---|---|
| **WHAT** | "What were X monthly sales vs target in Y region in Z month?" | Aggregated table: `{month, total_units, total_value, target_value, achievement_pct}` |
| **WHY** | "Why did X spike/drop in Y in week Z?" | Root-cause narrative + supporting data points + `citations[]` (non-empty) |
| **WHAT_TO_DO** | "What should we do about X?" | Recommendation narrative; `status` always `PENDING_APPROVAL` |
| **OUT_OF_DOMAIN** | Irrelevant queries (weather, etc.) | `status: ABSTAINED`, no fabricated answer |

### WHY Answer Requirements
- Every WHY answer carries a non-empty `citations` array grounding the explanation in the underlying data (structured or unstructured).
- Baseline comparison computed from prior 4-week average.
- Promotions, stockouts, and internal circulars are cross-referenced.

### WHAT_TO_DO Guardrails
- Any recommendation returns `status: PENDING_APPROVAL` — never `OK`.
- If insufficient evidence, returns `status: ABSTAINED`.

### ABSTAINED Rules
- Questions unanswerable from the provided data → `status: ABSTAINED`
- Questions resting on a false premise → `status: ABSTAINED`
- Out-of-domain questions → `status: ABSTAINED`, `intent: OUT_OF_DOMAIN`

---

## Section B — Solution & Agentic Construct Design

### Architecture Choice: Rule-Based Multi-Agent (Python + FastAPI)

**Why not an LLM-based agent?** The data is deterministic (CSV + text files). A rules-based approach is:
- **Deterministic**: same question → same answer, every time
- **Auditable**: every step can be traced and verified
- **Zero hallucination risk from model inference**: all aggregations are computed, not generated
- **Production-ready**: no GPU, no API keys, no model latency, no cost per query

### Agentic Construct

```
User Question
    │
    ▼
┌─────────────────────┐
│  Agent 1: Intent    │  Classifies WHAT / WHY / WHAT_TO_DO / OOD
│  Classifier         │  Input: raw question string
│                     │  Output: intent label
│                     │  Failure: defaults to WHAT
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Agent 2: Query     │  Parses question for brand, region, territory,
│  Parser & Engine    │  month, week. Executes pandas aggregations.
│                     │  Input: question + intent
│                     │  Output: query_result (dict or DataFrame) + parsed params
│                     │  Failure: returns None → ABSTAINED
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Agent 3: Reasoner  │  For WHY/WTD: cross-references promotions, stockouts,
│  (if WHY/WTD)       │  unstructured docs. Builds causal narrative.
│                     │  Input: question + parsed params
│                     │  Output: findings[] + citations[]
│                     │  Failure: empty findings → ABSTAINED
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Agent 4: Response  │  Formats answer, computes confidence, sets status
│  Builder            │  Input: intent, query_result, findings, citations
│                     │  Output: AskResponse {answer, intent, citations, confidence, status}
│                     │  Failure: never — always returns valid response object
└─────────────────────┘
```

### Handoff Protocol

| From → To | Data Passed | Failure Path |
|---|---|---|
| Classifier → Parser | `intent` | If OOD, skip to Response Builder |
| Parser → Reasoner | `{sku_codes, territories, month, week_start}` | If query_result is None, set status=ABSTAINED |
| Reasoner → Builder | `{findings[], citations[]}` | If empty findings, set status=ABSTAINED |
| Builder → Response | `AskResponse` | Always succeeds |

---

## Section C — Data Interaction Design

### Dataset Access
All datasets are loaded at startup into Pandas DataFrames, cleaned, and cached in memory. The `data_loader.py` module handles:
1. **Schema normalisation**: column name aliases (`material_no`→`sku_code`, `area`→`territory`, `item_code`→`sku_code`, `sku`→`sku_code`)
2. **Date parsing**: 5 date formats detected (ISO `YYYY-MM-DD`, US `MM/DD/YY`, Indian `DD-MM-YYYY`, text `DD Mon YYYY`, plus `DD-MM-YYYY` with 4-digit year)
3. **Territory aliasing**: BLR/BGL/Bangalore→Bengaluru, Bombay→Mumbai
4. **Value sanitisation**: strip `Rs` prefix, commas, quotes; parse `#N/A`/`NA`/empty as `NaN`
5. **Sentinel handling**: `9999` and `-1` units set to `NaN`; value column preserved

### Schema Awareness
The system exposes a `/schema` endpoint returning the full schema description. The `QueryEngine` maps question keywords to:
- `brand` → `dim_sku.brand` (case-insensitive match)
- `region` → `dim_geo.region` → expands to list of territories
- `territory` → direct match via alias map
- `month` → `YYYY-MM` format; detected from month names + year context
- `week` → `YYYY-MM-DD` format; detected from date patterns

### Aggregation Design

**Time grain**:
- Weekly: `week_start` column, pre-parsed as timestamp
- Monthly: `month` column derived from `week_start.dt.to_period("M")` for cross-table join with `fact_targets`

**Dimensional hierarchy**:
```
Territory (12) → Region (4: North/South/East/West)
Brand (13) → Category (4: Biscuits/Tea/Detergent/Shampoo/Snacks)
SKU (137) → Pack Size → Tier (Value/Mainstream/Premium)
```

**Metric derivation**:
- `achievement_pct = total_sales_value / total_target_value * 100`
- `baseline = avg(prior 4 weeks value)` for WHY spike/drop analysis
- Unit economics: `implied_unit_price = value / units` (when units available)

---

## Section D — Risk Awareness & Trade-Off Reasoning

### Risk 1: Incorrect Query Generation
**Risk**: The date-parsing heuristic may mis-interpret DD-MM-YYYY as MM-DD-YYYY for dates where both parts are ≤12.

**Concrete Mitigation**: Four-pass parsing with format detection:
1. Exact ISO match (`YYYY-MM-DD`) → unambiguous
2. US format (`MM/DD/YY`) → explicit `strptime`
3. Indian format (`DD-MM-YYYY`) → explicit `strptime` with `%d-%m-%Y`
4. Fallback: `dateutil.parser.parse(dayfirst=True)` for text formats

This ensures Indian sales data is never misinterpreted as US dates.

### Risk 2: Hallucinated Responses
**Risk**: A WHY answer might fabricate causal factors not present in the data.

**Concrete Mitigation**: All WHY answers must carry a non-empty `citations` array. The Reasoner only returns findings that are explicitly backed by:
- Queried aggregation results (sales values, units)
- Recorded promotions (from `promotions.csv`)
- Recorded stockouts (from `stockouts.csv`)
- Unstructured documents (from `docs/`)

If no supporting evidence is found, the system returns `status: ABSTAINED` rather than fabricating a cause.

### Risk 3: Data Misinterpretation
**Risk**: The `primary_sales_value` includes returns, discounts, or other adjustments not visible in the fact table.

**Concrete Mitigation**: Per `sop_policy_01.txt`, "Returns are logged separately and must not be netted into primary sales." The system treats `primary_sales_value` as gross sales to distributors. No netting is applied. The RECONCILIATION.md explicitly documents this rule.

### Design Trade-Off: Rule-Based vs LLM-Based Agent

**Chosen**: Rule-based multi-agent (Python logic + pandas)

**Trade-off Rationale**:

| Factor | Rule-Based (Chosen) | LLM-Based |
|---|---|---|
| Correctness | Deterministic — same input always same output | Probabilistic — may vary |
| Hallucination | Zero — all calculations are verifiable | Non-trivial — requires guardrails |
| Cost | Free (no API calls) | API cost per query |
| Latency | <100ms | 1-5s+ |
| Maintenance | Requires explicit logic for each question type | Can handle novel questions without code changes |
| Coverage | Limited to programmed patterns | Broad natural language understanding |

**Accepted limitation**: The rule-based parser cannot handle arbitrarily complex questions. For example, "Compare SparkClean's Q3 performance in West vs East regions" requires explicit code support. The trade-off is acceptable for a production system where correctness and auditability are paramount over conversational breadth.

---

---

## Section E — B2B SaaS Churn-Prediction Pipeline (`src/solution.py`)

### Problem
The retention team at a B2B SaaS company acts reactively — after cancellation. They need a forward-looking churn-risk score per account to intervene early (check-in call, discount, feature walkthrough).

### Architecture

```
Raw Data (synthetic)
    │
    ▼
┌──────────────────────┐
│ Data Generation      │  2 500 accounts × 12 months = 30 000 rows
│                      │  Churn causally driven by declining usage
│                      │  (feature adoption, sessions, DAU)
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ Feature Engineering  │  65 features: lags, rolling 3-month avgs,
│                      │  trends, max-decline, ratio features
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ Model Training       │  XGBoost, train until month 9,
│ (XGBoost)            │  test on months 10-12
│                      │  scale_pos_weight handles imbalance
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ Evaluation           │  ROC-AUC, precision, recall, F1,
│                      │  confusion matrix, feature importance,
│                      │  optimal threshold via PR curve
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ Risk Scoring         │  Per-account churn probability → risk tier
│                      │  (Low < 15% / Medium < 40% / High 40%+)
│                      │  Top-3 drivers per high-risk account
└──────────────────────┘
```

### Data Design
- **Synthetic data generation** (no external dataset used): 2 500 accounts across 6 industries (fintech, healthtech, ecommerce, saas, logistics, edtech) and 3 plan tiers (starter/growth/enterprise).
- **Churn is causal**: accounts that will churn experience a gradual usage decline starting 2-3 months prior. The decline is driven by `churn_severity` × `months_declining`, producing realistic decay in DAU, sessions, feature adoption, and API calls.
- **Label**: `churned = 1` in the month AFTER the usage quality drops below 50% (to simulate the customer actually cancelling after a period of disengagement).

### Feature Engineering
| Category | Features |
|---|---|
| **Lags (t-1, t-2, t-3)** | DAU, sessions, feature adoption, API calls, MRR, tickets, satisfaction |
| **Rolling 3-month avg** | Same 7 metrics |
| **Trend (3-month slope)** | Same 7 metrics |
| **Max decline (3-month drawdown)** | Same 7 metrics |
| **Ratio** | API per user, tickets per user, revenue per user, feature-to-ticket ratio |
| **Time** | month_sin, month_cos |

### Model
- **Algorithm**: XGBoost (400 trees, max_depth=5, lr=0.05, colsample=0.8, subsample=0.8)
- **Imbalance handling**: `scale_pos_weight` = inverse of positive-ratio
- **Time-based split**: Months 1-9 train, 10-12 test (prevents lookahead)
- **Target**: `churned in month t+1` (shift(-1))

### Risk Scoring
- Raw probability from `predict_proba` → binned into Low / Medium / High tiers
- Top-5 account-level drivers via feature-importance-weighted contribution (proxy SHAP)
- Output ready for CRM upload or alerting

### Trade-Offs & Risks
| Risk | Mitigation |
|---|---|
| **Synthetic data may not reflect real patterns** | Generation uses realistic tier/industry churn-rate multipliers; causal structure mirrors known SaaS churn mechanics (usage decline precedes cancellation) |
| **Class imbalance (2.2% churn rate)** | scale_pos_weight + threshold tuning via PR curve |
| **Lookahead leakage** | Time-based split (no random shuffle); lags prevent forward-looking features |
| **Feature importance ≠ causal explanation** | Drivers are suggestive; retention team should treat as signals, not diagnoses |
| **Model retraining** | Pipeline is self-contained; monthly retraining would require appending new data to the generation step |

## Chat Transcripts

### Approach-Phase AI Chat Transcript
Available at: `transcripts/approach_chat.md`

### Build-Phase AI Chat Transcript  
Available at: `transcripts/build_chat.md`