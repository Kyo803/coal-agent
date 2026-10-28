"""ROX N tool permission model.

Three tiers, resolved against config.json "tools" section:

  Tier 0  auto         read-only / safe: memory, calculator, search,
                       glob/grep, web_fetch, info queries. Never prompts.
  Tier 1  confirm      mutating / executing: file writes, run commands,
                       install packages, git push, browser. ROX N proposes
                       the action; the user types yes/no in chat.
  Tier 2  disabled     cloud CLIs, secrets, billing, IAM, destructive
                       system ops. Off by default; can be enabled per tool
                       in config.json under tools.allow_tier2.

Per-tool overrides:
  tools.auto_allow: ["write_file", ...]   -> these Tier-1 tools never prompt
  tools.block:      ["rm -rf", ...]       -> these are always refused
  tools.enabled:    list of category names; omitted categories are hidden
"""
from __future__ import annotations

import json
import os

DEFAULT = {
    "enabled": [
        "filesystem", "search", "execution", "sandbox", "git", "web",
        "browser", "database", "orchestration", "output", "system",
        "project", "knowledge", "build", "self", "board", "security",
        "chip", "learning", "3d",
    ],
    "tier0": [],
    "tier1": [],
    "tier2": [],
    "auto_allow": [
        "read_file", "read_multiple_files", "get_file_info",
        "list_directory", "directory_tree", "glob", "grep", "find_files",
        "find_symbol", "list_symbols", "web_fetch", "http_request",
        "sql_query", "list_tables", "describe_table", "data_analysis",
        "git_status", "git_diff", "git_log", "process_list", "tail_logs",
        "ps", "df", "netstat", "ping", "system_status",
        "sandbox_run", "sandbox_write", "sandbox_read", "sandbox_edit",
        "sandbox_list", "sandbox_move", "sandbox_delete", "sandbox_pkg",
        "sandbox_toolchain", "sandbox_info", "sandbox_upload",
        "sandbox_download", "generate_3d", "render_3d", "list_3d_shapes",
        "convert_3d", "validate_3d", "repair_3d", "texture_3d", "image_to_3d",
        "list_3d_backends", "generate_hd_image", "character_sheet",
        "chip_build", "chip_gate", "chip_tools", "chip_views", "chip_batch",
        "chip_unique",
    ],
    "block": [],
    "allow_tier2": [],
    "ask_confirms": True,
}

_TIER = {"auto": 0, "confirm": 1, "disabled": 2}


def _load_cfg():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)          # rox_chat/
    install = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "Programs", "ROX N", "config.json")
    candidates = [
        os.environ.get("ROX_CONFIG"),
        os.path.join(root, "tools.json"),
        os.path.join(root, "config.json"),
        install,
    ]
    for path in candidates:
        if not (path and os.path.exists(path)):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            tools = data.get("tools") or {}
            merged = dict(DEFAULT)
            merged.update(tools)
            return merged
        except Exception:
            continue
    return DEFAULT


class Permissions:
    def __init__(self, tools_cfg=None):
        self.cfg = tools_cfg or _load_cfg()
        self.enabled_cats = set(self.cfg.get("enabled") or DEFAULT["enabled"])
        self.auto_allow = set(self.cfg.get("auto_allow") or [])
        self.block = set(self.cfg.get("block") or [])
        self.allow_tier2 = set(self.cfg.get("allow_tier2") or [])
        self.ask_confirms = bool(self.cfg.get("ask_confirms", True))
        # tier lookup tables from config if provided
        self.t0 = set(self.cfg.get("tier0") or [])
        self.t1 = set(self.cfg.get("tier1") or [])
        self.t2 = set(self.cfg.get("tier2") or [])

    def category_enabled(self, category):
        return category in self.enabled_cats

    def tier(self, name, declared="auto"):
        if name in self.block:
            return 2
        if name in self.auto_allow:
            return 0
        if name in self.allow_tier2:
            return 1 if declared == "disabled" else 0
        if declared == "confirm":
            return 1
        if declared == "disabled":
            return 2
        if name in self.t0:
            return 0
        if name in self.t1:
            return 1
        if name in self.t2:
            return 2
        return _TIER.get(declared, 0)

    def can_auto(self, name, declared="auto"):
        return self.tier(name, declared) == 0

    def needs_confirm(self, name, declared="auto"):
        return self.tier(name, declared) == 1

    def blocked(self, name, declared="auto"):
        return (name in self.block
                or (declared == "disabled" and name not in self.allow_tier2))


if __name__ == "__main__":
    p = Permissions()
    print("enabled cats:", sorted(p.enabled_cats))
    for t in ["search_memory", "write_file", "run_command",
              "aws_cli", "web_fetch", "read_file"]:
        declared = "confirm" if t in ("write_file", "run_command") else "auto"
        print(f"{t:16s} tier={p.tier(t, declared)} auto={p.can_auto(t, declared)} "
              f"confirm={p.needs_confirm(t, declared)}")