import sys
sys.path.insert(0, ".")
from coal import Coal

r = Coal(session_name="demo")
for u in ["hey, my name is WERU and I build industrial robot arms "
          "with NEMA 23 motors",
          "what motors do I use on my robot arm?"]:
    print("you:", u)
    ans, meta = r.respond(u, on_token=lambda t: None)
    print(f"coal [{meta['kind']}, {len(meta['tools'])} tools, "
          f"{meta['ms']:.0f}ms]: {ans[:250]}")
    print()
print("memory:", r.mem.store.stats())
print("personality:", r.personality.describe())
r.close()
