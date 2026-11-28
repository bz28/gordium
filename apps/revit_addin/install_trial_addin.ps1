# Installs the trial build of the Gordium Revit add-in for the current Windows user (docs/revit/windows_trial_runbook.md,
# days 3 and 4). Builds it, copies the build to one fixed folder (%LOCALAPPDATA%\Gordium\addin\<version>\current),
# writes the clone's path beside it, and writes Revit's manifest (.addin) pointing at it.
# Revit locks the files it loads, so this refuses while Revit is running: close Revit first. Revit asked "Always Load"
# again after every rebuild of an unsigned add-in, in a new folder or the same one (seen on the trial laptop,
# 2026-11-19), so each build is signed with this machine's own certificate (trust_trial_addin.ps1, run once): Revit
# trusts the publisher, and doesn't ask.
# -Python names the Python to run for a clone with no venv of its own (a git worktree): written beside the build
# (gordium_python.txt); the add-in then points it at this clone's packages (PYTHONPATH), so the code run is this clone's.
# By default it installs the build an architect gets (Ben, 2026-11-23, for demos to architects): the Gordium tab shows
# Check, Results and Help only. The developer tools (the Trial panel: Check box house, Record scenes, Read inside,
# Record houses) come back with -Dev (a trial build, -p:GordiumTrial=true: the Trial panel always), or in any build
# with GORDIUM_TRIAL=1 set in the environment Revit starts in. -Architect is the default, kept so older notes work.
# The request files (run_request.json and the others) work in both.
param([string]$Revit = "2027", [string]$Python = "", [switch]$Dev, [switch]$Architect)
$ErrorActionPreference = "Stop"
$tfm = @{ "2027" = "net10.0-windows"; "2026" = "net8.0-windows" }[$Revit]
if (-not $tfm) { throw "Revit $Revit is not one the add-in is built for (2026, 2027)" }
if (Get-Process Revit -ErrorAction SilentlyContinue) { throw "Revit is running: close it first (it locks the add-in's files)" }
$project = Join-Path $PSScriptRoot "src\Gordium.Revit.Addin"
$clone = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if ($Dev -and $Architect) { throw "-Dev and -Architect: choose one (-Dev adds the Trial panel's developer tools)" }
$trialBuild = if ($Dev) { "true" } else { "false" }
# Compile, then freeze (rule_format/published.py): each rulebook's certificate (state laws' and zoning districts') is written from exactly the files
# installed, with the Python the add-in runs (gordium_python.txt pointed at this clone's packages, or its venv), so the
# worker reads laws validated once. A law with problems is refused here, before anything is installed.
$python = if ($Python) { (Resolve-Path $Python).Path } else { Join-Path $clone ".venv\Scripts\python.exe" }
if (-not (Test-Path $python)) { throw "no Python at $python (give -Python for a clone with no venv)" }
$packages = (Get-ChildItem -Directory (Join-Path $clone "packages") | Sort-Object Name | ForEach-Object { $_.FullName }) -join ";"
$kept = $env:PYTHONPATH
try {
    $env:PYTHONPATH = $packages
    & $python -m rule_format publish
    if ($LASTEXITCODE -ne 0) { throw "python -m rule_format publish failed: a rulebook can't be published (see above)" }
} finally { $env:PYTHONPATH = $kept }
# -t:Rebuild: the trial switch is compiled in, so a build left by the other kind is never reused
dotnet build $project -c Release -f $tfm -v q -t:Rebuild "-p:GordiumTrial=$trialBuild"
if ($LASTEXITCODE -ne 0) { throw "build failed" }
$target = Join-Path $env:LOCALAPPDATA "Gordium\addin\$Revit\current"
if (Test-Path $target) { Remove-Item (Join-Path $target "*") -Recurse -Force }
New-Item -ItemType Directory -Force $target | Out-Null
Copy-Item (Join-Path $project "bin\Release\$tfm\*") $target -Recurse
[IO.File]::WriteAllText((Join-Path $target "gordium_clone.txt"), $clone, (New-Object Text.UTF8Encoding $false))
if ($Python) {
    if (-not (Test-Path $Python)) { throw "no Python at $Python" }
    [IO.File]::WriteAllText((Join-Path $target "gordium_python.txt"), (Resolve-Path $Python).Path, (New-Object Text.UTF8Encoding $false))
}
# signed with this machine's trial certificate (trust_trial_addin.ps1), so Revit doesn't ask "Always Load" after every
# build; without the certificate the build is installed unsigned, and Revit asks
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
    Where-Object { $_.Subject -eq "CN=Gordium trial add-in (this machine)" -and $_.NotAfter -gt (Get-Date) } |
    Sort-Object NotAfter -Descending | Select-Object -First 1
if ($cert) {
    foreach ($dll in Get-ChildItem $target -Filter "Gordium*.dll") {
        $signed = Set-AuthenticodeSignature -FilePath $dll.FullName -Certificate $cert -HashAlgorithm SHA256
        if ($signed.Status -ne "Valid") { throw "signing $($dll.Name) gave $($signed.Status): $($signed.StatusMessage)" }
    }
} else { "No trial certificate (run trust_trial_addin.ps1 once): installed unsigned, so Revit will ask whether to load it" }
$manifestDir = Join-Path $env:APPDATA "Autodesk\Revit\Addins\$Revit"
New-Item -ItemType Directory -Force $manifestDir | Out-Null
$manifest = @"
<?xml version="1.0" encoding="utf-8"?>
<RevitAddIns>
  <AddIn Type="Application">
    <Name>Gordium</Name>
    <Assembly>$target\Gordium.Revit.Addin.dll</Assembly>
    <AddInId>6f1d3c0e-5a8b-4f7e-9c2d-1b7a4e9d2c51</AddInId>
    <FullClassName>Gordium.Revit.Addin.App</FullClassName>
    <VendorId>Gordium</VendorId>
    <VendorDescription>Gordium: zoning and egress checks</VendorDescription>
  </AddIn>
</RevitAddIns>
"@
[IO.File]::WriteAllText((Join-Path $manifestDir "Gordium.addin"), $manifest, (New-Object Text.UTF8Encoding $false))
"Installed $tfm $(if ($Architect) { 'architect' } else { 'trial' }) build for Revit $Revit at $target (clone: $clone), signed: $([bool]$cert). Start Revit."
