"""Builder state machine: PLAN -> ... -> DONE with real sandbox feedback.

    generate -> COMPILE (loop: diagnose -> patch -> recompile)
             -> TEST (loop) -> ACCEPTANCE -> OPTIMIZE -> POLISH -> DONE

A surviving 'patch_fn' keeps the compile loop going; when no safe patch is
possible the loop escalates to the restructurer (re-plan/regenerate) rather
than thrashing. All state is checkpointed so a build can resume.
"""
from __future__ import annotations

import os
import re

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from . import (checkpoints, compiler, diagnoser, objectives as OBJ, optimizer,
               patcher, polisher, requirements_check, restructurer, tester,
               verifier_ui)


def _report(name, stack, compiled, tested, accept, rounds, diagnosis, obj,
            state, plan):
    return {"name": name, "stack": stack, "compiled": compiled,
            "tested": tested, "accept": accept, "rounds": rounds,
            "diagnosis": diagnosis, "objectives": obj,
            "restructure": plan,
            "history": state.get("history", [])[-12:]}


def run(name: str, cwd: str, stack: str | None = None, patch_fn=None,
        criteria: list | None = None, objectives: dict | None = None,
        max_rounds: int = 6, polish: bool = True, optimize: bool = True,
        design_space: list | None = None) -> dict:
    stack = stack or compiler.detect_stack(cwd)
    obj = objectives or OBJ.choose(name, stack=stack)
    state = checkpoints.load(name) or {}
    state.update({"name": name, "cwd": cwd, "stack": stack})
    state.setdefault("history", [])

    # --- COMPILE (build) loop ---
    rounds, compiled = 0, False
    while rounds < max_rounds:
        c = compiler.compile(cwd, stack)
        state["history"].append({"phase": "COMPILE", "round": rounds,
                                 "ok": c["ok"]})
        checkpoints.save(name, state)
        if c["ok"]:
            compiled = True
            break
        diag = diagnoser.classify(c.get("err") or c.get("out"), stack)
        state["last_diagnosis"] = diag
        patched = False
        if patch_fn:
            try:
                patched = bool(patch_fn(cwd, diag, c))
            except Exception:
                patched = False
        rounds += 1
        if not patched:
            plan = restructurer.propose(state["history"], diag, criteria)
            state["restructure"] = plan
            state["phase"] = "RESTRUCTURE"
            checkpoints.save(name, state)
            return _report(name, stack, False, None, False, rounds, diag,
                           obj, state, plan)

    # --- TEST ---
    tested = None
    if compiled:
        t = tester.run(cwd, stack)
        tested = t["ok"]
        state["history"].append({"phase": "TEST", "ok": tested})
        if not tested:
            state["last_diagnosis"] = diagnoser.classify(
                t.get("out") or t.get("err"), stack)

    # --- ACCEPTANCE ---
    acc = requirements_check.check(cwd, criteria) if criteria \
        else {"ok": None, "results": [], "unchecked": 0}
    artifacts = verifier_ui.build_outputs(cwd, stack)
    accept = bool(compiled and tested is not False
                  and acc.get("ok") in (True, None)
                  and artifacts.get("ok", True))

    # --- OPTIMIZE (quantum-inspired design search) ---
    opt = optimizer.optimize(design_space, obj) if (optimize and design_space) \
        else None

    # --- POLISH ---
    pol = polisher.polish(cwd, stack) if (polish and accept) else None

    state.update({"phase": "DONE" if accept else "RESTRUCTURE",
                  "compiled": compiled, "tested": tested, "accept": accept,
                  "acceptance": acc, "artifacts": artifacts})
    checkpoints.save(name, state)
    rep = _report(name, stack, compiled, tested, accept, rounds,
                  state.get("last_diagnosis"), obj, state, None)
    rep.update({"acceptance": acc, "artifacts": artifacts,
                "optimize": opt, "polish": pol})
    return rep


def repair(name: str, cwd: str, stack: str | None = None, patch_fn=None,
           **kw) -> dict:
    """Just the compile/test repair loop (no generation)."""
    return run(name, cwd, stack=stack, patch_fn=patch_fn, polish=False,
               optimize=False, **kw)


def _validate_code(rel: str, code: str) -> tuple:
    import json as _json
    import os
    import py_compile
    import tempfile
    if rel.endswith(".py"):
        fd, tmp = tempfile.mkstemp(suffix=".py")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(code)
            py_compile.compile(tmp, doraise=True)
            return True, "py ok"
        except Exception as e:
            return False, str(e)
        finally:
            try:
                os.remove(tmp)
            except Exception:
                pass
    if rel.endswith(".json"):
        try:
            _json.loads(code)
            return True, "json ok"
        except Exception as e:
            return False, str(e)
    return True, "no static check"


def generate_project(name: str, cwd: str, description: str,
                     stack: str = "node", criteria: list | None = None,
                     max_rounds: int = 6) -> dict:
    """Plan -> contract-aware generate (freeze verified units) -> run()."""
    import posixpath

    from sandbox import sb

    from . import contract as CT
    from . import freezer, generator, planner

    plan = planner.plan(description, stack)
    ct = CT.Contract()
    fz = freezer.Freezer(name)
    generated, skipped = [], []
    objectives = OBJ.choose(description, stack=stack)

    for f in plan.get("manifest", []):
        rel = f.get("path")
        if not rel:
            continue
        dest = posixpath.join(cwd, rel)
        existing = sb.read_text(dest)
        exports = CT.infer_exports(existing, stack) if existing else []
        if existing and fz.is_frozen(rel, existing, exports):
            ct.set_unit(rel, exports=exports)
            skipped.append(rel)
            continue
        code = generator.generate_unit(rel, f.get("purpose", ""), ct,
                                       objectives, context=description,
                                       stack=stack)
        if not code:
            continue
        ok, _why = _validate_code(rel, code)
        if not ok:
            continue
        sb.write(dest, code)
        exports = CT.infer_exports(code, stack)
        fz.freeze(rel, code, exports)
        ct.set_unit(rel, exports=exports,
                    imports=CT.infer_imports(code, stack))
        generated.append(rel)

    rep = run(name, cwd, stack=stack, criteria=criteria,
              objectives=objectives, max_rounds=max_rounds)
    rep.update({"planned": [f.get("path") for f in
                            plan.get("manifest", [])],
                "generated": generated, "kept_frozen": skipped,
                "contract": ct.to_dict()})
    return rep


def _parse_ports(text: str) -> list:
    ports = []
    for tok in (text or "").replace(";", ",").split(","):
        tok = tok.strip()
        m = re.match(
            r"(input|output|inout)\s+(?:reg|wire)?\s*(?:\[[^\]]*\]\s*)?"
            r"([A-Za-z_]\w*)", tok, re.I)
        if m:
            ports.append({"name": m.group(2), "dir": m.group(1).lower()})
    return ports


def _declared_in(fpath: str) -> set:
    from sandbox import sb
    src = sb.read_text(fpath) or ""
    return set(re.findall(r"^\s*module\s+([A-Za-z_]\w*)\s*[;(]", src, re.M))


def _hdl_patch(cwd: str, diagnosis: dict, last=None) -> bool:
    """Mechanical fix for 'Unknown module type: X': rename the instantiation
    to the actual declared module when there is a unique non-testbench, non-
    self candidate. The module self-check is done structurally (grep), not by
    substring, so names in comments can't confuse it."""
    import posixpath

    from sandbox import sb
    msg = (diagnosis or {}).get("message") or ""
    m = re.search(r"Unknown module\s+(?:type\s*)?[:*]?\s*([A-Za-z_]\w*)",
                  msg, re.I)
    if not m:
        return False
    unknown = m.group(1)
    rel = (diagnosis or {}).get("file")
    if not rel:
        return False
    target = posixpath.join(cwd, rel)
    src = sb.read_text(target)
    if not src:
        return False

    declared = set()
    for f in sb.shell(f"ls {cwd!r}/*.v 2>/dev/null", timeout=30).get(
            "out", "").split():
        declared |= _declared_in(f)
    if not declared:
        return False
    in_self = _declared_in(target)
    candidates = [d for d in declared if d != unknown
                  and d not in in_self and "tb" not in d.lower()]
    if len(candidates) != 1:
        return False
    fix = candidates[0]
    new = re.sub(r"\b" + re.escape(unknown) + r"\b", fix, src, count=1)
    if new == src:
        return False
    sb.write(target, new)
    return True


def _cpp_patch(cwd: str, diagnosis: dict, last=None) -> bool:
    """Fix 'No rule to make target X' by pointing the Makefile at the
    source file that actually exists in the project."""
    import posixpath

    from sandbox import sb
    msg = (diagnosis or {}).get("message") or ""
    m = re.search(r"No rule to make target '([^']+)', needed by", msg)
    if not m:
        return False
    missing = m.group(1)
    if not missing.endswith((".c", ".cpp", ".cxx")):
        return False
    r = sb.shell(f"ls {cwd!r}/*.c {cwd!r}/*.cpp {cwd!r}/*.cxx "
                 "2>/dev/null", timeout=30)
    cands = [x.strip() for x in r.get("out", "").split() if x.strip()]
    if not cands:
        return False
    found = None
    for c in cands:
        b = posixpath.basename(c)
        if b != missing and b.endswith((".c", ".cpp", ".cxx")):
            found = b
            break
    if not found:
        return False
    patched = False
    for mk in ("Makefile", "CMakeLists.txt"):
        p = posixpath.join(cwd, mk)
        src = sb.read_text(p)
        if not src:
            continue
        new = src.replace(missing, found)
        if new != src:
            sb.write(p, new)
            patched = True
    return patched


def _verify_hdl(cwd: str, spec: dict) -> dict:
    import posixpath

    from sandbox import sb

    from chip_architect import ChipArchitect
    a = ChipArchitect()
    out = {}
    for u in spec.get("manifest", []):
        rel = u.get("path")
        ports = u.get("ports") or ""
        if not (rel and ports):
            continue
        src = sb.read_text(posixpath.join(cwd, rel))
        if not src:
            out[rel] = "missing"
            continue
        expected = _parse_ports(ports)
        try:
            ok, missing, extra = a.verify_contract(src, expected)
            out[rel] = {"ok": ok, "missing": missing, "extra": extra}
        except Exception as e:
            out[rel] = {"error": str(e)}
    return out


def generate_mission(name: str, spec: dict | None = None,
                     stack: str | None = None, criteria: list | None = None,
                     max_rounds: int = 8) -> dict:
    """Build an extreme project from a mission spec (contract-first).

    Uses the spec's explicit file manifest + port contracts (instead of the
    LLM planner) so multi-module systems like a CPU stay deterministic:
    generate unit -> freeze -> compile -> diagnose/patch -> test ->
    acceptance -> (HDL) per-module port verification.
    """
    import posixpath

    from sandbox import sb

    from . import contract as CT
    from . import freezer as FR
    from . import generator as GEN
    from . import missions

    spec = spec or missions.load(name)
    if not spec:
        return {"ok": False, "reason": f"unknown mission: {name}"}
    stack = stack or spec.get("stack", "python")
    cwd = missions.workspace_dir(name)
    sb.mkdir(cwd)
    is_hdl = stack == "hdl"
    if criteria is None:
        criteria = spec.get("criteria", [])

    ct = CT.Contract()
    fz = FR.Freezer("mission_" + name)
    obj = OBJ.choose(spec.get("title") or name, stack=stack)
    ctx_txt = missions.context(spec)
    try:
        from specialization import route as _route
        ov = _route(spec.get("title") or name).get("overlay", "")
        if ov:
            ctx_txt = ov + "\n\n" + ctx_txt
    except Exception:
        pass
    generated, kept, failed, refs_used = [], [], [], []

    do_btb = is_hdl and spec.get("behavior_tb", True)
    btb_report = {}

    def _behavior_ok(rel, code):
        from chip_architect import ChipArchitect
        from . import hdl_tb
        modname = ChipArchitect().extract_module_name(code)
        if not modname:
            return False, "no module name"
        tb_rel2 = f"tb_{modname}.v"
        if any(u_.get("path") == tb_rel2
               for u_ in missions.units(spec)):   # manual TB covers it
            return True, {"manual_tb": True}
        res = hdl_tb.build_behavior_tb(cwd, rel, behavior=u.get("behavior",
                                                                ""))
        return bool(res.get("ok")), res

    for u in missions.units(spec):
        rel = u.get("path")
        purpose = u.get("purpose", "")
        ports = u.get("ports") or ""
        if ports:
            purpose = f"{purpose}\nPORTS: {ports}"
        dest = posixpath.join(cwd, rel)
        existing = sb.read_text(dest)
        expected = [str(x).strip() for x in (u.get("exports") or [])
                    if str(x).strip()]
        if expected:
            ct.set_unit(rel, exports=expected)

        ref = u.get("reference")
        if ref:
            host = os.path.join(_ROOT, ref)
            if os.path.exists(host):
                with open(host, "rb") as _fh:
                    sb.write(dest, _fh.read())
                refs_used.append(rel)
                if is_hdl and ports and not rel.lower().startswith("tb_"):
                    _rok, _rres = _behavior_ok(rel, sb.read_text(dest))
                    _cause = (_rres.get("cause") if isinstance(_rres, dict)
                              else ("behavior" if not _rok else "ok"))
                    btb_report[rel] = {"reference": True, "ok": _rok,
                                       "cause": _cause}
                continue

        if existing:
            if is_hdl:
                frozen = fz.is_frozen(rel, existing, ports if ports else None)
            else:
                have = CT.infer_exports(existing, stack)
                frozen = (fz.is_frozen(rel, existing, have if have else None)
                          or (expected and set(expected) <= set(have)))
            if frozen:
                kept.append(rel)
                continue

        try_behavior = bool(do_btb and ports and not rel.lower().startswith("tb_"))
        attempts = 3 if try_behavior else 1
        code, tb_res = None, None
        made = False
        for attempt in range(attempts):
            code = GEN.generate_unit(rel, purpose, ct, obj, context=ctx_txt,
                                     stack=stack)
            if not code:
                break
            okc, _ = _validate_code(rel, code)
            if not okc:
                continue
            if is_hdl and ports:
                raw = rel[:-2] if rel.endswith(".v") else rel
                code = re.sub(r"\bmodule\s+[A-Za-z_]\w*\s*\(",
                              f"module {raw} (", code, count=1)
            sb.write(dest, code)
            made = True
            if not try_behavior:
                tb_res = None
                break
            tb_ok, tb_res = _behavior_ok(rel, code)
            if tb_ok:
                break
            sb.remove(dest)     # behavior not proven -> regenerate module
            made = False
        if not code or not made:
            failed.append(rel)
            if tb_res:
                btb_report[rel] = {"ok": False, "try": attempt + 1,
                                   "out": (tb_res.get("out") or
                                           tb_res.get("reason", ""))[:400]}
            continue
        exs = CT.infer_exports(code, stack)
        fz.freeze(rel, code, ports.split(",") if is_hdl else exs)
        ct.set_unit(rel, exports=exs,
                    imports=[] if is_hdl else CT.infer_imports(code, stack))
        generated.append(rel)
        if tb_res and tb_res.get("ok") is not None:
            btb_report[rel] = tb_res

    patch_fn = _hdl_patch if is_hdl else (_cpp_patch if stack == "cpp"
                                          else None)
    rep = run("mission_" + name, cwd, stack=stack, criteria=criteria,
              objectives=obj, max_rounds=max_rounds, patch_fn=patch_fn)
    hdl = _verify_hdl(cwd, spec) if is_hdl else {}
    gate_fail = [k for k, v in btb_report.items() if isinstance(v, dict)
             and v.get("ok") is False and v.get("cause") != "tb"]
    rep.update({"mission": name, "title": spec.get("title"),
                "manifest": [u.get("path") for u in missions.units(spec)],
                "generated": generated, "kept_frozen": kept,
                "failed_to_generate": failed,
                "contract": ct.to_dict(), "hdl_verify": hdl,
                "behavior_tb": btb_report, "behavior_gate": not gate_fail,
                "gate_failures": gate_fail, "refs_used": refs_used})
    return rep
