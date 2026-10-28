# DPO watcher: RAM gate then run, checkpoints at 25-step intervals.
$ErrorActionPreference = "SilentlyContinue"
$log = Join-Path $PSScriptRoot "dpo_out.log"
Remove-Item $log -Force -ErrorAction SilentlyContinue
"[$(Get-Date)] dpo watch started" | Out-File $log -Append
$deadline = (Get-Date).AddHours(8)
$launched = $false
while ((Get-Date) -lt $deadline -and -not $launched) {
    $free = [math]::Round((Get-Counter '\Memory\Available MBytes').CounterSamples[0].CookedValue / 1024, 1)
    "[$(Get-Date)] free=${free}GB" | Out-File $log -Append
    if ($free -ge 6) {
        "[$(Get-Date)] RAM gate open, launching DPO" | Out-File $log -Append
        python (Join-Path $PSScriptRoot "train_dpo.py") --steps=50 >> $log 2>&1
        "[$(Get-Date)] DPO exited code $LASTEXITCODE" | Out-File $log -Append
        $launched = $true
    } else {
        Start-Sleep -Seconds 300
    }
}
