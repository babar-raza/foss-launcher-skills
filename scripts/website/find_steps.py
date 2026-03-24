import os

def check_steps_in_file(file_path):
    """Check if a file contains matching {{% steps %}} and {{% /steps %}} tags."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Count occurrences of {{% steps %}} and {{% /steps %}} tags
    steps_start = content.count("{{% steps %}}")
    steps_end = content.count("{{% /steps %}}")
    
    # If the count of start and end tags doesn't match, it's an issue
    if steps_start != steps_end:
        return True  # Return True if there's a mismatch
    return False

def scan_directory_for_mismatched_steps(directory):
    """Scan all .md files in the directory recursively and find files with mismatched tags."""
    files_with_issues = []

    # Walk through the directory
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".md"):  # Only process .md files
                file_path = os.path.join(root, file)
                if check_steps_in_file(file_path):
                    files_with_issues.append(file_path)

    return files_with_issues

def main():
    directory = input("Enter the directory path to scan: ")  # Prompt user for directory path
    files_with_issues = scan_directory_for_mismatched_steps(directory)

    if files_with_issues:
        print("The following files have mismatched {{% steps %}} and {{% /steps %}} tags:")
        for file in files_with_issues:
            print(file)
    else:
        print("All files have matching {{% steps %}} and {{% /steps %}} tags.")

if __name__ == "__main__":
    main()
