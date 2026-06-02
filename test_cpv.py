import sys
sys.path.insert(0, '.')
from pipeline.extract.ted_csv import get_cpv_label

print("Testing CPV label lookup:")
print(f"  45214210 -> '{get_cpv_label('45214210')}'")
print(f"  85000000 -> '{get_cpv_label('85000000')}'")
print(f"  72230000 -> '{get_cpv_label('72230000')}'")
print(f"  90910000 -> '{get_cpv_label('90910000')}'")