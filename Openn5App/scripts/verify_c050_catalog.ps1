# C-050 M1 verification (OP5, no TIA needed): the workspace catalog's web/app handling, through the real
# WorkspaceCatalog of a built Openn5.exe loaded by reflection (no Siemens type is touched). It writes synthetic
# workspaces - one good web application and one defect each - scans them and checks:
#   - a good manifest is Ready and Uploadable, never Importable; its resources are Ignored; a file the manifest
#     does not list is noted "never uploaded";
#   - a resource of another size, of the same size but other bytes, or missing makes the manifest Invalid;
#   - two default pages make it Invalid; a manifest outside <PLC>\Web applications\<app>\ is Invalid;
#   - a manifest of an older run is Stale; resources with no manifest are noted "nothing uploads it".
# Usage: powershell -File scripts\verify_c050_catalog.ps1 [-Exe <path to Openn5.exe>] [-Work <scratch folder>]
# Exit code = verdict (0 = every check passed).
param(
    [string]$Exe = (Join-Path $PSScriptRoot "..\bin\Debug\Openn5.exe"),
    [string]$Work = (Join-Path $env:TEMP "openn5_c050_catalog")
)
$ErrorActionPreference = "Stop"
$run = "20261028-140000-c050"

function Write-Text([string]$path, [string]$text) {
    New-Item -ItemType Directory -Force (Split-Path $path) | Out-Null
    [IO.File]::WriteAllText($path, $text, (New-Object Text.UTF8Encoding($false)))
}

function New-Workspace([string]$case, [string]$manifestRun = $run, [string[]]$defaults = @("index.html"),
                       [string]$manifestRel = "n1\Web applications\safety", [bool]$writeManifest = $true, [string]$extra = "") {
    $ws = Join-Path $Work $case
    if (Test-Path $ws) { Remove-Item -Recurse -Force $ws }
    Write-Text "$ws\.openn\workspace.openn.config" ("#!openn`r`n#! contract: 1`r`n#! project: 8FVT`r`n#! producer: Pipeline5 5.0`r`n" +
        "#! generated: 2026-10-28T14:00:00Z`r`n#! run: $run`r`n#! plcs: n1`r`n#! templates: Templates`r`n#!end`r`n")
    $app = "$ws\n1\Web applications\safety"
    $resources = [ordered]@{ "index.html" = @("<!doctype html><title>safety</title>", "text/html");
                             "app.js" = @("console.log('safety');`n", "application/javascript");
                             "plant.json" = @("{`"schema`": 1}`n", "application/json") }
    $rows = @("name,media_type,size,sha256,visibility,default_page")
    foreach ($name in $resources.Keys) {
        Write-Text "$app\$name" $resources[$name][0]
        $file = Get-Item "$app\$name"
        $hash = (Get-FileHash -Algorithm SHA256 $file.FullName).Hash.ToLowerInvariant()
        $default = if ($defaults -contains $name) { "yes" } else { "" }
        $rows += "$name,$($resources[$name][1]),$($file.Length),$hash,public,$default"
    }
    if ($extra) { Write-Text "$app\$extra" "not listed" }
    if ($writeManifest) {
        Write-Text "$ws\$manifestRel\webapp.manifest.csv" ("#!openn`r`n#! kind: web/app`r`n#! schema: 1`r`n#! producer: Pipeline5 5.0 (phase 650)`r`n" +
            "#! generated: 2026-10-28T14:00:00Z`r`n#! run: $manifestRun`r`n#! project: 8FVT`r`n#! plc: n1`r`n" +
            "#! target: Web applications/safety`r`n#! name: safety`r`n#! source: webui`r`n#!end`r`n" + ($rows -join "`r`n") + "`r`n")
    }
    return $app
}

$failures = 0
function Check([bool]$condition, [string]$what) {
    if ($condition) { "  PASS  $what" } else { "  FAIL  $what"; $script:failures++ }
}

$asm = [Reflection.Assembly]::LoadFrom((Resolve-Path $Exe))
$catalogType = $asm.GetType("Openn._00_Contract.WorkspaceCatalog")
function Scan([string]$case) { $catalogType.GetMethod("Scan").Invoke($null, [object[]]@([string](Join-Path $Work $case))) }
function Item($catalog, [string]$rel) { $catalog.Items | Where-Object { $_.RelativePath -eq $rel } | Select-Object -First 1 }
$manifest = "n1/Web applications/safety/webapp.manifest.csv"

"== verify_c050_catalog ($Exe) =="
New-Workspace "ok" -extra "notes.txt" | Out-Null
$c = Scan "ok"; $m = Item $c $manifest
Check ($m.Status.ToString() -eq "Ready" -and $m.Uploadable -and -not $m.Importable) "a good manifest is Ready, Uploadable, not Importable"
Check (@($c.Items | Where-Object { $_.RelativePath -like "n1/Web applications/safety/*" -and $_.RelativePath -ne $manifest -and $_.Status.ToString() -ne "Ignored" }).Count -eq 0) "its resources are Ignored"
Check ((Item $c "n1/Web applications/safety/notes.txt").Notes -join " " -match "never uploaded") "an unlisted file is noted never uploaded"
Check (@($c.InImportOrder()).Count -eq 0) "Import Workspace has nothing to import"
Check ((@($c.Summary()) -join "`n") -match "1 web application\(s\), 1 uploadable") "the summary counts the uploadable app"

$app = New-Workspace "tampered"; [IO.File]::AppendAllText("$app\plant.json", " ")
$m = Item (Scan "tampered") $manifest
Check ($m.Status.ToString() -eq "Invalid" -and ($m.Notes -join " ") -match "plant.json' is 15 bytes") "a resource of another size: Invalid"

$app = New-Workspace "same_size"; $bytes = [IO.File]::ReadAllBytes("$app\app.js"); $bytes[0] = [byte][char]'C'; [IO.File]::WriteAllBytes("$app\app.js", $bytes)
$m = Item (Scan "same_size") $manifest
Check ($m.Status.ToString() -eq "Invalid" -and ($m.Notes -join " ") -match "app.js' changed since the generation") "same size, other bytes: Invalid (SHA-256)"

$app = New-Workspace "missing"; Remove-Item "$app\app.js"
$m = Item (Scan "missing") $manifest
Check ($m.Status.ToString() -eq "Invalid" -and ($m.Notes -join " ") -match "app.js' is missing") "a missing resource: Invalid"

New-Workspace "two_defaults" -defaults @("index.html", "app.js") | Out-Null
$m = Item (Scan "two_defaults") $manifest
Check ($m.Status.ToString() -eq "Invalid" -and ($m.Notes -join " ") -match "2 resources are marked default_page") "two default pages: Invalid"

New-Workspace "misplaced" -manifestRel "n1\Web applications" | Out-Null
$m = Item (Scan "misplaced") "n1/Web applications/webapp.manifest.csv"
Check ($m.Status.ToString() -eq "Invalid" -and -not $m.Uploadable) "a manifest outside its app folder: Invalid"

New-Workspace "stale" -manifestRun "20261027-090000-old0" | Out-Null
$m = Item (Scan "stale") $manifest
Check ($m.Status.ToString() -eq "Stale" -and -not $m.Uploadable) "a manifest of an older run: Stale, not uploadable"

New-Workspace "no_manifest" -writeManifest $false | Out-Null
$r = Item (Scan "no_manifest") "n1/Web applications/safety/index.html"
Check ($r.Status.ToString() -eq "Ignored" -and ($r.Notes -join " ") -match "nothing uploads it") "resources with no manifest: noted"

"  -> " + $(if ($failures -eq 0) { "all checks passed" } else { "$failures check(s) FAILED" })
exit $(if ($failures -eq 0) { 0 } else { 1 })
