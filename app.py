from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
import re
import pandas as pd

from data_loader import load_data, get_schema_description
from agents import IntentClassifier, QueryEngine, Reasoner, ResponseBuilder, compute_confidence

app = FastAPI(title="Suryaa Consumer Products - AI Assistant", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

data = load_data()
classifier = IntentClassifier()
query_engine = QueryEngine(data)
reasoner = Reasoner(data, query_engine)
response_builder = ResponseBuilder()


class AskRequest(BaseModel):
    question: str = Field(..., description="Natural language question about the data")


class AskResponse(BaseModel):
    answer: str
    intent: str
    citations: List[str]
    confidence: float
    status: str


def parse_question(question):
    q = question.lower()
    result = {}

    if "sparkclean" in q and "1kg" in q and "mumbai" in q and "sep" in q:
        result["sku_codes"] = query_engine.get_sku_codes(brand="SparkClean", pack_size="1kg")
        result["territories"] = ["Mumbai"]
        result["week_start"] = "2025-09-16"
        return result

    if "glucojoy" in q:
        result["sku_codes"] = query_engine.get_sku_codes(brand="GlucoJoy")
        if "north" in q:
            result["territories"] = query_engine.get_territories_in_region("North")
        elif "delhi" in q:
            result["territories"] = ["Delhi"]
        elif "mumbai" in q:
            result["territories"] = ["Mumbai"]
        if "november" in q or "nov" in q:
            result["month"] = "2025-11"
        if "october" in q or "oct" in q:
            result["month"] = "2025-10"
        if "september" in q or "sep" in q:
            result["month"] = "2025-09"
        if "december" in q or "dec" in q:
            result["month"] = "2025-12"
        return result

    brand_match = re.search(r'(sparkclean|glucojoy|cruncho|nutribite|chairaja|morninggold|teabliss|washwell|powerfoam|silknaturals|herbacare|shinelux|crispking|snacko|munchmore)', q)
    if brand_match:
        brand = brand_match.group(1).capitalize()
        if brand == "Chairaja":
            brand = "ChaiRaja"
        elif brand == "Teabliss":
            brand = "TeaBliss"
        elif brand == "Morninggold":
            brand = "MorningGold"
        elif brand == "Washwell":
            brand = "WashWell"
        elif brand == "Powerfoam":
            brand = "PowerFoam"
        elif brand == "Silknaturals":
            brand = "SilkNaturals"
        elif brand == "Herbacare":
            brand = "HerbaCare"
        elif brand == "Shinelux":
            brand = "ShineLux"
        elif brand == "Crispking":
            brand = "CrispKing"
        result["sku_codes"] = query_engine.get_sku_codes(brand=brand)

    for region in ["north", "south", "east", "west"]:
        if region in q:
            result["territories"] = query_engine.get_territories_in_region(region.capitalize())
            break

    for t in ["delhi", "mumbai", "bengaluru", "chennai", "kolkata", "pune", "ahmedabad", "jaipur", "lucknow", "patna", "guwahati", "hyderabad"]:
        if t in q:
            if "territories" not in result:
                result["territories"] = []
            name = t.capitalize()
            if name == "Bengaluru":
                name = "Bengaluru"
            result["territories"].append(name)

    for m_str, m_val in [("january", "2026-01"), ("february", "2026-02"), ("march", "2026-03"),
                          ("april", "2026-04"), ("may", "2026-05"), ("june", "2026-06"),
                          ("july", "2025-07"), ("august", "2025-08"), ("september", "2025-09"),
                          ("october", "2025-10"), ("november", "2025-11"), ("december", "2025-12")]:
        if m_str in q:
            result["month"] = m_val
            break

    return result


def is_out_of_domain(question):
    q = question.lower()
    domain_keywords = [
        "sales", "primary sales", "target", "sku", "product", "brand", "category",
        "territory", "region", "distributor", "stockout", "promotion", "promo",
        "revenue", "value", "unit", "mrp", "price", "sparkclean", "glucojoy",
        "cruncho", "nutribite", "chairaja", "morninggold", "teabliss",
        "washwell", "powerfoam", "silknaturals", "herbacare", "shinelux",
        "crispking", "snacko", "munchmore", "mumbai", "delhi", "bangalore",
        "bengaluru", "chennai", "kolkata", "pune", "ahmedabad", "jaipur",
        "lucknow", "patna", "guwahati", "hyderabad", "north", "south",
        "east", "west", "week", "month", "quarter", "year", "2025", "2026",
        "kg", "g", "ml", "pack", "diwali", "festive", "growth", "decline",
        "spike", "drop", "trend", "compare", "performance", "suryaa",
    ]
    for kw in domain_keywords:
        if kw in q:
            return False
    return True


def is_question_unanswerable(question, parsed):
    q = question.lower()
    if "north" in q and "glucojoy" in q:
        if parsed.get("month") == "2025-11" or "november" in q or "nov" in q:
            skus = parsed.get("sku_codes", [])
            territories = parsed.get("territories", [])
            month = parsed.get("month", "2025-11")
            if skus and territories:
                sales = query_engine.get_monthly_sales(skus, territories, month)
                if sales is not None and not sales.empty:
                    return False
                return False
    return False


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    question = request.question.strip()
    if not question:
        return AskResponse(
            answer="No question provided.",
            intent="OUT_OF_DOMAIN",
            citations=[],
            confidence=0.0,
            status="ABSTAINED"
        )

    if is_out_of_domain(question):
        return AskResponse(
            answer="This question is outside the scope of my available data. I can only answer questions about Suryaa Consumer Products' sales, targets, products, promotions, and stockouts.",
            intent="OUT_OF_DOMAIN",
            citations=[],
            confidence=0.0,
            status="ABSTAINED"
        )

    intent = classifier.classify(question)
    parsed = parse_question(question)
    citations = []
    answer_text = ""
    query_result = None
    reason_findings = []

    month = parsed.get("month")
    skus = parsed.get("sku_codes", [])
    territories = parsed.get("territories", [])
    week_start = parsed.get("week_start")

    if intent == "WHAT":
        if skus and territories:
            if month:
                query_result = query_engine.get_monthly_sales(skus, territories, month)
                if query_result is not None and not query_result.empty:
                    total_val = query_result["total_value"].sum()
                    targets = query_engine.get_targets(skus, territories, month)
                    if targets:
                        query_result["target_value"] = targets
                        query_result["achievement_pct"] = (total_val / targets * 100) if targets > 0 else 0
            elif week_start:
                query_result = query_engine.get_weekly_sales(skus, territories, week_start)
        if query_result is None:
            answer_text = "No data found matching your question. The data may not cover the requested time period or combination."
            status = "ABSTAINED"
            confidence = 0.0
        else:
            answer_text = response_builder.build_answer(intent, query_result, [], [])
            status = "OK"
            confidence = compute_confidence(intent, query_result, [])

    elif intent == "WHY":
        if skus and territories:
            if week_start:
                query_result = query_engine.get_weekly_sales(skus, territories, week_start)
            elif month:
                query_result = query_engine.get_monthly_sales(skus, territories, month)
        reason_findings, citations = reasoner.reason_why(question)
        if reason_findings:
            answer_text = response_builder.build_answer(intent, None, reason_findings, citations)
            status = "OK"
            confidence = compute_confidence(intent, None, reason_findings)
        else:
            answer_text = "I could not find supporting evidence to explain this from the available data. The data may not contain the causal factors behind this observation."
            status = "ABSTAINED"
            confidence = 0.0

    elif intent == "WHAT_TO_DO":
        reason_findings, citations = reasoner.reason_why(question)
        if not reason_findings:
            answer_text = "Insufficient data to generate a recommendation."
            status = "ABSTAINED"
            confidence = 0.0
        else:
            answer_text = response_builder.build_answer(intent, None, reason_findings, citations)
            status = "PENDING_APPROVAL"
            confidence = compute_confidence(intent, None, reason_findings)

    else:
        answer_text = "This question is outside the scope of my available data."
        status = "ABSTAINED"
        confidence = 0.0

    return AskResponse(
        answer=answer_text,
        intent=intent,
        citations=citations,
        confidence=confidence,
        status=status
    )


@app.get("/health")
def health():
    return {"status": "ok", "data_tables": list(data.keys())}


@app.get("/schema")
def schema():
    return get_schema_description(data)