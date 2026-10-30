# Sequential launcher: KTO -> ORPO -> distill -> online_dpo -> GRPO
# Each runs from scratch (fresh LoRA), saves to its own dir.
$ErrorActionPreference = "SilentlyContinue"
$log = Join-Path $PSScriptRoot "train_log.txt"
"[$(Get-Date)] sequential training started" | Out-File $log -Append
$deadline = (Get-Date).AddHours(24)
$scripts = @("run_kto.py --steps=100", "run_orpo.py --steps=100",
             "run_distill.py --steps=100", "run_online_dpo.py",
             "run_grpo.py --steps=30")
foreach ($script in $scripts) {
    if ((Get-Date) -ge $deadline) { break }
    "[$(Get-Date)] launching $script" | Out-File $log -Append
    python (Join-Path $PSScriptRoot $script.Split(" ")[0]) $script.Split(" ")[1..99] >> $log 2>&1
    "[$(Get-Date)] finished $script (exit $LASTEXITCODE)" | Out-File $log -Append
}
"[$(Get-Date)] sequential training complete" | Out-File $log -Append
