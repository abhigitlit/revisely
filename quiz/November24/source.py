import os
import json

def list_quiz_files(directory):
    """
    Recursively list all JSON files in the given directory.
    Returns a list of file paths.
    """
    quiz_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(".json"):
                quiz_files.append(os.path.join(root, file))
    return quiz_files

def update_source_in_file(file_path, new_source):
    """
    Reads a JSON quiz file, updates the "source" field to new_source for every question,
    and writes the changes back to the file.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            quiz_data = json.load(f)
        modified = False
        for question in quiz_data:
            # Update the source field regardless of whether it exists.
            if question.get("source") != new_source:
                question["source"] = new_source
                modified = True

        if modified:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(quiz_data, f, indent=4)
            print(f"✅ Updated source in: {file_path}")
        else:
            print(f"ℹ️  No update needed for: {file_path} (source already set to '{new_source}')")
    except Exception as e:
        print(f"❌ Error processing {file_path}: {e}")

def main():
    # Ask user for the quiz directory (default is "quiz")
    directory = input("Enter quiz directory path (default 'quiz'): ").strip() or "quiz"
    if not os.path.exists(directory):
        print("The specified directory does not exist.")
        return

    # List all JSON quiz files
    files = list_quiz_files(directory)
    if not files:
        print("No quiz files found in the directory.")
        return

    print("\nFound the following quiz files:")
    for idx, file_path in enumerate(files, start=1):
        print(f"{idx}: {file_path}")

    # Ask user which file(s) to update.
    selection = input(
        "\nEnter the file numbers separated by commas (e.g., 1,3,5) or type 'all' to update all files: "
    ).strip().lower()

    if selection == "all":
        selected_files = files
    else:
        try:
            indices = [int(x.strip()) for x in selection.split(",")]
            # Validate indices and convert them to file paths.
            selected_files = [files[i - 1] for i in indices if 1 <= i <= len(files)]
            if not selected_files:
                print("No valid file numbers were selected.")
                return
        except ValueError:
            print("Invalid input. Please enter valid numbers separated by commas or 'all'.")
            return

    # Ask user for the new source value.
    new_source = input("Enter the new source value to set for the quiz questions: ").strip()
    if not new_source:
        print("No source value entered. Aborting update.")
        return

    # Update each selected file.
    for file_path in selected_files:
        update_source_in_file(file_path, new_source)

if __name__ == "__main__":
    main()