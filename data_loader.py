import pandas as pd
import re
import os
from dateutil.parser import parse as parse_date
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

TERRITORY_ALIASES = {
    "BLR": "Bengaluru",
    "BANGALORE": "Bengaluru",
    "BGL": "Bengaluru",
    "BOMBAY": "Mumbai",
    "MUMBAI": "Mumbai",
    "CALCUTTA": "Kolkata",
}

REGION_MAP = {
    "Delhi": "North", "Lucknow": "North", "Jaipur": "North",
    "Mumbai": "West", "Pune": "West", "Ahmedabad": "West",
    "Bengaluru": "South", "Chennai": "South", "Hyderabad": "South",
    "Kolkata": "East", "Patna": "East", "Guwahati": "East",
}

TIER_NORMALIZE = {"VAL": "Value", "PREM": "Premium"}

BAD_UNITS = {"#N/A", "NA", "N/A", "", " "}
BAD_VALUES = {-1, 9999}


def clean_date(val):
    if pd.isna(val) or str(val).strip() in ("", "#N/A", "NA", "N/A"):
        return pd.NaT
    s = str(val).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        try:
            return datetime.strptime(s, "%Y-%m-%d")
        except ValueError:
            pass
    if re.match(r"^\d{2}/\d{2}/\d{2}$", s):
        try:
            return datetime.strptime(s, "%m/%d/%y")
        except ValueError:
            pass
    if re.match(r"^\d{2}-\d{2}-\d{4}$", s):
        try:
            return datetime.strptime(s, "%d-%m-%Y")
        except ValueError:
            pass
    try:
        dt = parse_date(s, dayfirst=True)
        return dt
    except Exception:
        pass
    return pd.NaT


def parse_numeric(val):
    if pd.isna(val):
        return None
    s = str(val).strip().strip('"').strip("'")
    s = s.replace(",", "")
    s = s.replace("Rs", "").replace("rs", "").replace("INR", "").replace(" ", "")
    if s in ("#N/A", "NA", "N/A", ""):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def clean_distributor_id(did):
    if pd.isna(did):
        return did
    s = str(did).strip()
    if s.startswith("0") and len(s) > 1 and not s.startswith("0."):
        s = s[1:]
    if s == "":
        return None
    return s


def normalize_territory(t):
    if pd.isna(t):
        return t
    s = str(t).strip().title()
    return TERRITORY_ALIASES.get(s.upper(), s)


def load_data():
    dim_sku = pd.read_csv(os.path.join(DATA_DIR, "dim_sku.csv"))
    dim_sku["sku_code"] = dim_sku["sku_code"].str.strip().str.upper()
    dim_sku["tier"] = dim_sku["tier"].str.strip().str.title()
    dim_sku["tier"] = dim_sku["tier"].replace(TIER_NORMALIZE)
    dim_sku = dim_sku.drop_duplicates(subset=["sku_code"], keep="first")

    dim_geo = pd.read_csv(os.path.join(DATA_DIR, "dim_geo.csv"))
    dim_geo["territory"] = dim_geo["territory"].str.strip().str.title()
    dim_geo["territory"] = dim_geo["territory"].apply(
        lambda t: TERRITORY_ALIASES.get(t.upper(), t)
    )
    dim_geo = dim_geo.drop_duplicates(subset=["territory"], keep="first")

    dim_distributor = pd.read_csv(os.path.join(DATA_DIR, "dim_distributor.csv"))
    dim_distributor["distributor_id"] = dim_distributor["distributor_id"].str.strip().str.upper()
    dim_distributor = dim_distributor.drop_duplicates(subset=["distributor_id"], keep="first")

    dim_rep = pd.read_csv(os.path.join(DATA_DIR, "dim_rep.csv"))

    fact_sales = pd.read_csv(
        os.path.join(DATA_DIR, "fact_primary_sales.csv"),
        dtype={"primary_sales_units": str, "primary_sales_value": str},
    )
    fact_sales["week_start"] = fact_sales["week_start"].apply(clean_date)
    fact_sales = fact_sales.dropna(subset=["week_start"])
    fact_sales["sku_code"] = fact_sales["sku_code"].str.strip().str.upper()
    fact_sales["territory"] = fact_sales["territory"].apply(normalize_territory)
    fact_sales["distributor_id"] = fact_sales["distributor_id"].apply(clean_distributor_id)
    fact_sales["primary_sales_units_raw"] = fact_sales["primary_sales_units"]
    fact_sales["primary_sales_units"] = fact_sales["primary_sales_units_raw"].apply(parse_numeric)
    fact_sales["primary_sales_value"] = fact_sales["primary_sales_value"].apply(parse_numeric)
    fact_sales = fact_sales.dropna(subset=["primary_sales_value"])
    mask_bad = fact_sales["primary_sales_units"].isin(BAD_VALUES)
    fact_sales.loc[mask_bad, "primary_sales_units"] = None
    fact_sales["month"] = fact_sales["week_start"].dt.to_period("M").astype(str)

    fact_targets = pd.read_csv(os.path.join(DATA_DIR, "fact_targets.csv"))
    fact_targets["material_no"] = fact_targets["material_no"].str.strip().str.upper()
    fact_targets["area"] = fact_targets["area"].apply(normalize_territory)

    stockouts = pd.read_csv(os.path.join(DATA_DIR, "stockouts.csv"))
    stockouts["week_start"] = stockouts["week_start"].apply(clean_date)
    stockouts["item_code"] = stockouts["item_code"].str.strip().str.upper()
    stockouts["territory"] = stockouts["territory"].apply(normalize_territory)

    promotions = pd.read_csv(os.path.join(DATA_DIR, "promotions.csv"))
    promotions["week_start"] = promotions["week_start"].apply(clean_date)
    promotions["sku"] = promotions["sku"].str.strip().str.upper()
    promotions["territory"] = promotions["territory"].apply(normalize_territory)

    docs = _load_docs()

    return {
        "dim_sku": dim_sku,
        "dim_geo": dim_geo,
        "dim_distributor": dim_distributor,
        "dim_rep": dim_rep,
        "fact_sales": fact_sales,
        "fact_targets": fact_targets,
        "stockouts": stockouts,
        "promotions": promotions,
        "docs": docs,
    }


def _load_docs():
    docs_dir = os.path.join(DATA_DIR, "docs")
    docs = {}
    if os.path.isdir(docs_dir):
        for fname in sorted(os.listdir(docs_dir)):
            if fname.endswith(".txt"):
                fpath = os.path.join(docs_dir, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                ref = fname.replace(".txt", "")
                docs[ref] = content.strip()
    return docs


def get_schema_description(data):
    return {
        "fact_primary_sales": {
            "columns": ["week_start", "sku_code", "territory", "distributor_id", "primary_sales_units", "primary_sales_value", "month"],
            "grain": "One row per SKU x territory x week",
            "description": "Weekly primary sales (company to distributor) in units and INR value"
        },
        "fact_targets": {
            "columns": ["month (YYYY-MM)", "material_no (sku_code)", "area (territory)", "target_value (INR)"],
            "grain": "One row per SKU x territory x month",
            "description": "Monthly primary sales targets in INR"
        },
        "dim_sku": {
            "columns": ["sku_code", "category", "brand", "sku_name", "pack_size", "flavour", "tier", "base_mrp"],
            "description": "Product master with brand, category, pack size, tier"
        },
        "dim_geo": {
            "columns": ["territory", "region"],
            "description": "Geography master mapping territory to region (North/South/East/West)"
        },
        "stockouts": {
            "columns": ["week_start", "item_code (sku_code)", "territory", "stockout_flag", "stockout_days"],
            "description": "Weekly stockout events"
        },
        "promotions": {
            "columns": ["week_start", "sku", "territory", "promo_type", "promo_discount_pct"],
            "description": "Promotions calendar"
        },
        "unstructured_docs": {
            "count": len(data["docs"]),
            "refs": list(data["docs"].keys()),
            "description": "Internal notes, emails, circulars with operational context"
        }
    }
