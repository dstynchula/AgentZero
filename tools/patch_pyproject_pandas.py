from pathlib import Path

path = Path("pyproject.toml")
text = path.read_text(encoding="utf-8")
if "pandas" not in text:
    text = text.replace('"mutmut>=2.4",', '"mutmut>=2.4",\n    "pandas>=2.0",')
if "beautifulsoup4" not in text:
    text = text.replace('"pandas>=2.0",', '"pandas>=2.0",\n    "beautifulsoup4>=4.12",')
    path.write_text(text, encoding="utf-8")
    print("added pandas to dev deps")
else:
    print("pandas already present")
