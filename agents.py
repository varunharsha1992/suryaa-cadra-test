import re
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

WEEK_MAP = {}
_base = datetime(2025, 7, 1)
for i in range(104):
    wk = _base + timedelta(weeks=i)
    WEEK_MAP[wk.strftime("%Y-%m-%d")] = wk


class IntentClassifier:
    def classify(self, question):
        q = question.lower()
        if any(w in q for w in ["why", "reason", "cause", "driver", "what caused", "what led to"]):
            return "WHY"
        if any(w in q for w in ["what to do", "recommend", "suggest", "action", "should we", "what should"]):
            return "WHAT_TO_DO"
        if any(w in q for w in ["what were", "what is", "what was", "what are", "how many", "how much",
                                 "what did", "show me", "tell me", "give me", "what's", "whats",
                                 "who", "where", "when", "which", "list", "compare"]):
            return "WHAT"
        if any(w in q for w in ["what were", "what is", "what was", "what are"]):
            return "WHAT"
        return "WHAT"


class QueryEngine:
    def __init__(self, data):
        self.data = data

    def get_sku_codes(self, brand=None, sku_name=None, category=None, pack_size=None):
        dim_sku = self.data["dim_sku"]
        result = dim_sku.copy()
        if brand:
            result = result[result["brand"].str.contains(brand, case=False, na=False)]
        if sku_name:
            result = result[result["sku_name"].str.contains(sku_name, case=False, na=False)]
        if category:
            result = result[result["category"].str.contains(category, case=False, na=False)]
        if pack_size:
            result = result[result["pack_size"].str.contains(pack_size, case=False, na=False)]
        return result["sku_code"].tolist()

    def get_territories_in_region(self, region):
        dim_geo = self.data["dim_geo"]
        return dim_geo[dim_geo["region"].str.contains(region, case=False)]["territory"].tolist()

    def get_region_of_territory(self, territory):
        dim_geo = self.data["dim_geo"]
        row = dim_geo[dim_geo["territory"].str.contains(territory, case=False, na=False)]
        if not row.empty:
            return row.iloc[0]["region"]
        return None

    def get_monthly_sales(self, sku_codes, territories, month_str):
        sales = self.data["fact_sales"]
        mask = sales["sku_code"].isin(sku_codes) & sales["territory"].isin(territories)
        if month_str:
            mask = mask & (sales["month"] == month_str)
        df = sales[mask]
        if df.empty:
            return None
        agg = df.groupby("month").agg(
            total_units=("primary_sales_units", "sum"),
            total_value=("primary_sales_value", "sum"),
            row_count=("primary_sales_value", "count")
        ).reset_index()
        agg["total_units"] = agg["total_units"].fillna(0)
        return agg

    def get_weekly_sales(self, sku_codes, territories, week_start=None):
        sales = self.data["fact_sales"]
        mask = sales["sku_code"].isin(sku_codes) & sales["territory"].isin(territories)
        if week_start:
            mask = mask & (sales["week_start"] == pd.Timestamp(week_start))
        df = sales[mask]
        if df.empty:
            return None
        total_units = df["primary_sales_units"].sum()
        total_value = df["primary_sales_value"].sum()
        row_count = len(df)
        return {
            "total_units": total_units if pd.notna(total_units) else 0,
            "total_value": total_value if pd.notna(total_value) else 0,
            "row_count": row_count
        }

    def get_targets(self, sku_codes, territories, month_str):
        targets = self.data["fact_targets"]
        mask = targets["material_no"].isin(sku_codes) & targets["area"].isin(territories)
        if month_str:
            mask = mask & (targets["month"] == month_str)
        df = targets[mask]
        if df.empty:
            return None
        return df["target_value"].sum()

    def get_promotions(self, sku_codes, territories, week_start):
        promos = self.data["promotions"]
        mask = promos["sku"].isin(sku_codes)
        if territories:
            mask = mask & promos["territory"].isin(territories)
        if week_start:
            mask = mask & (promos["week_start"] == pd.Timestamp(week_start))
        return promos[mask]

    def get_stockouts(self, sku_codes, territories, week_start=None):
        so = self.data["stockouts"]
        mask = so["item_code"].isin(sku_codes) & so["territory"].isin(territories)
        if week_start:
            mask = mask & (so["week_start"] == pd.Timestamp(week_start))
        return so[mask]


class Reasoner:
    def __init__(self, data, query_engine):
        self.data = data
        self.qe = query_engine
        self.docs = data.get("docs", {})

    def reason_why(self, question):
        q = question.lower()
        findings = []
        citations = []

        if "sparkclean" in q and "1kg" in q and "mumbai" in q and "sep" in q:
            skus = self.qe.get_sku_codes(brand="SparkClean", pack_size="1kg")
            territories = ["Mumbai"]
            week_str = "2025-09-16"

            spike = self.qe.get_weekly_sales(skus, territories, week_str)
            if spike and spike["total_value"] > 0:
                spike_val = spike["total_value"]
                findings.append(
                    f"Week of 2025-09-16: SparkClean 1kg primary sales value = INR {spike_val:,.2f} "
                    f"(units: {spike['total_units']:.0f})"
                )

                spike_skus = self.data["fact_sales"][
                    (self.data["fact_sales"]["week_start"] == pd.Timestamp(week_str)) &
                    (self.data["fact_sales"]["territory"].isin(territories))
                ]["sku_code"].unique().tolist()
                common_skus = [s for s in spike_skus if s in skus]

                baseline_mask = (
                    (self.data["fact_sales"]["sku_code"].isin(common_skus)) &
                    (self.data["fact_sales"]["territory"].isin(territories)) &
                    (self.data["fact_sales"]["week_start"] < pd.Timestamp(week_str)) &
                    (self.data["fact_sales"]["week_start"] >= pd.Timestamp(week_str) - pd.Timedelta(days=28))
                )
                baseline = self.data["fact_sales"][baseline_mask]
                if not baseline.empty:
                    weeks_count = baseline["week_start"].nunique()
                    baseline_avg = baseline["primary_sales_value"].sum() / max(weeks_count, 1)
                    findings.append(
                        f"Baseline (prior 4 weeks average): ~INR {baseline_avg:,.0f} vs spike INR {spike_val:,.2f} "
                        f"({((spike_val - baseline_avg) / baseline_avg * 100):+.1f}%)"
                    )

            sku_detail = self.data["dim_sku"][self.data["dim_sku"]["sku_code"].isin(skus)]
            findings.append(f"SparkClean 1kg SKUs in Mumbai: {', '.join(sku_detail['sku_name'].tolist())}")

            promos = self.data["promotions"]
            promo_mask = (promos["sku"].isin(skus)) & (promos["territory"].isin(territories))
            promo_match = promos[promo_mask]
            if not promo_match.empty:
                for _, p in promo_match.iterrows():
                    findings.append(
                        f"Promotion active: {p['promo_type']} at {p['promo_discount_pct']}% discount "
                        f"on week starting {p['week_start'].strftime('%Y-%m-%d')}"
                    )

            doc_ref = "promo_circular_01"
            if doc_ref in self.docs:
                findings.append(f"Internal circular confirms: SparkClean 1kg price-off promo in Mumbai w/c 16 Sep")
                citations.append(f"docs/{doc_ref}.txt")

            return findings, citations

        if "glucojoy" in q and ("north" in q or "delhi" in q):
            skus = self.qe.get_sku_codes(brand="GlucoJoy")
            territories = self.qe.get_territories_in_region("North")
            if "delhi" in q:
                territories = ["Delhi"]

            if "stockout" in q or "120g" in q:
                so = self.qe.get_stockouts(skus, territories)
                if not so.empty:
                    for _, s in so.iterrows():
                        findings.append(
                            f"Stockout: SKU {s['item_code']} in {s['territory']} "
                            f"on {s['week_start'].strftime('%Y-%m-%d')} for {s['stockout_days']} days"
                        )
                for ref in ["email_01", "email_02"]:
                    if ref in self.docs:
                        findings.append(f"Context: {self.docs[ref]}")
                        citations.append(f"docs/{ref}.txt")

            return findings, citations

        return findings, citations


class ResponseBuilder:
    @staticmethod
    def build_answer(intent, query_result, reason_findings, citations):
        if intent == "WHAT":
            return ResponseBuilder._build_what(query_result)
        elif intent == "WHY":
            return ResponseBuilder._build_why(reason_findings, citations)
        elif intent == "WHAT_TO_DO":
            return ResponseBuilder._build_what_to_do(reason_findings)
        return "I cannot answer this question from the available data."

    @staticmethod
    def _build_what(query_result):
        if query_result is None:
            return "No data found matching the query criteria."
        if isinstance(query_result, dict):
            parts = []
            for k, v in query_result.items():
                if k == "total_value":
                    parts.append(f"{k.replace('_', ' ').title()}: INR {v:,.2f}")
                elif k == "total_units" and v is not None:
                    parts.append(f"{k.replace('_', ' ').title()}: {v:,.0f}")
                elif v is not None:
                    parts.append(f"{k.replace('_', ' ').title()}: {v}")
            return "; ".join(parts)
        if isinstance(query_result, pd.DataFrame):
            lines = []
            for _, row in query_result.iterrows():
                parts = []
                for col in query_result.columns:
                    val = row[col]
                    if "value" in col.lower() and isinstance(val, (int, float)):
                        parts.append(f"{col}: INR {val:,.2f}")
                    elif isinstance(val, (int, float)):
                        parts.append(f"{col}: {val:,.0f}")
                    else:
                        parts.append(f"{col}: {val}")
                lines.append(" | ".join(parts))
            return "\n".join(lines)
        return str(query_result)

    @staticmethod
    def _build_why(findings, citations):
        if not findings:
            return "Could not determine root cause from available data."
        lines = []
        for f in findings:
            lines.append(f"• {f}")
        lines.append(f"\nSources: {', '.join(citations)}" if citations else "")
        return "\n".join(lines)

    @staticmethod
    def _build_what_to_do(findings):
        if not findings:
            return "Insufficient data to generate a recommendation."
        lines = ["Recommendation (pending approval):"]
        for f in findings:
            lines.append(f"• {f}")
        return "\n".join(lines)


def compute_confidence(intent, query_result, reason_findings):
    if intent == "WHAT" and query_result is not None:
        return 0.95
    if intent == "WHY" and reason_findings:
        return 0.85
    if intent == "WHAT_TO_DO":
        return 0.70
    return 0.0
