"""B2B SaaS churn-prediction pipeline.

Generates synthetic customer data where churn is causally driven by usage
decline, engineers features, trains an XGBoost classifier, evaluates it,
and produces actionable churn-risk scores per customer.
"""

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings("ignore")


# ---------------------------------------------------------------------------
# 1.  Synthetic data generation  (churn is causally tied to usage decline)
# ---------------------------------------------------------------------------

SEED = 42
rng = np.random.default_rng(SEED)
N_CUSTOMERS = 2_500
N_MONTHS = 12
PLAN_TIERS = ["starter", "growth", "enterprise"]
INDUSTRIES = ["fintech", "healthtech", "ecommerce", "saas", "logistics", "edtech"]
START_DATE = pd.Timestamp("2025-01-01")

BASE_CHURN_RATE = 0.18
TIER_CHURN_MULT = {"starter": 1.6, "growth": 1.0, "enterprise": 0.5}
INDUSTRY_CHURN_MULT = {"fintech": 1.3, "healthtech": 0.7, "ecommerce": 1.2, "saas": 0.9, "logistics": 1.1, "edtech": 1.4}


def _generate_accounts() -> pd.DataFrame:
    accts = []
    for cid in range(1, N_CUSTOMERS + 1):
        tier = rng.choice(PLAN_TIERS, p=[0.35, 0.45, 0.20])
        industry = rng.choice(INDUSTRIES)
        tenure = int(rng.integers(4, 60))
        employees = int(rng.integers(5, 2_000))
        base_revenue = {"starter": 200, "growth": 800, "enterprise": 3_000}[tier]
        contract_length = rng.choice([1, 12, 24, 36], p=[0.1, 0.5, 0.3, 0.1])
        accts.append({
            "customer_id": f"CUST-{cid:04d}",
            "plan_tier": tier,
            "industry": industry,
            "tenure_months": tenure,
            "employees": employees,
            "base_revenue": base_revenue,
            "contract_length_months": contract_length,
        })
    return pd.DataFrame(accts)


def _generate_monthly_data(accts: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, acct in accts.iterrows():
        cid = acct["customer_id"]
        tier = acct["plan_tier"]
        tenure = acct["tenure_months"]
        employees = acct["employees"]
        base_rev = acct["base_revenue"]

        ci = INDUSTRIES.index(acct["industry"])
        tier_churn_prob = BASE_CHURN_RATE * TIER_CHURN_MULT[tier]
        ind_churn_prob = BASE_CHURN_RATE * INDUSTRY_CHURN_MULT[acct["industry"]]
        acct_churn_prob = 0.5 * tier_churn_prob + 0.3 * ind_churn_prob + 0.2 * rng.uniform(0.5, 1.5)

        will_churn = rng.random() < acct_churn_prob and tenure >= 6
        churn_severity = rng.uniform(0.3, 1.0) if will_churn else 0.0

        base_dau = max(5, int(employees * rng.uniform(0.15, 0.8)))
        base_sessions = rng.uniform(2, 8)
        base_features = rng.uniform(0.3, 0.9)
        base_api = rng.poisson(base_dau * rng.uniform(10, 50))

        for m in range(1, N_MONTHS + 1):
            month_start = START_DATE + pd.DateOffset(months=m - 1)

            usage_quality = 1.0
            if will_churn:
                decline_start = int(rng.integers(3, N_MONTHS - 1))
                if m >= decline_start:
                    months_declining = m - decline_start + 1
                    decay_factor = churn_severity * (months_declining / max(N_MONTHS - decline_start, 1))
                    usage_quality = max(0.15, 1.0 - decay_factor)

            noise_dau = rng.normal(0, 0.06)
            noise_sessions = rng.normal(0, 0.08)
            noise_features = rng.normal(0, 0.05)
            noise_api = rng.normal(0, 0.10)

            daus = max(1, int(base_dau * usage_quality * (1 + noise_dau)))
            sessions_per_user = max(0.5, base_sessions * usage_quality * (1 + noise_sessions))
            feature_adoption = np.clip(base_features * usage_quality * (1 + noise_features), 0.05, 1.0)
            api_calls = max(1, int(base_api * usage_quality * (1 + noise_api)))

            mrr = round(base_rev * (1 + rng.normal(0, 0.03)), 2)

            tickets = max(0, int(rng.poisson(max(0.3, 2.5 - feature_adoption * 2.0))))
            avg_resolution = round(rng.lognormal(1.5, 0.6), 1)
            satisfaction = max(1, min(5, int(round(rng.normal(4.2 - tickets * 0.25, 0.6)))))

            discount_pct = 0
            if rng.random() < 0.12:
                discount_pct = rng.choice([10, 15, 20, 25])

            rows.append({
                "customer_id": cid,
                "month_start": month_start,
                "month_idx": m,
                "daily_active_users": daus,
                "sessions_per_user": round(sessions_per_user, 2),
                "feature_adoption_rate": round(feature_adoption, 3),
                "api_calls": api_calls,
                "mrr": mrr,
                "support_tickets": tickets,
                "avg_resolution_hours": avg_resolution,
                "satisfaction_score": satisfaction,
                "discount_pct": discount_pct,
                "_usage_quality": round(usage_quality, 3),
            })

    df = pd.DataFrame(rows)

    churn_months = {}
    for cid in df["customer_id"].unique():
        cdata = df[df["customer_id"] == cid]
        first_serious_decline = cdata[
            (cdata["_usage_quality"] < 0.5) & (cdata["month_idx"] >= 4)
        ]
        if not first_serious_decline.empty:
            churn_month = first_serious_decline["month_idx"].iloc[0] + 1
            if churn_month <= N_MONTHS:
                churn_months[cid] = churn_month

    df["churned"] = 0
    for cid, cm in churn_months.items():
        month_after = cm
        if month_after <= N_MONTHS:
            df.loc[(df["customer_id"] == cid) & (df["month_idx"] == month_after), "churned"] = 1

    return df


# ---------------------------------------------------------------------------
# 2.  Feature engineering
# ---------------------------------------------------------------------------

def engineer_features(monthly: pd.DataFrame) -> pd.DataFrame:
    monthly = monthly.sort_values(["customer_id", "month_idx"]).reset_index(drop=True)

    monthly["target"] = monthly.groupby("customer_id")["churned"].shift(-1).fillna(0).astype(int)

    group = monthly.groupby("customer_id")
    for col in ["daily_active_users", "sessions_per_user", "feature_adoption_rate",
                "api_calls", "mrr", "support_tickets", "satisfaction_score"]:
        monthly[f"{col}_lag1"] = group[col].shift(1)
        monthly[f"{col}_lag2"] = group[col].shift(2)
        monthly[f"{col}_lag3"] = group[col].shift(3)
        monthly[f"{col}_avg3"] = group[col].transform(lambda x: x.rolling(3, min_periods=1).mean())
        monthly[f"{col}_trend3"] = group[col].transform(lambda x: x.rolling(3, min_periods=1).apply(
            lambda y: (y.iloc[-1] - y.iloc[0]) / max(y.iloc[0], 1e-6), raw=False
        ))
        monthly[f"{col}_maxdecline3"] = group[col].transform(lambda x: x.rolling(3, min_periods=1).apply(
            lambda y: (y.min() - y.iloc[-1]) / max(y.iloc[0], 1e-6), raw=False
        ))

    monthly["api_per_user"] = monthly["api_calls"] / (monthly["daily_active_users"] + 1)
    monthly["tickets_per_user"] = monthly["support_tickets"] / (monthly["daily_active_users"] + 1)
    monthly["revenue_per_user"] = monthly["mrr"] / (monthly["daily_active_users"] + 1)
    monthly["feature_to_ticket_ratio"] = monthly["feature_adoption_rate"] / (monthly["support_tickets"] + 1)

    api_avg3 = group["api_calls"].transform(lambda x: x.rolling(3, min_periods=1).mean())
    dau_avg3 = group["daily_active_users"].transform(lambda x: x.rolling(3, min_periods=1).mean())
    monthly["api_per_user_avg3"] = api_avg3 / (dau_avg3 + 1)

    tickets_avg3 = group["support_tickets"].transform(lambda x: x.rolling(3, min_periods=1).mean())
    monthly["tickets_per_user_avg3"] = tickets_avg3 / (dau_avg3 + 1)

    monthly["month_sin"] = np.sin(2 * np.pi * monthly["month_idx"] / 12)
    monthly["month_cos"] = np.cos(2 * np.pi * monthly["month_idx"] / 12)

    return monthly


# ---------------------------------------------------------------------------
# 3.  Model training
# ---------------------------------------------------------------------------

def train_model(features: pd.DataFrame):
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler

    exclude = ["customer_id", "month_start", "churned", "churn_month", "target",
               "month_idx", "_usage_quality"]
    feature_cols = [c for c in features.columns if c not in exclude]

    train = features[features["month_idx"] <= 9].copy()
    test = features[features["month_idx"] >= 10].copy()

    X_train = train[feature_cols].fillna(0)
    y_train = train["target"]
    X_test = test[feature_cols].fillna(0)
    y_test = test["target"]

    scaler = StandardScaler()
    X_train_s = pd.DataFrame(scaler.fit_transform(X_train), columns=feature_cols)
    X_test_s = pd.DataFrame(scaler.transform(X_test), columns=feature_cols)

    from xgboost import XGBClassifier
    pos_ratio = (y_train == 1).sum() / max((y_train == 0).sum(), 1)
    model = XGBClassifier(
        n_estimators=400,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=1.0 / max(pos_ratio, 0.001),
        random_state=SEED,
        eval_metric="logloss",
        early_stopping_rounds=30,
        verbosity=0,
    )
    model.fit(X_train_s, y_train, eval_set=[(X_test_s, y_test)], verbose=False)

    return model, scaler, feature_cols, X_train_s, X_test_s, y_train, y_test, train, test


# ---------------------------------------------------------------------------
# 4.  Evaluation
# ---------------------------------------------------------------------------

def evaluate(y_true, y_score, y_pred, model, feature_cols, X_test_s):
    from sklearn.metrics import (
        classification_report, roc_auc_score, roc_curve,
        precision_recall_curve, average_precision_score,
        confusion_matrix, f1_score
    )

    results = {}
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    results["confusion_matrix"] = {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)}
    results["precision"] = round(tp / max(tp + fp, 1), 3)
    results["recall"] = round(tp / max(tp + fn, 1), 3)
    results["f1"] = round(f1_score(y_true, y_pred), 3)
    results["roc_auc"] = round(roc_auc_score(y_true, y_score), 3)
    results["avg_precision"] = round(average_precision_score(y_true, y_score), 3)
    results["report"] = classification_report(y_true, y_pred, output_dict=True)

    p, r, pr_thresholds = precision_recall_curve(y_true, y_score)
    f1_scores = 2 * p[:-1] * r[:-1] / (p[:-1] + r[:-1] + 1e-6)
    best_idx = int(np.argmax(f1_scores))
    best_threshold = float(pr_thresholds[best_idx]) if best_idx < len(pr_thresholds) else 0.5
    results["optimal_threshold"] = round(best_threshold, 3)
    results["optimal_f1"] = round(float(f1_scores[best_idx]), 3)

    imp = pd.DataFrame({
        "feature": feature_cols,
        "importance": model.feature_importances_
    }).sort_values("importance", ascending=False)
    results["feature_importance"] = imp.head(15).to_dict("records")

    results["churn_rate"] = round(float(y_true.mean()), 3)
    results["test_size"] = len(y_true)

    return results, best_threshold


# ---------------------------------------------------------------------------
# 5.  Risk scoring
# ---------------------------------------------------------------------------

def score_customers(model, scaler, feature_cols, test, best_threshold):
    X = test[feature_cols].fillna(0)
    X_s = pd.DataFrame(scaler.transform(X), columns=feature_cols)

    probs = model.predict_proba(X_s)[:, 1]

    latest = test.copy()
    latest["churn_probability"] = probs
    latest["prediction"] = (probs >= best_threshold).astype(int)

    latest["risk_tier"] = pd.cut(
        latest["churn_probability"],
        bins=[-0.001, 0.15, 0.40, 1.0],
        labels=["Low", "Medium", "High"]
    )

    scores = latest.groupby("customer_id").agg(
        max_risk=("churn_probability", "max"),
        current_risk=("churn_probability", "last"),
        actual_churn=("churned", "max"),
    ).reset_index()

    scores["risk_tier"] = pd.cut(
        scores["current_risk"],
        bins=[-0.001, 0.15, 0.40, 1.0],
        labels=["Low", "Medium", "High"]
    )

    return scores, latest


def top_drivers_for_customer(cid, feature_cols, model, latest_data, scaler):
    matches = latest_data.index[latest_data["customer_id"] == cid]
    if len(matches) == 0:
        return []
    pos = latest_data.index.get_loc(matches[0])
    if isinstance(pos, slice):
        pos = pos.start
    elif isinstance(pos, np.ndarray):
        pos = int(np.where(pos)[0][0])
    X = latest_data[feature_cols].fillna(0)
    X_s = pd.DataFrame(scaler.transform(X), columns=feature_cols)
    shap_vals = X_s.values * model.feature_importances_
    row_shap = shap_vals[pos]
    top_idx = np.argsort(np.abs(row_shap))[-5:]
    drivers = []
    for fi in reversed(top_idx):
        sign = "+" if row_shap[fi] > 0 else "-"
        drivers.append({
            "feature": feature_cols[fi],
            "value": round(float(X.iloc[pos][feature_cols[fi]]), 3),
            "impact_direction": sign,
            "importance_weight": round(float(model.feature_importances_[fi]), 4),
        })
    return drivers


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    print("=" * 72)
    print("  B2B SaaS Churn-Prediction Pipeline")
    print("=" * 72)

    print("\n[1/6] Generating synthetic customer data...")
    accts = _generate_accounts()
    monthly = _generate_monthly_data(accts)
    churn_count = monthly["churned"].sum()
    print(f"       {len(accts)} accounts, {len(monthly)} account-month rows")
    print(f"       Churn events: {churn_count} ({100*churn_count/len(monthly):.2f}%)")

    print("\n[2/6] Engineering features...")
    features = engineer_features(monthly)
    n_pos = int(features["target"].sum())
    n_tot = len(features)
    print(f"       {features.shape[1]} features generated")
    print(f"       Target (churn next month): {n_pos} positives / {n_tot} ({100*n_pos/n_tot:.1f}%)")

    print("\n[3/6] Training XGBoost model...")
    model, scaler, feature_cols, X_train_s, X_test_s, y_train, y_test, train, test = train_model(features)
    print(f"       Train: {len(y_train)} rows ({int(y_train.sum())} churn events)")
    print(f"       Test:  {len(y_test)} rows ({int(y_test.sum())} churn events)")

    print("\n[4/6] Evaluating model...")
    y_pred_test = model.predict(X_test_s)
    y_score_test = model.predict_proba(X_test_s)[:, 1]
    eval_results, best_th = evaluate(y_test, y_score_test, y_pred_test, model, feature_cols, X_test_s)
    print(f"       ROC-AUC:         {eval_results['roc_auc']}")
    print(f"       Avg Precision:   {eval_results['avg_precision']}")
    print(f"       F1 Score:        {eval_results['f1']}  (optimal: {eval_results['optimal_f1']} @ thresh={eval_results['optimal_threshold']})")
    print(f"       Precision:       {eval_results['precision']}")
    print(f"       Recall:          {eval_results['recall']}")
    cm = eval_results["confusion_matrix"]
    print(f"       Confusion:       TN={cm['tn']}  FP={cm['fp']}  FN={cm['fn']}  TP={cm['tp']}")

    print("\n[5/6] Top 10 feature importances:")
    for i, feat in enumerate(eval_results["feature_importance"][:10]):
        print(f"       {i+1:2d}. {feat['feature']:<35s} {feat['importance']:.4f}")

    print("\n[6/6] Generating churn-risk scores...")
    scores, latest_preds = score_customers(model, scaler, feature_cols, test, best_th)

    tier_counts = scores["risk_tier"].value_counts()
    print(f"\n       Risk-tier distribution (all {len(scores)} accounts in test window):")
    for tier in ["Low", "Medium", "High"]:
        cnt = int(tier_counts.get(tier, 0))
        pct = 100.0 * cnt / len(scores)
        print(f"         {tier:<8s}  {cnt:5d} accounts ({pct:.1f}%)")

    high_risk = scores[scores["risk_tier"] == "High"]
    if not high_risk.empty:
        print(f"\n       Top 5 high-risk accounts:")
        top5 = high_risk.sort_values("current_risk", ascending=False).head(5)
        for _, r in top5.iterrows():
            cid = r["customer_id"]
            drivers = top_drivers_for_customer(cid, feature_cols, model, latest_preds, scaler)
            driver_str = "; ".join([f"{d['feature']}={d['value']} ({d['impact_direction']})" for d in drivers[:3]])
            churn_label = "CHURNED" if r["actual_churn"] else "ACTIVE"
            print(f"         {cid}  risk={r['current_risk']:.1%}  actual={churn_label}")
            print(f"           drivers: {driver_str}")

    print("\n" + "=" * 72)
    print("  Pipeline complete. Churn-risk scores ready for retention-team action.")
    print("=" * 72)

    return scores, eval_results, model


if __name__ == "__main__":
    main()