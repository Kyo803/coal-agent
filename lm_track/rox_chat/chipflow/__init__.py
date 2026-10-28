"""ROX N chip flow — RTL build + verification (WSL or WASM toolchain)."""
from .core import (available, equivalence, formal, lint, report, run,
                   simulate, summary_text, synthesize, tool, yosys_cmd)
from .flow import build_block, build_composition, build_design, verify_dir
from .designs import GENERATORS, generate_block
from .build import build, detect_block
from .compose import Composition
from . import compositions, model, pnr, ports

__all__ = ["available", "equivalence", "formal", "lint", "report", "run",
           "simulate", "summary_text", "synthesize", "tool", "yosys_cmd",
           "build_block", "build_composition", "build_design", "verify_dir",
           "GENERATORS", "generate_block", "build", "detect_block",
           "Composition", "compositions", "model", "pnr", "ports"]
