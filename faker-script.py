# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.18.1
#   kernelspec:
#     display_name: .venv
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Scope
# Implicit _production_ knowledge graph
#
# ## Limitations
#
# - **Static Substitutability**: No explicit modeling of backup materials / suppliers 
# - **Logistics Blindspot**: Logistic Route Disruptions from supplier to buyer (e.g. Read Sea blockage) are ignored 
# - **Hidden Correlations**: All supplier entities are independent, possible clustering within parent holding company is isolated
# - **Clear BOM hierarchy**: Without skipping tiers and cyclic dependencies
# - **No product variants**: For simplicity, but would add extra granularity
# - Only one material per purchase order (could be multiple in reality, but would lead to extra complexity)
# - **No Temporal Logic**: Random PO dates, no time phasing for product delivery flow from lower to higher tiers (completely independent of each other) -> loses "Bullwhip" effect
# - **Strict Tier Rigidity**: Enforces a strict Tier N -> Tier N + 1 dependency (in reality, there are "skip-level" edge like directed buys)
#

# %% [markdown] id="JSV3iFgxEDE0"
# # Configuration & Parameters

# %% colab={"base_uri": "https://localhost:8080/"} id="_9D_di66EMVe" outputId="dbc85c12-0906-44f5-b1e5-29e64e203f1f"
# %pip install faker pandas numpy
import pandas as pd
import numpy as np
from faker import Faker
import random
import os
from datetime import timedelta, date

# %% id="r-qa-rjmE1Zf"
seed = 42 # for reproducible random output across runs
fake = Faker()
Faker.seed(seed)
np.random.seed(seed)
random.seed(seed)

# %% [markdown] id="pH6MHJlpHZsu"
# ## Volume Constraints

# %% id="fIYjpTPRHjt5"
NUM_SUPPLIERS = 3000
NUM_MATERIALS = 7000  # Total material nodes across all tiers
TARGET_PO_COUNT = 80000

# %% [markdown] id="sdJrY4OMFHf3"
# ## Tier Distribution
#
# Probabilities for a material falling into a specific tier
#
# 0.   Finished EV
# 1.   Battery Pack
# 2.   Module
# 3.   Cell
# 4.   Raw Material
#
#

# %% id="xhocanr6Fqaj"
TIER_DISTRIBUTION = [0.05, 0.10, 0.20, 0.30, 0.35]

# %% [markdown] id="XVXR2vfdGp8Q"
# ## Country Distribution
#
# Simulating realistic EV supply chain hubs

# %% id="1YqbCboKG09s"
COUNTRY_WEIGHTS = {
    'CN': 0.45, # China dominates battery supply chain
    'KR': 0.15, # South Korea (LG, SK, Samsung)
    'JP': 0.10, # Japan (Panasonic)
    'DE': 0.10, # Germany (Auto tiers)
    'US': 0.10, # USA
    'XX': 0.10  # Rest of World
}

# %% [markdown] id="3PLKRz-3G9tH"
# # Generate Supplier Nodes
# Apply Power Law to create _Hub_ Suppliers
#
# - TODO Review Attributes: Why are tier category / risk & capacity needed?

# %% colab={"base_uri": "https://localhost:8080/", "height": 258} id="23I495KNHMX3" outputId="83da386f-7ee6-480b-bb88-e6d9a0023e27"
suppliers = []
countries = list(COUNTRY_WEIGHTS.keys())
weights = list(COUNTRY_WEIGHTS.values())

# We assign a 'capability_score' which determines how many materials they can supply
dominance_scores = np.random.zipf(a=1.5, size=NUM_SUPPLIERS)
# Normalize scores to a realistic capacity (max 50 materials per supplier for hubs)
dominance_scores = (dominance_scores / dominance_scores.max()) * 50
dominance_scores = np.maximum(dominance_scores, 1).astype(int)

for i in range(NUM_SUPPLIERS):
    country = random.choices(countries, weights=weights, k=1)[0]
    sup_id = f"SUP_{country}_{str(i+1).zfill(5)}"

    suppliers.append({
        "supplier_id": sup_id,
        "name": fake.company(),
        "country": country,
        "capacity_score": int(dominance_scores[i]) # Hidden attribute for graph generation logic
    })

df_suppliers = pd.DataFrame(suppliers)
df_suppliers.head()

# %% [markdown] id="LSJSk_O1LBiF"
# # Generate Material Nodes
# - REVIEW: What are current limitations with this approach?

# %% id="Ey_0TdeQLPga"
# Pre-define some semantic categories for realism
tier_names = {
    0: ["EV_Sedan", "EV_SUV", "EV_Truck"],
    1: ["Battery_Pack_HighRange", "Battery_Pack_Std", "Inverter_Assy", "Drive_Unit"],
    2: ["Module_LFP", "Module_NMC", "BMS_Circuit", "Cooling_Plate"],
    3: ["Cell_Prismatic", "Cell_Cylindrical_4680", "Cell_Pouch", "Anode_Sheet"],
    4: ["Lithium_Hydroxide", "Cobalt_Sulfate", "Nickel_Class1", "Graphite_Synth", "Copper_Foil"]
}

# %% colab={"base_uri": "https://localhost:8080/", "height": 206} id="0G7UgbkYLdTa" outputId="656ff1e5-825c-41e7-d460-4344cc5da0ae"
materials = []

for i in range(NUM_MATERIALS):
    tier = np.random.choice([0, 1, 2, 3, 4], p=TIER_DISTRIBUTION)

    # Semantic Naming
    base_name = random.choice(tier_names[tier])
    mat_id = f"MAT_T{tier}_{str(i+1).zfill(5)}"

    materials.append({
        "material_id": mat_id,
        "description": base_name,
        "tier_level": tier, # to be used for BOM hierarchy
        "base_unit": "EA" if tier < 4 else "KG",
        "cost_estimate": round(random.lognormvariate(3, 1) * (5 - tier), 2) # Higher tiers = more expensive
    })

df_materials = pd.DataFrame(materials)
df_materials.head()

# %% [markdown] id="j-sNDHadM0d-"
# # Generate BOM Edges
#
# Material -> Material
#
#
# - Includes "Nexus" Logic: We intentionally sample from a smaller subset of Tier 4 items to ensure multiple Tier 3s depend on the SAME Tier 4s (creating bottlenecks).
# ---
# * BOM Type seems redundant
# * should quantity be whole number?

# %% colab={"base_uri": "https://localhost:8080/", "height": 206} id="xcOSor_HNAqA" outputId="38b9bbdc-5344-4227-dcfb-680ad8c83d12"
bom_edges = []
# Group materials by tier for easy lookup
mats_by_tier = df_materials.groupby("tier_level")["material_id"].apply(list).to_dict()

# Logic: Iterate through Tiers 0 to 3 and assign children from Tier N+1
# We use a constrained random approach to ensure every item has children (except Raw Materials)
for tier in range(4): # 0, 1, 2, 3
    parents = mats_by_tier.get(tier, [])
    potential_children = mats_by_tier.get(tier+1, [])

    if not potential_children: continue

    for parent in parents:
        # Determine number of components (Fan-out)
        # Complex items (Tier 0) have many components; Raw parents (Tier 3) have few
        num_children = max(1, int(np.random.poisson(lam=4.0 - (tier * 0.5))))

        # Select children
        if tier == 3:
            # Heavily biased selection for Raw Materials to create dependency hubs
            children = np.random.choice(potential_children, size=num_children, replace=False)
        else:
            children = random.sample(potential_children, k=min(len(potential_children), num_children))

        for child in children:
            qty = round(random.uniform(1.0, 20.0), 2)
            if tier == 3: qty = round(random.uniform(0.5, 5.0), 3) # KG for raw materials

            bom_edges.append({
                "parent_material_id": parent,
                "child_material_id": child,
                "quantity": qty,
            })

df_bom = pd.DataFrame(bom_edges)
df_bom.head()

# %% [markdown] id="8ETJvEPtNy1a"
# # Generate Order Fulfillment Edges
#
# Supplier -> Material
#
# Merges Purchase Orders and Goods Receipt documents
#
# ---

# %% id="Yay1A7xIQaSf"
order_records = []
supplier_list = df_suppliers.to_dict('records')
material_list = df_materials.to_dict('records')

# %% [markdown] id="G_3yDb82N7jO"
# ## Assign _Approved Supplier List_ (ASL)
#
# Not every supplier supplies every part. We link them first.
#
# ### Logic
#
# * Higher tier items (Tier 0/1) usually have strategic partners (Tier 1 Suppliers)
# * Raw materials (Tier 4) are bought from Commodity suppliers
# * Pick candidate suppliers based on the 'capacity_score' we generated earlier
# * High capacity suppliers are more likely to be chosen (Preferential Attachment)

# %% id="6KBhiF_kQItk"
mat_supplier_map = {} # material_id -> list of possible supplier_ids

# Iterate materials and assign 1-3 suppliers each
for mat in material_list:
    candidates = random.choices(
        supplier_list,
        weights=[s['capacity_score'] for s in supplier_list],
        k=random.randint(1, 3) # Multi-sourcing
    )
    mat_supplier_map[mat['material_id']] = [s['supplier_id'] for s in candidates]

# %% [markdown] id="QjfBU0PTQzGn"
# ## Generate POs based on relationships
#
# Status is used to differentiate between historic data and current exposure.

# %% id="d8PwPzpPQ8v8"
current_po_count = 0
po_id_counter = 100000
current_date = date(2025, 10, 31)

while current_po_count < TARGET_PO_COUNT:
    # Pick a random material
    mat = random.choice(material_list)
    # Pick one of its valid suppliers
    valid_suppliers = mat_supplier_map[mat['material_id']]
    supplier_id = random.choice(valid_suppliers)

    # Generate Date
    po_date = fake.date_between(start_date=date(2024, 1, 1), end_date=date(2025, 12, 31))
    lead_time = random.randint(14, 90)
    due_date = po_date + timedelta(days=lead_time)

    # Pareto Volume: 20% of orders get 80% of volume
    is_bulk = random.random() < 0.20
    quantity_ordered = int(np.random.pareto(a=1.16) * 50) + 1 if is_bulk else random.randint(1, 100)

    if due_date > current_date: # Open order
        quantity_received = 0
        receipt_date = None
    else:
        fulfillment_status = np.random.choice(["Full", "Partial", "Missing"], p=[0.85, 0.10, 0.05])

        if fulfillment_status == "Full":
            quantity_received = quantity_ordered
            # Receipt happened -2 to +10 days around due date
            receipt_date = due_date + timedelta(days=random.randint(-2, 10))
        elif fulfillment_status == "Partial":
            quantity_received = int(quantity_ordered * random.uniform(0.1, 0.9))
            receipt_date = due_date + timedelta(days=random.randint(1, 15))
        else: # Missing
            quantity_received = 0
            receipt_date = None

    # Unit Price with some noise
    unit_price = mat['cost_estimate'] * random.uniform(0.95, 1.05)

    order_records.append({
        "po_id": f"PO-{po_id_counter}", # Unique line ID
        "supplier_id": supplier_id,
        "material_id": mat['material_id'],
        "order_date": po_date,
        "due_date": due_date,
        "receipt_date": receipt_date,
        "quantity_ordered": quantity_ordered,
        "quantity_received": quantity_received,
        "unit_price": round(unit_price, 2),
    })

    po_id_counter += 1
    current_po_count += 1

# %% colab={"base_uri": "https://localhost:8080/", "height": 226} id="1HGC134xRAjw" outputId="532d29c7-e5f4-4815-9429-b69c8ed88173"
df_po = pd.DataFrame(order_records)
df_po.head()

# %% [markdown] id="bBGHOhdZRUN3"
# # Export

# %% [markdown]
# Remove explicit columns used for edge generation.

# %%
df_suppliers = df_suppliers.drop(columns=['capacity_score'])
df_materials = df_materials.drop(columns=['cost_estimate', 'tier_level'])

# %% colab={"base_uri": "https://localhost:8080/"} id="wx79jTVDRhBd" outputId="3664da5f-aee8-4aa0-b7a0-219d0164a499"
parent_folder = "data-gen"
subfolder = "data"
os.makedirs(subfolder, exist_ok=True)
df_suppliers.to_csv(f"./{parent_folder}/{subfolder}/suppliers.csv", index=False)
df_materials.to_csv(f"./{parent_folder}/{subfolder}/materials.csv", index=False)
df_bom.to_csv(f"./{parent_folder}/{subfolder}/bom_relationships.csv", index=False)
df_po.to_csv(f"./{parent_folder}/{subfolder}/order_records.csv", index=False)

print("Done! Files generated:")
print(f" - suppliers.csv ({len(df_suppliers)} rows)")
print(f" - materials.csv ({len(df_materials)} rows)")
print(f" - bom_relationships.csv ({len(df_bom)} rows)")
print(f" - order_records.csv ({len(df_po)} rows)")
