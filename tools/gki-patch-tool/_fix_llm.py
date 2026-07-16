"""Clean up duplicate code blocks in llm_service.py"""
import re

filepath = r'e:\qoder\gkiPatchTool\web_app\llm_service.py'
with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find all occurrences of the hybrid approach header
header_indices = []
for i, line in enumerate(lines):
    if 'Main crash analysis' in line and 'hybrid' in line:
        header_indices.append(i)

print(f"Found {len(header_indices)} header occurrences at lines: {[i+1 for i in header_indices]}")

if len(header_indices) == 2:
    first = header_indices[0]
    second = header_indices[1]
    print(f"Removing lines {first+1} to {second} (keeping second occurrence)")
    new_lines = lines[:first] + lines[second:]
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print(f"Done. File now has {len(new_lines)} lines.")
else:
    print("Unexpected number of headers, not modifying.")
