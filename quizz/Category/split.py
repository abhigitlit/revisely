import json
import os

def split_json_file(input_file, output_dir, num_parts):
    # Load the JSON file
    with open(input_file, 'r', encoding='utf-8') as f:
        questions = json.load(f)
    
    total_questions = len(questions)
    questions_per_part = total_questions // num_parts
    remainder = total_questions % num_parts
    
    # Ensure the output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    base_filename = os.path.splitext(os.path.basename(input_file))[0]
    
    start = 0
    for i in range(num_parts):
        end = start + questions_per_part + (1 if i < remainder else 0)  # Distribute remainder evenly
        part_questions = questions[start:end]
        output_file = os.path.join(output_dir, f'{base_filename}_part_{i+1}.json')
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(part_questions, f, indent=4, ensure_ascii=False)
        
        start = end
    
    print(f"Split {total_questions} questions into {num_parts} files in '{output_dir}'")

if __name__ == "__main__":
    input_dir = '.'  # Directory to search for JSON files
    
    json_files = [f for f in os.listdir(input_dir) if f.endswith('.json')]
    
    for json_file in json_files:
        user_input = input(f"Do you want to process {json_file}? (yes/no): ").strip().lower()
        if user_input == 'yes':
            num_parts = int(input(f"Enter the number of parts for {json_file}: "))
            output_dir = os.path.join('output_questions', os.path.splitext(json_file)[0])
            split_json_file(json_file, output_dir, num_parts)
