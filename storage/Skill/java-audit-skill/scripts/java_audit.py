#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Java/Kotlin/前端 代码审计辅助脚本 - 跨平台统一入口
用于 Phase 0 代码度量、语言检测、Phase 1 Tier 分类、Layer 1 预扫描、覆盖率检查

支持语言：
- Java/Kotlin (后端)
- JavaScript/TypeScript (前端通用)
- React (前端框架)
- Vue (前端框架)
- 混合项目 (前后端分离)

Usage:
    python java_audit.py <project_path> [options]

Options:
    --scan          执行 Layer 1 危险模式预扫描
    --tier          执行 Tier 分类
    --coverage      执行覆盖率检查（需配合 --reviewed-file）
    --reviewed-file 指定审阅清单文件路径
    --detect-lang   执行语言检测
    --output        输出格式: json (默认), sarif
    --help, -h      显示帮助信息

Examples:
    python java_audit.py /path/to/project
    python java_audit.py /path/to/project --detect-lang
    python java_audit.py /path/to/project --scan
    python java_audit.py /path/to/project --tier
    python java_audit.py /path/to/project --scan --tier
    python java_audit.py /path/to/project --coverage --reviewed-file reviewed.md
    python java_audit.py /path/to/project --scan --output sarif
"""

import os
import sys
import io
import json
import argparse
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# ============================================
# Windows 终端 UTF-8 编码修复
# ============================================
if sys.platform == 'win32':
    # 设置 stdout/stderr 为 UTF-8 编码
    if sys.stdout.encoding != 'utf-8':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ============================================
# 工具函数
# ============================================

def count_lines(file_path):
    """统计文件行数"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return sum(1 for _ in f)
    except:
        return 0

def get_file_content(file_path):
    """读取文件内容"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except:
        return ""

def write_file(file_path, content):
    """写入文件"""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

# ============================================
# 语言检测
# ============================================

def detect_project_language(project_path):
    """检测项目主要语言类型
    
    返回：
    - "java": Java/Kotlin 后端项目
    - "javascript": JavaScript/TypeScript 前端项目
    - "react": React 前端项目
    - "vue": Vue 前端项目
    - "mixed": 混合项目（前后端分离）
    - "unknown": 无法识别
    """
    file_counts = {
        "java": 0,
        "kt": 0,
        "js": 0,
        "ts": 0,
        "jsx": 0,
        "tsx": 0,
        "vue": 0,
        "html": 0,
        "css": 0,
        "json": 0
    }
    
    # 检测框架特征文件
    has_pom = False
    has_gradle = False
    has_package_json = False
    has_react_indicators = False
    has_vue_indicators = False
    
    # 检测框架配置
    for root, dirs, files in os.walk(project_path):
        # 排除目录
        dirs[:] = [d for d in dirs if d not in ['target', 'node_modules', '.git', 'build', 'out', '.gradle', '.idea', 'dist', '.next']]
        
        # 检测构建文件
        if 'pom.xml' in files:
            has_pom = True
        if any(f in files for f in ['build.gradle', 'build.gradle.kts', 'settings.gradle']):
            has_gradle = True
        if 'package.json' in files:
            has_package_json = True
        
        # 统计文件扩展名
        for file in files:
            ext = file.split('.')[-1].lower() if '.' in file else ''
            if ext in file_counts:
                file_counts[ext] += 1
            
            # 检测 React 特征
            if file.endswith('.tsx') or file.endswith('.jsx'):
                has_react_indicators = True
            if file in ['App.js', 'App.tsx', 'index.jsx', 'index.tsx']:
                has_react_indicators = True
            
            # 检测 Vue 特征
            if file.endswith('.vue'):
                has_vue_indicators = True
            if file in ['App.vue', 'main.js', 'main.ts']:
                # 检查是否是 Vue 项目
                file_path = os.path.join(root, file)
                content = get_file_content(file_path)
                if 'createApp' in content or 'new Vue' in content:
                    has_vue_indicators = True
    
    # 检查 package.json 内容
    if has_package_json:
        package_json_path = os.path.join(project_path, 'package.json')
        if os.path.exists(package_json_path):
            try:
                with open(package_json_path, 'r', encoding='utf-8') as f:
                    package_data = json.load(f)
                    deps = package_data.get('dependencies', {})
                    dev_deps = package_data.get('devDependencies', {})
                    all_deps = {**deps, **dev_deps}
                    
                    # React 检测
                    if 'react' in all_deps or 'react-dom' in all_deps or '@types/react' in all_deps:
                        has_react_indicators = True
                    
                    # Vue 检测
                    if 'vue' in all_deps or '@vue/cli' in all_deps or 'vue-router' in all_deps:
                        has_vue_indicators = True
            except:
                pass
    
    # 计算语言占比
    java_count = file_counts["java"] + file_counts["kt"]
    frontend_count = file_counts["js"] + file_counts["ts"] + file_counts["jsx"] + file_counts["tsx"] + file_counts["vue"]
    
    # 判断逻辑
    # 1. 纯 Java/Kotlin 项目
    if java_count > 0 and frontend_count == 0:
        return "java", {
            "java_files": file_counts["java"],
            "kt_files": file_counts["kt"],
            "build_system": "maven" if has_pom else ("gradle" if has_gradle else "unknown")
        }
    
    # 2. 纯前端项目
    if java_count == 0 and frontend_count > 0:
        if has_vue_indicators:
            return "vue", {
                "vue_files": file_counts["vue"],
                "js_files": file_counts["js"],
                "ts_files": file_counts["ts"],
                "build_system": "npm/yarn"
            }
        elif has_react_indicators:
            return "react", {
                "jsx_files": file_counts["jsx"],
                "tsx_files": file_counts["tsx"],
                "js_files": file_counts["js"],
                "ts_files": file_counts["ts"],
                "build_system": "npm/yarn"
            }
        else:
            return "javascript", {
                "js_files": file_counts["js"],
                "ts_files": file_counts["ts"],
                "html_files": file_counts["html"],
                "build_system": "npm/yarn"
            }
    
    # 3. 混合项目（前后端分离）
    if java_count > 0 and frontend_count > 0:
        # 检查是否是前后端分离结构
        # 常见结构：backend/ + frontend/ 或 src/main/java + src/main/frontend
        has_backend_dir = any(d in ['backend', 'server', 'api'] for d in os.listdir(project_path) if os.path.isdir(os.path.join(project_path, d)))
        has_frontend_dir = any(d in ['frontend', 'client', 'web', 'ui'] for d in os.listdir(project_path) if os.path.isdir(os.path.join(project_path, d)))
        
        if has_backend_dir or has_frontend_dir or (has_pom and has_package_json):
            return "mixed", {
                "java_files": file_counts["java"],
                "kt_files": file_counts["kt"],
                "frontend_files": frontend_count,
                "frontend_type": "vue" if has_vue_indicators else ("react" if has_react_indicators else "javascript"),
                "build_system": "mixed"
            }
        
        # 默认认为是 Java 项目（前端文件可能是少量配置）
        if java_count > frontend_count * 2:
            return "java", {
                "java_files": file_counts["java"],
                "kt_files": file_counts["kt"],
                "frontend_files": frontend_count,
                "build_system": "maven" if has_pom else ("gradle" if has_gradle else "unknown")
            }
    
    # 4. 无法识别
    return "unknown", {
        "file_counts": file_counts,
        "has_pom": has_pom,
        "has_gradle": has_gradle,
        "has_package_json": has_package_json
    }

def run_language_detection(project_path, output_dir):
    """执行语言检测"""
    print("\n" + "=" * 60)
    print("Phase 0: 语言检测")
    print("=" * 60)
    
    language, details = detect_project_language(project_path)
    
    # 语言类型说明
    language_names = {
        "java": "Java/Kotlin 后端项目",
        "javascript": "JavaScript/TypeScript 前端项目",
        "react": "React 前端项目",
        "vue": "Vue 前端项目",
        "mixed": "混合项目（前后端分离）",
        "unknown": "无法识别"
    }
    
    print(f"\n[*] 检测结果:")
    print(f"  语言类型: {language_names.get(language, language)}")
    print(f"  详细信息:")
    for key, value in details.items():
        print(f"    {key}: {value}")
    
    # 根据语言类型推荐审计规则
    recommended_rules = {
        "java": ["java-rce.yaml", "java-config.yaml", "java-sqli.yaml", "java-auth.yaml"],
        "javascript": ["js-security.yaml", "frontend-config.yaml"],
        "react": ["react-security.yaml", "js-security.yaml", "frontend-config.yaml"],
        "vue": ["vue-security.yaml", "js-security.yaml", "frontend-config.yaml"],
        "mixed": ["java-rce.yaml", "java-config.yaml", "js-security.yaml", "frontend-config.yaml"],
        "unknown": []
    }
    
    rules = recommended_rules.get(language, [])
    print(f"\n[*] 推荐审计规则:")
    for rule in rules:
        print(f"  - {rule}")
    
    # 生成报告
    report_path = os.path.join(output_dir, "language-detection.md")
    report_content = f"""# 语言检测结果

## 检测摘要

| 项目 | 结果 |
|------|------|
| 语言类型 | **{language_names.get(language, language)}** |
| 检测时间 | {datetime.now().isoformat()} |

## 详细信息

| 指标 | 数值 |
|------|------|
"""
    for key, value in details.items():
        report_content += f"| {key} | {value} |\n"
    
    report_content += f"""
## 推荐审计规则

根据检测到的语言类型，推荐使用以下 Semgrep 规则：

"""
    for rule in rules:
        report_content += f"- `{rule}`\n"
    
    report_content += f"""
## 审计流程建议

"""
    if language == "java":
        report_content += """- 执行 Java 后端审计流程
- Tier 分类：Controller(T1) → Service(T2) → Entity(T3)
- 重点检查：反序列化、SQL注入、命令执行、认证绕过
"""
    elif language in ["javascript", "react", "vue"]:
        report_content += """- 执行前端审计流程
- Tier 分类：页面组件(T1) → 业务组件(T2) → 工具函数(T3)
- 重点检查：XSS、DOM操作、敏感信息泄露、配置安全
"""
    elif language == "mixed":
        report_content += """- 执行前后端分离审计流程
- 后端：Java 后端审计流程
- 前端：前端审计流程
- 重点检查：API安全、前后端数据交互、认证机制
"""
    
    write_file(report_path, report_content)
    print(f"\n[OK] 语言检测报告: {report_path}")
    
    return {
        "language": language,
        "language_name": language_names.get(language, language),
        "details": details,
        "recommended_rules": rules
    }

# ============================================
# Tier 分类
# ============================================

def classify_tier(file_path, content=None):
    """根据规则分类文件 Tier"""
    if content is None:
        content = get_file_content(file_path)
        if not content:
            return "T2"  # 保守兜底
    
    # Rule 0: 第三方库
    if '/target/' in file_path or 'node_modules' in file_path or '/build/' in file_path:
        return "SKIP"
    
    # Rule 2: Controller/Filter (扩展支持多框架)
    # Spring MVC
    t1_patterns = [
        '@Controller', '@RestController',
        # Servlet (javax + jakarta)
        '@WebServlet', 'extends HttpServlet', 'implements Servlet',
        # Struts 2
        'extends ActionSupport', 'implements Action', '@Action', '@StrutsAction',
        # Filter (javax + jakarta)
        '@WebFilter', 'implements Filter', 'extends OncePerRequestFilter', 'extends GenericFilterBean',
        # Jersey/JAX-RS
        '@Path', '@Provider', 'extends ResourceConfig',
        # Play Framework
        'extends Controller', 'extends Action', 'extends Results',
        # Vert.x
        '@Route', 'extends AbstractVerticle', 'Router.',
        # Dubbo
        '@Service(', '@DubboService', '@AlibabaDubboService',  # Dubbo 服务暴露注解
        # gRPC
        'extends AbstractService', 'extends GeneratedServiceV3',
        # 其他 Web 框架
        '@HttpController', '@Router', '@Endpoint'
    ]
    if any(x in content for x in t1_patterns):
        return "T1"
    
    # Rule 3: Service/DAO
    if any(x in content for x in ['@Service', '@Repository', '@Mapper', '@Dao', '@Component']):
        return "T2"
    
    # Rule 4: Util/Helper
    filename = os.path.basename(file_path).lower()
    if any(x in filename for x in ['util', 'helper', 'handler', 'utils', 'config']):
        return "T2"
    
    # Rule 6: Entity
    if any(x in content for x in ['@Entity', '@Table', '@Data', 'extends BaseEntity', 'data class']):
        return "T3"
    
    # Rule 7: 未匹配，保守兜底
    return "T2"

def run_tier_classification(project_path, output_dir):
    """执行 Tier 分类"""
    print("\n" + "=" * 60)
    print("Phase 1: Tier 分类")
    print("=" * 60)
    
    tier_files = {"T1": [], "T2": [], "T3": [], "SKIP": []}
    tier_loc = {"T1": 0, "T2": 0, "T3": 0, "SKIP": 0}
    
    for root, dirs, files in os.walk(project_path):
        # 排除目录
        dirs[:] = [d for d in dirs if d not in ['target', 'node_modules', '.git', 'build', 'out', '.gradle', '.idea', 'test', 'tests']]
        
        for file in files:
            if not file.endswith(('.java', '.kt')):
                continue
            
            file_path = os.path.join(root, file)
            content = get_file_content(file_path)
            tier = classify_tier(file_path, content)
            
            rel_path = os.path.relpath(file_path, project_path)
            lines = count_lines(file_path)
            
            tier_files[tier].append(rel_path)
            tier_loc[tier] += lines
    
    # 计算 EALOC
    ealoc = tier_loc["T1"] * 1.0 + tier_loc["T2"] * 0.5 + tier_loc["T3"] * 0.1
    agents_needed = max(1, -(-int(ealoc) // 15000))  # ceil division
    
    # 输出统计
    print("\n[*] Tier 分类统计:")
    for tier in ["T1", "T2", "T3", "SKIP"]:
        print(f"  {tier}: {len(tier_files[tier])} 文件, {tier_loc[tier]:,} LOC")
    
    print(f"\n[*] EALOC 计算:")
    print(f"  EALOC = {ealoc:,.0f}")
    print(f"  建议 Agent 数: {agents_needed}")
    
    # 生成报告
    report_path = os.path.join(output_dir, "tier-classification.md")
    report_content = f"""# Tier 分类结果

## 统计摘要

| Tier | 文件数 | LOC | 权重 | EALOC 贡献 |
|------|--------|-----|------|------------|
| T1 (Controller/Filter) | {len(tier_files['T1'])} | {tier_loc['T1']:,} | 1.0 | {tier_loc['T1']:,} |
| T2 (Service/DAO/Util) | {len(tier_files['T2'])} | {tier_loc['T2']:,} | 0.5 | {int(tier_loc['T2'] * 0.5):,} |
| T3 (Entity/VO/DTO) | {len(tier_files['T3'])} | {tier_loc['T3']:,} | 0.1 | {int(tier_loc['T3'] * 0.1):,} |
| SKIP | {len(tier_files['SKIP'])} | - | - | - |

**总 EALOC**: {ealoc:,.0f}  
**所需 Agent 数量**: {agents_needed} (按 15,000 EALOC/Agent 预算)

## Tier 分类规则

| 规则 | 条件 | Tier |
|------|------|------|
| Rule 0 | 第三方库源码 | SKIP |
| Rule 2 | @Controller/@RestController/@WebServlet/Filter | T1 |
| Rule 3 | @Service/@Repository/@Mapper | T2 |
| Rule 4 | 类名含 Util/Helper/Handler | T2 |
| Rule 5 | .properties/.yml/security.xml | T2 |
| Rule 6 | @Entity/@Table/@Data | T3 |
| Rule 7 | 未匹配任何规则 | T2 (保守兜底) |

## 文件清单

### T1 文件 ({len(tier_files['T1'])} 个)
```
{chr(10).join(tier_files['T1'][:50])}
{'... 还有 ' + str(len(tier_files['T1']) - 50) + ' 个文件' if len(tier_files['T1']) > 50 else ''}
```

### T2 文件 ({len(tier_files['T2'])} 个)
```
{chr(10).join(tier_files['T2'][:30])}
{'... 还有 ' + str(len(tier_files['T2']) - 30) + ' 个文件' if len(tier_files['T2']) > 30 else ''}
```

### T3 文件 ({len(tier_files['T3'])} 个)
```
{chr(10).join(tier_files['T3'][:30])}
{'... 还有 ' + str(len(tier_files['T3']) - 30) + ' 个文件' if len(tier_files['T3']) > 30 else ''}
```
"""
    
    write_file(report_path, report_content)
    print(f"\n[OK] Tier 分类报告: {report_path}")
    
    return {
        "tier_files": {k: len(v) for k, v in tier_files.items()},
        "tier_loc": tier_loc,
        "ealoc": ealoc,
        "agents_needed": agents_needed
    }

# ============================================
# Scenario Tags 生成
# ============================================

# 场景类型关键词映射
SCENARIO_KEYWORDS = {
    "FINANCIAL_TRANSACTION": {
        "keywords": ["pay", "payment", "refund", "transfer", "withdraw", "充值", "支付", "退款", "转账"],
        "risk_level": "CRITICAL",
        "focus_checks": ["金额篡改", "并发竞争", "状态机绕过", "水平越权"]
    },
    "PRIVILEGED_OPERATION": {
        "keywords": ["admin", "manage", "delete", "config", "system", "管理", "删除", "配置"],
        "risk_level": "HIGH",
        "focus_checks": ["垂直越权", "权限绕过"]
    },
    "RESOURCE_ALLOCATION": {
        "keywords": ["order", "create", "book", "reserve", "下单", "预约", "抢购"],
        "risk_level": "HIGH",
        "focus_checks": ["并发竞争", "库存绕过"]
    },
    "STATE_TRANSITION": {
        "keywords": ["approve", "reject", "ship", "deliver", "cancel", "审批", "发货", "取消"],
        "risk_level": "HIGH",
        "focus_checks": ["状态机绕过", "流程跳跃"]
    },
    "DATA_ACCESS": {
        "keywords": ["get", "query", "list", "detail", "export", "查询", "列表", "详情", "导出"],
        "risk_level": "MEDIUM",
        "focus_checks": ["水平越权", "信息泄露"]
    },
    "USER_OPERATION": {
        "keywords": ["profile", "password", "update", "modify", "个人", "密码", "修改"],
        "risk_level": "MEDIUM",
        "focus_checks": ["认证绕过", "密码安全"]
    },
    "PUBLIC_ACCESS": {
        "keywords": ["public", "open", "anonymous", "公开", "匿名"],
        "risk_level": "LOW",
        "focus_checks": ["XSS", "SSRF"]
    }
}

def identify_scenario(method, path, annotations, method_name=""):
    """根据方法、路径和注解识别场景类型"""
    # 只在路径和方法名中匹配，排除注释和变量名
    # 使用单词边界匹配避免误报（如 paymentService 变量名）
    combined = f"{method} {path} {method_name}".lower()
    
    for scenario, config in SCENARIO_KEYWORDS.items():
        for keyword in config["keywords"]:
            # 使用单词边界匹配，避免匹配变量名或注释中的关键词
            # 例如：避免 "paymentService" 匹配到 "payment"
            if re.search(rf'\b{re.escape(keyword.lower())}\b', combined):
                return scenario, config["risk_level"], config["focus_checks"]
    
    # 默认返回 DATA_ACCESS
    return "DATA_ACCESS", "MEDIUM", ["水平越权", "信息泄露"]

def generate_scenario_tags(project_path, output_dir):
    """生成 API 场景标签"""
    print("\n" + "=" * 60)
    print("Phase 1: API 场景标签生成")
    print("=" * 60)
    
    apis = []
    scenario_count = {}
    
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in ['target', 'node_modules', '.git', 'build', 'out', '.gradle', '.idea', 'test', 'tests']]
        
        for file in files:
            if not file.endswith(('.java', '.kt')):
                continue
            
            file_path = os.path.join(root, file)
            content = get_file_content(file_path)
            
            # 检查是否是 Controller
            if not any(x in content for x in ['@Controller', '@RestController', '@WebServlet']):
                continue
            
            rel_path = os.path.relpath(file_path, project_path)
            
            # 提取 RequestMapping 类级别路径
            class_mapping = ""
            rm_match = re.search(r'@RequestMapping\(["\']([^"\']+)["\']', content)
            if rm_match:
                class_mapping = rm_match.group(1)
            
            # 提取方法级别映射
            method_patterns = [
                (r'@GetMapping\(["\']([^"\']+)["\']', 'GET'),
                (r'@PostMapping\(["\']([^"\']+)["\']', 'POST'),
                (r'@PutMapping\(["\']([^"\']+)["\']', 'PUT'),
                (r'@DeleteMapping\(["\']([^"\']+)["\']', 'DELETE'),
                (r'@PatchMapping\(["\']([^"\']+)["\']', 'PATCH'),
                (r'@RequestMapping\([^)]*value\s*=\s*["\']([^"\']+)["\'][^)]*method\s*=\s*RequestMethod\.(\w+)', None),
            ]
            
            for pattern, method in method_patterns:
                for match in re.finditer(pattern, content):
                    if method:
                        path = class_mapping + match.group(1)
                    else:
                        path = class_mapping + match.group(1)
                        method = match.group(2)
                    
                    # 获取方法名
                    line_start = content[:match.start()].count('\n') + 1
                    lines = content.split('\n')
                    method_name = ""
                    for i in range(match.start() // 80, min(len(lines), match.start() // 80 + 10)):
                        if 'public' in lines[i] or 'def' in lines[i]:
                            method_match = re.search(r'(?:public|def)\s+\w+\s+(\w+)\s*\(', lines[i])
                            if method_match:
                                method_name = method_match.group(1)
                                break
                    
                    # 检查权限注解
                    annotations = []
                    if '@PreAuthorize' in content[match.start():match.start()+500]:
                        annotations.append('@PreAuthorize')
                    if '@Secured' in content[match.start():match.start()+500]:
                        annotations.append('@Secured')
                    if 'permitAll' in content[match.start():match.start()+500]:
                        annotations.append('permitAll')
                    
                    # 识别场景
                    scenario, risk_level, focus_checks = identify_scenario(method, path, annotations)
                    
                    apis.append({
                        "method": method,
                        "path": path,
                        "controller": f"{rel_path}:{line_start}",
                        "method_name": method_name,
                        "scenario_type": scenario,
                        "risk_level": risk_level,
                        "focus_checks": focus_checks,
                        "annotations": annotations
                    })
                    
                    scenario_count[scenario] = scenario_count.get(scenario, 0) + 1
    
    # 输出统计
    print(f"\n[*] 发现 API 端点: {len(apis)} 个")
    print(f"[*] 场景分布:")
    for scenario, count in sorted(scenario_count.items(), key=lambda x: -x[1]):
        print(f"  {scenario}: {count} 个")
    
    # 生成 scenario-tags.json
    output = {
        "generated_at": datetime.now().isoformat(),
        "project": os.path.basename(project_path),
        "total_apis": len(apis),
        "scenario_distribution": scenario_count,
        "apis": apis
    }
    
    output_path = os.path.join(output_dir, "scenario-tags.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n[OK] 场景标签文件: {output_path}")
    
    return output

# ============================================
# Layer 1 预扫描
# ============================================

DANGER_PATTERNS = {
    "P0": {
        "反序列化": [
            "ObjectInputStream", "XMLDecoder", "XStream", "JSON.parseObject", "JSON.parse", "@type",
            "enableDefaultTyping", "activateDefaultTyping", "HessianInput", "Hessian2Input",
            "new Yaml(", "SnakeYAML"
        ],
        "SSTI": [
            "Velocity.evaluate", "VelocityEngine", "freemarker.template", "Template.process",
            "SpringTemplateEngine", "TemplateEngine.process"
        ],
        "表达式注入": [
            "SpelExpressionParser", "parseExpression", "evaluateExpression", "OgnlUtil", "Ognl.getValue",
            "MVEL.eval", "MVEL.executeExpression"
        ],
        "JNDI": ["InitialContext.lookup", "JdbcRowSetImpl", "setDataSourceName"],
        "命令执行": ["Runtime.getRuntime", "ProcessBuilder", ".exec("]
    },
    "P1": {
        "SQL注入": [
            "Statement", "createStatement", "executeQuery", "executeUpdate",
            "createQuery", "createNativeQuery"
        ],
        "MyBatis注入": ["${"],
        "SSRF": ["new URL(", "HttpURLConnection", "HttpClient", "RestTemplate", "WebClient", "OkHttpClient"],
        "文件操作": [
            "FileInputStream", "FileOutputStream", "FileWriter", "Files.read", "Files.write",
            "getOriginalFilename", "transferTo", "MultipartFile", "Paths.get"
        ],
        "XXE": ["DocumentBuilder", "SAXParser", "XMLReader", "XMLInputFactory", "SAXReader", "SAXBuilder"]
    },
    "P2": {
        "认证": ["@PreAuthorize", "@Secured", "@RolesAllowed", "hasRole", "hasAuthority", "permitAll"],
        "加密": ["MessageDigest", "Cipher", "SecretKey", "PasswordEncoder", "MD5", "SHA-1"],
        "配置": ["debug:", "swagger", "actuator", "h2.console"]
    }
}

def run_layer1_scan(project_path, output_dir):
    """执行 Layer 1 预扫描"""
    print("\n" + "=" * 60)
    print("Layer 1: 危险模式预扫描")
    print("=" * 60)
    
    results = defaultdict(lambda: defaultdict(list))
    
    for root, dirs, files in os.walk(project_path):
        # 排除目录
        dirs[:] = [d for d in dirs if d not in ['target', 'node_modules', '.git', 'build', 'out', '.gradle', '.idea', 'test', 'tests']]
        
        for file in files:
            if not file.endswith(('.java', '.kt', '.xml', '.gradle', '.kts', '.yml', '.yaml', '.properties')):
                continue
            
            file_path = os.path.join(root, file)
            content = get_file_content(file_path)
            
            for priority, categories in DANGER_PATTERNS.items():
                for category, keywords in categories.items():
                    for keyword in keywords:
                        if keyword in content:
                            # 找到行号
                            lines = content.split('\n')
                            for i, line in enumerate(lines, 1):
                                if keyword in line:
                                    rel_path = os.path.relpath(file_path, project_path)
                                    results[priority][category].append({
                                        "file": rel_path,
                                        "line": i,
                                        "keyword": keyword,
                                        "snippet": line.strip()[:100]
                                    })
                                    break  # 每个文件每种模式只记录一次
    
    # 输出结果
    total_findings = 0
    for priority in ["P0", "P1", "P2"]:
        if priority in results:
            print(f"\n[!] {priority} 级发现:")
            for category, findings in results[priority].items():
                print(f"  [{category}] {len(findings)} 处")
                total_findings += len(findings)
                for f in findings[:5]:
                    print(f"    - {f['file']}:{f['line']} ({f['keyword']})")
                if len(findings) > 5:
                    print(f"    ... 还有 {len(findings) - 5} 处")
    
    print(f"\n[*] 总计发现: {total_findings} 处危险模式")
    
    # 生成报告 - 只生成有内容的报告（P0/P1/P2），移除无意义的 P3 文件
    priority_names = {"P0": "critical", "P1": "high", "P2": "medium"}
    for priority in ["P0", "P1", "P2"]:
        report_path = os.path.join(output_dir, f"{priority.lower()}-{priority_names[priority]}.md")
        
        if priority in results:
            content = f"# {priority} 级危险模式\n\n## 发现记录\n\n"
            for category, findings in results[priority].items():
                content += f"### {category}\n\n"
                for f in findings:
                    content += f"- `{f['file']}:{f['line']}` - `{f['keyword']}`\n"
                content += "\n"
            write_file(report_path, content)
    
    print(f"\n[OK] 扫描报告: {output_dir}/p0-critical.md, p1-high.md, p2-medium.md")
    
    return dict(results)

# ============================================
# 覆盖率检查
# ============================================

def run_coverage_check(project_path, reviewed_file, output_dir):
    """执行覆盖率检查"""
    print("\n" + "=" * 60)
    print("Phase 2.5: 覆盖率门禁检查")
    print("=" * 60)
    
    # 获取实际文件列表
    actual_files = set()
    t1_files = set()  # Controller/Filter 文件
    t2_files = set()  # Service/DAO 文件
    t3_files = set()  # Entity/VO 文件
    
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in ['target', 'node_modules', '.git', 'build', 'out', '.gradle', 'test', 'tests']]
        for file in files:
            if file.endswith(('.java', '.kt')):
                actual_files.add(file)
                file_path = os.path.join(root, file)
                content = get_file_content(file_path)
                tier = classify_tier(file_path, content)
                if tier == "T1":
                    t1_files.add(file)
                elif tier == "T2":
                    t2_files.add(file)
                elif tier == "T3":
                    t3_files.add(file)
    
    actual_count = len(actual_files)
    t1_count = len(t1_files)
    t2_count = len(t2_files)
    t3_count = len(t3_files)
    
    # 读取审阅清单 - 改进的文件路径识别
    reviewed_files = set()
    reviewed_t1 = set()
    reviewed_t2 = set()
    reviewed_t3 = set()
    
    if os.path.exists(reviewed_file):
        content = get_file_content(reviewed_file)
        
        # 方法1: 从 markdown 表格格式提取（优先，最准确）
        # 匹配格式: | 1 | UserController.java | T1 | 完成 | 或带路径格式
        # 使用更严格的正则，要求文件名前有序号或路径分隔符
        table_matches = re.findall(r'\|\s*\d+\s*\|\s*`?([a-zA-Z0-9_/.-]+\.(java|kt))`?\s*\|\s*(T[123])', content)
        for match in table_matches:
            filename = os.path.basename(match[0])  # 提取文件名部分
            tier = match[2]
            reviewed_files.add(filename)
            if tier == "T1":
                reviewed_t1.add(filename)
            elif tier == "T2":
                reviewed_t2.add(filename)
            elif tier == "T3":
                reviewed_t3.add(filename)
        
        # 方法2: 从代码块中的完整路径提取（备用）
        # 要求路径包含至少一个目录分隔符，避免匹配类名
        if not reviewed_files:
            # 匹配带完整路径的文件引用: `src/main/java/com/example/UserController.java`
            code_block_matches = re.findall(r'`([a-zA-Z0-9_/.-]+/[a-zA-Z0-9_-]+\.(java|kt))`', content)
            for match in code_block_matches:
                filename = os.path.basename(match[0])
                reviewed_files.add(filename)
        
        # 方法3: 从行首文件路径列表提取（最后备用）
        if not reviewed_files:
            # 匹配单独一行的完整路径（要求包含路径分隔符）
            line_matches = re.findall(r'^\s*([a-zA-Z0-9_/.-]+/[a-zA-Z0-9_-]+\.(java|kt))\s*$', content, re.MULTILINE)
            for match in line_matches:
                filename = os.path.basename(match)
                reviewed_files.add(filename)
        
        # 方法4: 从漏洞报告的代码位置提取
        # 格式: 代码位置：E:\path\to\File.java:123 或 /path/to/File.java:123
        if not reviewed_files:
            code_location_matches = re.findall(r'代码位置[：:\s]*\n\s*`?([a-zA-Z0-9_/.-:/\\]+\.(java|kt)):\d+', content)
            for match in code_location_matches:
                filename = os.path.basename(match[0].replace('\\', '/'))
                reviewed_files.add(filename)
    
    reviewed_count = len(reviewed_files)
    
    # 分别计算各级别的覆盖率
    t1_reviewed = len(reviewed_t1)
    t2_reviewed = len(reviewed_t2)
    t3_reviewed = len(reviewed_t3)
    
    t1_coverage = round(t1_reviewed / t1_count * 100, 1) if t1_count > 0 else 100
    t2_coverage = round(t2_reviewed / t2_count * 100, 1) if t2_count > 0 else 100
    t3_coverage = round(t3_reviewed / t3_count * 100, 1) if t3_count > 0 else 100
    
    # 计算总体遗漏
    missed_files = actual_files - reviewed_files
    missed_count = len(missed_files)
    missed_t1 = t1_files - reviewed_t1
    
    # 计算总体覆盖率
    coverage = round((actual_count - missed_count) / actual_count * 100, 1) if actual_count > 0 else 0
    
    # 输出结果
    print(f"\n[*] 覆盖率统计:")
    print(f"  实际文件总数: {actual_count}")
    print(f"  已审阅文件数: {reviewed_count}")
    print(f"  遗漏文件数: {missed_count}")
    print(f"  总体覆盖率: {coverage}%")
    
    print(f"\n[*] 分层覆盖率:")
    print(f"  T1 (Controller/Filter): {t1_reviewed}/{t1_count} = {t1_coverage}%")
    print(f"  T2 (Service/DAO): {t2_reviewed}/{t2_count} = {t2_coverage}%")
    print(f"  T3 (Entity/VO): {t3_reviewed}/{t3_count} = {t3_coverage}%")
    
    # 门禁判断 - T1 必须 100% 覆盖
    t1_passed = t1_coverage == 100
    
    if t1_passed and coverage >= 90:
        print(f"\n[OK] 门禁通过 - T1 覆盖率 100%，总体覆盖率 {coverage}%")
        passed = True
    else:
        print(f"\n[!] 门禁未通过:")
        if not t1_passed:
            print(f"  - T1 文件覆盖率 {t1_coverage}% < 100%（必须 100%）")
        if coverage < 90:
            print(f"  - 总体覆盖率 {coverage}% < 90%")
        
        if missed_t1:
            print(f"\n[*] 遗漏的 T1 文件（必须补扫）:")
            for f in list(missed_t1)[:20]:
                print(f"  - {f}")
            if len(missed_t1) > 20:
                print(f"  ... 还有 {len(missed_t1) - 20} 个文件")
        
        passed = False
    
    # 生成报告
    report_path = os.path.join(output_dir, "coverage-report.md")
    report_content = f"""# 覆盖率验证报告

## 覆盖率统计

| 指标 | 数值 |
|------|------|
| 实际文件总数 | {actual_count} |
| 已审阅文件数 | {reviewed_count} |
| 遗漏文件数 | {missed_count} |
| **总体覆盖率** | **{coverage}%** |

## 分层覆盖率

| Tier | 文件数 | 已审阅 | 覆盖率 | 要求 | 状态 |
|------|--------|--------|--------|------|------|
| T1 (Controller/Filter) | {t1_count} | {t1_reviewed} | {t1_coverage}% | 100% | {"✅ 通过" if t1_coverage == 100 else "❌ 未通过"} |
| T2 (Service/DAO) | {t2_count} | {t2_reviewed} | {t2_coverage}% | 95% | {"✅ 通过" if t2_coverage >= 95 else "⚠️ 需补扫"} |
| T3 (Entity/VO) | {t3_count} | {t3_reviewed} | {t3_coverage}% | 80% | {"✅ 通过" if t3_coverage >= 80 else "⚠️ 需补扫"} |

## 门禁状态

{"✅ **通过** - T1 覆盖率 100%，总体覆盖率 ≥ 90%" if passed else "❌ **未通过** - T1 文件必须 100% 覆盖"}

"""
    
    if missed_count > 0:
        report_content += f"""## 遗漏文件列表

### T1 遗漏文件（必须补扫）
```
{chr(10).join(list(missed_t1)[:50]) if missed_t1 else "无"}
{"... 还有 " + str(len(missed_t1) - 50) + " 个文件" if len(missed_t1) > 50 else ""}
```

### 其他遗漏文件
```
{chr(10).join(list(missed_files - missed_t1)[:50])}
{"... 还有 " + str(len(missed_files - missed_t1) - 50) + " 个文件" if len(missed_files - missed_t1) > 50 else ""}
```
"""
    
    write_file(report_path, report_content)
    print(f"\n[OK] 覆盖率报告: {report_path}")
    
    return {
        "actual_count": actual_count,
        "reviewed_count": reviewed_count,
        "missed_count": missed_count,
        "coverage": coverage,
        "t1_coverage": t1_coverage,
        "t2_coverage": t2_coverage,
        "t3_coverage": t3_coverage,
        "passed": passed
    }

# ============================================
# Phase 0 代码度量
# ============================================

def measure_project(project_path):
    """Phase 0: 项目度量"""
    stats = {
        "total_loc": 0,
        "java_files": 0,
        "kt_files": 0,
        "xml_files": 0,
        "gradle_files": 0,
        "controllers": 0,
        "modules": 0,
        "build_system": "unknown",
        "tier_stats": {
            "T1": {"files": 0, "loc": 0},
            "T2": {"files": 0, "loc": 0},
            "T3": {"files": 0, "loc": 0},
            "SKIP": {"files": 0, "loc": 0}
        }
    }
    
    pom_count = 0
    gradle_count = 0
    
    for root, dirs, files in os.walk(project_path):
        # 统计构建系统
        if 'pom.xml' in files:
            pom_count += 1
        if any(f in files for f in ['build.gradle', 'build.gradle.kts', 'settings.gradle', 'settings.gradle.kts']):
            gradle_count += 1
        
        # 排除目录
        dirs[:] = [d for d in dirs if d not in ['target', 'node_modules', '.git', 'build', 'out', '.gradle', '.idea']]
        
        for file in files:
            file_path = os.path.join(root, file)
            
            if file.endswith('.java'):
                stats["java_files"] += 1
                lines = count_lines(file_path)
                stats["total_loc"] += lines
                
                tier = classify_tier(file_path)
                stats["tier_stats"][tier]["files"] += 1
                stats["tier_stats"][tier]["loc"] += lines
                
                # 统计 Controller
                content = get_file_content(file_path)
                if any(x in content for x in ['@Controller', '@RestController', '@WebServlet', '@HttpController']):
                    stats["controllers"] += 1
            
            elif file.endswith('.kt'):
                stats["kt_files"] += 1
                lines = count_lines(file_path)
                stats["total_loc"] += lines
                
                tier = classify_tier(file_path)
                stats["tier_stats"][tier]["files"] += 1
                stats["tier_stats"][tier]["loc"] += lines
            
            elif file.endswith('.xml'):
                stats["xml_files"] += 1
            
            elif file.endswith(('.gradle', '.gradle.kts')):
                stats["gradle_files"] += 1
    
    # 确定构建系统
    if pom_count > 0:
        stats["build_system"] = "maven"
        stats["modules"] = pom_count
    elif gradle_count > 0:
        stats["build_system"] = "gradle"
        stats["modules"] = gradle_count
    
    # 计算 EALOC
    stats["ealoc"] = (
        stats["tier_stats"]["T1"]["loc"] * 1.0 +
        stats["tier_stats"]["T2"]["loc"] * 0.5 +
        stats["tier_stats"]["T3"]["loc"] * 0.1
    )
    
    stats["agents_needed"] = max(1, -(-int(stats["ealoc"]) // 15000))
    
    return stats

# ============================================
# SARIF 输出
# ============================================

def to_sarif(scan_results, project_path):
    """转换为 SARIF 格式"""
    sarif = {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "Java Audit Skill - Layer 1 Scanner",
                    "version": "1.0.0",
                    "informationUri": "https://github.com/your-username/java-audit-skill"
                }
            },
            "results": []
        }]
    }
    
    severity_map = {"P0": "error", "P1": "warning", "P2": "note"}
    
    for priority, categories in scan_results.items():
        for category, findings in categories.items():
            for finding in findings:
                sarif["runs"][0]["results"].append({
                    "ruleId": f"{priority}-{category}",
                    "level": severity_map.get(priority, "warning"),
                    "message": {
                        "text": f"发现 {category} 相关的危险模式: {finding['keyword']}"
                    },
                    "locations": [{
                        "physicalLocation": {
                            "artifactLocation": {
                                "uri": finding["file"]
                            },
                            "region": {
                                "startLine": finding["line"]
                            }
                        }
                    }]
                })
    
    return sarif

# ============================================
# 主入口函数（供 audit.py 调用）
# ============================================

def run_java_audit(project_path, output_dir, args=None):
    """Java/Kotlin 后端审计主入口
    
    Args:
        project_path: 项目根目录
        output_dir: 输出目录
        args: 命令行参数对象（可选）
    
    Returns:
        dict: 审计结果
    """
    print("\n" + "=" * 60)
    print("Java/Kotlin 后端审计")
    print("=" * 60)
    
    # Phase 0: 代码度量
    print("\n[*] 项目路径:", project_path)
    
    stats = measure_project(project_path)
    
    print("\n[*] 项目统计:")
    print(f"  构建系统: {stats['build_system'].upper()}")
    print(f"  总代码行数: {stats['total_loc']:,}")
    print(f"  Java 文件: {stats['java_files']}")
    print(f"  Kotlin 文件: {stats['kt_files']}")
    print(f"  XML 文件: {stats['xml_files']}")
    print(f"  Controller 数量: {stats['controllers']}")
    print(f"  模块数: {stats['modules']}")
    
    print("\n[*] Tier 分类统计:")
    for tier in ["T1", "T2", "T3", "SKIP"]:
        print(f"  {tier}: {stats['tier_stats'][tier]['files']} 文件, {stats['tier_stats'][tier]['loc']:,} LOC")
    
    print("\n[*] EALOC 计算:")
    print(f"  EALOC = {stats['ealoc']:,.0f}")
    print(f"  建议 Agent 数: {stats['agents_needed']}")
    
    # Phase 1: Tier 分类
    tier_results = None
    if args and hasattr(args, 'tier') and args.tier:
        tier_results = run_tier_classification(project_path, output_dir)
    elif args is None:
        # 默认执行 Tier 分类
        tier_results = run_tier_classification(project_path, output_dir)
    
    # Phase 1: 场景标签生成
    scenario_results = None
    if args and hasattr(args, 'scenario') and args.scenario:
        scenario_results = generate_scenario_tags(project_path, output_dir)
    
    # Layer 1: 预扫描
    scan_results = None
    if args and hasattr(args, 'scan') and args.scan:
        scan_results = run_layer1_scan(project_path, output_dir)
    elif args is None:
        # 默认执行预扫描
        scan_results = run_layer1_scan(project_path, output_dir)
    
    # Phase 2.5: 覆盖率检查
    coverage_results = None
    if args and hasattr(args, 'coverage') and args.coverage:
        if hasattr(args, 'reviewed_file') and args.reviewed_file:
            coverage_results = run_coverage_check(project_path, args.reviewed_file, output_dir)
    
    # 输出结果
    output_data = {
        "language": "java",
        "metrics": stats,
        "tier_results": tier_results,
        "scenario_results": scenario_results,
        "scan_results": scan_results,
        "coverage_results": coverage_results,
        "generated_at": datetime.now().isoformat()
    }
    
    output_path = os.path.join(output_dir, "java-audit-metrics.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n[OK] Java 审计完成，结果保存到: {output_path}")
    
    return output_data

# ============================================
# 主函数（独立运行）
# ============================================

def main():
    parser = argparse.ArgumentParser(
        description="Java/Kotlin 代码审计辅助脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python java_audit.py /path/to/project                    # 仅度量
  python java_audit.py /path/to/project --scan             # 度量 + Layer 1 预扫描
  python java_audit.py /path/to/project --tier             # 度量 + Tier 分类
  python java_audit.py /path/to/project --scenario         # 度量 + 场景标签
  python java_audit.py /path/to/project --scan --tier --scenario  # 全部执行
  python java_audit.py /path/to/project --coverage --reviewed-file reviewed.md  # 覆盖率检查
  python java_audit.py /path/to/project --scan --output sarif  # SARIF 格式输出
        """
    )
    parser.add_argument("project_path", help="项目根目录")
    parser.add_argument("--scan", action="store_true", help="执行 Layer 1 危险模式预扫描")
    parser.add_argument("--tier", action="store_true", help="执行 Tier 分类")
    parser.add_argument("--scenario", action="store_true", help="生成 API 场景标签")
    parser.add_argument("--coverage", action="store_true", help="执行覆盖率检查")
    parser.add_argument("--reviewed-file", help="审阅清单文件路径（用于覆盖率检查）")
    parser.add_argument("--output", choices=["json", "sarif"], default="json", help="输出格式 (默认: json)")
    parser.add_argument("--output-dir", help="输出目录 (默认: <project>/audit-output)")
    
    args = parser.parse_args()
    
    if not os.path.isdir(args.project_path):
        print(f"Error: {args.project_path} is not a valid directory")
        sys.exit(1)
    
    # 设置输出目录
    output_dir = args.output_dir or os.path.join(args.project_path, "audit-output")
    os.makedirs(output_dir, exist_ok=True)
    
    # 调用审计主入口
    run_java_audit(args.project_path, output_dir, args)

if __name__ == "__main__":
    main()