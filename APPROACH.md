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

## Chat Transcripts

### Approach-Phase AI Chat Transcript
Available at: `transcripts/approach_chat.md`

### Build-Phase AI Chat Transcript  
Available at: `transcripts/build_chat.md`