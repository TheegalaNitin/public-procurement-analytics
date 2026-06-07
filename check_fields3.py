import sys
sys.path.insert(0, '.')
import pandas as pd

df = pd.read_csv('data/raw/ted_awards_2023.csv', nrows=3, low_memory=False)

# Look for the four fields we need
keywords = {
    'procedure': ['TYPE_OF', 'PROC', 'TOP_TYPE'],
    'bidders': ['OFFER', 'TENDER', 'NUMBER'],
    'framework': ['FRA', 'FRAMEWORK'],
    'gpa': ['GPA'],
}

for need, kws in keywords.items():
    print(f"\n=== {need.upper()} ===")
    for col in df.columns:
        if any(kw in col.upper() for kw in kws):
            print(f"  {col}: {df[col].tolist()}")