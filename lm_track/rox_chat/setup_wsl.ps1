<#
  ROX N — one-click WSL setup (Verilog / chip-design sandbox)

  Run (normal user is fine — it self-elevates via UAC):
      powershell -ExecutionPolicy Bypass -File setup_wsl.ps1

  What it does, idempotently:
    1. enables the WSL + VirtualMachinePlatform Windows features
    2. installs WSL itself (no distro) if missing
    3. if a reboot is needed, tells you and stops
    4. re-attaches your surviving sandbox disk (import-in-place)
    5. installs iverilog + verilator + gtkwave inside it
    6. verifies the toolchain

  Log: %LOCALAPPDATA%\ROXN\setup_wsl.log
#>
[CmdletBinding()]
param(
    [switch]$NoReboot,                       # don't prompt about rebooting
    [string]$Distro = 'ROX-N-Ubuntu',
    [string]$Vhdx   = 'D:\ROX_N_SANDBOX\Ubuntu-24.04\ext4.vhdx'
)

$ErrorActionPreference = 'Continue'
$logDir = Join-Path $env:LOCALAPPDATA 'ROXN'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'setup_wsl.log'
function Log($m) {
    $t = (Get-Date).ToString('HH:mm:ss')
    "$t  $m" | Tee-Object -FilePath $log -Append
}

# ---------------------------------------------------------------- elevate
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Log 'Not elevated - relaunching with UAC...'
    $argline = "-ExecutionPolicy Bypass -NoProfile -File `"$PSCommandPath`""
    if ($NoReboot) { $argline += ' -NoReboot' }
    Start-Process powershell -Verb RunAs -ArgumentList $argline
    exit
}
Log "Elevated. ROX N WSL setup starting."

$needReboot = $false

# ---------------------------------------------------------------- features
foreach ($f in 'Microsoft-Windows-Subsystem-Linux', 'VirtualMachinePlatform') {
    $state = (Get-WindowsOptionalFeature -Online -FeatureName $f `
        -ErrorAction SilentlyContinue).State
    Log "feature $f = $state"
    if ($state -ne 'Enabled') {
        Log "enabling $f ..."
        Enable-WindowsOptionalFeature -Online -FeatureName $f -All -NoRestart `
            | Out-Null
        $needReboot = $true
    }
}

# ---------------------------------------------------------------- WSL core
$wslOk = $false
try { $null = & wsl.exe --version 2>&1; $wslOk = ($LASTEXITCODE -eq 0) } catch {}
if (-not $wslOk) {
    # after the feature-enabling reboot the kernel package may still be
    # missing; try an update before declaring another reboot necessary.
    Log 'WSL not responding yet - trying wsl --update ...'
    & wsl.exe --update 2>&1 | Out-Null
    try { $null = & wsl.exe --version 2>&1; $wslOk = ($LASTEXITCODE -eq 0) } catch {}
}
if (-not $wslOk) {
    Log 'installing WSL (no distro) ...'
    & wsl.exe --install --no-distribution
    $needReboot = $true
} else {
    Log 'WSL already present.'
}

if ($needReboot) {
    Log '============================================================'
    Log ' A REBOOT is required to finish enabling WSL.'
    Log ' Reboot, then run this script again - it will pick up here.'
    Log '============================================================'
    if (-not $NoReboot) {
        $a = Read-Host 'Reboot now? (y/N)'
        if ($a -match '^[Yy]') { Restart-Computer -Force }
    }
    exit
}

# ---------------------------------------------------------------- register
$existing = @()
try { $existing = (& wsl.exe -l -q) -replace "`0", '' | Where-Object { $_ } }
catch {}
if ($existing -notcontains $Distro) {
    if (Test-Path $Vhdx) {
        Log "importing sandbox disk: $Vhdx  ->  $Distro"
        & wsl.exe --import-in-place $Distro $Vhdx
        $importRc = $LASTEXITCODE
        Log "import exit code = $importRc"
        if ($importRc -ne 0) {
            Log 'IMPORT FAILED. If this says HCS_E_SERVICE_NOT_AVAILABLE,'
            Log 'the VirtualMachinePlatform feature is still pending a'
            Log 'REAL restart (Shutdown with Fast Startup does not apply it).'
            Log 'Keeping the logon task so it retries after the next logon.'
            exit 1
        }
    } else {
        # fresh machine (or the old sandbox disk is gone): install a distro
        Log "no sandbox disk at $Vhdx - installing a fresh Ubuntu-24.04"
        & wsl.exe --install -d Ubuntu-24.04 --no-launch
        $installRc = $LASTEXITCODE
        Log "wsl --install exit code = $installRc"
        $now = @()
        try { $now = (& wsl.exe -l -q) -replace "`0", '' | Where-Object { $_ } }
        catch {}
        if ($now -contains 'Ubuntu-24.04') {
            $Distro = 'Ubuntu-24.04'
            Log "using distro $Distro"
        } else {
            Log 'fresh distro did not register; a reboot may be required.'
            exit 1
        }
    }
} else {
    Log "distro $Distro already registered."
}

# ---------------------------------------------------------------- toolchain
Log 'installing verilog toolchain inside the sandbox ...'
& wsl.exe -d $Distro -u root -- bash -lc `
    "apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq iverilog verilator yosys gtkwave >/dev/null 2>&1; apt-get install -y -qq nextpnr-ice40 >/dev/null 2>&1 || true; iverilog -V | head -n1; verilator --version; yosys -V | head -n1; command -v abc || true"

# ---------------------------------------------------------------- verify
Log '--- verification ---'
& wsl.exe -d $Distro -u root -- bash -lc `
    "echo distro=\$(. /etc/os-release; echo \$PRETTY_NAME); iverilog -V | head -n1; yosys -V | head -n1"
Log 'Done. ROX N can now run HDL builds in the sandbox.'

# one-shot: remove the logon task that finished the install after reboot
try {
    & schtasks.exe /Delete /TN 'ROX_WSL_Finish' /F 2>$null | Out-Null
    Log 'removed one-shot logon task ROX_WSL_Finish'
} catch {}
