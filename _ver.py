p = r'C:\Users\A\Documents\Codex\auto-clicker\outputs\auto_clicker.py'
c = open(p, 'r', encoding='utf-8').read()
c = c.replace('APP_VERSION = "v25"', 'APP_VERSION = "v26"')
open(p, 'w', encoding='utf-8').write(c)
print('Version updated to v26')
