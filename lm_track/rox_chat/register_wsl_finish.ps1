# Registers a one-shot logon task that finishes the WSL install after the
# pending reboot. setup_wsl.ps1 deletes this task when it succeeds.
$wrapper = "C:\Users\gamel\.rox\finish_wsl.cmd"
& schtasks.exe /Create /SC ONLOGON /TN ROX_WSL_Finish /TR $wrapper /RL HIGHEST /F
Write-Output "--- registered ---"
& schtasks.exe /Query /TN ROX_WSL_Finish /FO LIST
