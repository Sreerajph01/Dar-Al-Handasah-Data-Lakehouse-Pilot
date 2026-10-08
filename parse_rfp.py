import pandas as pd
import yaml
import sys
import os

df = pd.read_excel('docs/source/RFP_tooling.xlsx')
reqs = []
for index, row in df.iterrows():
    if pd.notna(row.get('Nb')):
        nb_val = row['Nb']
        if isinstance(nb_val, float) and nb_val.is_integer():
            nb_str = str(int(nb_val))
        else:
            nb_str = str(nb_val).split('.')[0] if isinstance(nb_val, float) else str(nb_val)
        
        reqs.append({
            'Nb': nb_str,
            'Requirement': str(row.get('Requirement', '')).strip()
        })

os.makedirs('docs/rfp', exist_ok=True)
with open('docs/rfp/requirements.yaml', 'w') as f:
    yaml.dump(reqs, f, sort_keys=False, default_flow_style=False)

print(f"Parsed {len(reqs)} requirements into docs/rfp/requirements.yaml")
