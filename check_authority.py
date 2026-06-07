import sys
sys.path.insert(0, '.')
import pandas as pd

df = pd.read_csv('data/raw/ted_awards_2023.csv', low_memory=False)
bremen = df[df["TAL_LOCATION_NUTS"].fillna("").str.startswith("DE50")]

print("=== CAE_TYPE values (authority type) ===")
print(bremen["CAE_TYPE"].value_counts(dropna=False))

print("\n=== Sample buyer names per CAE_TYPE ===")
for t in bremen["CAE_TYPE"].dropna().unique()[:8]:
    sample = bremen[bremen["CAE_TYPE"] == t]["CAE_NAME"].dropna().head(2).tolist()
    print(f"\n{t}:")
    for s in sample:
        print(f"   {s[:60]}")