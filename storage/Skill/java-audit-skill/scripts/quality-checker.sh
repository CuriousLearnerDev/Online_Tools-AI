#!/bin/bash
# quality-checker.sh - 阶段输出质量校验
# 用法: ./scripts/quality-checker.sh <phase> <project_path>
# 示例: ./scripts/quality-checker.sh phase1 /path/to/project

set -e

PHASE=$1
PROJECT_PATH=${2:-.}

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0

# 输出函数
success() { echo -e "${GREEN}[✓] $1${NC}"; }
error() { echo -e "${RED}[!] $1${NC}"; ERRORS=$((ERRORS + 1)); }
warn() { echo -e "${YELLOW}[⚠] $1${NC}"; WARNINGS=$((WARNINGS + 1)); }
info() { echo -e "${CYAN}[*] $1${NC}"; }

# ============================================
# Phase 1 校验
# ============================================
test_phase1() {
    info "Phase 1 质量校验..."
    
    # 检查 tier-classification.md
    if [ -f "$PROJECT_PATH/tier-classification.md" ]; then
        content=$(cat "$PROJECT_PATH/tier-classification.md")
        
        if echo "$content" | grep -qi "EALOC"; then
            success "EALOC 计算存在"
        else
            error "缺少 EALOC 计算"
        fi
        
        if echo "$content" | grep -q "T1\|Tier"; then
            t1_count=$(echo "$content" | grep -c "T1" || echo "0")
            success "Tier 分类存在，T1 引用 $t1_count 次"
        else
            error "缺少 Tier 分类"
        fi
    else
        warn "tier-classification.md 不存在"
    fi
    
    # 检查 audit-metrics.json
    if [ -f "$PROJECT_PATH/audit-metrics.json" ]; then
        if command -v jq &> /dev/null; then
            ealoc=$(jq -r '.ealoc // empty' "$PROJECT_PATH/audit-metrics.json" 2>/dev/null || echo "")
            if [ -n "$ealoc" ]; then
                success "audit-metrics.json 有效，EALOC = $ealoc"
            fi
        else
            success "audit-metrics.json 存在"
        fi
    fi
    
    # 检查 dependency-security.md
    if [ -f "$PROJECT_PATH/dependency-security.md" ]; then
        if grep -qE "CVE|Direct vulnerabilities" "$PROJECT_PATH/dependency-security.md"; then
            success "依赖安全检查已执行"
        else
            warn "dependency-security.md 缺少漏洞信息"
        fi
    fi
    
    info "Phase 1 校验完成: $ERRORS 错误, $WARNINGS 警告"
}

# ============================================
# Phase 2 Layer 1 校验
# ============================================
test_phase2_layer1() {
    info "Phase 2 Layer 1 质量校验..."
    
    total_findings=0
    existing_files=0
    
    for file in p0-critical.md p1-high.md p2-medium.md; do
        if [ -f "$PROJECT_PATH/$file" ]; then
            existing_files=$((existing_files + 1))
            findings=$(grep -oE "\.(java|kt):[0-9]+" "$PROJECT_PATH/$file" 2>/dev/null | wc -l || echo "0")
            total_findings=$((total_findings + findings))
            
            if [ "$findings" -gt 0 ]; then
                success "$file 存在，发现 $findings 个危险模式"
            else
                info "$file 存在，无危险模式发现"
            fi
        fi
    done
    
    if [ "$existing_files" -eq 0 ]; then
        warn "所有 Layer 1 扫描文件都不存在"
    else
        info "Layer 1 共发现 $total_findings 个危险模式"
    fi
    
    info "Phase 2 Layer 1 校验完成: $ERRORS 错误, $WARNINGS 警告"
}

# ============================================
# Phase 2 Layer 2 校验
# ============================================
test_phase2_layer2() {
    info "Phase 2 Layer 2 质量校验..."
    
    if [ ! -f "$PROJECT_PATH/findings-raw.md" ]; then
        error "findings-raw.md 不存在"
        return
    fi
    
    content=$(cat "$PROJECT_PATH/findings-raw.md")
    
    # 检查精确行号
    line_matches=$(echo "$content" | grep -oE "[A-Za-z]:[\\/].*\.(java|kt):[0-9]+" | wc -l || echo "0")
    if [ "$line_matches" -eq 0 ]; then
        error "漏洞缺少精确行号（文件:行号 格式）"
    else
        success "精确行号格式正确，共 $line_matches 处"
    fi
    
    # 检查调用链
    callchain_count=$(echo "$content" | grep -c "调用链" || echo "0")
    if [ "$callchain_count" -eq 0 ]; then
        warn "缺少调用链分析"
    else
        success "调用链分析存在，共 $callchain_count 处"
    fi
    
    # 检查状态标记
    status_count=$(echo "$content" | grep -cE "CONFIRMED|HYPOTHESIS" || echo "0")
    if [ "$status_count" -eq 0 ]; then
        warn "缺少漏洞状态标记"
    else
        success "漏洞状态标记存在"
    fi
    
    info "Phase 2 Layer 2 校验完成: $ERRORS 错误, $WARNINGS 警告"
}

# ============================================
# Phase 2.5 校验
# ============================================
test_phase25() {
    info "Phase 2.5 覆盖率门禁校验..."
    
    if [ -f "$PROJECT_PATH/coverage-report.md" ]; then
        coverage=$(grep -oE "覆盖率[:\s]+[0-9]+" "$PROJECT_PATH/coverage-report.md" | head -1 | grep -oE "[0-9]+" || echo "0")
        
        if [ "$coverage" -lt 90 ]; then
            warn "覆盖率 $coverage% 低于门禁阈值"
        else
            success "覆盖率 $coverage% 达标"
        fi
        
        # T1 覆盖率必须 100%
        t1_coverage=$(grep -oE "T1.*[0-9]+%" "$PROJECT_PATH/coverage-report.md" | grep -oE "[0-9]+" | head -1 || echo "0")
        if [ "$t1_coverage" -lt 100 ]; then
            error "T1 覆盖率 $t1_coverage% 未达到 100% 要求"
        else
            success "T1 覆盖率 100% 达标"
        fi
    else
        info "coverage-report.md 不存在"
    fi
    
    info "Phase 2.5 校验完成: $ERRORS 错误, $WARNINGS 警告"
}

# ============================================
# Phase 3 校验
# ============================================
test_phase3() {
    info "Phase 3 质量校验..."
    
    if [ ! -f "$PROJECT_PATH/findings-verified.md" ]; then
        error "findings-verified.md 不存在"
        return
    fi
    
    content=$(cat "$PROJECT_PATH/findings-verified.md")
    
    # 状态统计
    confirmed=$(echo "$content" | grep -c "CONFIRMED" || echo "0")
    hypothesis=$(echo "$content" | grep -c "HYPOTHESIS" || echo "0")
    
    if [ "$confirmed" -eq 0 ] && [ "$hypothesis" -eq 0 ]; then
        error "缺少漏洞状态标记"
    else
        success "CONFIRMED: $confirmed, HYPOTHESIS: $hypothesis"
    fi
    
    # DKTSS 评分
    if echo "$content" | grep -qE "DKTSS|Score"; then
        success "DKTSS 评分存在"
    else
        warn "缺少 DKTSS 评分"
    fi
    
    # CVE 核实
    if echo "$content" | grep -qE "CVE-[0-9]{4}-[0-9]+"; then
        if echo "$content" | grep -qE "NVD|Snyk|mvnrepository|已核实"; then
            success "CVE 已联网核实"
        else
            warn "CVE 编号未标注核实来源"
        fi
    fi
    
    info "Phase 3 校验完成: $ERRORS 错误, $WARNINGS 警告"
}

# ============================================
# Phase 5 校验
# ============================================
test_phase5() {
    info "Phase 5 质量校验..."
    
    if [ ! -f "$PROJECT_PATH/audit-report.md" ]; then
        error "audit-report.md 不存在"
        return
    fi
    
    content=$(cat "$PROJECT_PATH/audit-report.md")
    
    # 漏洞列表
    if echo "$content" | grep -q "## 漏洞列表"; then
        success "「漏洞列表」部分存在"
    else
        error "缺少「漏洞列表」部分"
    fi
    
    # 审计进度
    if echo "$content" | grep -q "## 审计进度"; then
        success "「审计进度」部分存在"
    else
        error "缺少「审计进度」部分"
    fi
    
    # 代码位置格式
    bad_paths=$(echo "$content" | grep -cE "代码位置[：:\s]*\n\s*[^/\nA-Z][^:\n]*\.java:" || echo "0")
    if [ "$bad_paths" -gt 0 ]; then
        error "存在 $bad_paths 处非完整路径的代码位置"
    else
        success "代码位置格式正确"
    fi
    
    # 标题格式
    bad_titles=$(echo "$content" | grep -cE "^#+ .+\((Critical|High|Medium|Low)\)" || echo "0")
    if [ "$bad_titles" -gt 0 ]; then
        error "存在 $bad_titles 处标题包含严重程度标签"
    else
        success "标题格式正确"
    fi
    
    # 漏洞分析要素
    vuln_count=$(echo "$content" | grep -cE "^# [^#\n]+" || echo "0")
    callchain_count=$(echo "$content" | grep -c "调用链" || echo "0")
    
    if [ "$callchain_count" -lt "$vuln_count" ]; then
        warn "部分漏洞缺少调用链分析"
    else
        success "调用链分析完整"
    fi
    
    # 修复建议
    if echo "$content" | grep -q "修复建议"; then
        success "修复建议存在"
    else
        warn "缺少修复建议"
    fi
    
    info "Phase 5 校验完成: $ERRORS 错误, $WARNINGS 警告"
}

# ============================================
# 全量校验
# ============================================
test_all() {
    echo -e "${CYAN}========== 全量质量校验 ==========${NC}"
    echo ""
    
    test_phase1
    echo ""
    
    test_phase2_layer1
    echo ""
    
    test_phase2_layer2
    echo ""
    
    test_phase25
    echo ""
    
    test_phase3
    echo ""
    
    test_phase5
    echo ""
    
    echo -e "${CYAN}========== 校验汇总 ==========${NC}"
    if [ "$ERRORS" -eq 0 ] && [ "$WARNINGS" -eq 0 ]; then
        success "所有校验通过！"
    elif [ "$ERRORS" -eq 0 ]; then
        warn "校验通过，但有 $WARNINGS 个警告"
    else
        error "校验失败：$ERRORS 个错误，$WARNINGS 个警告"
        exit 1
    fi
}

# ============================================
# 主入口
# ============================================
case "$PHASE" in
    phase1) test_phase1 ;;
    phase2-layer1) test_phase2_layer1 ;;
    phase2-layer2) test_phase2_layer2 ;;
    phase25|phase2.5) test_phase25 ;;
    phase3) test_phase3 ;;
    phase5) test_phase5 ;;
    all) test_all ;;
    *)
        error "未知阶段: $PHASE"
        echo "可用阶段: phase1, phase2-layer1, phase2-layer2, phase25, phase3, phase5, all"
        exit 1
        ;;
esac

if [ "$ERRORS" -gt 0 ]; then
    exit 1
fi
exit 0