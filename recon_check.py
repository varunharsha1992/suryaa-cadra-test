import pandas as pd
import sys
sys.path.insert(0, ".")
from data_loader import load_data

raw = pd.read_csv("data/fact_primary_sales.csv", dtype=str)
total = len(raw)
print(f"Total raw rows: {total}")

bad_val = 0
for v in raw["primary_sales_value"]:
    s = str(v).strip().upper().replace("RS", "").replace(" ", "").replace(",", "").replace('"', "")
    if s in ["", "#N/A", "NA", "N/A"]:
        bad_val += 1
print(f"Rows with unparseable values: {bad_val}")

bad_date = raw["week_start"].isna().sum()
print(f"Rows with blank dates: {bad_date}")

# Check dim_sku
dim_sku = pd.read_csv("data/dim_sku.csv")
dup = dim_sku["sku_code"].str.strip().str.lower().duplicated().sum()
print(f"Duplicate SKU rows: {dup}")

# Check dim_rep
dim_rep = pd.read_csv("data/dim_rep.csv")
empty = (dim_rep["rep_name"].fillna("").str.strip() == "").sum()
print(f"Missing rep names: {empty}")