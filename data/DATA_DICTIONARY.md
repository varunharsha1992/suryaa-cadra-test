# Data Dictionary

Datasets provided for the assessment. Data is exported as-is from source systems. Column names and value formats vary across tables, as in real operational data.

## fact_primary_sales
Weekly primary sales (company -> distributor).  
*Grain:* one row per SKU x territory x week

| column | meaning |
|---|---|
| `week_start` | Week-starting date (weekly grain). |
| `sku_code` | Product code; links to dim_sku. |
| `territory` | Sales territory; links to dim_geo. |
| `distributor_id` | Distributor code; links to dim_distributor. |
| `primary_sales_units` | Primary sales volume (units) shipped to the trade. |
| `primary_sales_value` | Primary sales value in INR. |

## fact_targets
Monthly primary-sales targets.  
*Grain:* one row per SKU x territory x month

| column | meaning |
|---|---|
| `month` | Calendar month (YYYY-MM). |
| `material_no` | Product code; links to dim_sku.  _(note: this column is named differently here than in other tables)_ |
| `area` | Sales territory; links to dim_geo.  _(note: this column is named differently here than in other tables)_ |
| `target_value` | Monthly primary-sales target in INR. |

## stockouts
Weekly stockout events.  
*Grain:* one row per stockout (SKU x territory x week)

| column | meaning |
|---|---|
| `week_start` | Week-starting date (weekly grain). |
| `item_code` | Product code; links to dim_sku.  _(note: this column is named differently here than in other tables)_ |
| `territory` | Sales territory; links to dim_geo. |
| `stockout_flag` | 1 if the SKU was out of stock in that week, else 0. |
| `stockout_days` | Number of days the SKU was out of stock that week. |

## promotions
Promotions calendar.  
*Grain:* one row per promotion (SKU x territory x week)

| column | meaning |
|---|---|
| `week_start` | Week-starting date (weekly grain). |
| `sku` | Product code; links to dim_sku.  _(note: this column is named differently here than in other tables)_ |
| `territory` | Sales territory; links to dim_geo. |
| `promo_type` | Type of promotion running. |
| `promo_discount_pct` | Promotion discount percentage. |

## dim_sku
Product master.  
*Grain:* one row per SKU

| column | meaning |
|---|---|
| `sku_code` | Product code; links to dim_sku. |
| `category` | Product category. |
| `brand` | Brand. |
| `sku_name` | Product description. |
| `pack_size` | Pack size. |
| `flavour` | Flavour / variant. |
| `tier` | Price tier (value/mainstream/premium). |
| `base_mrp` | Base maximum retail price (INR). |

## dim_geo
Geography master.  
*Grain:* one row per territory

| column | meaning |
|---|---|
| `territory` | Sales territory; links to dim_geo. |
| `region` | Sales region. |

## dim_rep
Sales officer master.  
*Grain:* one row per territory

| column | meaning |
|---|---|
| `rep_id` | Sales officer code. |
| `rep_name` | Sales officer name. |
| `territory` | Sales territory; links to dim_geo. |

## dim_distributor
Distributor master.  
*Grain:* one row per distributor

| column | meaning |
|---|---|
| `distributor_id` | Distributor code; links to dim_distributor. |
| `distributor_name` | Distributor name. |
| `territory` | Sales territory; links to dim_geo. |

