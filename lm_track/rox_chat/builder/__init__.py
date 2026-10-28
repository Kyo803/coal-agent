"""ROX N builder — the extreme-coding machine.

Turns a goal into a product with a real feedback loop:

    plan/spec -> contract-aware generation -> COMPILE (diagnose/patch loop)
    -> TEST -> ACCEPTANCE -> OPTIMIZE (quantum-inspired) -> POLISH -> DONE

Everything runs against the isolated Linux sandbox for real feedback.

    from builder import build
    build.run("my-app", "/home/rox/work/my-app", stack="vite")
    build.objectives("a fast accessible dashboard", stack="react")
    build.optimize(designs, objectives)
"""
from __future__ import annotations

from . import (checkpoints, compiler, contract, diagnoser, freezer,
               generator, loop, missions as _missions, objectives, optimizer,
               patcher, planner, polisher, requirements_check, restructurer,
               tester, verifier_ui)


class Builder:
    run = staticmethod(loop.run)
    repair = staticmethod(loop.repair)
    generate_project = staticmethod(loop.generate_project)
    generate_mission = staticmethod(loop.generate_mission)
    plan = staticmethod(planner.plan)
    missions = staticmethod(_missions.all_names)
    mission = staticmethod(_missions.load)
    choose_objectives = staticmethod(objectives.choose)
    optimize = staticmethod(optimizer.optimize)
    compile = staticmethod(compiler.compile)
    test = staticmethod(tester.run)
    detect_stack = staticmethod(compiler.detect_stack)
    diagnose = staticmethod(diagnoser.classify)
    generate_unit = staticmethod(generator.generate_unit)
    model_available = staticmethod(generator.available)
    Freezer = freezer.Freezer
    Contract = contract.Contract
    checkpoints = checkpoints


build = Builder()

__all__ = ["build", "Builder", "loop", "optimizer", "objectives", "compiler",
           "tester", "diagnoser", "contract", "freezer", "generator"]
