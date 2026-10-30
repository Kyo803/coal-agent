# 500M pretrain watcher: RAM gate, then python train_500m.py
$ErrorActionPreference = "SilentlyContinue"
$log = Join-Path $PSScriptRoot "pretrain_log.txt"
"[$(Get-Date)] 500M pretrain watch started" | Out-File $log -Append
$deadline = (Get-Date).AddHours(24)
$launched = $false
while ((Get-Date) -lt $deadline -and -not $launched) {
    $free = [math]::Round((Get-Counter '\Memory\Available MBytes').CounterSamples[0].CookedValue / 1024, 1)
    "[$(Get-Date)] free=${free}GB" | Out-File $log -Append
    if ($free -ge 8) {
        "[$(Get-Date)] RAM gate open, launching 500M pretrain" | Out-File $log -Append
        python (Join-Path $PSScriptRoot "train_500m.py") --mode sft --steps 500 >> $log 2>&1
        "[$(Get-Date)] SFT exited code $LASTEXITCODE" | Out-File $log -Append
        if ($LASTEXITCODE -eq 0) {
            "[$(Get-Date)] launching KTO alignment" | Out-File $log -Append
            python (Join-Path $PSScriptRoot "train_500m.py") --mode align --steps 500 >> $log 2>&1
            "[$(Get-Date)] KTO exited code $LASTEXITCODE" | Out-File $log -Append
        }
        $launched = $true
    } else {
        Start-Sleep -Seconds 300
    }
}
