"""从 GitHub 拉取 Nuclei 模板与 Afrog POC；工具箱下载后自动建漏洞库索引。"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tongling_web.library_paths import (
    afrog_pocs_dir,
    afrog_pocs_repo_dir,
    default_github_proxy,
    nuclei_index_cache_path,
    nuclei_templates_dir,
)

NUCLEI_REPO = "https://github.com/projectdiscovery/nuclei-templates.git"
AFROG_REPO = "https://github.com/zan8in/afrog.git"
GIT_TIMEOUT_SEC = 600


def _git_env(use_proxy: bool = True) -> Dict[str, str]:
    env = os.environ.copy()
    if use_proxy:
        proxy = (
            os.environ.get("GITHUB_PROXY")
            or os.environ.get("HTTP_PROXY")
            or default_github_proxy()
        ).strip()
        if proxy:
            for key in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "http_proxy",
                "https_proxy",
                "GIT_HTTP_PROXY",
                "GIT_HTTPS_PROXY",
            ):
                env[key] = proxy
    return env


def _run_git(args: List[str], *, cwd: Optional[Path] = None, use_proxy: bool = True) -> Tuple[int, str, str]:
    if not shutil.which("git"):
        raise RuntimeError("未找到 git 命令，请先安装 Git 并加入 PATH")
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SEC,
        encoding="utf-8",
        errors="replace",
        env=_git_env(use_proxy=use_proxy),
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    return proc.returncode, out, err


def _git_sync_repo(repo_url: str, dest: Path, *, depth: int = 1, use_proxy: bool = True) -> Dict[str, Any]:
    dest = dest.resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    action = "clone"

    if (dest / ".git").is_dir():
        code, out, err = _run_git(["-C", str(dest), "pull", "--ff-only"], use_proxy=use_proxy)
        if code != 0:
            _run_git(["-C", str(dest), "fetch", "origin"], use_proxy=use_proxy)
            _, branch_out, _ = _run_git(["-C", str(dest), "rev-parse", "--abbrev-ref", "HEAD"], use_proxy=use_proxy)
            branch = (branch_out or "main").strip() or "main"
            _run_git(["-C", str(dest), "clean", "-fd"], use_proxy=use_proxy)
            code2, out2, err2 = _run_git(
                ["-C", str(dest), "reset", "--hard", f"origin/{branch}"],
                use_proxy=use_proxy,
            )
            if code2 != 0:
                raise RuntimeError(err2 or err or out2 or out or "git pull / reset 失败")
            action = "reset"
            return {"action": action, "path": str(dest), "repo": repo_url, "log": (out2 or err2 or out or err)[-800:]}
        return {"action": "pull", "path": str(dest), "repo": repo_url, "log": (out or err)[-800:]}

    if dest.exists() and any(dest.iterdir()):
        raise RuntimeError(f"目标目录已存在且非 git 仓库: {dest}")

    code, out, err = _run_git(
        ["clone", "--depth", str(depth), repo_url, str(dest)],
        use_proxy=use_proxy,
    )
    if code != 0:
        raise RuntimeError(err or out or "git clone 失败")
    return {"action": action, "path": str(dest), "repo": repo_url, "log": (out or err)[-800:]}


def _git_adopt_existing_dir(dest: Path, repo_url: str, *, use_proxy: bool = True) -> Dict[str, Any]:
    """工具箱自带的 nuclei-templates（非 git）对齐 GitHub 远端。"""
    dest = dest.resolve()
    if not dest.is_dir():
        raise RuntimeError(f"目录不存在: {dest}")
    if not any(dest.iterdir()):
        return _git_sync_repo(repo_url, dest, use_proxy=use_proxy)

    _run_git(["init"], cwd=dest, use_proxy=use_proxy)
    code, _, err = _run_git(["remote", "add", "origin", repo_url], cwd=dest, use_proxy=use_proxy)
    if code != 0 and "already exists" not in err.lower():
        _run_git(["remote", "set-url", "origin", repo_url], cwd=dest, use_proxy=use_proxy)
    _run_git(["fetch", "origin"], cwd=dest, use_proxy=use_proxy)
    for branch in ("main", "master"):
        code2, out2, err2 = _run_git(["reset", "--hard", f"origin/{branch}"], cwd=dest, use_proxy=use_proxy)
        if code2 == 0:
            return {"action": "adopt", "path": str(dest), "repo": repo_url, "log": (out2 or err2)[-800:]}
    raise RuntimeError("无法将现有 nuclei-templates 与 GitHub 对齐")


def _dir_has_yaml(root: Path) -> bool:
    if not root.is_dir():
        return False
    try:
        return any(root.rglob("*.yaml"))
    except OSError:
        return False


def sync_nuclei_templates(*, use_proxy: bool = True) -> Dict[str, Any]:
    dest = nuclei_templates_dir()
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        if dest.is_dir() and not (dest / ".git").is_dir():
            sync = _git_adopt_existing_dir(dest, NUCLEI_REPO, use_proxy=use_proxy)
        else:
            sync = _git_sync_repo(NUCLEI_REPO, dest, use_proxy=use_proxy)
    except RuntimeError:
        if use_proxy:
            if dest.is_dir() and not (dest / ".git").is_dir():
                sync = _git_adopt_existing_dir(dest, NUCLEI_REPO, use_proxy=False)
            else:
                sync = _git_sync_repo(NUCLEI_REPO, dest, use_proxy=False)
        else:
            raise
    return {"ok": True, "source": "nuclei", "sync": sync, "path": str(dest)}


def sync_afrog_pocs(*, use_proxy: bool = True) -> Dict[str, Any]:
    """克隆 zan8in/afrog 到 storage/afrog-pocs（不覆盖 storage/afrog/afrog.exe）。"""
    dest = afrog_pocs_repo_dir()
    try:
        sync = _git_sync_repo(AFROG_REPO, dest, use_proxy=use_proxy)
    except RuntimeError:
        if use_proxy:
            sync = _git_sync_repo(AFROG_REPO, dest, use_proxy=False)
        else:
            raise
    pocs = afrog_pocs_dir()
    return {
        "ok": True,
        "source": "afrog",
        "sync": sync,
        "repo_path": str(dest),
        "pocs_path": str(pocs),
        "pocs_exists": pocs.is_dir(),
    }


def ensure_poc_libraries_ready(*, use_proxy: bool = True, auto_sync_afrog: bool = True) -> Dict[str, Any]:
    """
    打开 Web「漏洞库」时生成所需资料：
    - Nuclei：storage/nuclei/nuclei-templates 建索引
    - Afrog：若无 POC 则 git 到 storage/afrog-pocs
    """
    from tongling_web.library_service import get_nuclei_library

    steps: List[Dict[str, str]] = []
    notes: List[str] = []

    def add_step(step_id: str, label: str, status: str, detail: str = "") -> None:
        steps.append({"id": step_id, "label": label, "status": status, "detail": detail})

    def set_last_step(status: str, detail: str = "") -> None:
        if steps:
            steps[-1]["status"] = status
            if detail:
                steps[-1]["detail"] = detail

    nuclei_dir = nuclei_templates_dir()
    pocs_dir = afrog_pocs_dir()
    cache_path = nuclei_index_cache_path()

    add_step("check_nuclei", "检测 Nuclei 模板", "running", str(nuclei_dir))
    has_nuclei = _dir_has_yaml(nuclei_dir)
    set_last_step(
        "ok" if has_nuclei else "warn",
        f"已找到模板目录" if has_nuclei else "未找到模板，请先在工具箱下载 nuclei",
    )

    add_step("check_afrog", "检测 Afrog POC", "running", str(pocs_dir))
    has_afrog = _dir_has_yaml(pocs_dir)
    afrog_sync: Optional[Dict[str, Any]] = None

    if has_afrog:
        set_last_step("ok", f"已找到 {pocs_dir}")
    elif auto_sync_afrog and shutil.which("git"):
        set_last_step("warn", "未找到 POC，准备从 GitHub 拉取…")
        add_step("sync_afrog", "拉取 Afrog POC（GitHub → afrog-pocs）", "running", "可能需要数十秒…")
        try:
            afrog_sync = sync_afrog_pocs(use_proxy=use_proxy)
            has_afrog = _dir_has_yaml(afrog_pocs_dir())
            set_last_step(
                "ok" if has_afrog else "warn",
                str(afrog_pocs_dir()) if has_afrog else "拉取完成但未发现 YAML",
            )
        except Exception as exc:
            notes.append(str(exc))
            set_last_step("err", str(exc))
    elif auto_sync_afrog:
        notes.append("未安装 git，Afrog POC 需手动点「拉取最新 POC」")
        set_last_step("warn", "未找到 POC 且无 git")
    else:
        set_last_step("warn", "未找到 POC 目录")

    if not has_nuclei and not has_afrog:
        return {
            "ok": False,
            "error": "未找到 Nuclei 模板或 Afrog POC，请先下载 nuclei/afrog 工具",
            "steps": steps,
            "notes": notes,
            "nuclei_templates": str(nuclei_dir),
            "afrog_pocs": str(pocs_dir),
        }

    need_reindex = not cache_path.is_file()
    if not need_reindex and has_nuclei:
        try:
            if nuclei_dir.stat().st_mtime > cache_path.stat().st_mtime:
                need_reindex = True
        except OSError:
            need_reindex = True

    if need_reindex:
        add_step("index", "建立漏洞库索引", "running", "扫描 YAML 模板…")
        get_nuclei_library().reload()
        index = get_nuclei_library().reindex()
        set_last_step(
            "ok",
            f"Nuclei {index.get('nuclei_indexed', 0)} + Afrog {index.get('afrog_indexed', 0)} = {index.get('indexed', 0)} 条",
        )
    else:
        get_nuclei_library().reload()
        stats_now = get_nuclei_library().stats()
        index = {
            "indexed": stats_now.get("total", 0),
            "nuclei_indexed": stats_now.get("nuclei_indexed", 0),
            "afrog_indexed": stats_now.get("afrog_indexed", 0),
        }
        add_step("index", "建立漏洞库索引", "skip", f"索引已存在，共 {index.get('indexed', 0)} 条")

    return {
        "ok": True,
        "auto": True,
        "nuclei_templates": str(nuclei_dir),
        "nuclei_ready": has_nuclei,
        "afrog_pocs": str(pocs_dir),
        "afrog_ready": has_afrog,
        "afrog_sync": afrog_sync,
        "index": index,
        "index_cache": str(cache_path),
        "steps": steps,
        "notes": notes,
        "stats": get_nuclei_library().stats(),
    }


def sync_all_poc_libraries(*, use_proxy: bool = True) -> Dict[str, Any]:
    """手动「拉取最新 POC」：更新 Nuclei + Afrog 并重建索引。"""
    from tongling_web.library_service import get_nuclei_library

    notes: List[str] = []
    nuclei_result: Dict[str, Any] = {}
    afrog_result: Dict[str, Any] = {}

    try:
        nuclei_result = sync_nuclei_templates(use_proxy=use_proxy)
    except Exception as exc:
        notes.append(f"Nuclei 同步失败: {exc}")

    try:
        afrog_result = sync_afrog_pocs(use_proxy=use_proxy)
    except Exception as exc:
        notes.append(f"Afrog 同步失败: {exc}")

    if not nuclei_result.get("ok") and not afrog_result.get("ok"):
        fallback = ensure_poc_libraries_ready(use_proxy=use_proxy, auto_sync_afrog=False)
        if fallback.get("ok"):
            fallback["notes"] = notes + (fallback.get("notes") or [])
            fallback["partial"] = True
            return fallback
        return {"ok": False, "error": "；".join(notes) or "同步失败"}

    get_nuclei_library().reload()
    index = get_nuclei_library().reindex()
    return {
        "ok": True,
        "nuclei": nuclei_result,
        "afrog": afrog_result,
        "index": index,
        "proxy_used": default_github_proxy() if use_proxy else "",
        "notes": notes,
        "stats": get_nuclei_library().stats(),
    }
