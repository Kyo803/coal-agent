# Overnight queue: waits for free RAM, then runs the SFT job. Log: overnight.log
# Launched detached; survives this session. Kills nothing, touches nothing else.
$ErrorActionPreference = "SilentlyContinue"
$log = Join-Path $PSScriptRoot "overnight.log"
"[$(Get-Date)] overnight watch started" | Out-File $log -Append
$deadline = (Get-Date).AddHours(8)
$launched = $false
while ((Get-Date) -lt $deadline -and -not $launched) {
    $free = [math]::Round((Get-Counter '\Memory\Available MBytes').CounterSamples[0].CookedValue / 1024, 1)
    "[$(Get-Date)] free=${free}GB" | Out-File $log -Append
    if ($free -ge 4.5) {
        "[$(Get-Date)] RAM gate open, launching SFT" | Out-File $log -Append
        python (Join-Path $PSScriptRoot "train_sft.py") --steps=1000 --batch=2 >> $log 2>&1
        "[$(Get-Date)] SFT exited code $LASTEXITCODE" | Out-File $log -Append
        $launched = $true
    } else {
        Start-Sleep -Seconds 300
    }
}
if (-not $launched) { "[$(Get-Date)] deadline reached, SFT not launched" | Out-File $log -Append }
