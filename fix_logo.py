import os, shutil
base = r'C:\Users\Yash Srivastava\OneDrive\Desktop\data-sage-frontend'

# 1. Fix favicon
src_logo = os.path.join(base, 'src', 'assets', 'logo.png')
dest_favicon = os.path.join(base, 'public', 'favicon.png')
if os.path.exists(src_logo):
    shutil.copyfile(src_logo, dest_favicon)
    print("Copied logo to favicon.png")
else:
    print("Source logo.png not found")

# 2. Fix LandingPage.tsx
fpath = os.path.join(base, 'src', 'pages', 'LandingPage.tsx')
if not os.path.exists(fpath):
    fpath = os.path.join(base, 'src', 'LandingPage.tsx')

with open(fpath, 'r', encoding='utf-8') as f:
    content = f.read()

target = """<a href="#top" className="flex items-center gap-2 font-semibold tracking-tight text-foreground">
          <Logo />
          <span>Magic Excel</span>
        </a>"""

replacement = """<a href="#top" className="flex items-center gap-2 font-semibold tracking-tight text-foreground">
          {/* Logo kept on the left */}
        </a>"""

if target in content:
    content = content.replace(target, replacement)
    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Updated LandingPage.tsx successfully.")
else:
    print("Target string not found in LandingPage.tsx")
