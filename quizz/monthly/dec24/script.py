import json
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

filename = "march.json"

# Load the questions from the JSON file
with open(filename, "r", encoding="utf-8") as f:
    questions = json.load(f)

# Iterate through each question one-by-one
for i, q in enumerate(questions, start=1):
    print(f"{Fore.MAGENTA}\nQuestion {i}: {q['question']}{Style.RESET_ALL}")

    for idx, option in enumerate(q["options"], start=1):
        print(f"  {Fore.MAGENTA}{idx}. {option}{Style.RESET_ALL}")

    while True:
        try:
            user_input = int(input(f"{Fore.WHITE}Enter the correct option number (1-{len(q['options'])}) for this question: {Style.RESET_ALL}").strip())
            if 1 <= user_input <= len(q["options"]):
                selected_option = q["options"][user_input - 1]

                if selected_option == q['answer']:
                    print(f"{Fore.GREEN}Answer is correct already!{Style.RESET_ALL}")
                else:
                    q['answer'] = selected_option
                    print(f"{Fore.YELLOW}Answer updated to: {q['answer']}{Style.RESET_ALL}")
                break
            else:
                print(f"{Fore.RED}Please enter a valid option number between 1 and {len(q['options'])}.{Style.RESET_ALL}")
        except ValueError:
            print(f"{Fore.RED}Invalid input. Please enter a valid integer.{Style.RESET_ALL}")

# Write the updated questions back to the file
with open(filename, "w", encoding="utf-8") as f:
    json.dump(questions, f, indent=2, ensure_ascii=False)
print(f"{Fore.GREEN}\nAll updates completed successfully!{Style.RESET_ALL}")