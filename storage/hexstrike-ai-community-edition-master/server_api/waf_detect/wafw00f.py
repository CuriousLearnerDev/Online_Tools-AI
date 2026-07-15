# 导入 Flask 相关模块：Blueprint 用于创建路由蓝图，request 处理 HTTP 请求，jsonify 返回 JSON 响应
from flask import Blueprint, request, jsonify
import logging          # 日志记录模块，用于输出运行状态和错误信息
import os               # 操作系统接口，用于读取环境变量
import shlex            # Shell 解析模块，安全地拆分命令行参数
import shutil           # 高级文件操作模块，此处用于 which() 查找可执行文件
import subprocess       # 子进程管理模块，用于执行 wafw00f 命令
import time             # 时间模块，用于计算命令执行耗时
from datetime import datetime  # 日期时间模块，用于生成时间戳

# 获取当前模块的日志记录器
logger = logging.getLogger(__name__)

# 创建 Flask 蓝图，用于组织 /api/tools/wafw00f 路由
# 蓝图名称 "api_waf_detect_wafw00f" 便于在应用中注册
api_waf_detect_wafw00f_bp = Blueprint("api_waf_detect_wafw00f", __name__)



# 定义 API 路由：POST 请求 /api/tools/wafw00f
@api_waf_detect_wafw00f_bp.route("/api/tools/wafw00f", methods=["POST"])
def wafw00f():
    """
    执行 wafw00f 工具识别目标网站的 WAF（Web Application Firewall）产品
    
    请求体（JSON 格式）：
        - target / url (必填): 目标网站 URL，如 "https://example.com"
        - additional_args (可选): 额外的 wafw00f 命令行参数，如 "-v -a"
    
    返回（JSON 格式）：
        - success: bool，命令是否执行成功（return_code == 0）
        - stdout: str，命令的标准输出内容
        - stderr: str，命令的错误输出内容
        - return_code: int，命令的返回码
        - timed_out: bool，是否超时
        - partial_results: bool，是否有部分结果（预留字段）
        - execution_time: float，命令执行耗时（秒）
        - timestamp: str，执行时间戳（ISO 格式）
        - command: list[str]，实际执行的命令（用于调试）
        - error: str（仅失败时），错误信息
    
    Returns:
        Flask Response: JSON 格式的 HTTP 响应
    """
    try:
        # 1. 解析请求参数
        params = request.json or {}  # 获取 JSON 请求体，为空则使用空字典
        target = (params.get("target") or params.get("url") or "").strip()  # 获取目标 URL
        additional_args = (params.get("additional_args") or "").strip()     # 获取额外参数
        print(request)  # 调试输出，打印请求对象

        # 2. 参数校验：target 不能为空
        if not target:
            logger.warning("🛡️ Wafw00f called without target parameter")
            return jsonify({"error": "Target parameter is required", "success": False}), 400

        # 3. 解析 wafw00f 可执行文件路径
        
        # 4. 构建命令行参数列表
        cmd: list[str] = ["wafw00f", target]  # 基础命令：[wafw00f, https://example.com]
        if additional_args:
            # 安全地拆分额外参数（处理引号、转义字符等）
            # posix=True 表示使用 POSIX 风格的解析规则（Linux/macOS）
            # posix=False 则表示 Windows 风格
            cmd += shlex.split(additional_args, posix=os.name == "posix")

        # 5. 记录日志
        logger.info("🛡️ Wafw00f: %s", " ".join(cmd))

        # 6. 执行命令并计时
        started = time.monotonic()  # 使用单调时钟，避免系统时间调整的影响
        
        try:
            # 执行子进程
            proc = subprocess.run(
                cmd,
                capture_output=True,   # 捕获 stdout 和 stderr
                text=True,             # 以文本模式返回输出（而非 bytes）
                encoding="utf-8",      # 指定编码为 UTF-8
                errors="replace",      # 遇到无法解码的字符用 � 替换
                timeout=300,           # 超时时间 300 秒（5 分钟）
                stdin=subprocess.DEVNULL,  # 禁止从标准输入读取（避免挂起）
            )
        except subprocess.TimeoutExpired:
            # 超时异常处理
            return jsonify(
                {
                    "success": False,
                    "stdout": "",
                    "stderr": "wafw00f timeout (>300s)",
                    "return_code": 124,          # 124 是超时的约定返回码
                    "timed_out": True,
                    "partial_results": False,
                    "execution_time": round(time.monotonic() - started, 4),
                    "timestamp": datetime.now().isoformat(),
                    "command": cmd,
                }
            ), 500  # HTTP 500 内部服务器错误
        except Exception as e:
            # 其他执行异常（如文件不存在、权限不足等）
            logger.exception("wafw00f execution failed")
            return jsonify(
                {
                    "success": False,
                    "stdout": "",
                    "stderr": str(e),
                    "return_code": 1,
                    "timed_out": False,
                    "partial_results": False,
                    "execution_time": round(time.monotonic() - started, 4),
                    "timestamp": datetime.now().isoformat(),
                    "command": cmd,
                }
            ), 500

        # 7. 正常完成，计算执行耗时
        elapsed = round(time.monotonic() - started, 4)
        
        # 8. 返回成功响应
        return jsonify(
            {
                "success": proc.returncode == 0,      # return_code == 0 表示成功
                "stdout": proc.stdout or "",          # 标准输出（可能为空）
                "stderr": proc.stderr or "",          # 标准错误输出
                "return_code": proc.returncode,       # 命令的返回码
                "timed_out": False,
                "partial_results": False,
                "execution_time": elapsed,
                "timestamp": datetime.now().isoformat(),
                "command": cmd,
            }
        )
    except Exception as e:
        # 顶层异常捕获（处理 JSON 解析失败等请求层面的错误）
        logger.error(f"💥 Error in wafw00f endpoint: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}", "success": False}), 500