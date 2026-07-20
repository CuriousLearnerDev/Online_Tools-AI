#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用代码审计入口 - 语言检测 + 路由分发

自动检测项目语言类型，并调用对应的审计脚本：
- Java/Kotlin 项目 → java_audit.py
- JavaScript/React/Vue 项目 → frontend_audit.py
- 混合项目 → 两者都执行

Usage:
    python audit.py <project_path> [options]

Options:
    --detect-lang   仅执行语言检测
    --scan          执行 Layer 1 危险模式预扫描
    --tier          执行 Tier 分类
    --coverage      执行覆盖率检查（需配合 --reviewed-file）
    --reviewed-file 指定审阅清单文件路径
    --output        输出格式: json (默认), sarif
    --help, -h      显示帮助信息

Examples:
    python audit.py /path/to/project --detect-lang
    python audit.py /path/to/project --scan --tier
    python audit.py /path/to/java-project --scan
    python audit.py /path/to/react-project --scan
    python audit.py /path/to/mixed-project --scan --tier
"""

import os
import sys
import io
import json
import argparse
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
        try:
            has_backend_dir = any(d in ['backend', 'server', 'api'] for d in os.listdir(project_path) if os.path.isdir(os.path.join(project_path, d)))
            has_frontend_dir = any(d in ['frontend', 'client', 'web', 'ui'] for d in os.listdir(project_path) if os.path.isdir(os.path.join(project_path, d)))
        except:
            has_backend_dir = False
            has_frontend_dir = False
        
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
    
    # 根据语言类型推荐审计脚本
    script_mapping = {
        "java": "java_audit.py",
        "javascript": "frontend_audit.py",
        "react": "frontend_audit.py",
        "vue": "frontend_audit.py",
        "mixed": "java_audit.py + frontend_audit.py",
        "unknown": "手动选择"
    }
    
    print(f"\n[*] 推荐审计脚本: {script_mapping.get(language, '未知')}")
    
    # 生成报告
    report_path = os.path.join(output_dir, "language-detection.md")
    report_content = f"""# 语言检测结果

## 检测摘要

| 项目 | 结果 |
|------|------|
| 语言类型 | **{language_names.get(language, language)}** |
| 检测时间 | {datetime.now().isoformat()} |
| 推荐脚本 | `{script_mapping.get(language, '未知')}` |

## 详细信息

| 指标 | 数值 |
|------|------|
"""
    for key, value in details.items():
        report_content += f"| {key} | {value} |\n"
    
    report_content += f"""
## 审计流程建议

"""
    if language == "java":
        report_content += """- 使用 `java_audit.py` 执行 Java 后端审计
- Tier 分类：Controller(T1) → Service(T2) → Entity(T3)
- 重点检查：反序列化、SQL注入、命令执行、认证绕过
"""
    elif language in ["javascript", "react", "vue"]:
        report_content += """- 使用 `frontend_audit.py` 执行前端审计
- Tier 分类：页面组件(T1) → 业务组件(T2) → 工具函数(T3)
- 重点检查：XSS、DOM操作、敏感信息泄露、配置安全
"""
    elif language == "mixed":
        report_content += """- 分别执行 `java_audit.py` 和 `frontend_audit.py`
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
        "recommended_script": script_mapping.get(language, "未知")
    }

# ============================================
# 路由分发
# ============================================

def dispatch_audit(project_path, output_dir, language, args):
    """根据语言类型分发到对应的审计脚本"""
    
    # 获取脚本目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    if language == "java":
        print("\n[*] 调用 Java 审计脚本...")
        import java_audit
        java_audit.run_java_audit(project_path, output_dir, args)
        
    elif language in ["javascript", "react", "vue"]:
        print(f"\n[*] 调用前端审计脚本 (语言: {language})...")
        import frontend_audit
        frontend_audit.run_frontend_audit(project_path, output_dir, language, args)
        
    elif language == "mixed":
        print("\n[*] 混合项目，执行两种审计...")
        
        # Java 审计
        import java_audit
        java_audit.run_java_audit(project_path, output_dir, args)
        
        # 前端审计
        import frontend_audit
        frontend_language = args.frontend_language or "javascript"
        frontend_audit.run_frontend_audit(project_path, output_dir, frontend_language, args)
        
    else:
        print("\n[!] 无法识别项目类型，请手动指定审计脚本")
        print("  使用方法:")
        print("    python java_audit.py <project_path> --scan --tier")
        print("    python frontend_audit.py <project_path> --scan --tier")

# ============================================
# 主函数
# ============================================

def main():
    parser = argparse.ArgumentParser(
        description="通用代码审计入口 - 语言检测 + 路由分发",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python audit.py /path/to/project --detect-lang      # 仅语言检测
  python audit.py /path/to/project --scan --tier      # 自动检测并执行审计
  python audit.py /path/to/java-project --scan        # Java 项目审计
  python audit.py /path/to/react-project --scan       # React 项目审计
  python audit.py /path/to/mixed-project --scan       # 混合项目审计
        """
    )
    parser.add_argument("project_path", help="项目根目录")
    parser.add_argument("--detect-lang", action="store_true", help="仅执行语言检测（不执行审计）")
    parser.add_argument("--scan", action="store_true", help="执行 Layer 1 危险模式预扫描")
    parser.add_argument("--tier", action="store_true", help="执行 Tier 分类")
    parser.add_argument("--coverage", action="store_true", help="执行覆盖率检查")
    parser.add_argument("--reviewed-file", help="审阅清单文件路径（用于覆盖率检查）")
    parser.add_argument("--frontend-language", choices=["javascript", "react", "vue"], 
                        help="手动指定前端语言类型（用于混合项目）")
    parser.add_argument("--output", choices=["json", "sarif"], default="json", help="输出格式 (默认: json)")
    parser.add_argument("--output-dir", help="输出目录 (默认: <project>/audit-output)")
    
    args = parser.parse_args()
    
    if not os.path.isdir(args.project_path):
        print(f"Error: {args.project_path} is not a valid directory")
        sys.exit(1)
    
    # 设置输出目录
    output_dir = args.output_dir or os.path.join(args.project_path, "audit-output")
    os.makedirs(output_dir, exist_ok=True)
    
    # Phase 0: 语言检测
    language_results = run_language_detection(args.project_path, output_dir)
    language = language_results["language"]
    
    # 仅语言检测模式
    if args.detect_lang:
        print("\n[OK] 语言检测完成，未执行审计")
        print(f"  如需执行审计，请运行:")
        print(f"    python audit.py {args.project_path} --scan --tier")
        return
    
    # 路由分发
    dispatch_audit(args.project_path, output_dir, language, args)

if __name__ == "__main__":
    main()