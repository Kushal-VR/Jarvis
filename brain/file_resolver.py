# brain/file_resolver.py

"""
File Resolver

Fixes incorrect filenames using fuzzy matching.
Example:
"readmeand.py" → "main.py"
"""

import os
import difflib


def get_all_files(base_path="."):
    """
    Get all files recursively
    """
    file_list = []

    for root, dirs, files in os.walk(base_path):
        for file in files:
            file_list.append(file.lower())

    return file_list


def find_best_match(target, files):
    """
    Find closest matching filename
    """
    matches = difflib.get_close_matches(target.lower(), files, n=1, cutoff=0.5)

    return matches[0] if matches else None


def resolve_filename(raw_name: str, base_path="."):
    """
    Try to correct filename using fuzzy match
    """

    files = get_all_files(base_path)

    best_match = find_best_match(raw_name, files)

    return best_match if best_match else raw_name