"""Language packs: curated, accurate references ROX N learns from so it
can write modern stacks (TypeScript, Tailwind, React, Vite, Verilog).

Structure:  ~/.rox/langpacks/<tech>/*.md
`install_curated()` writes the built-in cheatsheets (fast, offline).
ROX N can then extend them by browsing official docs and running
`ingest_docs` / `ingest_langpack`.

  from langpacks import install_curated, list_packs, pack_dir
  install_curated()          # write all curated cheatsheets
"""
from __future__ import annotations

import os

from rox_config import cfg


def root():
    return os.path.expanduser(
        cfg.get("langpacks", {}).get("root", "~/.rox/langpacks"))


def pack_dir(tech):
    p = os.path.join(root(), tech)
    os.makedirs(p, exist_ok=True)
    return p


def list_packs():
    r = root()
    if not os.path.isdir(r):
        return []
    return sorted(d for d in os.listdir(r)
                  if os.path.isdir(os.path.join(r, d)))


# ---------------------------------------------------------------------------
# Curated cheatsheets (kept tight + accurate; the model retrieves these)
# ---------------------------------------------------------------------------
CHEATSHEETS = {
    "typescript/cheatsheet.md": """# TypeScript cheatsheet

## tsconfig.json (Vite + React, modern)
{
  "compilerOptions": {
    "target": "ES2022", "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext", "moduleResolution": "Bundler",
    "jsx": "react-jsx", "strict": true, "noUnusedLocals": true,
    "noUnusedParameters": true, "noEmit": true, "skipLibCheck": true,
    "esModuleInterop": true, "resolveJsonModule": true,
    "isolatedModules": true, "forceConsistentCasingInFileNames": true
  },
  "include": ["src"]
}

## Types
- `let n: number = 1; const s: string = "x"; const b: boolean = true;`
- Arrays: `number[]` or `Array<number>`.
- Tuples: `[string, number]`.
- Union: `string | number`. Literal union: `"a" | "b"`.
- Optional: `{ name?: string }`. Nullable: `string | null`.
- `unknown` (safe) vs `any` (avoid). Narrow with `typeof`/`instanceof`/`in`.

## Interfaces vs types
- interface Foo { x: number; y?: string }
- type Point = { x: number; y: number };
- Extend: `interface B extends A {}`; intersection `type C = A & B`.

## Functions
- `function add(a: number, b: number): number { return a + b; }`
- Arrow: `const add = (a: number, b: number): number => a + b;`
- Optional param `b?: number`; default `b: number = 0`.
- Rest: `(...nums: number[]) => number`.

## Generics
- `function first<T>(arr: T[]): T | undefined { return arr[0]; }`
- Constraints: `<T extends { id: number }>`.
- Generic component: `function List<T>({ items }: { items: T[] }) {...}`

## React-common types
- `React.FC` (avoid); prefer explicit props type: `type Props = { title: string }`.
- Events: `React.ChangeEvent<HTMLInputElement>`,
  `React.MouseEvent<HTMLButtonElement>`, `React.FormEvent`.
- Refs: `useRef<HTMLDivElement>(null)`.
- `useState<number>(0)`, `useState<string[]>([])`.
- Children: `{ children: React.ReactNode }`.

## Utility types
- Partial<T>, Required<T>, Readonly<T>, Pick<T,K>, Omit<T,K>,
  Record<K,V>, ReturnType<F>, Awaited<P>.

## Enums / const objects
- Prefer `const STATUS = { ON: "on", OFF: "off" } as const;`
- `type Status = typeof STATUS[keyof typeof STATUS];`

## Common errors
- "Object is possibly 'undefined'" -> guard or use `?.` / `!`.
- "Type X is not assignable to Y" -> align the shape / widen the type.
- "Cannot find module 'X'" -> `npm i X` + `@types/X` if needed.
- "implicitly has an 'any' type" -> annotate the parameter.
""",
    "tailwind/cheatsheet.md": """# Tailwind CSS cheatsheet (v3 utility-first)

## Setup (Vite)
- `npm i -D tailwindcss postcss autoprefixer` then `npx tailwindcss init -p`.
- tailwind.config.js:
  module.exports = { content: ["./index.html","./src/**/*.{ts,tsx}"],
    theme: { extend: {} }, plugins: [] };
- src/index.css (top):
  @tailwind base;
  @tailwind components;
  @tailwind utilities;

## Layout
- flex: `flex items-center justify-between gap-4`
- grid: `grid grid-cols-3 gap-6 md:grid-cols-2`
- container: `mx-auto max-w-7xl px-4`
- position: `relative absolute inset-0 top-0 z-10`

## Spacing / size
- padding `p-4 px-6 py-2`, margin `m-2 mx-auto mt-8`
- width/height `w-full h-screen max-w-md min-h-[60vh]`
- space between children `space-y-4` / `space-x-2`

## Typography
- `text-sm/base/lg/xl/2xl/4xl font-bold font-medium`
- color `text-slate-700 text-white`; align `text-center`
- leading/tracking `leading-relaxed tracking-tight`

## Color / background
- `bg-white bg-slate-900 bg-blue-600/80` (opacity slash)
- gradient `bg-gradient-to-r from-indigo-500 to-purple-600`
- border `border border-gray-200 rounded-lg rounded-full shadow-md`

## States / responsive / dark
- hover/focus/active: `hover:bg-blue-700 focus:ring-2`
- responsive prefixes: `sm: md: lg: xl: 2xl:`
- dark mode: enable `darkMode: "class"` then `dark:bg-slate-900`
- group/peer: `group` + `group-hover:opacity-100`

## Common recipes
- Card: `rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-900/5`
- Button: `inline-flex items-center rounded-lg bg-indigo-600 px-4 py-2
  text-white font-medium hover:bg-indigo-500`
- Nav: `sticky top-0 backdrop-blur bg-white/70 border-b`
- Hero: `min-h-screen flex flex-col items-center justify-center text-center`
- Use `@apply` for repeated component classes inside a `@layer components`.
""",
    "react/cheatsheet.md": """# React cheatsheet (18+, function components + hooks)

## Component
- `export function Card({ title }: { title: string }) { return <div>{title}</div>; }`
- Props with children: `{ children }: { children: React.ReactNode }`
- One component per file; default-export the component.

## Hooks
- State: `const [n, setN] = useState<number>(0);`
  update: `setN(n + 1)` or `setN(prev => prev + 1)`.
- Effect: `useEffect(() => { const id = setInterval(...); return () => clearInterval(id); }, []);`
  deps `[]` = once; `[x]` = when x changes.
- Ref: `const ref = useRef<HTMLCanvasElement>(null);`
- Memo: `const v = useMemo(() => expensive(a), [a]);`
  Callback: `const fn = useCallback(() => {...}, [deps]);`
- Context: `const Ctx = createContext<T>(init);` + `useContext(Ctx)`.

## Events & forms
- `onClick={() => setOpen(o => !o)}`
- input: `onChange={(e: React.ChangeEvent<HTMLInputElement>) => setV(e.target.value)}`
- form: `onSubmit={(e: React.FormEvent) => { e.preventDefault(); ... }}`
- controlled: `value={v} onChange={...}`

## Lists & conditional
- `{items.map((it) => <li key={it.id}>{it.title}</li>)}`
- `{loading ? <Spinner/> : <List items={items}/>}`
- `{count > 0 && <Badge>{count}</Badge>}`

## Patterns
- Lift state up; keep data fetching in effects or a hook.
- Custom hook: `function useLocalStorage<T>(k: string, init: T) {...}`
- Avoid stale closures: use functional setState and correct deps.

## Canvas game in React
- `const ref = useRef<HTMLCanvasElement>(null);`
- `useEffect(() => { const ctx = ref.current!.getContext("2d")!;
  let raf = 0; const loop = () => { /* draw */ raf = requestAnimationFrame(loop); };
  loop(); return () => cancelAnimationFrame(raf); }, []);`
- `<canvas ref={ref} width={400} height={400} />`
- Keyboard: `useEffect(() => { const h = (e: KeyboardEvent) => {...};
  window.addEventListener("keydown", h);
  return () => window.removeEventListener("keydown", h); }, []);`

## Rules
- Hooks only at the top level (not in loops/conditions).
- Never mutate state directly; return new objects/arrays.
""",
    "vite/cheatsheet.md": """# Vite cheatsheet

## Create / structure
- `npm create vite@latest myapp -- --template react-ts`
- Project: index.html (root), src/main.tsx, src/App.tsx, vite.config.ts,
  tsconfig.json, package.json.
- index.html must have `<div id="root"></div>` and
  `<script type="module" src="/src/main.tsx"></script>`.

## main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><App /></React.StrictMode>);

## vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({ plugins: [react()] });

## package.json scripts
"dev": "vite", "build": "tsc -b && vite build", "preview": "vite preview"

## Deps (react-ts + tailwind)
npm i react react-dom
npm i -D typescript vite @vitejs/plugin-react @types/react @types/react-dom
npm i -D tailwindcss postcss autoprefixer

## Build output
- `npm run build` -> dist/. `npm run preview` serves it.
- Env vars: prefix with VITE_ and read `import.meta.env.VITE_X`.

## Gotchas
- Import CSS in main.tsx.
- Assets in `public/` are served at `/`; imports in `src/assets` get hashed.
""",
    "verilog/cheatsheet.md": """# Verilog cheatsheet (RTL, Icarus Verilog compatible)

## Module
module alu(input [3:0] a, b, input [1:0] op, output reg [3:0] y,
           output zero, carry);
  always @(*) begin
    case (op)
      2'b00: {carry, y} = a + b;
      2'b01: {carry, y} = a - b;
      2'b10: y = a & b;
      2'b11: y = a ^ b;
    endcase
  end
  assign zero = (y == 4'b0000);
endmodule

## Nets vs regs
- `wire` for continuous assignments (`assign`); `reg` for procedural
  (`always`). In always @(*) use `reg` (or `logic` in SystemVerilog).
- Widths: `[3:0]` = 4 bits. Concatenate `{a,b}`, replicate `{4{a}}`.

## Sequential logic
always @(posedge clk) begin
  if (reset) q <= 4'b0000;
  else       q <= d;
end
- Use non-blocking `<=` in sequential blocks; blocking `=` in comb blocks.

## Parameters / reuse
parameter W = 4;
module regfile #(parameter W=4) (...);

## Testbench (Icarus Verilog)
`timescale 1ns/1ps
module tb;
  reg clk = 0, reset = 1;
  reg [3:0] a = 0, b = 0; reg [1:0] op = 0;
  wire [3:0] y; wire zero, carry;
  alu uut(.a(a), .b(b), .op(op), .y(y), .zero(zero), .carry(carry));
  always #5 clk = ~clk;
  initial begin
    $dumpfile("wave.vcd"); $dumpvars(0, tb);
    #10 reset = 0;
    a = 4'd3; b = 4'd5; op = 2'b00; #10;
    $display("3+5 = %0d carry=%b", y, carry);
    if (y !== 4'd8) $display("FAIL add");
    $finish;
  end
endmodule

## Simulate (Icarus Verilog)
iverilog -o sim.out tb_cpu.v cpu.v alu.v regfile.v memory.v
vvp sim.out
# waveform: gtkwave wave.vcd

## Common errors
- "syntax error" near `<=` in comb block -> use `=` in `always @(*)`.
- Multiple drivers on a `reg`/`wire` -> drive from one block only.
- Missing `default` in `case` -> latch inference; add defaults.
""",
}


def install_curated(techs=None):
    """Write the built-in curated cheatsheets to the langpacks dir.
    Returns {tech: [files written]}."""
    written = {}
    for rel, content in CHEATSHEETS.items():
        tech = rel.split("/", 1)[0]
        if techs and tech not in techs:
            continue
        path = os.path.join(pack_dir(tech), os.path.basename(rel))
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        written.setdefault(tech, []).append(os.path.basename(rel))
    return written


def ingest_all():
    """Ingest every language pack into the RAG index. Returns chunks."""
    from tools.handlers_rag import _rag
    rag = _rag()
    total = 0
    for t in list_packs():
        total += rag.ingest_dir(os.path.join(root(), t)).get("chunks", 0)
    rag.save()
    return total


if __name__ == "__main__":
    print("installed:", install_curated())
    print("packs:", list_packs())
    print("ingested chunks:", ingest_all())