import sys
import time

sys.path.insert(0, ".")
from eval import (gen_arithmetic, gen_memory, gen_fact_extraction,
                  run_arithmetic, run_memory, run_fact_extraction)

for n in (200, 1000):
    t0 = time.time()
    r = run_memory(gen_memory(n))
    dt = time.time() - t0
    print(f"memory n={n}: acc={r['acc']} {dt:.1f}s ({dt/n*1000:.0f}ms/case)")

t0 = time.time()
r = run_fact_extraction(gen_fact_extraction(2000))
print(f"facts n=2000: acc={r['acc']} {time.time()-t0:.1f}s")

t0 = time.time()
r = run_arithmetic(gen_arithmetic(50000))
print(f"arith n=50000: acc={r['acc']} {time.time()-t0:.1f}s")
