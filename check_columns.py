import sys
sys.path.insert(0, '.')
import pandas as pd

df = pd.read_csv('data/raw/ted_awards_2023.csv', nrows=2, low_memory=False)

cpv_cols = [c for c in df.columns if 'CPV' in c.upper() or 'LABEL' in c.upper()]
print('CPV-related columns:', cpv_cols)

dt_cols = [c for c in df.columns if 'DT' in c.upper() or 'DATE' in c.upper()]
print('Date columns:', dt_cols)

print()
print('Sample values:')
for col in cpv_cols + dt_cols:
    print(f'  {col}: {df[col].tolist()}')