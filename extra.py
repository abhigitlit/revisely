import json

# File paths
input_json_path = "./january.json"  # Your input JSON file
output_json_path = "./january2.json"   # Output JSON file after cleaning

# Load JSON data
with open(input_json_path, "r", encoding="utf-8") as file:
    data = json.load(file)

# Remove \n from questions
for item in data:
    item["question"] = item["question"].replace("\n", "").strip()

# Save cleaned data
with open(output_json_path, "w", encoding="utf-8") as file:
    json.dump(data, file, indent=4, ensure_ascii=False)

print(f"\n✅ Cleaned JSON saved to {output_json_path}")
