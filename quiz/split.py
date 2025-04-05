import json
import os

def split_json(data, num_parts):
    """Generically split JSON data into num_parts parts."""
    if isinstance(data, list):
        # Split list evenly
        total_items = len(data)
        items_per_part = total_items // num_parts
        remainder = total_items % num_parts

        parts = []
        start = 0
        for i in range(num_parts):
            end = start + items_per_part + (1 if i < remainder else 0)
            parts.append(data[start:end])
            start = end
        return parts

    elif isinstance(data, dict):
        # Split dictionary keys across parts
        keys = list(data.keys())
        total_keys = len(keys)
        keys_per_part = total_keys // num_parts
        remainder = total_keys % num_parts

        parts = [{} for _ in range(num_parts)]
        start = 0
        for i in range(num_parts):
            end = start + keys_per_part + (1 if i < remainder else 0)
            for key in keys[start:end]:
                parts[i][key] = data[key]
            start = end
        return parts

    else:
        # Cannot split non-list/non-dict JSON
        print("Error: Unsupported JSON format. Only lists and dictionaries can be split.")
        return None

def split_json_file(input_file, output_dir, num_parts):
    """Loads a JSON file, splits it, and saves it in parts."""
    with open(input_file, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            print(f"Error: {input_file} is not a valid JSON file.")
            return

    if num_parts <= 0:
        print("Error: Number of parts must be greater than 0.")
        return

    split_data = split_json(data, num_parts)
    if split_data is None:
        return

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    base_filename = os.path.splitext(os.path.basename(input_file))[0]

    for i, part in enumerate(split_data):
        output_file = os.path.join(output_dir, f'{base_filename}_part_{i+1}.json')
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(part, f, indent=4, ensure_ascii=False)

    print(f"Successfully split '{input_file}' into {num_parts} parts in '{output_dir}'.")

def select_directory(start_dir="."):
    """Allows user to navigate directories and select a JSON file."""
    current_dir = start_dir

    while True:
        print(f"\nCurrent Directory: {current_dir}")
        items = os.listdir(current_dir)
        
        directories = [d for d in items if os.path.isdir(os.path.join(current_dir, d))]
        json_files = [f for f in items if f.endswith('.json')]

        print("\nSelect a directory or JSON file:")
        for i, directory in enumerate(directories):
            print(f"  [{i}] 📂 {directory}")
        for j, json_file in enumerate(json_files, start=len(directories)):
            print(f"  [{j}] 📄 {json_file}")
        
        print("  [b] 🔙 Go Back")
        print("  [q] ❌ Quit")

        choice = input("Enter your choice: ").strip().lower()

        if choice == "q":
            print("Exiting...")
            return None
        elif choice == "b":
            if current_dir == start_dir:
                print("You're already at the root directory.")
            else:
                current_dir = os.path.dirname(current_dir)  # Move up one directory
        elif choice.isdigit():
            index = int(choice)
            if index < len(directories):
                current_dir = os.path.join(current_dir, directories[index])  # Move into subdirectory
            elif index < len(directories) + len(json_files):
                return os.path.join(current_dir, json_files[index - len(directories)])  # Return selected JSON file
            else:
                print("Invalid selection. Try again.")
        else:
            print("Invalid input. Try again.")

if __name__ == "__main__":
    print("Welcome to the JSON Splitter!")

    while True:
        selected_file = select_directory()
        if selected_file is None:
            break

        while True:
            try:
                num_parts = int(input(f"Enter the number of parts for {selected_file}: "))
                if num_parts > 0:
                    break
                else:
                    print("Number of parts must be greater than 0.")
            except ValueError:
                print("Invalid input. Please enter a valid integer.")

        output_dir = os.path.join('output_json', os.path.splitext(os.path.basename(selected_file))[0])
        split_json_file(selected_file, output_dir, num_parts)