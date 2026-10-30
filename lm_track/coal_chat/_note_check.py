from playwright.sync_api import sync_playwright

P = F = 0


def chk(n, c, d=""):
    global P, F
    if c:
        P += 1
        print(f"  [ok] {n}")
    else:
        F += 1
        print(f"  [FAIL] {n} {d}")


with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 1400, "height": 850})
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.goto("http://127.0.0.1:8790/", wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(1500)

    # create a note
    pg.mouse.dblclick(250, 760)
    pg.wait_for_timeout(200)
    chk("note created", pg.eval_on_selector_all(".note", "e=>e.length") == 1)

    # edit it
    pg.dblclick(".note")
    pg.wait_for_timeout(200)
    editable = pg.eval_on_selector(".note", "e=>e.isContentEditable")
    chk("note is editable", editable)

    # select all + type
    pg.keyboard.press("Control+A")
    pg.keyboard.type("buy more red string")
    pg.wait_for_timeout(300)
    txt = pg.inner_text(".note")
    chk("typing works", "buy more red string" in txt, txt)

    # wait past the 15s auto-refresh; the note must NOT be wiped
    pg.wait_for_timeout(17000)
    still = pg.eval_on_selector_all(".note", "e=>e.length")
    txt2 = pg.inner_text(".note") if still else ""
    editing2 = pg.eval_on_selector(".note", "e=>e.isContentEditable") if still else False
    chk("note survives auto-refresh", still == 1, f"notes={still}")
    chk("typed text survives refresh", "buy more red string" in txt2, txt2)
    chk("still editable after refresh", editing2)

    # keep typing after the refresh
    pg.keyboard.type(" now")
    pg.wait_for_timeout(200)
    chk("can keep typing after refresh", "now" in pg.inner_text(".note"))

    # blur + reload -> persisted
    pg.mouse.click(1200, 120)
    pg.wait_for_timeout(300)
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(1800)
    final = pg.inner_text(".note") if pg.eval_on_selector_all(".note", "e=>e.length") else ""
    chk("text persisted across reload", "buy more red string" in final, final)

    print("errors:", errs[:3])
    b.close()
print(f"{P} passed, {F} failed")
