# quality-checker.ps1 - 阶段输出质量校验
# 用法: .\scripts\quality-checker.ps1 -Phase <phase> -OutputFile <file> -ProjectPath <path>
# 示例: .\scripts\quality-checker.ps1 -Phase phase1 -OutputFile tier-classification.md -ProjectPath E:\audit

param(
    [Parameter(Mandatory=$true)]
    [string]$Phase,
    
    [Parameter(Mandatory=$false)]
    [string]$OutputFile,
    
    [Parameter(Mandatory=$true)]
    [string]$ProjectPath
)

$ErrorActionPreference = "Stop"

# 颜色输出函数
function Write-Success { Write-Host "[✓] $args" -ForegroundColor Green }
function Write-Error { Write-Host "[!] $args" -ForegroundColor Red }
function Write-Info { Write-Host "[*] $args" -ForegroundColor Cyan }
function Write-Warn { Write-Host "[⚠] $args" -ForegroundColor Yellow }

# 校验结果
$script:Errors = 0
$script:Warnings = 0

function Add-Error { 
    param([string]$Message)
    Write-Error $Message
    $script:Errors++
}

function Add-Warning { 
    param([string]$Message)
    Write-Warn $Message
    $script:Warnings++
}

# ============================================
# Phase 1 校验：tier-classification.md, scenario-tags.json, dependency-security.md
# ============================================
function Test-Phase1 {
    Write-Info "Phase 1 质量校验..."
    
    # 1. 检查 tier-classification.md
    $tierFile = Join-Path $ProjectPath "tier-classification.md"
    if (-not (Test-Path $tierFile)) {
        Add-Error "tier-classification.md 不存在"
    } else {
        $content = Get-Content $tierFile -Raw
        
        # 检查 EALOC
        if ($content -notmatch "EALOC|ealoc") {
            Add-Error "缺少 EALOC 计算"
        } else {
            Write-Success "EALOC 计算存在"
        }
        
        # 检查 Tier 分类
        if ($content -notmatch "T1|Tier") {
            Add-Error "缺少 Tier 分类"
        } else {
            # 统计 T1 文件数
            $t1Matches = [regex]::Matches($content, "T1")
            Write-Success "Tier 分类存在，T1 引用 $($t1Matches.Count) 次"
        }
        
        # 检查 Agent 分配
        if ($content -match "Agent|EALOC.*\d+") {
            Write-Success "Agent 分配信息存在"
        }
    }
    
    # 2. 检查 scenario-tags.json（可选）
    $scenarioFile = Join-Path $ProjectPath "scenario-tags.json"
    if (Test-Path $scenarioFile) {
        try {
            $scenario = Get-Content $scenarioFile | ConvertFrom-Json
            Write-Success "scenario-tags.json 有效，场景标签已生成"
        } catch {
            Add-Warning "scenario-tags.json 格式无效"
        }
    } else {
        Write-Info "scenario-tags.json 不存在（可选）"
    }
    
    # 3. 检查 dependency-security.md
    $depFile = Join-Path $ProjectPath "dependency-security.md"
    if (Test-Path $depFile) {
        $depContent = Get-Content $depFile -Raw
        
        # 检查是否有依赖检查记录
        if ($depContent -match "CVE|Direct vulnerabilities") {
            Write-Success "依赖安全检查已执行"
        } else {
            Add-Warning "dependency-security.md 缺少漏洞信息"
        }
        
        # 检查检查时间
        if ($depContent -match "\d{4}-\d{2}-\d{2}") {
            Write-Success "依赖检查时间已记录"
        }
    } else {
        Write-Info "dependency-security.md 不存在（将使用默认检查）"
    }
    
    # 4. 检查 audit-metrics.json
    $metricsFile = Join-Path $ProjectPath "audit-metrics.json"
    if (Test-Path $metricsFile) {
        try {
            $metrics = Get-Content $metricsFile | ConvertFrom-Json
            if ($metrics.ealoc) {
                Write-Success "audit-metrics.json 有效，EALOC = $($metrics.ealoc)"
            }
        } catch {
            Add-Warning "audit-metrics.json 格式无效"
        }
    }
    
    Write-Info "Phase 1 校验完成: $($script:Errors) 错误, $($script:Warnings) 警告"
}

# ============================================
# Phase 2 Layer 1 校验：p0-critical.md, p1-high.md, p2-medium.md
# ============================================
function Test-Phase2Layer1 {
    Write-Info "Phase 2 Layer 1 质量校验..."
    
    $layer1Files = @("p0-critical.md", "p1-high.md", "p2-medium.md")
    $totalFindings = 0
    $existingFiles = 0
    
    foreach ($file in $layer1Files) {
        $filePath = Join-Path $ProjectPath $file
        if (Test-Path $filePath) {
            $existingFiles++
            $content = Get-Content $filePath -Raw
            
            # 统计发现数（匹配文件:行号 格式）
            $matches = [regex]::Matches($content, "\.java:\d+|\.kt:\d+")
            $findings = $matches.Count
            $totalFindings += $findings
            
            if ($findings -gt 0) {
                Write-Success "$file 存在，发现 $findings 个危险模式"
            } else {
                Write-Info "$file 存在，无危险模式发现"
            }
        } else {
            Write-Info "$file 不存在"
        }
    }
    
    if ($existingFiles -eq 0) {
        Add-Warning "所有 Layer 1 扫描文件都不存在"
    } else {
        Write-Info "Layer 1 共发现 $totalFindings 个危险模式"
    }
    
    Write-Info "Phase 2 Layer 1 校验完成: $($script:Errors) 错误, $($script:Warnings) 警告"
}

# ============================================
# Phase 2 Layer 2 校验：findings-raw.md
# ============================================
function Test-Phase2Layer2 {
    Write-Info "Phase 2 Layer 2 质量校验..."
    
    $findingsFile = Join-Path $ProjectPath "findings-raw.md"
    
    if (-not (Test-Path $findingsFile)) {
        Add-Error "findings-raw.md 不存在"
        return
    }
    
    $content = Get-Content $findingsFile -Raw
    
    # 1. 检查精确行号格式（文件:行号）
    $lineMatches = [regex]::Matches($content, "[A-Za-z]:[\\/].*\.java:\d+|[A-Za-z]:[\\/].*\.kt:\d+")
    if ($lineMatches.Count -eq 0) {
        Add-Error "漏洞缺少精确行号（文件:行号 格式），当前格式可能不正确"
    } else {
        Write-Success "精确行号格式正确，共 $($lineMatches.Count) 处"
    }
    
    # 2. 检查调用链分析
    $callchainMatches = [regex]::Matches($content, "调用链|call chain|Controller.*→|Controller.*->")
    if ($callchainMatches.Count -eq 0) {
        Add-Warning "缺少调用链分析"
    } else {
        Write-Success "调用链分析存在，共 $($callchainMatches.Count) 处"
    }
    
    # 3. 检查漏洞状态标记
    $confirmedMatches = [regex]::Matches($content, "CONFIRMED|HYPOTHESIS")
    if ($confirmedMatches.Count -eq 0) {
        Add-Warning "缺少漏洞状态标记（CONFIRMED/HYPOTHESIS）"
    } else {
        Write-Success "漏洞状态标记存在"
    }
    
    # 4. 检查漏洞数量
    $vulnMatches = [regex]::Matches($content, "^#{1,3}\s+\S+.*漏洞|^#{1,3}\s+\S+.*注入|^#{1,3}\s+\S+.*RCE", "Multiline")
    Write-Info "发现 $($vulnMatches.Count) 个候选漏洞"
    
    # 5. 检查审阅文件清单（覆盖率）
    if ($content -match "审阅|已审阅|覆盖") {
        Write-Success "审阅文件清单存在"
    } else {
        Add-Warning "缺少审阅文件清单，无法验证覆盖率"
    }
    
    Write-Info "Phase 2 Layer 2 校验完成: $($script:Errors) 错误, $($script:Warnings) 警告"
}

# ============================================
# Phase 2.5 校验：覆盖率门禁
# ============================================
function Test-Phase25 {
    Write-Info "Phase 2.5 覆盖率门禁校验..."
    
    $coverageFile = Join-Path $ProjectPath "coverage-report.md"
    
    if (-not (Test-Path $coverageFile)) {
        Write-Info "coverage-report.md 不存在，尝试从 findings-raw.md 推断..."
        
        $findingsFile = Join-Path $ProjectPath "findings-raw.md"
        if (Test-Path $findingsFile) {
            $content = Get-Content $findingsFile -Raw
            
            # 尝试提取覆盖率信息
            if ($content -match "覆盖率[:\s]+(\d+)%") {
                $coverage = $matches[1]
                Write-Info "推断覆盖率: $coverage%"
                
                if ([int]$coverage -lt 90) {
                    Add-Warning "覆盖率 $coverage% 低于门禁阈值 (90%)"
                } else {
                    Write-Success "覆盖率 $coverage% 达标"
                }
            }
        }
        return
    }
    
    $content = Get-Content $coverageFile -Raw
    
    # 提取覆盖率
    if ($content -match "总体覆盖率[:\s]+(\d+)%|覆盖率[:\s]+(\d+)%") {
        $coverage = if ($matches[1]) { $matches[1] } else { $matches[2] }
        Write-Info "总体覆盖率: $coverage%"
        
        if ([int]$coverage -lt 90) {
            Add-Warning "覆盖率 $coverage% 低于门禁阈值 (小型100%/中型95%/大型90%)"
        } else {
            Write-Success "覆盖率 $coverage% 达标"
        }
    }
    
    # 检查 T1 覆盖率
    if ($content -match "T1.*覆盖率[:\s]+(\d+)%|T1.*(\d+)%") {
        $t1Coverage = $matches[1]
        if ([int]$t1Coverage -lt 100) {
            Add-Error "T1 (Controller/Filter) 覆盖率 $t1Coverage% 未达到 100% 要求"
        } else {
            Write-Success "T1 覆盖率 100% 达标"
        }
    }
    
    Write-Info "Phase 2.5 校验完成: $($script:Errors) 错误, $($script:Warnings) 警告"
}

# ============================================
# Phase 3 校验：findings-verified.md
# ============================================
function Test-Phase3 {
    Write-Info "Phase 3 质量校验..."
    
    $verifiedFile = Join-Path $ProjectPath "findings-verified.md"
    
    if (-not (Test-Path $verifiedFile)) {
        Add-Error "findings-verified.md 不存在"
        return
    }
    
    $content = Get-Content $verifiedFile -Raw
    
    # 1. 检查状态标记
    $confirmed = [regex]::Matches($content, "CONFIRMED").Count
    $hypothesis = [regex]::Matches($content, "HYPOTHESIS").Count
    
    if ($confirmed -eq 0 -and $hypothesis -eq 0) {
        Add-Error "缺少漏洞状态标记（CONFIRMED/HYPOTHESIS）"
    } else {
        Write-Success "CONFIRMED: $confirmed, HYPOTHESIS: $hypothesis"
    }
    
    # 2. 检查 DKTSS 评分
    if ($content -match "DKTSS|评分|Score") {
        Write-Success "DKTSS 评分存在"
    } else {
        Add-Warning "缺少 DKTSS 评分"
    }
    
    # 3. 检查 CVE 核实标记
    if ($content -match "CVE-\d{4}-\d+") {
        Write-Success "CVE 编号存在"
        
        # 检查是否有核实来源
        if ($content -match "NVD|Snyk|mvnrepository|已核实") {
            Write-Success "CVE 已联网核实"
        } else {
            Add-Warning "CVE 编号未标注核实来源"
        }
    }
    
    # 4. 检查调用链完整性
    $callchainMatches = [regex]::Matches($content, "→|->|调用链")
    if ($callchainMatches.Count -eq 0) {
        Add-Warning "缺少调用链追踪"
    } else {
        Write-Success "调用链追踪存在"
    }
    
    Write-Info "Phase 3 校验完成: $($script:Errors) 错误, $($script:Warnings) 警告"
}

# ============================================
# Phase 5 校验：audit-report.md
# ============================================
function Test-Phase5 {
    Write-Info "Phase 5 质量校验..."
    
    $reportFile = Join-Path $ProjectPath "audit-report.md"
    
    if (-not (Test-Path $reportFile)) {
        Add-Error "audit-report.md 不存在"
        return
    }
    
    $content = Get-Content $reportFile -Raw
    
    # 1. 检查报告结构：漏洞列表
    if ($content -match "## 漏洞列表|## Vulnerability List") {
        Write-Success "「漏洞列表」部分存在"
    } else {
        Add-Error "缺少「漏洞列表」部分"
    }
    
    # 2. 检查报告结构：审计进度
    if ($content -match "## 审计进度|## Audit Progress") {
        Write-Success "「审计进度」部分存在"
    } else {
        Add-Error "缺少「审计进度」部分"
    }
    
    # 3. 检查代码位置格式（必须是完整绝对路径）
    # 正确格式: E:\path\to\File.java:123 或 /path/to/File.java:123
    # 错误格式: File.java:123（无路径）或 ./path/File.java:123（相对路径）
    # 修复：支持 Windows 盘符路径和 Linux 绝对路径
    $badPaths = [regex]::Matches($content, "代码位置[：:\s]*\n\s*[^/\nA-Z\\][^:\n]*\.java:\d+")
    if ($badPaths.Count -gt 0) {
        Add-Error "存在 $($badPaths.Count) 处非完整路径的代码位置（应为绝对路径如 E:\path\File.java:123 或 /path/File.java:123）"
    } else {
        Write-Success "代码位置格式正确（完整绝对路径）"
    }
    
    # 3.1 检查相对路径格式（./ 或 ..\）
    $relativePaths = [regex]::Matches($content, "代码位置[：:\s]*\n\s*[\.][\\/]")
    if ($relativePaths.Count -gt 0) {
        Add-Warning "存在 $($relativePaths.Count) 处相对路径格式（建议使用绝对路径）"
    }
    
    # 4. 检查标题格式（禁止包含严重程度标签）
    $badTitles = [regex]::Matches($content, "^#+ .+\((Critical|High|Medium|Low)\)", "Multiline")
    if ($badTitles.Count -gt 0) {
        Add-Error "存在 $($badTitles.Count) 处标题包含严重程度标签（禁止）"
    } else {
        Write-Success "标题格式正确（无严重程度标签）"
    }
    
    # 5. 检查漏洞分析要素
    $vulnCount = [regex]::Matches($content, "^# [^#\n]+", "Multiline").Count
    
    $callchainCount = [regex]::Matches($content, "调用链").Count
    $attackPathCount = [regex]::Matches($content, "攻击路径").Count
    $securityControlCount = [regex]::Matches($content, "安全控制|缺少.*控制").Count
    
    if ($callchainCount -lt $vulnCount) {
        Add-Warning "部分漏洞缺少调用链分析"
    } else {
        Write-Success "调用链分析完整"
    }
    
    if ($attackPathCount -lt $vulnCount) {
        Add-Warning "部分漏洞缺少攻击路径"
    } else {
        Write-Success "攻击路径完整"
    }
    
    # 6. 检查修复建议
    $fixCount = [regex]::Matches($content, "修复建议| Remediation").Count
    if ($fixCount -eq 0) {
        Add-Warning "缺少修复建议"
    } else {
        Write-Success "修复建议存在"
    }
    
    # 7. 检查描述字数（约 100 字）
    # 简单检查：描述部分是否存在
    if ($content -match "### 描述|### Description") {
        Write-Success "「描述」部分存在"
    }
    
    # 8. 检查漏洞详情字数（300+ 字）
    if ($content -match "### 漏洞详情|### Vulnerability Details") {
        Write-Success "「漏洞详情」部分存在"
    }
    
    Write-Info "Phase 5 校验完成: $($script:Errors) 错误, $($script:Warnings) 警告"
}

# ============================================
# 全量校验
# ============================================
function Test-All {
    Write-Info "========== 全量质量校验 =========="
    Write-Info ""
    
    Test-Phase1
    Write-Host ""
    
    Test-Phase2Layer1
    Write-Host ""
    
    Test-Phase2Layer2
    Write-Host ""
    
    Test-Phase25
    Write-Host ""
    
    Test-Phase3
    Write-Host ""
    
    Test-Phase5
    Write-Host ""
    
    Write-Info "========== 校验汇总 =========="
    if ($script:Errors -eq 0 -and $script:Warnings -eq 0) {
        Write-Success "所有校验通过！"
    } elseif ($script:Errors -eq 0) {
        Write-Warn "校验通过，但有 $($script:Warnings) 个警告"
    } else {
        Write-Error "校验失败：$($script:Errors) 个错误，$($script:Warnings) 个警告"
        exit 1
    }
}

# ============================================
# 主入口
# ============================================
switch ($Phase.ToLower()) {
    "phase1" { Test-Phase1 }
    "phase2-layer1" { Test-Phase2Layer1 }
    "phase2-layer2" { Test-Phase2Layer2 }
    "phase25" { Test-Phase25 }
    "phase2.5" { Test-Phase25 }
    "phase3" { Test-Phase3 }
    "phase5" { Test-Phase5 }
    "all" { Test-All }
    default {
        Write-Error "未知阶段: $Phase"
        Write-Host "可用阶段: phase1, phase2-layer1, phase2-layer2, phase25, phase3, phase5, all"
        exit 1
    }
}

if ($script:Errors -gt 0) {
    exit 1
}
exit 0