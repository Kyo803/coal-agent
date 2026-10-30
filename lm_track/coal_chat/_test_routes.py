from tools.exec import lazy_schemas
from tools.permissions import Permissions
from tools.specs import categories_for_trigger

CASES = [
    (r"Create a small website directly in C:\Users\gamel\.coal\work\web_test"
     r"\store2 using write_file: index.html, styles.css, app.js "
     r"(a click counter).", "write_file"),
    (r"Create an Amazon-like storefront called Nile with a cart directly in "
     r"C:\x\store", "write_file"),
    ("build a 4-bit gray to binary converter chip", "chip_build"),
    ("explain XSS and how to prevent it", "security_kb"),
]

for text, wanted in CASES:
    cats = sorted(categories_for_trigger(text))
    names = [s["function"]["name"]
             for s in lazy_schemas(text, Permissions())]
    print(f"{text[:58]:60s} cats={cats}")
    print(f"{'':60s} n={len(names)} {wanted}={wanted in names} "
          f"write_file={'write_file' in names}")
