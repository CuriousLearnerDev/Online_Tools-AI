# Layer 1 Danger Pattern Pre-scan (PowerShell)

param(
    [Parameter(Mandatory=$true)]
    [string]$ProjectPath,
    [string]$OutputDir = "",
    [switch]$Help
)

if ($Help) {
    Write-Host "Usage: .\layer1-scan.ps1 -ProjectPath <path> [-OutputDir <dir>]"
    exit 0
}

if ($OutputDir -eq "") {
    $OutputDir = Join-Path $ProjectPath "audit-output"
}

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

Write-Host ("=" * 60)
Write-Host "Layer 1: Danger Pattern Pre-scan"
Write-Host ("=" * 60)

$P0_KEYWORDS = @("ObjectInputStream", "XMLDecoder", "XStream", "JSON.parseObject", "Velocity.evaluate", "SpelExpressionParser", "Runtime.getRuntime", "ProcessBuilder", "InitialContext.lookup")
$P1_KEYWORDS = @("Statement", "createStatement", "executeQuery", "HttpURLConnection", "RestTemplate", "FileInputStream", "MultipartFile", "DocumentBuilder")

Write-Host "[*] Scanning P0 patterns..."
$p0Results = @()
$files = Get-ChildItem -Path $ProjectPath -Recurse -Include *.java,*.kt -ErrorAction SilentlyContinue

foreach ($file in $files) {
    if ($file.FullName -match "target|node_modules|\.git|build|out|\.gradle|\.idea|test") { continue }
    $lines = Get-Content $file.FullName -ErrorAction SilentlyContinue
    for ($i = 0; $i -lt $lines.Count; $i++) {
        foreach ($kw in $P0_KEYWORDS) {
            if ($lines[$i] -match [regex]::Escape($kw)) {
                $relPath = $file.FullName.Substring($ProjectPath.Length).TrimStart("\", "/")
                $p0Results += "$($relPath):$($i+1):$kw"
                break
            }
        }
    }
}

Write-Host "[*] Scanning P1 patterns..."
$p1Results = @()
foreach ($file in $files) {
    if ($file.FullName -match "target|node_modules|\.git|build|out|\.gradle|\.idea|test") { continue }
    $lines = Get-Content $file.FullName -ErrorAction SilentlyContinue
    for ($i = 0; $i -lt $lines.Count; $i++) {
        foreach ($kw in $P1_KEYWORDS) {
            if ($lines[$i] -match [regex]::Escape($kw)) {
                $relPath = $file.FullName.Substring($ProjectPath.Length).TrimStart("\", "/")
                $p1Results += "$($relPath):$($i+1):$kw"
                break
            }
        }
    }
}

Write-Host ""
Write-Host ("=" * 60)
Write-Host "Scan Results"
Write-Host ("=" * 60)

if ($p0Results.Count -gt 0) {
    Write-Host ""
    Write-Host "[!] P0 Critical: $($p0Results.Count) findings" -ForegroundColor Red
    $p0Results | Select-Object -First 10 | ForEach-Object { Write-Host "  - $_" }
    if ($p0Results.Count -gt 10) { Write-Host "  ... and $($p0Results.Count - 10) more" }
}

if ($p1Results.Count -gt 0) {
    Write-Host ""
    Write-Host "[!] P1 High: $($p1Results.Count) findings" -ForegroundColor Yellow
    $p1Results | Select-Object -First 10 | ForEach-Object { Write-Host "  - $_" }
    if ($p1Results.Count -gt 10) { Write-Host "  ... and $($p1Results.Count - 10) more" }
}

$total = $p0Results.Count + $p1Results.Count
Write-Host ""
Write-Host "[*] Total: $total danger patterns found"

$p0Path = Join-Path $OutputDir "p0-critical.md"
$p1Path = Join-Path $OutputDir "p1-high.md"

$output0 = "# P0 Critical Patterns`n`n## $($p0Results.Count) findings`n`n" + ($p0Results -join "`n")
$output1 = "# P1 High Patterns`n`n## $($p1Results.Count) findings`n`n" + ($p1Results -join "`n")

$output0 | Out-File -FilePath $p0Path -Encoding UTF8
$output1 | Out-File -FilePath $p1Path -Encoding UTF8

Write-Host ""
Write-Host "[OK] Reports saved to: $OutputDir" -ForegroundColor Green