import os
import json

def get_quiz_files(directory):
    """Returns a list of JSON quiz file paths in the given directory."""
    return [f for f in os.listdir(directory) if f.endswith(".json")]

def count_questions_in_file(file_path):
    """Counts the number of quiz questions in a JSON file."""
    with open(file_path, "r", encoding="utf-8") as f:
        quizzes = json.load(f)
        return len(quizzes)

def select_file_cli(directory):
    """Allows the user to select a file from the directory via CLI."""
    quiz_files = get_quiz_files(directory)
    if not quiz_files:
        print("No JSON quiz files found.")
        return None
    
    print("Available quiz files:")
    for idx, file in enumerate(quiz_files, start=1):
        print(f"{idx}. {file} ({count_questions_in_file(os.path.join(directory, file))} questions)")
    
    choice = int(input("Enter the number of the file you want to select: ")) - 1
    if 0 <= choice < len(quiz_files):
        return os.path.join(directory, quiz_files[choice])
    else:
        print("Invalid choice.")
        return None

directory = input("Enter the path of the quiz directory: ")
if os.path.isdir(directory):
    selected_file = select_file_cli(directory)
    if selected_file:
        print(f"You selected: {selected_file} ({count_questions_in_file(selected_file)} questions)")
else:
    print("Invalid directory.")