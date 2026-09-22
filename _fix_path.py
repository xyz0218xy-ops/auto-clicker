# -*- coding: utf-8 -*-
"""Fix MACRO_SCRIPTS_PATH ordering."""

PATH = r"C:\Users\A\Documents\Codex\auto-clicker\outputs\auto_clicker.py"

with open(PATH, "r", encoding="utf-8") as f:
    c = f.read()

# Remove MACRO_SCRIPTS_PATH from its current position
old = 'MACRO_SCRIPTS_NAME = "macro_scripts.json"\nMACRO_SCRIPTS_PATH = os.path.join(APP_DIR, MACRO_SCRIPTS_NAME)\n'
new_old = 'MACRO_SCRIPTS_NAME = "macro_scripts.json"\n'
assert old in c, "Cannot find old MACRO_SCRIPTS_PATH block"
c = c.replace(old, new_old, 1)
print("Removed old MACRO_SCRIPTS_PATH")

# Add it after CONFIG_PATH is defined
anchor = 'CONFIG_PATH = choose_config_path()\n'
assert anchor in c, "Cannot find CONFIG_PATH anchor"
c = c.replace(anchor, anchor + 'MACRO_SCRIPTS_PATH = os.path.join(APP_DIR, MACRO_SCRIPTS_NAME)\n', 1)
print("Added MACRO_SCRIPTS_PATH after APP_DIR")

# Verify
assert 'MACRO_SCRIPTS_PATH = os.path.join(APP_DIR' in c
# Make sure it comes AFTER APP_DIR definition
lines = c.split('\n')
app_dir_line = 0
macro_path_line = 0
for i, line in enumerate(lines):
    if 'APP_DIR = get_app_dir()' in line:
        app_dir_line = i
    if 'MACRO_SCRIPTS_PATH = os.path.join(APP_DIR' in line:
        macro_path_line = i
assert macro_path_line > app_dir_line, f"Order wrong: APP_DIR at {app_dir_line}, MACRO_SCRIPTS_PATH at {macro_path_line}"
print(f"Order verified: APP_DIR line {app_dir_line}, MACRO_SCRIPTS_PATH line {macro_path_line}")

import py_compile, tempfile, os
tmp = tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding="utf-8")
tmp.write(c)
tmp.close()
py_compile.compile(tmp.name, doraise=True)
os.unlink(tmp.name)
print("Syntax OK")

with open(PATH, "w", encoding="utf-8") as f:
    f.write(c)
print("Saved!")
