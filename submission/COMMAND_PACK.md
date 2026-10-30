# Coal — demo command pack

Four prompts per profession. Every prompt is written to hit a real tool and
produce on-screen evidence. Paths are absolute so the agent cannot write
somewhere unexpected.

> Before recording: `demo.cmd` (or the desktop launcher) sets `COAL_NO_35B=1`
> and the Nebius endpoint. Approve prompts with `y`.

---

## 1. Chip designer — RTL that is proven, not described

**C1 · deterministic block (≈35 s)**
```
build a 4-bit binary to Gray code converter chip and verify it through the full gate
```
Shows `gray4: PASS` with lint / sim / synth / formal / PnR, area and timing.
(The block is binary→Gray: `gray = bin ^ (bin >> 1)`. Do not call it Gray→binary.)

**C2 · sequential design + floorplan (≈45 s)**
```
build an 8-bit up/down counter chip with load and verify it, then render the 2D floorplan
```
Shows `counter8: PASS`, then `chip_layout` drawing real nextpnr placement.

**C3 · composed chip + waveforms (≈50 s)**
```
build a UART loopback chip and verify it, then run the testbench and open the waveform in GTKWave
```
Shows `uart_loopback: PASS` (613 cells / 159 FF), the VCD PNG, and GTKWave
opening on the trace.

**C4 · different width, same gate (≈35 s)**
```
build a 12-bit up counter with synchronous reset and enable and verify it through the full gate
```
Shows the gate is general, not a single canned design.

---

## 2. Full-stack developer — real files, not snippets

**W1 · portfolio (≈40 s)**
```
Create a personal portfolio website in C:\Users\gamel\.coal\work\demo\portfolio using write_file: index.html, styles.css and app.js, with a dark/light theme toggle and smooth scrolling. Then list the directory to confirm.
```

**W2 · storefront (≈50 s)**
```
Create a storefront called Nile in C:\Users\gamel\.coal\work\demo\nile using write_file: live search, category filters, product cards with ratings, a slide-out cart with quantity update, and a mock checkout. Then list the directory to confirm.
```

**W3 · interactive 3D page (≈55 s)**
```
Create an interactive 3D page in C:\Users\gamel\.coal\work\demo\three3d using Three.js from a CDN: a rotating chip die, OrbitControls, a starfield, and scroll-driven camera movement. Then list the directory to confirm.
```

**W4 · code + execution + approval (≈30 s)**
```
Write and run a Python script that prints the first 20 Fibonacci numbers, then show me the output.
```
`write_file` and `run_command` both raise the inline approval prompt — press `y`.

---

## 3. Security analyst — defensive, on the user's own machine

**S1 · binary triage without execution (≈40 s)**
```
Analyze this binary without executing it: C:\Users\gamel\.coal\work\sec_test\target.exe — what is it, what strings stand out, and does it contain an unsafe pattern?
```
Shows `binary_triage`: sha256, PE sections + entropy, capability indicators,
and Intel disassembly naming `strcpy`. (Keep the words "analyze this binary"
so the security toolset is exposed.)

**S2 · static review (≈30 s)**
```
Run a static security review of C:\Users\gamel\.coal\work\sec_test and report findings with file:line.
```
Shows a real finding: `target.c:10 [high] unsafe_c_string (strcpy)`.

**S3 · web vulnerability method (≈30 s, no tools needed)**
```
I own this web app. Explain how to test it for SQL injection safely, and what to fix.
```
Uses `security_method` / `security_kb`; answer is authorisation-first.

**S4 · assembly-level reasoning (≈30 s)**
```
Explain how a stack buffer overflow works at the x86-64 assembly level and how to defend against it.
```

---

## 4. 3D / technical artist — generated geometry and imagery

**T1 · 3D package from a verified chip (safest)**
```
build a UART loopback chip, then generate its 3D package and tell me the GLB path
```
`chip_views` writes `package.glb`, `.obj`, `.fbx`, `.png` from the real design.

**T2 · render / validate the model**
```
Validate the GLB for that chip and convert it to OBJ.
```
`validate_3d`, `convert_3d`.

**T3 · generate a standalone 3D model**
```
Generate a 3D model of a chip package and export it as GLB in C:\Users\gamel\.coal\work\demo\3d.
```
`generate_3d` (needs a 3D backend; if unavailable it reports that instead of pretending).

**T4 · generated image**
```
Generate an HD image of a futuristic silicon die and tell me the output path.
```
`generate_hd_image` (falls back to procedural output when no image model is installed).

> If Blender is not installed, record T1/T2 (the chip's own GLB/OBJ) — they are
> produced by the chip flow and always work. T3/T4 are optional.

---

## Suggested recording order (fits 3:00)

| Time | Prompt | Evidence on screen |
|---|---|---|
| 0:00–0:12 | — | Title card: “Anyone can make a model write Verilog. Coal proves it.” |
| 0:12–0:47 | C1 | `PASS` across five stages, area + Fmax |
| 0:47–1:12 | C2 | 2D floorplan with named core regions |
| 1:12–1:37 | C3 | waveform PNG + GTKWave window |
| 1:37–1:57 | S1 | binary triage + disassembly |
| 1:57–2:17 | W2 | three files written, directory listed |
| 2:17–2:37 | W4 | approval prompt, press `y`, output |
| 2:37–2:50 | — | results slide: 44/50, UART 135.9 MHz, honest limits |
| 2:50–3:00 | — | links: repo, live page, model choice |

Do not read slides over tool output — let the PASS lines and the waveform
carry the claim. Voiceover should name what the gate checked, not adjectives.
