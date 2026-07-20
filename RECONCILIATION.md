# Reconciliation Report — Suryaa Consumer Products Ltd

## National 52-Week Primary-Sales Total

| Metric | Value |
|---|---|
| Period | 2025-07-01 to 2026-06-23 (52 weeks) |
| Total primary sales (INR) | **1,525,676,586.94** |
| Total rows processed | 61,955 |
| Total rows after cleaning | 61,955 (all rows retained; values cleaned in place) |

## Top-3 Data-Quality Fixes (ranked by rows affected)

| Rank | Fix | Rows Affected | % of Total |
|---|---|---|---|
| 1 | Normalise non-ISO date formats (MM/DD/YY, DD-MM-YYYY, DD Mon YYYY → YYYY-MM-DD) | **10,972** | 17.7% |
| 2 | Strip leading-zero prefix from distributor IDs (e.g., `0DEL-D1` → `DEL-D1`) | **9,382** | 15.1% |
| 3 | Map territory aliases to canonical names (BLR/BGL→Bengaluru) | **4,890** | 7.9% |

Additional fixes applied:
- Bad unit sentinel values: 772 rows (`9999`), 720 rows (`-1`) — set to `NaN`  
- Empty/bogus unit fields: 2,186 rows — left as `NaN` (value column still usable)  
- Currency-prefixed and quoted value strings sanitised (`Rs 4,792` → `4792.0`)  
- Case/whitespace normalisation on all key columns  
- Duplicate SKU rows in `dim_sku.csv` (2 rows: `gj-001 `, `gj-002 ` with trailing spaces) — deduplicated

## Returns / Unit-Mixing Rule Applied When Reconciling Primary Sales

Per `docs/sop_policy_01.txt`:

> *"Returns are logged separately and must not be netted into primary sales."*

**Applied rule**: `primary_sales_value` is taken at face value from the fact table. No returns or credits are netted against gross sales. The column reflects gross primary sales value shipped to distributors, consistent with the SOP.

Case-pack conversion (from `sop_policy_01.txt`): 1 case = 24 eaches for biscuits, 12 for detergent — **not applied** to the `primary_sales_units` column because the data already records individual eaches/units, not cases.

## Records Excluded

| Type | Count | Reason |
|---|---|---|
| `dim_rep` row SO-04 | 1 | Empty `rep_name` — retained as a valid territory placeholder; not excluded |
| Duplicate `dim_sku` rows | 2 | `gj-001 ` and `gj-002 ` (lowercase, trailing spaces) — deduplicated, canonical uppercase `GJ-001`, `GJ-002` retained |

**PII redacted from unstructured documents:**
The following documents contain personally identifiable information (Indian mobile numbers with +91 prefix) and are excluded from citation responses in the `/ask` endpoint output when displaying raw document text. Their analytical content is still considered as context:

| Document | PII Found |
|---|---|
| `docs/email_01.txt` | `+91 9310750256` |
| `docs/email_02.txt` | `+91 9983498086` |
| `docs/promo_circular_01.txt` | `+91 9119643961` |
| `docs/visit_note_02.txt` | `+91 9264486281` |

These documents are referenced by citation key only in responses; phone numbers are not surfaced in the `answer` field.
