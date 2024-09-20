import os
from workbook_rewriter import process_workbook

current_directory = os.path.dirname(os.path.abspath(__file__))

max_lesson = 3

for lesson in range(1, max_lesson):
    json_data = process_workbook(lesson, current_directory)
    print()

    output_path = f"/lesson{lesson}/les{lesson}a-autogenerated.md"

    f = open(current_directory+output_path, "w")
    f.write(json_data)
    f.close()
