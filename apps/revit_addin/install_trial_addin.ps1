# Installs the trial build of the Gordium Revit add-in for the current Windows user (docs/revit/windows_trial_runbook.md,
# days 3 and 4). Builds it, copies the build to its own folder (Revit locks the files it loads, so the clone's build
# folder stays free to rebuild), writes the clone's path beside it, and writes Revit's manifest (.addin) pointing at it.
# Then start Revit (on the trial laptop, a running Revit 2027.4 picked the add-in up without a restart and never asked
# "Always Load"; another Revit may need a restart, or ask once whether to load it: answer "Always Load").
param([string]$Revit = "2027")
$ErrorActionPreference = "Stop"
$tfm = @{ "2027" = "net10.0-windows"; "2026" = "net8.0-windows" }[$Revit]
if (-not $tfm) { throw "Revit $Revit is not one the add-in is built for (2026, 2027)" }
$project = Join-Path $PSScriptRoot "src\Gordium.Revit.Addin"
$clone = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
dotnet build $project -c Release -f $tfm -v q
if ($LASTEXITCODE -ne 0) { throw "build failed" }
$stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$target = Join-Path $env:LOCALAPPDATA "Gordium\addin\$Revit\$stamp"
New-Item -ItemType Directory -Force $target | Out-Null
Copy-Item (Join-Path $project "bin\Release\$tfm\*") $target -Recurse
[IO.File]::WriteAllText((Join-Path $target "gordium_clone.txt"), $clone, (New-Object Text.UTF8Encoding $false))
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
"Installed $tfm build for Revit $Revit at $target (clone: $clone). Start Revit, or check its Gordium tab if it is running; if the tab is missing, restart Revit."
