import json
import re
import urllib.request
from datetime import date

# Most common generic medicine names in the public FDA drug label database
URL = "https://api.fda.gov/drug/label.json?count=openfda.generic_name.exact&limit=1000"

# Same medicine, different names in the US and elsewhere (general knowledge,
# not FDA data)
ALIASES = {
    "acetaminophen": "paracetamol",
    "calcipotriene": "calcipotriol",
    "albuterol": "salbutamol",
    "epinephrine": "adrenaline",
}

# Salt words are removed from the END of a name only
SALT_WORDS = {
    "hydrochloride", "sodium", "potassium", "calcium", "acetate", "sulfate",
    "phosphate", "maleate", "tartrate", "citrate", "succinate", "mesylate",
    "besylate", "fumarate", "furoate", "propionate", "dipropionate",
    "valerate", "nitrate", "hydrobromide",
}


def base_name(name):
    # "terbinafine hydrochloride" -> "terbinafine"
    # "sodium thiosulfate" stays as it is, because the salt word is not last
    words = name.split()
    while len(words) > 1 and words[-1] in SALT_WORDS:
        words.pop()
    return " ".join(words)


with urllib.request.urlopen(URL, timeout=60) as response:
    data = json.load(response)

names = set()
for item in data["results"]:
    full = item["term"].lower().strip()
    # keep single-ingredient names only: skip combinations, numbers, brackets
    if re.search(r"\band\b|,|/|\d|\(", full):
        continue
    # keep both the full name and the name without its trailing salt word
    for name in (full, base_name(full)):
        if len(name) >= 5:
            names.add(name)

for us_name, other_name in ALIASES.items():
    if us_name in names:
        names.add(other_name)

drugs = sorted(names)
json.dump(drugs, open("data/drug_list.json", "w", encoding="utf-8"), indent=1)

info = {
    "name": "FDA-derived generic medication vocabulary",
    "source": URL,
    "retrieved": str(date.today()),
    "count": len(drugs),
    "notes": [
        "Most common single-ingredient generic names from US drug labels (openFDA).",
        "Not a complete drug database, and not validated for clinical decisions.",
        "Aliases (US vs international names) are general knowledge, not FDA data.",
        "Used only to suggest spellings to a human reviewer.",
    ],
}
json.dump(info, open("data/drug_list_info.json", "w", encoding="utf-8"), indent=2)

print("Saved", len(drugs), "names to data/drug_list.json")
print("First 30:", drugs[:30])