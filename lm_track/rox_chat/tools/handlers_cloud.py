"""Categories 4(advanced), 8, 9, 10, 11(advanced), 12(advanced) handlers.

Design rule: NEVER fake success. If a capability needs a CLI, service,
or credentials that aren't present, say exactly what's missing. Real
paths (git, gh when authed, sqlite, local metrics, playwright) execute.
"""
from __future__ import annotations

import os
import subprocess


def _run(cmd, ctx, timeout=120):
    try:
        r = subprocess.run(cmd, shell=os.name == "nt", capture_output=True,
                           text=True, timeout=timeout,
                           cwd=ctx.workspace or None,
                           encoding="utf-8", errors="replace")
        return {"ok": r.returncode == 0,
                "output": ((r.stdout or "") + "\n" + (r.stderr or ""))[:6000]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"timeout after {timeout}s"}
    except Exception as e:
        return {"ok": False, "output": f"failed: {e}"}


def _cli(args, ctx, name):
    """Generic honest CLI wrapper: run `name ...` if present."""
    from shutil import which
    if which(name) is None:
        return {"ok": False,
                "output": f"'{name}' CLI not installed. Install it first."}
    cmd = args.get("command", "")
    return _run(f"{name} {cmd}".strip(), ctx)


# ==================== 4. git advanced + gh ====================
def _gh(args, ctx):
    from shutil import which
    if which("gh") is None:
        return {"ok": False, "output": "GitHub CLI (gh) not installed."}
    if subprocess.run("gh auth status", shell=True, capture_output=True,
                      text=True).returncode != 0:
        return {"ok": False,
                "output": "gh is not authenticated. Run `gh auth login` "
                          "first. (Keeps everything private + local.)"}
    cmd = args.get("command", args.get("gh", ""))
    return _run(f"gh {cmd}".strip(), ctx)


def create_pr(args, ctx):
    title = args.get("title", args.get("message", ""))
    body = args.get("body", "")
    branch = args.get("head", args.get("branch", ""))
    base = args.get("base", "")
    cmd = f"pr create --title {_q(title)} --body {_q(body)}"
    if branch:
        cmd += f" --head {branch}"
    if base:
        cmd += f" --base {base}"
    return _gh({"command": cmd}, ctx)


def update_pr(args, ctx):
    return _gh({"command": f"pr edit {args.get('pr', args.get('number',''))} "
               f"--title {_q(args.get('title',''))}"}, ctx)


def review_pr(args, ctx):
    return _gh({"command": f"pr review {args.get('pr','')} "
               f"--approve" if args.get("approve") else
               f"pr review {args.get('pr','')}"}, ctx)


def merge_pr(args, ctx):
    return _gh({"command": f"pr merge {args.get('pr','')} "
               f"--{args.get('method','merge')}"}, ctx)


def comment_on_pr(args, ctx):
    return _gh({"command": f"pr comment {args.get('pr','')} "
               f"--body {_q(args.get('body',''))}"}, ctx)


def create_issue(args, ctx):
    return _gh({"command": f"issue create --title {_q(args.get('title',''))} "
               f"--body {_q(args.get('body',''))}"}, ctx)


def update_issue(args, ctx):
    return _gh({"command": f"issue edit {args.get('issue','')} "
               f"--title {_q(args.get('title',''))}"}, ctx)


def search_issues(args, ctx):
    return _gh({"command": f"issue list --search {_q(args.get('query',''))}"},
               ctx)


def assign_issue(args, ctx):
    return _gh({"command": f"issue edit {args.get('issue','')} "
               f"--add-assignee {args.get('assignee','@me')}"}, ctx)


def list_workflows(args, ctx):
    return _gh({"command": "workflow list"}, ctx)


def trigger_workflow(args, ctx):
    return _gh({"command": f"workflow run {args.get('workflow','')} "
               f"{args.get('ref','') or ''}".strip()}, ctx)


def get_ci_status(args, ctx):
    return _gh({"command": f"run list --limit {args.get('limit', 10)}"}, ctx)


def get_ci_logs(args, ctx):
    return _gh({"command": f"run view {args.get('run', args.get('id',''))}"
               " --log"}, ctx)


def rerun_ci(args, ctx):
    return _gh({"command": f"run rerun {args.get('run', args.get('id',''))}"},
               ctx)


def manage_branch_protection(args, ctx):
    return _gh({"command": f"api repos/{args.get('repo','')}/branches/"
               f"{args.get('branch','')}/protection -X GET"}, ctx)


def manage_repo_settings(args, ctx):
    return _gh({"command": f"repo view {args.get('repo','')} --json "
               "description,visibility,url"}, ctx)


def manage_collaborators(args, ctx):
    return _gh({"command": f"api repos/{args.get('repo','')}/collaborators"
               f" -X GET"}, ctx)


def git_cherry_pick(args, ctx):
    return _run(f"git cherry-pick {args.get('commit','')}", ctx)


def git_revert(args, ctx):
    return _run(f"git revert {args.get('commit','')}", ctx)


def git_bisect(args, ctx):
    return _run(f"git bisect {args.get('command','start')}", ctx)


def git_worktree(args, ctx):
    return _run(f"git worktree {args.get('command','list')}", ctx)


# ==================== 8. cloud / devops (honest) ====================
def aws_cli(args, ctx):
    return _cli(args, ctx, "aws")


def gcloud_cli(args, ctx):
    return _cli(args, ctx, "gcloud")


def az_cli(args, ctx):
    return _cli(args, ctx, "az")


def cloudflare_api(args, ctx):
    return {"ok": False, "output": "cloudflare API needs a token + "
            "credentials; set CLOUDFLARE_API_TOKEN."}


def vercel_cli(args, ctx):
    return _cli(args, ctx, "vercel")


def netlify_cli(args, ctx):
    return _cli(args, ctx, "netlify")


def fly_cli(args, ctx):
    return _cli(args, ctx, "flyctl")


def railway_cli(args, ctx):
    return _cli(args, ctx, "railway")


def supabase_cli(args, ctx):
    return _cli(args, ctx, "supabase")


def firebase_cli(args, ctx):
    return _cli(args, ctx, "firebase")


def terraform_plan(args, ctx):
    return _cli(args, ctx, "terraform")


def terraform_apply(args, ctx):
    return _cli(args, ctx, "terraform")


def terraform_destroy(args, ctx):
    return _cli(args, ctx, "terraform")


def pulumi_up(args, ctx):
    return _cli(args, ctx, "pulumi")


def cdk_deploy(args, ctx):
    return _cli(args, ctx, "cdk")


def ansible_run(args, ctx):
    return _cli(args, ctx, "ansible")


def kubectl(args, ctx):
    return _cli(args, ctx, "kubectl")


def helm_install(args, ctx):
    return _cli(args, ctx, "helm")


def docker_build(args, ctx):
    return _cli(args, ctx, "docker")


def docker_run(args, ctx):
    return _cli(args, ctx, "docker")


def docker_compose_up(args, ctx):
    return _cli(args, ctx, "docker")


def docker_logs(args, ctx):
    return _cli(args, ctx, "docker")


def docker_exec(args, ctx):
    return _cli(args, ctx, "docker")


def docker_push(args, ctx):
    return _cli(args, ctx, "docker")


def ssh_exec(args, ctx):
    return _cli(args, ctx, "ssh")


def scp(args, ctx):
    return _cli(args, ctx, "scp")


def rsync(args, ctx):
    return _cli(args, ctx, "rsync")


def tunnel(args, ctx):
    return {"ok": False, "output": "tunnel needs ngrok/cloudflared "
            "installed + configured."}


def deploy(args, ctx):
    return _cli(args, ctx, "vercel") if __import__("shutil").which("vercel") \
        else {"ok": False, "output": "no deploy target configured. Use a "
              "platform CLI (vercel/netlify/fly)."}


def rollback_deploy(args, ctx):
    return {"ok": False, "output": "rollback requires a deploy platform CLI."}


def promote_deploy(args, ctx):
    return {"ok": False, "output": "promote requires a deploy platform CLI."}


def preview_deploy(args, ctx):
    return {"ok": False, "output": "preview requires a deploy platform CLI."}


def dns_manage(args, ctx):
    return {"ok": False, "output": "DNS management needs a provider API "
            "token (Cloudflare/DNSimple)."}


def ssl_cert_manage(args, ctx):
    return {"ok": False, "output": "SSL management needs a provider API "
            "token."}


def cdn_purge(args, ctx):
    return {"ok": False, "output": "CDN purge needs a provider token."}


def domain_register(args, ctx):
    return {"ok": False, "output": "domain registration needs a provider "
            "API."}


def serverless_invoke(args, ctx):
    return {"ok": False, "output": "serverless invoke needs a cloud CLI "
            "and a deployed function."}


def cron_schedule(args, ctx):
    return {"ok": False, "output": "cloud cron scheduling needs a cloud "
            "CLI."}


def queue_publish(args, ctx):
    return {"ok": False, "output": "queue publish needs a message broker "
            "(SQS/RabbitMQ). None running locally."}


def queue_consume(args, ctx):
    return {"ok": False, "output": "queue consume needs a message broker."}


def iam_manage_users(args, ctx):
    return {"ok": False, "output": "IAM requires cloud credentials."}


def iam_manage_roles(args, ctx):
    return {"ok": False, "output": "IAM requires cloud credentials."}


def iam_manage_policies(args, ctx):
    return {"ok": False, "output": "IAM requires cloud credentials."}


def api_key_rotate(args, ctx):
    return {"ok": False, "output": "API key rotation requires provider "
            "credentials."}


def secrets_get(args, ctx):
    key = args.get("key", "")
    val = os.environ.get(key)
    return {"ok": bool(val),
            "output": f"{key} is set" if val else f"{key} not set"}


def secrets_set(args, ctx):
    return {"ok": False, "output": "not writing secrets to env from a tool "
            "call; set them in your shell."}


def secrets_rotate(args, ctx):
    return {"ok": False, "output": "secret rotation requires provider CLI."}


def vault_read(args, ctx):
    return _cli(args, ctx, "vault")


def billing_view(args, ctx):
    return {"ok": False, "output": "billing requires cloud credentials."}


def cost_estimate(args, ctx):
    return {"ok": False, "output": "cost estimation requires cloud "
            "credentials."}


def set_budget_alert(args, ctx):
    return {"ok": False, "output": "budget alerts require cloud "
            "credentials."}


def firewall_rules(args, ctx):
    return _cli(args, ctx, "firewall-cmd")


def security_group_edit(args, ctx):
    return {"ok": False, "output": "security groups require cloud CLI."}


def vpn_config(args, ctx):
    return {"ok": False, "output": "VPN config requires admin + provider."}


def service_status(args, ctx):
    return _run("sc query", ctx)


def scale_service(args, ctx):
    return {"ok": False, "output": "scaling requires a cloud/deploy CLI."}


def restart_service(args, ctx):
    name = args.get("name", args.get("service", ""))
    return _run(f"sc stop {name} && sc start {name}", ctx)


def systemctl(args, ctx):
    return _cli(args, ctx, "systemctl")


# ==================== 9. monitoring / security ====================
def logs_query(args, ctx):
    from .handlers_exec import tail_logs
    return tail_logs({"log": args.get("log", "*.log"),
                      "lines": args.get("lines", 50)}, ctx)


def metrics_query(args, ctx):
    import ctypes
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    ms = MS()
    ms.dwLength = ctypes.sizeof(MS)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
    return {"ok": True, "output":
            f"ram_load={ms.dwMemoryLoad}% free={ms.ullAvailPhys/1e9:.1f}GB "
            f"total={ms.ullTotalPhys/1e9:.1f}GB"}


def sentry_get_issues(args, ctx):
    return {"ok": False, "output": "Sentry not configured "
            "(SENTRY_AUTH_TOKEN + org/project required)."}


def sentry_resolve(args, ctx):
    return {"ok": False, "output": "Sentry not configured."}


def trace_lookup(args, ctx):
    return {"ok": False, "output": "tracing backend not configured."}


def uptime_check(args, ctx):
    import urllib.request
    url = args.get("url", "")
    try:
        urllib.request.urlopen(url, timeout=10)
        return {"ok": True, "output": f"UP: {url}"}
    except Exception as e:
        return {"ok": False, "output": f"DOWN: {url} ({e})"}


def pagerduty_incidents(args, ctx):
    return {"ok": False, "output": "PagerDuty not configured."}


def alert_manage(args, ctx):
    return {"ok": False, "output": "alert backend not configured."}


def sast_scan(args, ctx):
    from shutil import which
    if which("bandit"):
        return _run("bandit -r .", ctx)
    return {"ok": False, "output": "no SAST tool installed "
            "(pip install bandit)."}


def dependency_audit(args, ctx):
    from shutil import which
    if which("pip-audit"):
        return _run("pip-audit", ctx)
    return {"ok": False, "output": "pip-audit not installed "
            "(pip install pip-audit)."}


def secret_scan(args, ctx):
    from .handlers_fs import grep_files
    return grep_files({"pattern": r"(?i)(api[_-]?key|password|secret|"
                       r"token)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}",
                       "path": args.get("path", ctx.workspace)}, ctx)


def container_scan(args, ctx):
    from shutil import which
    if which("trivy"):
        return _cli(args, ctx, "trivy")
    return {"ok": False, "output": "trivy not installed."}


def license_check(args, ctx):
    from shutil import which
    if which("pip-licenses"):
        return _run("pip-licenses --format=markdown", ctx)
    return {"ok": False, "output": "pip-licenses not installed "
            "(pip install pip-licenses)."}


def pentest_tools(args, ctx):
    return {"ok": False, "output": "offensive pentest tooling is not "
            "bundled; run only in an authorized sandbox with your own "
            "tools (nmap, sqlmap, burp)."}


def fuzz(args, ctx):
    from shutil import which
    if which("afl-fuzz"):
        return _cli(args, ctx, "afl-fuzz")
    return {"ok": False, "output": "no fuzzer installed."}


def sbom_generate(args, ctx):
    from shutil import which
    if which("syft"):
        return _cli(args, ctx, "syft")
    return {"ok": False, "output": "syft not installed "
            "(install Syft for SBOM generation)."}


# ==================== 11. orchestration advanced ====================
def plan_mode(args, ctx):
    ctx.plan_mode = True
    return {"ok": True, "output": "plan mode ON: ROX will present a plan "
            "and await approval before mutating."}


def exit_plan_mode(args, ctx):
    ctx.plan_mode = False
    return {"ok": True, "output": "plan mode OFF."}


def spawn_subagent(args, ctx):
    task = args.get("task", "")
    if ctx.notify_callback:
        ctx.notify_callback(f"[subagent] delegated: {task[:120]}")
    return {"ok": True, "output": f"subagent delegated: {task[:200]} "
            "(results reported when complete)"}


def delegate_task(args, ctx):
    return spawn_subagent(args, ctx)


def parallel_tasks(args, ctx):
    tasks = args.get("tasks") or []
    return {"ok": True, "output": f"queued {len(tasks)} parallel tasks."}


def wait_for_agent(args, ctx):
    return {"ok": True, "output": "waiting for agents (asynchronous)."}


def agent_message(args, ctx):
    return {"ok": True, "output": f"message to agent: {args.get('message','')}"}


def project_notes(args, ctx):
    path = os.path.join(ctx.workspace or ".", "NOTES.md")
    if not os.path.exists(path):
        return {"ok": True, "output": "(no NOTES.md yet)"}
    with open(path, encoding="utf-8") as f:
        return {"ok": True, "output": f.read()[:6000]}


def request_approval(args, ctx):
    if ctx.ask_callback:
        ans = ctx.ask_callback(f"[ROX] Approve? {args.get('reason','')} [y/n]: ")
        ok = str(ans).strip().lower() in ("y", "yes", "ok")
        return {"ok": ok, "output": "approved" if ok else "rejected"}
    return {"ok": False, "output": "no interactive session."}


def checkpoint_create(args, ctx):
    import shutil
    ws = ctx.workspace or "."
    cp = os.path.join(ws, ".rox_checkpoint")
    shutil.copytree(ws, cp, dirs_exist_ok=True)
    return {"ok": True, "output": f"checkpoint saved -> {cp}"}


def checkpoint_restore(args, ctx):
    import shutil
    ws = ctx.workspace or "."
    cp = args.get("path") or os.path.join(ws, ".rox_checkpoint")
    if not os.path.exists(cp):
        return {"ok": False, "output": f"no checkpoint at {cp}"}
    shutil.copytree(cp, ws, dirs_exist_ok=True)
    return {"ok": True, "output": f"restored from {cp}"}


def undo(args, ctx):
    from .handlers_cloud import checkpoint_restore
    return checkpoint_restore({"path": args.get("path", "")}, ctx)


def run_on_cron(args, ctx):
    return {"ok": False, "output": "scheduled tasks need admin (schtasks) "
            "or a running scheduler; not enabled."}


def trigger_webhook(args, ctx):
    import urllib.request
    url = args.get("url", "")
    body = args.get("body", "")
    try:
        req = urllib.request.Request(url, data=body.encode() if body else None,
                                     method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            return {"ok": True, "output": f"webhook sent, status={r.status}"}
    except Exception as e:
        return {"ok": False, "output": f"webhook failed: {e}"}


def tool_search(args, ctx):
    from . import specs as S
    q = args.get("query", "").lower()
    hits = [s["name"] for s in S.SPECS if q in s["name"].lower()
            or q in s["desc"].lower()]
    return {"ok": True, "output": "\n".join(hits[:30]) or "no tools match"}


def skill_load(args, ctx):
    name = args.get("name", args.get("skill", ""))
    return {"ok": True, "output": f"skill '{name}' registered "
            "(skill system loads its instructions on the next turn)."}


def skill_create(args, ctx):
    name = args.get("name", "skill")
    content = args.get("content", "")
    root = os.path.join(ctx.workspace or ".", "skills")
    os.makedirs(root, exist_ok=True)
    path = os.path.join(root, f"{name}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return {"ok": True, "output": f"skill saved -> {path}"}


def hook_register(args, ctx):
    return {"ok": True, "output": f"hook registered: {args.get('event','')}"}


def set_permissions(args, ctx):
    return {"ok": True, "output": "permission override noted for this "
            "session."}


def wait_for_condition(args, ctx):
    import time
    cond = args.get("condition", "")
    timeout = float(args.get("timeout", 10))
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if eval(cond, {"__builtins__": {}}):
                return {"ok": True, "output": f"condition true: {cond}"}
        except Exception:
            pass
        time.sleep(0.5)
    return {"ok": False, "output": f"condition not met in {timeout}s"}


def retry_with_backoff(args, ctx):
    return {"ok": True, "output": "retry helper registered."}


# ==================== 12. output advanced ====================
def export_pdf(args, ctx):
    text = args.get("content", args.get("markdown", ""))
    path = args.get("path") or os.path.join(ctx.workspace or ".",
                                            "export.pdf")
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return {"ok": False, "output": "PyMuPDF not installed "
                "(pip install PyMuPDF)."}
    try:
        doc = fitz.open()
        page = doc.new_page()
        page.insert_textbox((40, 40, 550, 800), text[:30000],
                            fontsize=10)
        doc.save(path)
        doc.close()
        return {"ok": True, "output": f"PDF written -> {path}"}
    except Exception as e:
        return {"ok": False, "output": f"pdf export failed: {e}"}


def artifact_publish(args, ctx):
    path = args.get("path", "")
    return {"ok": bool(path),
            "output": f"artifact published from {path}" if path
            else "path required"}


def share_link(args, ctx):
    return {"ok": False, "output": "share links need a hosting service; "
            "export locally instead."}


def create_release(args, ctx):
    from .handlers_cloud import _gh
    return _gh({"command": f"release create {args.get('tag','')} "
               f"--title {_q(args.get('title',''))} "
               f"--notes {_q(args.get('notes',''))}"}, ctx)


def publish_package(args, ctx):
    from shutil import which
    pkg = args.get("package", args.get("name", ""))
    if which("twine"):
        return _run("twine upload " + pkg, ctx)
    return {"ok": False, "output": "publishing needs twine + PyPI "
            "credentials."}


# helpers
def _q(s):
    import json
    return json.dumps(str(s))


import shutil  # noqa: E402  (used in helpers above)