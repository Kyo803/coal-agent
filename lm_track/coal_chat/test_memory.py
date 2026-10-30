"""Phase D gate: persistent memory must survive a new session.

Tests:
  1. Write turns + facts in session 1
  2. Close, reopen (simulated new session)
  3. Recall a specific fact from session 1 by query
  4. Fact extraction from natural user text
  5. Consolidation produces a summary + profile
  6. Memory tools execute (search/remember/forget)

Exit 0 = gate passed.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

FAILS = []


def check(name, cond, info=""):
    print(f"  [{'OK ' if cond else 'FAIL'}] {name} {info}")
    if not cond:
        FAILS.append(name)


def main():
    print("PHASE D GATE: persistent memory\n")
    root = tempfile.mkdtemp(prefix="coal_mem_")
    from memory import Memory

    # --- session 1 ---
    print("== session 1 (write) ==")
    m1 = Memory(root)
    m1.add_turn("user", "Hi, my name is WERU and I am building an "
                        "industrial robot arm")
    m1.add_turn("assistant", "Nice to meet you, WERU.")
    m1.add_turn("user", "my dog is named Biscuit and I use NEMA 23 "
                        "stepper motors")
    m1.add_turn("user", "I like embedded systems and I hate flaky firmware")
    m1.consolidate()
    stats1 = m1.store.stats()
    print(f"  stats after s1: {stats1}")
    check("messages_stored", stats1["messages"] >= 4, str(stats1))
    check("facts_extracted", stats1["facts"] >= 3, str(stats1["facts"]))
    m1.store.close()

    # --- session 2 (new session, same disk) ---
    print("== session 2 (recall) ==")
    m2 = Memory(root)
    check("new_session_id", m2.session_id != m1.session_id)
    ctx = m2.assemble("what is my dog's name?")
    text = ctx["text"]
    check("recall_dog", "Biscuit" in text, "fact surfaced")
    check("recall_profile", "WERU" in text, "profile surfaced")
    ctx2 = m2.assemble("what motors am I using?")
    check("recall_motors", "NEMA 23" in ctx2["text"] or
          "nema 23" in ctx2["text"].lower())
    ctx3 = m2.assemble("what do I like and dislike?")
    t3 = ctx3["text"].lower()
    check("recall_prefs", "embedded" in t3 and "firmware" in t3)

    # --- tools ---
    print("== memory tools ==")
    from memory.tools import MemoryTools, format_tool_results
    mt = MemoryTools(m2)
    cleaned, res = mt.parse_and_run(
        "Sure. <|tools|>search_memory: dog<|tools|> Here you go.")
    check("tool_search", len(res) == 1 and "Biscuit" in res[0][2])
    _, r2 = mt.parse_and_run(
        "<|tools|>remember: robot arm uses CAN bus<|tools|>")
    check("tool_remember", "stored" in r2[0][2])
    check("tool_cleaned", "<|tools|>" not in cleaned)

    # --- persistence across a THIRD reopen ---
    print("== session 3 (re-recall) ==")
    m2.store.close()
    m3 = Memory(root)
    ctx4 = m3.assemble("what is my dog's name?")
    check("persist_third_open", "Biscuit" in ctx4["text"])

    print()
    if FAILS:
        print(f"GATE FAILED: {FAILS}")
        return 1
    print("GATE PASSED: persistent memory works across sessions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
