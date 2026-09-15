import zipfile
from pathlib import Path

numbers_file = Path(r"C:\Users\bokka\Downloads\Clean_Dataset.numbers")
output_file = Path("Clean_Dataset_raw.txt")

with zipfile.ZipFile(numbers_file, "r") as z:
    with output_file.open("w", encoding="utf-8", errors="ignore") as out:
        for name in z.namelist():
            if "DataList" in name or "CalculationEngine" in name:
                data = z.read(name)
                out.write(f"\n\n===== {name} =====\n")
                out.write(data.decode("utf-8", errors="ignore"))

print("EXTRACTION COMPLETE")
print("Created:", output_file)
print("Size:", output_file.stat().st_size, "bytes")