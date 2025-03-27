import json
import os
from colorama import Fore, Style, init

init(autoreset=True)

path = '.'
file = []
label = [
    'Appointment',
    'Awards',
    'Banking',
    'Index and ranking',
    'Economy',
    'Science and Tech',
    'Defence',
    'International',
    'General',
    'MoU',
    'National',
    'Inauguration',
    'Sports',
    'Book and art'
]
def trace(path):
    global file
    list = os.listdir(path)
    directory = [i for i in list if os.path.isdir(os.path.join(path, i))]
    tmpfile = [i for i in list if i.endswith('.json')]

    for each in tmpfile:
        
        # Extract the filename without the extension and check if it's in the label list
        if os.path.splitext(each)[0] not in label:
            full_path = os.path.join(path, each)
            file.append(full_path)
        else:
            print(f"⚠️ Ignoring file '{each}' as it matches a label name.")

    if not directory:
        return
    for i in directory:
        trace(os.path.join(path, i))


def save_to_label_files(question_data, selected_labels):
    for lbl in selected_labels:
        label_file = f"{lbl}.json"

        # Load existing data or initialize an empty list
        data = []
        if os.path.exists(label_file):
            try:
                with open(label_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except json.JSONDecodeError:
                print(f"{Fore.RED}Error reading '{label_file}'. Skipping append and starting fresh.{Style.RESET_ALL}")

        # Append the new question data
        data.append(question_data)

        # Save the updated data back to the file
        with open(label_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)

        print(f"{Fore.GREEN}Appended to '{label_file}' successfully!{Style.RESET_ALL}")


def main():
    trace(path)
    print("Found quiz files:", file)

    # Write CSV header initially
    with open('dataset.csv', 'w', encoding='utf-8') as csv:
        csv.write("Question,Labels\n")

    for each_file in file:
        print(f"\nProcessing file: {each_file}")
        
        # Ask if the user wants to skip this file
        skip_choice = input(f"{Fore.YELLOW}Do you want to skip this file? (yes/no): {Style.RESET_ALL}").strip().lower()
        if skip_choice in ["yes", "y"]:
            print(f"{Fore.CYAN}Skipping {each_file}...{Style.RESET_ALL}")
            continue  # Skip to the next file

        try:
            with open(each_file, 'r', encoding='utf-8') as ofile:
                quiz_data = json.load(ofile)
        except json.JSONDecodeError:
            print(f"{Fore.RED}Error reading {each_file}. Skipping this file.{Style.RESET_ALL}")
            continue

        with open('dataset.csv', 'a', encoding='utf-8') as csv:  # Append mode to avoid overwriting
            for i, q in enumerate(quiz_data, start=1):
                print(f"{Fore.LIGHTMAGENTA_EX}\nQuestion {i}: {q['question']}{Style.RESET_ALL}")
                print(f"Options: {', '.join(q['options'])}")
                print(f"Answer: {q['answer']}")
                print(f"{Fore.LIGHTBLACK_EX}Which labels do you want to set? (Enter comma-separated indices or '0' for custom label){Style.RESET_ALL}")

                # Display label options with index
                for idx, lbl in enumerate(label, start=1):
                    print(f"{idx}. {lbl}")
                print("0. Add Custom Label")

                try:
                    user_input = input("Enter your choice(s): ").strip()
                    if not user_input:  # If no input, skip to the next question
                        print(f"{Fore.YELLOW}No input provided. Skipping this question.{Style.RESET_ALL}")
                        continue

                    selected_indices = [int(choice.strip()) for choice in user_input.split(',') if choice.strip().isdigit()]

                    # Handle custom label input
                    if 0 in selected_indices:
                        custom_label = input("Enter a new custom label: ").strip()
                        if custom_label and custom_label not in label:
                            label.append(custom_label)
                            print(f"{Fore.GREEN}Custom label '{custom_label}' added!{Style.RESET_ALL}")

                        selected_indices = [idx for idx in selected_indices if idx != 0] + [len(label)]  # Include custom label index

                    # Validate label indices
                    selected_labels = [label[idx - 1] for idx in selected_indices if 1 <= idx <= len(label)]

                    if selected_labels:
                        # Write question and selected labels to CSV
                        csv.write(f"{q['question']}|{','.join(selected_labels)}\n")

                        # Save to label JSON files (append mode)
                        question_data = {
                            "question": q['question'],
                            "options": q['options'],
                            "answer": q['answer']
                        }
                        save_to_label_files(question_data, selected_labels)
                    else:
                        print(f"{Fore.RED}No valid labels selected. Moving to the next question.{Style.RESET_ALL}")

                except ValueError:
                    print(f"{Fore.RED}Invalid input! Please enter valid comma-separated numbers.{Style.RESET_ALL}")

    print(f"{Fore.CYAN}All files processed successfully!{Style.RESET_ALL}")


if __name__ == "__main__":
    main()