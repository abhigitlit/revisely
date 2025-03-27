import os
import json
import random
import shutil
import tkinter as tk
from tkinter import filedialog, simpledialog

def select_directory():
    """Opens a dialog for the user to select a directory."""
    root = tk.Tk()
    root.withdraw()  # Hide the main tkinter window
    folder_selected = filedialog.askdirectory(title="Select a Quiz Directory")
    return folder_selected

def get_quiz_files(directory):
    """Returns a list of JSON quiz file paths in the given directory."""
    return [os.path.join(directory, f) for f in os.listdir(directory) if f.endswith(".json")]

def load_quizzes(file_path):
    """Loads quiz data from a JSON file."""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_quizzes(file_path, quizzes):
    """Saves quiz data to a JSON file."""
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(quizzes, f, indent=4, ensure_ascii=False)

def balance_quiz_files(directory, target_question_count):
    """Ensures all JSON files in a selected directory have the specified number of quizzes."""
    quiz_files = get_quiz_files(directory)
    if not quiz_files:
        print("No JSON quiz files found. Creating a new file.")
        quiz_files.append(os.path.join(directory, "quiz_1.json"))
        save_quizzes(quiz_files[0], [])
    
    # Load all quizzes
    all_quizzes = {file: load_quizzes(file) for file in quiz_files}
    
    # Create a pool of all questions
    question_pool = [q for quizzes in all_quizzes.values() for q in quizzes]
    
    for file, quizzes in all_quizzes.items():
        while len(quizzes) < target_question_count:
            if question_pool:
                quizzes.append(random.choice(question_pool))
            else:
                print("Not enough questions available to balance all files.")
                break
        
        save_quizzes(file, quizzes)
        print(f"Updated {file} to have {target_question_count} questions.")
    
    # If more files are needed, create new ones
    file_index = len(quiz_files) + 1
    while len(question_pool) > 0:
        new_file = os.path.join(directory, f"quiz_{file_index}.json")
        new_quizzes = [question_pool.pop() for _ in range(min(target_question_count, len(question_pool)))]
        save_quizzes(new_file, new_quizzes)
        print(f"Created {new_file} with {len(new_quizzes)} questions.")
        file_index += 1

# 🔹 Ask user to select a directory
selected_directory = select_directory()

# 🔹 Ask user for the number of questions per file
if selected_directory:
    root = tk.Tk()
    root.withdraw()
    target_question_count = simpledialog.askinteger("Input", "Enter the number of questions per file:", minvalue=1)
    if target_question_count:
        balance_quiz_files(selected_directory, target_question_count)
    else:
        print("Invalid input. Exiting.")
else:
    print("No directory selected. Exiting.")