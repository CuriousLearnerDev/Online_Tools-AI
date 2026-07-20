# Coverage Gate Check Script (PowerShell)

param(
    [Parameter(Mandatory=$true)]
    [string]$ProjectPath,
    [Parameter(Mandatory=$true)]
    [string]$ReviewedFile,
    [string]$OutputDir = "",
    [switch]$Help
)

if ($Help) {
    Write-Host "Usage: .\coverage-check.ps1 -ProjectPath <path> -ReviewedFile <file>"
    exit 0
}

if ($OutputDir -eq "") {
    $OutputDir = Join-Path $ProjectPath "audit-output"
}

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

Write-Host ("=" * 60)
Write-Host "Phase 2.5: Coverage Gate Check"
Write-Host ("=" * 60)

$actualFiles = @{}
$t1Files = @{}

$files = Get-ChildItem -Path $ProjectPath -Recurse -Include *.java,*.kt -ErrorAction SilentlyContinue

foreach ($file in $files) {
    if ($file.FullName -match "target|node_modules|\.git|build|out|\.gradle|\.idea|test") { continue }
    
    $fileName = $file.Name
    $actualFiles[$fileName] = $true
    
    $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
    if (-not $content) { $content = "" }
    
    if ($content -match "@Controller|@RestController|@WebServlet|extends Filter") {
        $t1Files[$fileName] = $true
    }
}

$actualCount = $actualFiles.Count
$t1Count = $t1Files.Count

$reviewedFiles = @{}
if (Test-Path $ReviewedFile) {
    $content = Get-Content $ReviewedFile -Raw -ErrorAction SilentlyContinue
    $matches = [regex]::Matches($content, '[a-zA-Z0-9_-]+\.(java|kt)')
    foreach ($m in $matches) {
        $reviewedFiles[$m.Value] = $true
    }
}

$reviewedCount = $reviewedFiles.Count

$missedCount = 0
$missedT1 = @()

foreach ($f in $actualFiles.Keys) {
    if (-not $reviewedFiles.ContainsKey($f)) {
        $missedCount++
    }
}

foreach ($f in $t1Files.Keys) {
    if (-not $reviewedFiles.ContainsKey($f)) {
        $missedT1 += $f
    }
}

$coverage = [Math]::Round(($actualCount - $missedCount) / $actualCount * 100, 1)
$t1Coverage = [Math]::Round(($t1Count - $missedT1.Count) / $t1Count * 100, 1)

Write-Host ""
Write-Host "[*] Coverage Stats:"
Write-Host "  Total files: $actualCount"
Write-Host "  Reviewed: $reviewedCount"
Write-Host "  Coverage: $coverage%"
Write-Host ""
Write-Host "[*] T1 Coverage: $($t1Count - $missedT1.Count)/$t1Count = $t1Coverage%"

$passed = ($t1Coverage -eq 100) -and ($coverage -ge 90)

if ($passed) {
    Write-Host ""
    Write-Host "[OK] Gate passed" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "[!] Gate failed" -ForegroundColor Red
    if ($t1Coverage -lt 100) {
        Write-Host "  - T1 coverage $t1Coverage% < 100%" -ForegroundColor Red
        Write-Host "  Missing T1 files:"
        $missedT1 | Select-Object -First 20 | ForEach-Object { Write-Host "    - $_" }
    }
    if ($coverage -lt 90) {
        Write-Host "  - Total coverage $coverage% < 90%" -ForegroundColor Red
    }
}

$reportPath = Join-Path $OutputDir "coverage-report.md"
$status = if ($passed) { "PASSED" } else { "FAILED" }
$reportContent = "# Coverage Report`n`n| Metric | Value |`n|--------|-------|`n| Total files | $actualCount |`n| Reviewed | $reviewedCount |`n| Coverage | $coverage% |`n| T1 Coverage | $t1Coverage% |`n`n## Status: $status"
$reportContent | Out-File -FilePath $reportPath -Encoding UTF8

Write-Host ""
Write-Host "[OK] Report: $reportPath" -ForegroundColor Green

if ($passed) { exit 0 } else { exit 1 }