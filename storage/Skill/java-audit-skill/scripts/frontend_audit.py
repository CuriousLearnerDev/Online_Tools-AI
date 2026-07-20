#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
前端代码审计脚本 - JavaScript/TypeScript/React/Vue

专门用于前端项目的安全审计，支持：
- JavaScript/TypeScript 通用前端项目
- React 框架项目
- Vue 框架项目

Tier 分类规则：
- T1: 页面组件、路由组件（用户交互入口）
- T2: 业务组件、工具函数、API 调用（业务逻辑层）
- T3: 样式文件、静态资源、类型定义（低风险文件）

危险模式：
- P0: XSS、代码注入
- P1: 原型污染、敏感信息泄露
- P2: 配置安全

Usage:
    python frontend_audit.py <project_path> [options]

Options:
    --language      指定语言类型: javascript, react, vue
    --scan          执行 Layer 1 危险模式预扫描
    --tier          执行 Tier 分类
    --output        输出格式: json (默认), sarif
    --help, -h      显示帮助信息

Examples:
    python frontend_audit.py /path/to/project --language react --scan
    python frontend_audit.py /path/to/project --tier
    python frontend_audit.py /path/to/project --scan --tier
"""

import os
import sys
import io
import json
import argparse
import subprocess
from collections import defaultdict
from datetime import datetime

# ============================================
# Windows 终端 UTF-8 编码修复
# ============================================
if sys.platform == 'win32':
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
    if os.path.dirname(file_path):
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

# ============================================
# 前端 Tier 分类
# ============================================

def classify_tier_frontend(file_path, content=None, language="javascript"):
    """前端文件 Tier 分类
    
    Tier 规则：
    - T1: 页面组件、路由组件（pages/, views/, routes/, router/）
    - T2: 业务组件、工具函数、API调用（components/, hooks/, utils/, services/, api/）
    - T3: 样式文件、静态资源、类型定义（.css, .scss, .less, types/, @types/）
    - SKIP: node_modules, dist, build, .next
    """
    if content is None:
        content = get_file_content(file_path)
        if not content:
            return "T2"
    
    # Rule 0: 第三方库和构建产物
    skip_patterns = ['node_modules', 'dist', 'build', '.next', 'out', '.cache']
    if any(x in file_path for x in skip_patterns):
        return "SKIP"
    
    filename = os.path.basename(file_path).lower()
    file_path_lower = file_path.lower()
    
    # T1: 页面组件/路由组件
    t1_path_patterns = [
        'pages/', 'views/', 'routes/', 'screens/',
        'page/', 'view/', 'route/', 'screen/',
        'router/', 'routers/', 'app.js', 'app.ts',
        'app.jsx', 'app.tsx', 'app.vue', 'main.js', 'main.ts'
    ]
    if any(x in file_path_lower for x in t1_path_patterns):
        return "T1"
    
    # React 特定 T1 判断
    if language == "react":
        # 文件名包含 page/view/screen/container
        if any(x in filename for x in ['page', 'view', 'screen', 'container', 'layout']):
            return "T1"
        # 路由配置文件
        if 'route' in filename or 'router' in filename:
            return "T1"
        # 入口文件
        if filename in ['index.jsx', 'index.tsx', 'app.jsx', 'app.tsx']:
            return "T1"
    
    # Vue 特定 T1 判断
    if language == "vue":
        # .vue 文件在 pages/views 目录
        if file_path.endswith('.vue'):
            if any(x in file_path_lower for x in ['page', 'view', 'screen', 'route']):
                return "T1"
        # 路由配置
        if 'router' in filename or 'route' in filename:
            return "T1"
        # 入口文件
        if filename in ['app.vue', 'main.js', 'main.ts']:
            return "T1"
    
    # T2: 业务组件/工具函数/API调用
    t2_path_patterns = [
        'components/', 'hooks/', 'utils/', 'helpers/',
        'services/', 'api/', 'lib/', 'libs/',
        'store/', 'stores/', 'context/', 'contexts/',
        'middleware/', 'interceptors/'
    ]
    if any(x in file_path_lower for x in t2_path_patterns):
        return "T2"
    
    # 文件名包含 util/helper/service/api
    if any(x in filename for x in ['util', 'helper', 'service', 'api', 'hook', 'store', 'context']):
        return "T2"
    
    # T3: 样式文件/静态资源/类型定义
    t3_extensions = ['.css', '.scss', '.sass', '.less', '.styl', '.css.d.ts']
    if file_path.endswith(tuple(t3_extensions)):
        return "T3"
    
    # 类型定义文件
    if 'types/' in file_path_lower or '@types/' in file_path_lower:
        return "T3"
    if filename.endswith('.d.ts') and not filename.endswith('.css.d.ts'):
        return "T3"
    
    # 静态资源
    static_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf']
    if file_path.endswith(tuple(static_extensions)):
        return "T3"
    
    # 默认为 T2
    return "T2"

def run_tier_classification(project_path, output_dir, language="javascript"):
    """执行前端 Tier 分类"""
    print("\n" + "=" * 60)
    print("Phase 1: 前端 Tier 分类")
    print("=" * 60)
    
    tier_files = {"T1": [], "T2": [], "T3": [], "SKIP": []}
    tier_loc = {"T1": 0, "T2": 0, "T3": 0, "SKIP": 0}
    
    # 根据语言类型选择文件扩展名
    if language == "react":
        extensions = ('.js', '.ts', '.jsx', '.tsx')
    elif language == "vue":
        extensions = ('.vue', '.js', '.ts')
    else:  # javascript
        extensions = ('.js', '.ts', '.jsx', '.tsx', '.vue')
    
    for root, dirs, files in os.walk(project_path):
        # 排除目录
        dirs[:] = [d for d in dirs if d not in ['node_modules', '.git', 'dist', 'build', 'out', '.next', '.cache', 'coverage', 'test', 'tests', '__tests__', 'audit-output']]
        
        for file in files:
            if not file.endswith(extensions):
                continue
            
            file_path = os.path.join(root, file)
            content = get_file_content(file_path)
            
            tier = classify_tier_frontend(file_path, content, language)
            
            rel_path = os.path.relpath(file_path, project_path)
            lines = count_lines(file_path)
            
            tier_files[tier].append(rel_path)
            tier_loc[tier] += lines
    
    # 输出统计
    print("\n[*] Tier 分类统计:")
    for tier in ["T1", "T2", "T3", "SKIP"]:
        print(f"  {tier}: {len(tier_files[tier])} 文件, {tier_loc[tier]:,} LOC")
    
    # 计算前端 EALOC
    ealoc = tier_loc["T1"] * 1.0 + tier_loc["T2"] * 0.5 + tier_loc["T3"] * 0.1
    print(f"\n[*] 前端 EALOC: {ealoc:,.0f}")
    
    # 生成报告
    report_path = os.path.join(output_dir, "frontend-tier-classification.md")
    tier_names = {
        "T1": "页面组件（入口点）",
        "T2": "业务组件/工具函数",
        "T3": "样式文件/静态资源"
    }
    
    report_content = f"""# 前端 Tier 分类结果

## 统计摘要

| Tier | 说明 | 文件数 | LOC |
|------|------|--------|-----|
| T1 | {tier_names['T1']} | {len(tier_files['T1'])} | {tier_loc['T1']:,} |
| T2 | {tier_names['T2']} | {len(tier_files['T2'])} | {tier_loc['T2']:,} |
| T3 | {tier_names['T3']} | {len(tier_files['T3'])} | {tier_loc['T3']:,} |
| SKIP | 第三方库/构建产物 | {len(tier_files['SKIP'])} | - |

## EALOC 计算

| 公式 | 结果 |
|------|------|
| EALOC = T1 × 1.0 + T2 × 0.5 + T3 × 0.1 | **{ealoc:,.0f}** |

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
"""
    
    write_file(report_path, report_content)
    print(f"\n[OK] Tier 分类报告: {report_path}")
    
    return {
        "tier_files": {k: len(v) for k, v in tier_files.items()},
        "tier_loc": tier_loc,
        "ealoc": ealoc
    }

# ============================================
# 前端危险模式
# ============================================

DANGER_PATTERNS_FRONTEND = {
    "P0": {
        "XSS": [
            "innerHTML", "outerHTML", "document.write", "document.writeln",
            "dangerouslySetInnerHTML", "v-html", "$html",
            "insertAdjacentHTML", "createContextualFragment"
        ],
        "代码注入": [
            "eval(", "new Function(", "setTimeout(", "setInterval(",
            "execScript(", "setImmediate("
        ]
    },
    "P1": {
        "原型污染": [
            ".merge", ".extend", "Object.assign", "__proto__",
            "constructor.prototype", "prototype.__proto__"
        ],
        "敏感信息泄露": [
            "localStorage.setItem", "sessionStorage.setItem",
            "password", "secret", "api_key", "apikey", "private_key",
            "access_token", "auth_token", "bearer"
        ],
        "开放重定向": [
            "window.location =", "location.href =",
            "location.replace(", "location.assign(",
            "history.push(", "history.replace(",
            "router.push(", "router.replace("
        ]
    },
    "P2": {
        "配置安全": [
            "Access-Control-Allow-Origin: *",
            "Access-Control-Allow-Credentials: true",
            "unsafe-inline", "unsafe-eval",
            "debug: true", "development",
            "sourceMap: true", "sourcemap: true"
        ],
        "不安全随机数": [
            "Math.random()"  # 用于安全场景时需关注
        ]
    }
}

def run_layer1_scan(project_path, output_dir, language="javascript"):
    """执行前端 Layer 1 预扫描"""
    print("\n" + "=" * 60)
    print("Layer 1: 前端危险模式预扫描")
    print("=" * 60)
    
    results = defaultdict(lambda: defaultdict(list))
    
    # 前端文件扩展名
    extensions = ('.js', '.ts', '.jsx', '.tsx', '.vue', '.html', '.json', '.css', '.scss', '.less')
    
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in ['node_modules', '.git', 'dist', 'build', 'out', '.next', '.cache', 'coverage', 'test', 'tests', '__tests__']]
        
        for file in files:
            if not file.endswith(extensions):
                continue
            
            file_path = os.path.join(root, file)
            content = get_file_content(file_path)
            
            for priority, categories in DANGER_PATTERNS_FRONTEND.items():
                for category, keywords in categories.items():
                    for keyword in keywords:
                        if keyword.lower() in content.lower():
                            lines = content.split('\n')
                            for i, line in enumerate(lines, 1):
                                if keyword.lower() in line.lower():
                                    rel_path = os.path.relpath(file_path, project_path)
                                    results[priority][category].append({
                                        "file": rel_path,
                                        "line": i,
                                        "keyword": keyword,
                                        "snippet": line.strip()[:100]
                                    })
                                    break  # 每个文件每个关键词只记录一次
    
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
    
    # 生成报告
    priority_names = {"P0": "critical", "P1": "high", "P2": "medium"}
    for priority in ["P0", "P1", "P2"]:
        report_path = os.path.join(output_dir, f"frontend-{priority.lower()}-{priority_names[priority]}.md")
        
        if priority in results:
            content = f"# 前端 {priority} 级危险模式\n\n## 发现记录\n\n"
            for category, findings in results[priority].items():
                content += f"### {category}\n\n"
                for f in findings:
                    content += f"- `{f['file']}:{f['line']}` - `{f['keyword']}`\n"
                    content += f"  ```{f['snippet']}```\n\n"
            write_file(report_path, content)
    
    print(f"\n[OK] 扫描报告: {output_dir}/frontend-p0-critical.md, frontend-p1-high.md, frontend-p2-medium.md")
    
    return dict(results)

# ============================================
# 依赖安全检查
# ============================================

def check_dependencies(project_path, output_dir):
    """检查前端依赖安全 - 使用 npm audit 实时检查
    
    ⚠️ 根据 SKILL.md 要求：禁止凭记忆编造 CVE 编号或安全版本，必须联网核实
    """
    print("\n" + "=" * 60)
    print("依赖安全检查")
    print("=" * 60)
    
    package_json_path = os.path.join(project_path, "package.json")
    
    if not os.path.exists(package_json_path):
        print("[!] 未找到 package.json，跳过依赖检查")
        return None
    
    # 读取 package.json 统计依赖数量
    try:
        with open(package_json_path, 'r', encoding='utf-8') as f:
            package_data = json.load(f)
    except:
        print("[!] 无法解析 package.json")
        return None
    
    deps = package_data.get('dependencies', {})
    dev_deps = package_data.get('devDependencies', {})
    
    print(f"\n[*] 依赖统计:")
    print(f"  dependencies: {len(deps)} 个")
    print(f"  devDependencies: {len(dev_deps)} 个")
    
    # 检查 lock 文件和命令可用性
    lock_file = os.path.join(project_path, "package-lock.json")
    yarn_lock = os.path.join(project_path, "yarn.lock")
    
    has_npm_lock = os.path.exists(lock_file)
    has_yarn_lock = os.path.exists(yarn_lock)
    
    # 检查命令是否可用
    npm_available = False
    yarn_available = False
    
    try:
        result = subprocess.run(["npm", "--version"], capture_output=True, timeout=10)
        npm_available = result.returncode == 0
    except:
        pass
    
    try:
        result = subprocess.run(["yarn", "--version"], capture_output=True, timeout=10)
        yarn_available = result.returncode == 0
    except:
        pass
    
    print(f"\n[*] 环境检测:")
    print(f"  package-lock.json: {'存在' if has_npm_lock else '不存在'}")
    print(f"  yarn.lock: {'存在' if has_yarn_lock else '不存在'}")
    print(f"  npm 命令: {'可用' if npm_available else '不可用'}")
    print(f"  yarn 命令: {'可用' if yarn_available else '不可用'}")
    
    # 执行审计
    findings = []
    audit_result = None
    audit_method = None
    
    try:
        # 优先使用 npm（更常见）
        if npm_available:
            if not has_npm_lock:
                print("\n[!] 未找到 package-lock.json，尝试生成...")
                try:
                    subprocess.run(
                        ["npm", "i", "--package-lock-only"],
                        cwd=project_path,
                        capture_output=True,
                        timeout=300
                    )
                    print("[OK] 已生成 package-lock.json")
                except:
                    print("[!] 无法生成 package-lock.json")
            
            print("\n[*] 执行 npm audit...")
            result = subprocess.run(
                ["npm", "audit", "--json"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120
            )
            audit_output = result.stdout
            audit_method = "npm audit"
            
        elif yarn_available and has_yarn_lock:
            print("\n[*] 执行 yarn audit...")
            result = subprocess.run(
                ["yarn", "audit", "--json"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120
            )
            audit_output = result.stdout
            audit_method = "yarn audit"
            
        else:
            print("\n[!] 无法执行依赖审计:")
            if not npm_available and not yarn_available:
                print("    - npm 和 yarn 命令均不可用")
            elif not has_npm_lock and not has_yarn_lock:
                print("    - 未找到 lock 文件")
            print("\n[*] 建议手动执行:")
            print("    npm install && npm audit")
            audit_output = None
        
        # 解析 audit 输出
        if audit_output:
            try:
                audit_result = json.loads(audit_output)
                
                # npm audit 格式
                vulnerabilities = audit_result.get('vulnerabilities', {})
                
                for vuln_name, vuln_info in vulnerabilities.items():
                    severity = vuln_info.get('severity', 'unknown')
                    via = vuln_info.get('via', [])
                    fix_available = vuln_info.get('fixAvailable', False)
                    
                    # 获取漏洞详情
                    if isinstance(via, list) and len(via) > 0:
                        vuln_title = via[0].get('title', 'Unknown') if isinstance(via[0], dict) else str(via[0])
                        cwe = via[0].get('cwe', []) if isinstance(via[0], dict) else []
                    else:
                        vuln_title = str(via)
                        cwe = []
                    
                    findings.append({
                        "dependency": vuln_name,
                        "severity": severity,
                        "title": vuln_title,
                        "cwe": cwe,
                        "fix_available": fix_available
                    })
                    
            except json.JSONDecodeError:
                print("[!] 无法解析 audit 输出")
                
    except subprocess.TimeoutExpired:
        print("[!] 依赖审计执行超时")
    except Exception as e:
        print(f"[!] 依赖检查异常: {str(e)}")
    
    # 按严重程度分组
    severity_counts = {"critical": 0, "high": 0, "moderate": 0, "low": 0, "info": 0, "unknown": 0}
    for f in findings:
        sev = f.get('severity', 'unknown').lower()
        if sev in severity_counts:
            severity_counts[sev] += 1
    
    # 输出结果
    if findings:
        print(f"\n[!] 发现 {len(findings)} 个依赖漏洞:")
        for sev, count in severity_counts.items():
            if count > 0 and sev != 'unknown':
                print(f"  - {sev.upper()}: {count} 个")
        
        # 显示前 10 个高危漏洞
        high_severity = [f for f in findings if f.get('severity') in ['critical', 'high']]
        if high_severity:
            print(f"\n[!] 高危漏洞详情:")
            for f in high_severity[:10]:
                print(f"  - {f['dependency']}: {f['title'][:60]}")
                if f['fix_available']:
                    print(f"    [可修复] 运行 npm audit fix")
    elif audit_result is not None:
        print("\n[OK] 未发现依赖漏洞")
    else:
        print("\n[!] 依赖审计未执行，请手动检查")
    
    # 生成报告
    report_path = os.path.join(output_dir, "frontend-dependencies.md")
    report_content = f"""# 前端依赖安全检查

**检查方式**: {audit_method or '手动检查'}  
**检查时间**: {datetime.now().isoformat()}

## 依赖统计

| 类型 | 数量 |
|------|------|
| dependencies | {len(deps)} |
| devDependencies | {len(dev_deps)} |
| 总计 | {len(deps) + len(dev_deps)} |

## 环境检测

| 项目 | 状态 |
|------|------|
| package-lock.json | {'存在' if has_npm_lock else '不存在'} |
| yarn.lock | {'存在' if has_yarn_lock else '不存在'} |
| npm 命令 | {'可用' if npm_available else '不可用'} |
| yarn 命令 | {'可用' if yarn_available else '不可用'} |

## 漏洞统计

| 严重程度 | 数量 |
|----------|------|
| Critical | {severity_counts['critical']} |
| High | {severity_counts['high']} |
| Moderate | {severity_counts['moderate']} |
| Low | {severity_counts['low']} |
| Info | {severity_counts['info']} |

"""
    
    if findings:
        report_content += "## 漏洞详情\n\n"
        report_content += "| 依赖 | 严重程度 | 漏洞描述 | 可修复 |\n"
        report_content += "|------|----------|----------|--------|\n"
        for f in findings:
            fix_status = "✅ 是" if f['fix_available'] else "❌ 否"
            title = f['title'][:50] + "..." if len(f['title']) > 50 else f['title']
            report_content += f"| {f['dependency']} | {f['severity'].upper()} | {title} | {fix_status} |\n"
    
    report_content += f"""
## 修复建议

```bash
# 自动修复可修复的漏洞
npm audit fix

# 强制修复（可能有破坏性变更）
npm audit fix --force

# 查看详细漏洞信息
npm audit

# 使用 snyk 进行深度扫描
npx snyk test
```

## 注意事项

1. 定期执行 `npm audit` 检查依赖安全
2. 及时更新有漏洞的依赖版本
3. 使用 `npm audit fix` 自动修复
4. 对于无法自动修复的漏洞，手动升级依赖版本
"""
    
    write_file(report_path, report_content)
    print(f"\n[OK] 依赖检查报告: {report_path}")
    
    return {
        "total_deps": len(deps) + len(dev_deps),
        "vulnerability_counts": severity_counts,
        "total_vulnerabilities": len(findings),
        "findings": findings,
        "audit_available": audit_result is not None,
        "audit_method": audit_method
    }

# ============================================
# 主入口
# ============================================

def run_frontend_audit(project_path, output_dir, language="javascript", args=None):
    """前端审计主入口
    
    Args:
        project_path: 项目根目录
        output_dir: 输出目录
        language: 语言类型 (javascript, react, vue)
        args: 命令行参数对象
    """
    print("\n" + "=" * 60)
    print(f"前端审计 - {language.upper()}")
    print("=" * 60)
    
    # Phase 0: 项目分析
    print("\n[*] 项目路径:", project_path)
    print("[*] 语言类型:", language)
    
    # Phase 1: Tier 分类
    tier_results = None
    if args and args.tier:
        tier_results = run_tier_classification(project_path, output_dir, language)
    elif args is None:
        # 默认执行 Tier 分类
        tier_results = run_tier_classification(project_path, output_dir, language)
    
    # Layer 1: 预扫描
    scan_results = None
    if args and args.scan:
        scan_results = run_layer1_scan(project_path, output_dir, language)
    elif args is None:
        # 默认执行预扫描
        scan_results = run_layer1_scan(project_path, output_dir, language)
    
    # 依赖安全检查
    dep_results = check_dependencies(project_path, output_dir)
    
    # 输出汇总
    output_data = {
        "language": language,
        "tier_results": tier_results,
        "scan_results": scan_results,
        "dependency_results": dep_results,
        "generated_at": datetime.now().isoformat()
    }
    
    output_path = os.path.join(output_dir, "frontend-audit-metrics.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n[OK] 前端审计完成，结果保存到: {output_path}")
    
    return output_data

def main():
    """独立运行时的主函数"""
    parser = argparse.ArgumentParser(
        description="前端代码审计脚本 - JavaScript/TypeScript/React/Vue",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python frontend_audit.py /path/to/project --language react --scan
  python frontend_audit.py /path/to/project --language vue --tier
  python frontend_audit.py /path/to/project --scan --tier
        """
    )
    parser.add_argument("project_path", help="项目根目录")
    parser.add_argument("--language", choices=["javascript", "react", "vue"], 
                        default="javascript", help="语言类型 (默认: javascript)")
    parser.add_argument("--scan", action="store_true", help="执行 Layer 1 危险模式预扫描")
    parser.add_argument("--tier", action="store_true", help="执行 Tier 分类")
    parser.add_argument("--output", choices=["json", "sarif"], default="json", help="输出格式 (默认: json)")
    parser.add_argument("--output-dir", help="输出目录 (默认: <project>/audit-output)")
    
    args = parser.parse_args()
    
    if not os.path.isdir(args.project_path):
        print(f"Error: {args.project_path} is not a valid directory")
        sys.exit(1)
    
    # 设置输出目录
    output_dir = args.output_dir or os.path.join(args.project_path, "audit-output")
    os.makedirs(output_dir, exist_ok=True)
    
    # 执行审计
    run_frontend_audit(args.project_path, output_dir, args.language, args)

if __name__ == "__main__":
    main()