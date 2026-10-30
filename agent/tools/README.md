# tools — everything the model can call

`specs.py` defines all 434 tools: name, category, handler, JSON schema,
required arguments and a permission tier. `exec.py` is the executor.

| File | Role |
|---|---|
| `specs.py` | tool definitions + `categories_for_trigger()` routing |
| `exec.py` | validation, permissions, lazy schema loading, worker thread |
| `permissions.py` | tier policy (`auto` / `confirm` / `disabled`) + config overrides |
| `intent.py` | explicit-intent detection and the plausibility guard |
| `shell_gate.py` | per-command shell policy |
| `handlers_*.py` | implementations, grouped by domain |

Tiers: read-only tools run automatically; writes, commands, browser and
app launches ask first; cloud/billing/destructive tools are disabled by
default. `run_command`, `write_file` and `open_app` are always `confirm`.

`lazy_schemas()` only exposes the categories a request needs, and always
keeps `read_file` / `write_file` / `list_directory` / `run_command` so a
broad request can still act.
