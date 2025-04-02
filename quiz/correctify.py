import json
import os
from colorama import init, Fore, Style

# Initialize Colorama for colored output
init(autoreset=True)

def list_directory(path):
    """List directories and JSON files in the given path."""
    items = os.listdir(path)
    dirs = sorted([item for item in items if os.path.isdir(os.path.join(path, item))])
    json_files = sorted([item for item in items if os.path.isfile(os.path.join(path, item)) and item.lower().endswith(".json")])
    return dirs, json_files

def navigate_directory():
    """Allow user to navigate directories and select a JSON file."""
    current_path = os.path.abspath(".")
    
    while True:
        print(f"\n{Fore.CYAN}Current Directory: {current_path}{Style.RESET_ALL}")
        dirs, json_files = list_directory(current_path)
        
        # Build list of options to display
        options = {}
        idx = 1
        
        if current_path != os.path.abspath(os.sep):
            print(f"  0. {Fore.YELLOW}Go Back{Style.RESET_ALL}")
            options[0] = "back"
        
        for d in dirs:
            print(f"  {idx}. {Fore.BLUE}[DIR]{Style.RESET_ALL} {d}")
            options[idx] = os.path.join(current_path, d)
            idx += 1
        
        for f in json_files:
            print(f"  {idx}. {Fore.MAGENTA}[JSON]{Style.RESET_ALL} {f}")
            options[idx] = os.path.join(current_path, f)
            idx += 1

        try:
            choice = int(input("\nSelect a directory or JSON file by number: "))
        except ValueError:
            print("Invalid input. Please enter a number.")
            continue

        if choice not in options:
            print("Invalid selection. Try again.")
            continue

        selected = options[choice]
        if selected == "back":
            parent = os.path.dirname(current_path)
            if parent == current_path:
                print("Already at the root directory.")
            else:
                current_path = parent
        elif os.path.isdir(selected):
            current_path = selected
        elif os.path.isfile(selected) and selected.lower().endswith(".json"):
            return selected

def load_questions(file_path):
    """Load questions from a JSON file."""
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)

def save_questions(file_path, questions):
    """Save questions to a JSON file."""
    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(questions, file, indent=4, ensure_ascii=False)

def get_valid_answer(num_options):
    """Prompt the user until a valid option number is provided."""
    while True:
        try:
            answer = int(input("Enter the correct option number: "))
            if 1 <= answer <= num_options:
                return answer
            else:
                print(f"Please enter a number between 1 and {num_options}.")
        except ValueError:
            print("Invalid input. Please enter a number.")

def update_questions(file_path):
    """Load and update questions in the JSON file interactively, saving answer text."""
    try:
        questions = load_questions(file_path)
    except Exception as e:
        print(f"Error reading JSON file: {e}")
        return

    for index, question in enumerate(questions):
        q_text = question.get("question", "No question text available")
        options = question.get("options", [])
        print(f"\n{Fore.CYAN}Question {index + 1}: {q_text}{Style.RESET_ALL}")
        
        if not options:
            print("No options found for this question. Skipping...")
            continue

        for i, option in enumerate(options):
            print(f"  {Fore.MAGENTA}{i + 1}. {option}{Style.RESET_ALL}")

        existing_answer = question.get("answer")
        if existing_answer:
            print(f"{Fore.GREEN}Current answer: \"{existing_answer}\" is set.{Style.RESET_ALL}")
        else:
            print("No answer set yet.")

        user_choice = get_valid_answer(len(options))
        chosen_text = options[user_choice - 1]
        if existing_answer and chosen_text == existing_answer:
            print(f"{Fore.GREEN}The answer is already correct.{Style.RESET_ALL}")
        elif existing_answer and chosen_text != existing_answer:
            print(f"{Fore.YELLOW}Answer changed from \"{existing_answer}\" to \"{chosen_text}\".{Style.RESET_ALL}")
            question["answer"] = chosen_text
        else:
            print(f"{Fore.YELLOW}Answer set to \"{chosen_text}\".{Style.RESET_ALL}")
            question["answer"] = chosen_text

    try:
        save_questions(file_path, questions)
        print(f"\n{Fore.CYAN}All answers have been updated in the JSON file: {file_path}{Style.RESET_ALL}")
    except Exception as e:
        print(f"Error saving JSON file: {e}")

def main():
    print(f"{Fore.CYAN}Welcome to the JSON Question Editor!{Style.RESET_ALL}")
    selected_file = navigate_directory()
    print(f"\nSelected JSON file: {Fore.YELLOW}{selected_file}{Style.RESET_ALL}")
    update_questions(selected_file)

if __name__ == "__main__":
    main()
