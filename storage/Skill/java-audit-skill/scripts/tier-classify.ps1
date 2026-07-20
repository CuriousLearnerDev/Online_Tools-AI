# Tier 分类脚本 (PowerShell 版本)

param(
    [Parameter(Mandatory=$true)]
    [string]$ProjectPath,
    [string]$OutputDir = "",
    [switch]$Help
)

if ($Help) {
    Write-Host "Tier 分类脚本"
    Write-Host "用法: .\tier-classify.ps1 -ProjectPath <项目路径>"
    exit 0
}

if ($OutputDir -eq "") {
    $OutputDir = Join-Path $ProjectPath "audit-output"
}

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

Write-Host ("=" * 60)
Write-Host "Phase 1: Tier 分类"
Write-Host ("=" * 60)

# 分类统计
$t1Count = 0; $t1Loc = 0
$t2Count = 0; $t2Loc = 0
$t3Count = 0; $t3Loc = 0
$t1Files = @()
$t2Files = @()
$t3Files = @()

$files = Get-ChildItem -Path $ProjectPath -Recurse -Include *.java,*.kt -ErrorAction SilentlyContinue

foreach ($file in $files) {
    if ($file.FullName -match "target|node_modules|\.git|build|out|\.gradle|\.idea|test") { continue }
    
    $content = Get-Content $file.FullName -Raw -ErrorAction SilentlyContinue
    if (-not $content) { $content = "" }
    
    $relPath = $file.FullName.Substring($ProjectPath.Length).TrimStart('\', '/')
    $lines = (Get-Content $file.FullName | Measure-Object -Line).Lines
    
    # T1: Controller/Filter
    if ($content -match "@Controller|@RestController|@WebServlet|extends Filter") {
        $t1Count++; $t1Loc += $lines; $t1Files += $relPath
    }
    # T2: Service/DAO
    elseif ($content -match "@Service|@Repository|@Mapper|@Dao|@Component") {
        $t2Count++; $t2Loc += $lines; $t2Files += $relPath
    }
    # T3: Entity/VO
    elseif ($content -match "@Entity|@Table|@Data|data class") {
        $t3Count++; $t3Loc += $lines; $t3Files += $relPath
    }
    else {
        $t2Count++; $t2Loc += $lines; $t2Files += $relPath
    }
}

# 计算 EALOC
$ealoc = $t1Loc + $t2Loc * 0.5 + $t3Loc * 0.1
$agents = [Math]::Ceiling($ealoc / 15000)
if ($agents -lt 1) { $agents = 1 }

Write-Host ""
Write-Host "[*] Tier 分类统计:"
Write-Host "  T1: $t1Count 文件, $t1Loc LOC"
Write-Host "  T2: $t2Count 文件, $t2Loc LOC"
Write-Host "  T3: $t3Count 文件, $t3Loc LOC"
Write-Host ""
Write-Host "[*] EALOC = $([Math]::Round($ealoc)), 建议 Agent 数: $agents"

# 生成报告
$reportPath = Join-Path $OutputDir "tier-classification.md"
@"
# Tier 分类结果

| Tier | 文件数 | LOC | 权重 |
|------|--------|-----|------|
| T1 | $t1Count | $t1Loc | 1.0 |
| T2 | $t2Count | $t2Loc | 0.5 |
| T3 | $t3Count | $t3Loc | 0.1 |

**EALOC**: $([Math]::Round($ealoc))  
**Agent 数量**: $agents
"@ | Out-File -FilePath $reportPath -Encoding UTF8

Write-Host ""
Write-Host "[OK] 报告: $reportPath" -ForegroundColor Green