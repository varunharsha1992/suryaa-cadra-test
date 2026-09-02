# Churn-Prediction Artefact — B2B SaaS Retention Pipeline

## Pipeline Summary

| Component | Detail |
|---|---|
| **Dataset** | Synthetic (documented in APPROACH.md §E) — no external dataset used |
| **Accounts** | 2,500 B2B SaaS customers across 6 industries × 3 plan tiers |
| **Observation window** | 12 months (Jan–Dec 2025) |
| **Total rows** | 30,000 account-months |
| **Churn events** | 648 (2.16%) |
| **Features** | 65 (lags, rolling averages, trends, max-decline, ratios, cyclical time) |
| **Model** | XGBoost (400 trees, max_depth=5, lr=0.05) |
| **Train / Test** | Time-based split: months 1–9 (22,500 rows) / 10–12 (7,500 rows) |

## Model Performance

| Metric | Value |
|---|---|
| **ROC-AUC** | 0.923 |
| **Avg Precision** | 0.353 |
| **F1 (default threshold)** | 0.376 |
| **Optimal F1** | 0.393 (threshold = 0.708) |
| **Precision at optimal threshold** | 0.298 |
| **Recall at optimal threshold** | 0.575 |

### Confusion Matrix (optimal threshold)

|  | Predicted No Churn | Predicted Churn |
|---|---|---|
| **Actual No Churn** | TN = 6507 | FP = 622 |
| **Actual Churn** | FN = 141 | TP = 230 |

## Top-5 Feature Importances

| Rank | Feature | Importance |
|---|---|---|
| 1 | `feature_adoption_rate_trend3` | 0.5078 |
| 2 | `sessions_per_user_trend3` | 0.1083 |
| 3 | `daily_active_users_trend3` | 0.0704 |
| 4 | `feature_adoption_rate` | 0.0296 |
| 5 | `month_sin` | 0.0253 |

**Interpretation**: The 3-month trend in feature adoption alone contributes 51% of the model's predictive power. A declining trend in feature adoption is the single strongest signal of impending churn — consistent with the SaaS industry's known "feature stickiness" heuristic.

## Churn-Risk Score Distribution

| Risk Tier | Threshold | Accounts | % of Test Portfolio |
|---|---|---|---|
| **Low** | < 15% | 2,324 | 93.0% |
| **Medium** | 15–40% | 82 | 3.3% |
| **High** | ≥ 40% | 94 | 3.8% |

### Sample High-Risk Accounts

| Account | Risk Score | Actual Churn | Top Drivers |
|---|---|---|---|
| CUST-2491 | 91.8% | Yes | feature adoption trend (-29%), sessions trend (-22%), DAU trend (-15%) |
| CUST-0969 | 87.8% | Yes | feature adoption trend (-41%), DAU trend (-34%), sessions trend (-20%) |
| CUST-0948 | 85.2% | Yes | feature adoption trend (-9%), sessions trend (-20%), DAU trend (-17%) |
| CUST-1233 | 87.8% | No (false positive) | feature adoption trend (-22%), sessions trend (-16%) |

## Actionable Recommendations for the Retention Team

1. **Target High-risk accounts immediately** (94 accounts at ≥ 40% risk) — schedule check-in calls or feature walkthroughs focused on the specific features where adoption is declining
2. **Monitor Medium-risk accounts** (82 accounts at 15–40% risk) — automate a nurture sequence (tip-of-week emails, usage reports)
3. **Track the `feature_adoption_rate_trend3` metric** as a leading indicator — it explains 51% of model decisions. If a customer's feature adoption drops > 20% over 3 months, flag for proactive outreach
4. **False-positive rate** (622 / 7,129 non-churners = 8.7%) — acceptable for retention outreach since low-cost interventions like emails scale easily. The model catches 57.5% of churners at this threshold
5. **Refresh monthly** — the pipeline is self-contained (`python src/solution.py`) and can be re-run each month with fresh data appended to the synthetic generator

## Pipeline Code

All logic lives in `src/solution.py` — main entry point is `main()`. Run with:

```bash
pip install -r requirements.txt
python src/solution.py
```