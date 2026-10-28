from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8790/"
P = 0
F = 0


def chk(name, cond, detail=""):
    global P, F
    if cond:
        P += 1
        print(f"  [ok] {name}")
    else:
        F += 1
        print(f"  [FAIL] {name} {detail}")


with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page(viewport={"width": 1400, "height": 850})
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("dialog", lambda d: d.accept("testgroup"))
    pg.goto(URL, wait_until="networkidle", timeout=30000)
    pg.wait_for_timeout(1800)

    cards = pg.eval_on_selector_all(".card", "e=>e.length")
    chk("cards render", cards >= 3, f"cards={cards}")
    chk("no console errors", not errs, errs[:2])

    # --- ctrl+click multi-select ---
    pg.locator(".card").nth(0).click(force=True)
    pg.locator(".card").nth(1).click(force=True, modifiers=["Control"])
    sel = pg.eval_on_selector_all(".card.sel", "e=>e.length")
    chk("ctrl+click multi-select", sel == 2, f"selected={sel}")
    info = pg.inner_text("#selinfo")
    chk("selection info", "2 selected" in info.lower(), info)

    # --- align left on the two selected ---
    pg.click('[data-al="l"]')
    pg.wait_for_timeout(200)
    lefts = pg.eval_on_selector_all(".card.sel", "els=>els.map(e=>e.style.left)")
    chk("align-left equalizes x", len(set(lefts)) == 1, lefts)

    # --- group move: record a selected card pos, drag it, expect move ---
    before = pg.eval_on_selector(".card.sel", "e=>e.style.left")
    box = pg.eval_on_selector(".card.sel", "e=>{const r=e.getBoundingClientRect();return {x:r.x+40,y:r.y+20}}")
    pg.mouse.move(box["x"], box["y"])
    pg.mouse.down()
    pg.mouse.move(box["x"] + 120, box["y"] + 60, steps=6)
    pg.mouse.up()
    pg.wait_for_timeout(200)
    after = pg.eval_on_selector(".card.sel", "e=>e.style.left")
    chk("drag moves card", before != after, f"{before} -> {after}")

    # --- marquee select ---
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(100)
    pg.mouse.move(30, 200)
    pg.mouse.down()
    pg.mouse.move(900, 700, steps=8)
    pg.mouse.up()
    pg.wait_for_timeout(200)
    msel = pg.eval_on_selector_all(".card.sel", "e=>e.length")
    chk("marquee selects cards", msel >= 1, f"selected={msel}")

    # --- add note via double-click empty area ---
    pg.keyboard.press("Escape")
    notes_before = pg.eval_on_selector_all(".note", "e=>e.length")
    pg.mouse.dblclick(200, 780)
    pg.wait_for_timeout(200)
    notes_after = pg.eval_on_selector_all(".note", "e=>e.length")
    chk("double-click adds note", notes_after == notes_before + 1,
        f"{notes_before}->{notes_after}")

    # --- group box from selection ---
    pg.locator(".card").nth(0).click(force=True)
    pg.locator(".card").nth(1).click(force=True, modifiers=["Control"])
    pg.click("#grp")
    pg.wait_for_timeout(200)
    gboxes = pg.eval_on_selector_all(".groupbox", "e=>e.length")
    chk("group box created", gboxes >= 1, f"groups={gboxes}")

    # --- zoom ---
    z0 = pg.eval_on_selector("#world", "e=>e.style.transform")
    pg.mouse.move(700, 400)
    pg.mouse.wheel(0, -400)
    pg.wait_for_timeout(150)
    z1 = pg.eval_on_selector("#world", "e=>e.style.transform")
    chk("wheel zooms", z0 != z1, f"{z0} -> {z1}")

    # --- persistence across reload ---
    pos_before = pg.eval_on_selector(".card", "e=>Math.round(parseFloat(e.style.left))")
    notes_now = pg.eval_on_selector_all(".note", "e=>e.length")
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(1800)
    pos_after = pg.eval_on_selector(".card", "e=>Math.round(parseFloat(e.style.left))")
    notes_reload = pg.eval_on_selector_all(".note", "e=>e.length")
    chk("positions persist across reload", pos_before == pos_after,
        f"{pos_before} vs {pos_after}")
    chk("notes persist across reload", notes_reload == notes_now,
        f"{notes_now} vs {notes_reload}")

    print("console errors:", errs[:3])
    pg.screenshot(path=r"C:\Users\WERU1\.rox\board_ui.png")
    b.close()

print(f"{P} passed, {F} failed")
