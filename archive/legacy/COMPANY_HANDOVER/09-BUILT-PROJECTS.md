# 09 — BUILT PROJECTS (Desktop\Coal Projects\)

These are the projects Coal built **autonomously** (see `01-HOW-IT-WAS-BUILT.md`
§6). Two fully verified; two written but not verify-passing (the documented
35B model ceiling). Plus the two earlier test projects. Per-file notes included.

---

## ✅ `modern-portfolio` — Portfolio website (Vite + React + TS + Tailwind)

**Status:** `npm run build` passes (tsc + vite, 37 modules). Renders in
Chromium: title "Modern Portfolio", nav, hero/about/projects/contact, no JS
errors.

| File | Role |
|------|------|
| `package.json` | Scripts `build` = `tsc && vite build`; react/react-dom + TS/Tailwind/vite deps. |
| `vite.config.ts` | Vite + react plugin config. |
| `tsconfig.json` / `tsconfig.node.json` | TS config (unused-symbol checks disabled — deliberate, see `02-…`). |
| `tailwind.config.js`, `postcss.config.js` | Tailwind wiring. |
| `index.html` | Vite entry, `#root`, title. |
| `src/main.tsx` | React root render. |
| `src/App.tsx` | Layout + theme context + section composition. |
| `src/components/Header.tsx` | Nav + dark-mode toggle. |
| `src/components/Hero.tsx` | Hero section. |
| `src/components/About.tsx` | About section. |
| `src/components/Projects.tsx` | Projects grid. |
| `src/components/Contact.tsx` | Contact section. |
| `src/components/Footer.tsx` | Footer. |
| `src/index.css` | Tailwind entry + base styles. |
| `dist/` | Build output (index.html + css + js). |

## ✅ `arcade-frontend` — Game arcade (5 games, Vite + React + TS + Tailwind)

**Status:** `npm run build` passes (1510 modules). Renders "Neon Arcade" menu,
no console errors. Games: Snake, Tetris, Pong, Memory Match, 2048.

| File | Role |
|------|------|
| `src/App.tsx` | Game state machine + menu↔game switching. |
| `src/components/GameMenu.tsx` | Game selection menu (lists Snake, Tetris, Pong, Memory, 2048). |
| `src/components/GameContainer.tsx` | Shared game shell (score, restart, back). |
| `src/games/SnakeGame.tsx` | Snake. |
| `src/games/TetrisGame.tsx` | Tetris. |
| `src/games/PongGame.tsx` | Pong (player vs AI). |
| `src/games/MemoryGame.tsx` | Memory match. |
| config + build files | Same Vite+TS+Tailwind stack as the portfolio. |
| `dist/` | Build output. |

> **Note:** the menu advertises a fifth game (2048), but the 2048 game
> component does not exist in the final tree — a known gap from the build
> churn. The four implemented games are Snake, Tetris, Pong, Memory.

## ✅ `cli-calc` — Python CLI calculator (builder smoke test)

**Status:** `pytest` 5/5 pass; CLI works (`add/subtract/multiply/divide`).

| File | Role |
|------|------|
| `calculator.py` | The calculator CLI. |
| `test_calculator.py` | pytest suite (5 tests). |
| `requirements.txt` | Deps. |
| `README.md` | Usage. |

## ✅ `task-manager` — Task manager CLI (earlier coding test)

**Status:** working CLI with persistence; 4 cascading interface bugs found +
fixed via the repair loop (the origin of the verify-driven repair design).

| File | Role |
|------|------|
| `models.py` | Data model. |
| `storage.py` | Persistence (`tasks.json`). |
| `service.py` | Business logic. |
| `cli.py` | CLI. |
| `main.py` | Entry point. |
| `tasks.json` | Data file. |

## ✅ `4bit-verilog-cpu` — 4-bit CPU in Verilog (VERIFIED)

**Status:** `iverilog` compiles clean; `vvp` runs the testbench → **PASS:
(5 + 3) − 2 = 6**, R0 = 6 after 8 cycles; `waveform.vcd` produced. The ISA,
program, and assembler are mutually consistent (`python assembler.py` regenerates
`program.hex`, which `cpu_top.v` loads via `$readmemh`).

| File | Role |
|------|------|
| `alu_4bit.v` | 4-bit ALU: add/sub/and/xor + zero/carry flags. |
| `register_file.v` | 4×4 register file: dual combinational read, synchronous write, always-on `reg0`. |
| `memory.v` | 4×4 data memory (sync write, combinational read), preloaded with constants (5, 3, 2). |
| `cpu_top.v` | CPU: 3-bit PC + 8×8 instruction ROM (program.hex) + decoder + RF + ALU + data memory. Single-cycle. |
| `testbench.v` | Clocks the CPU until HALT, checks R0 == 6, prints PASS/FAIL, dumps VCD. |
| `assembler.py` | Small correct assembler: `program.asm` → `program.hex` (pads to 8 words). |
| `program.asm` | Sample program `(5+3)-2 = 6` (LOAD/ADD/SUB/STORE/HALT). |
| `Makefile` | `make sim` (note: `make` is not on this Windows box — use iverilog directly). |

ISA (8-bit instruction, 4-bit data): `MOV/ADD/SUB/AND/XOR Rd,Rs` (0x0–0x4),
`LDI Rd,imm2` (0x5), `STORE Rs,addr2` (0x6), `LOAD Rd,addr2` (0x7),
`JMP` (0x8), `JZ Rd,addr3` (0x9), `HALT` (0xF). See `cpu_top.v` header.

## ✅ `typescript-raytracer` — Ray tracer (TS → PNG) (VERIFIED)

**Status:** `tsc` builds clean; `npm start` (`node dist/main.js`) renders an
**800×600 shaded scene** with three spheres (red, blue, reflective gold) + a
ground plane, Phong lighting + shadows + recursive reflections, and writes
`output.png` (78 KB, 306+ distinct colors on a sampled grid). Verified with
PIL (dimensions, pixel colors, color variance).

| File | Role |
|------|------|
| `src/types.ts` | `Ray`, `Material`, `Hit`, `Object3D`, `Light`, `Camera`, `Scene`, `HitRecord`. |
| `src/vector3.ts` | Immutable `Vector3` math class (add/sub/mul/dot/cross/normalize). |
| `src/utils.ts` | `clamp`, `colorToRGB`, `debugLog` helpers. |
| `src/objects.ts` | `Sphere` + `Plane` primitives (`intersect`). |
| `src/scene.ts` | `createDefaultScene()` — camera, light, materials, objects. |
| `src/lighting.ts` | `traceRay` (recursive reflections) + `findNearest` + Phong shading + shadow rays. |
| `src/raytracer.ts` | `RayTracer.render(scene, w, h)` → `Uint8ClampedArray` RGBA (camera basis + per-pixel rays). |
| `src/main.ts` | Entry: build scene, render, write `output.png` via pngjs. |
| `package.json` | `build` = `tsc`, `start` = `node dist/main.js`; deps `pngjs` + `@types/pngjs`. |
| `tsconfig.json` | strict ES2020/commonjs → `dist/`. |

> Note: `src/index.ts` was removed (was a stale duplicate of `main.ts`); the
> entry is `main.ts`.

---

## How to reproduce these builds

```powershell
cd "...\coal_chat"
python coal.py --say "build a complete project: <prompt>"
# long-running: run detached via a .bat launcher; then:
python coal.py --say "finish <name>" --finish <project-name>
```

The builder's full capabilities and limitations are documented in
`01-HOW-IT-WAS-BUILT.md §6` and `02-ARCHITECTURE.md §7`.

---

_End of handover. Start with `00-READ-ME-FIRST.md`._