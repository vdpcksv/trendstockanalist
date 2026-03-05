import os
import glob
import re

replacements = [
    # text colors
    (r'(?<!dark:)text-white', r'text-slate-900 dark:text-white'),
    (r'(?<!dark:)text-slate-300', r'text-slate-600 dark:text-slate-300'),
    (r'(?<!dark:)text-slate-400', r'text-slate-500 dark:text-slate-400'),
    (r'(?<!dark:)text-indigo-300', r'text-indigo-600 dark:text-indigo-300'),
    (r'(?<!dark:)text-indigo-400', r'text-indigo-600 dark:text-indigo-400'),
    (r'(?<!dark:)text-emerald-400', r'text-emerald-600 dark:text-emerald-400'),
    (r'(?<!dark:)text-rose-400', r'text-rose-600 dark:text-rose-400'),
    (r'(?<!dark:)text-amber-400', r'text-amber-600 dark:text-amber-400'),
    (r'(?<!dark:)text-blue-400', r'text-blue-600 dark:text-blue-400'),
    (r'(?<!dark:)text-purple-400', r'text-purple-600 dark:text-purple-400'),
    
    # bg colors
    (r'(?<!dark:)bg-\[\#0B1021\]', r'bg-slate-50 dark:bg-[#0B1021]'),
    (r'(?<!dark:)bg-\[\#151b30\]', r'bg-white dark:bg-[#151b30]'),
    (r'(?<!dark:)bg-\[\#12182B\]', r'bg-slate-100 dark:bg-[#12182B]'),
    (r'(?<!dark:)bg-slate-800(\/\d+)?', r'bg-slate-200\1 dark:bg-slate-800\1'),
    (r'(?<!dark:)bg-slate-700(\/\d+)?', r'bg-slate-300\1 dark:bg-slate-700\1'),
    
    # borders
    (r'(?<!dark:)border-slate-800(\/\d+)?', r'border-slate-300\1 dark:border-slate-800\1'),
    (r'(?<!dark:)border-slate-700(\/\d+)?', r'border-slate-300\1 dark:border-slate-700\1'),
    (r'(?<!dark:)border-indigo-500(\/\d+)?', r'border-indigo-300\1 dark:border-indigo-500\1'),
]

templates_dir = "templates"
for filepath in glob.glob(os.path.join(templates_dir, "*.html")):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Optional: we can skip base.html's CSS block if needed, but the regex only matches specific classes usually in class="..." attributes.
    original_content = content
    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content)
        
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {filepath}")
        
    # Also fix some specific ones that might be doubled
    # If the file had manually added dark classes earlier, this might double them.
    # We used negative lookbehind (?<!dark:) to prevent doubling!
print("Done!")
