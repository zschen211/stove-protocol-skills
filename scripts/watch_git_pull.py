#!/usr/bin/env python3
"""
持续监听当前 Git 仓库的 main 分支（或指定分支），
当 origin 上有新提交时自动执行 git pull 拉取到本地。
拉取后若 skills/ 下有文件变更，会将对应 skill 目录同步到 ~/.openclaw/workspace/skills。

--repo 可为本地路径或克隆 URL（如 https://github.com/xxx/yyy.git）。
若为 URL，则会在 --work-dir 目录下 clone（不存在时），再对该目录做监听与拉取。
仅依赖 Python 标准库。
"""
import argparse
import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path

OPENCLAW_SKILLS_DIR = Path.home() / ".openclaw/workspace/skills"


def is_clone_url(repo: str) -> bool:
    return (
        repo.startswith("http://")
        or repo.startswith("https://")
        or repo.startswith("git@")
        or repo.startswith("ssh://")
    )


def default_workdir_from_url(url: str) -> str:
    """从 clone URL 推导默认目录名，如 .../stove-protocol-skills.git -> stove-protocol-skills。"""
    s = url.rstrip("/").replace("\\", "/")
    base = s.split("/")[-1] if "/" in s else s
    if base.endswith(".git"):
        base = base[:-4]
    return base or "repo"


def run_git(repo_dir: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["git", "-C", str(repo_dir), *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
        check=check,
    )


def get_current_commit(repo_dir: Path, ref: str = "HEAD") -> str:
    result = run_git(repo_dir, "rev-parse", ref)
    return result.stdout.strip()


def fetch_and_is_behind(repo_dir: Path, branch: str) -> bool:
    """Fetch origin and return True if local branch is behind origin/branch."""
    run_git(repo_dir, "fetch", "origin", branch, check=True)
    local_ref = f"refs/heads/{branch}"
    remote_ref = f"refs/remotes/origin/{branch}"
    try:
        local_sha = get_current_commit(repo_dir, local_ref)
        remote_sha = get_current_commit(repo_dir, remote_ref)
    except subprocess.CalledProcessError:
        return False
    # 若远程与本地 commit 不同，说明需要拉取（可能落后也可能超前，通常我们只关心落后）
    if local_sha != remote_sha:
        # 检查本地是否在 origin/branch 的祖先上（即落后）
        result = run_git(repo_dir, "merge-base", "--is-ancestor", local_ref, remote_ref, check=False)
        return result.returncode == 0
    return False


def pull(repo_dir: Path, branch: str, checkout_first: bool = False) -> bool:
    """Run git pull origin <branch>. If checkout_first, checkout branch before pull. Return True if pull succeeded."""
    if checkout_first:
        run_git(repo_dir, "checkout", branch, check=True)
    result = run_git(repo_dir, "pull", "origin", branch, check=False)
    return result.returncode == 0


def clone(url: str, work_dir: Path) -> None:
    """Clone url into work_dir. work_dir must not exist or be empty."""
    subprocess.run(
        ["git", "clone", url, str(work_dir)],
        check=True,
        timeout=300,
        capture_output=True,
        text=True,
    )


def get_skills_changed_since(repo_dir: Path, since_ref: str) -> list[str]:
    """返回自 since_ref 以来在 skills/ 下有变更的 skill 名列表（skills 下第一级目录名）。"""
    result = run_git(repo_dir, "diff", "--name-only", since_ref, "HEAD", "--", "skills/", check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return []
    names: set[str] = set()
    for line in result.stdout.strip().splitlines():
        path = line.strip().replace("\\", "/")
        if not path.startswith("skills/") or path == "skills":
            continue
        parts = path.split("/")
        if len(parts) >= 2:
            names.add(parts[1])
    return sorted(names)


def sync_skill_to_openclaw(repo_dir: Path, skill_name: str, dest_dir: Path, logger: logging.Logger) -> None:
    """将 repo_dir/skills/<skill_name> 整目录同步到 dest_dir/<skill_name>，覆盖已存在内容。"""
    src = repo_dir / "skills" / skill_name
    if not src.is_dir():
        return
    dest = dest_dir / skill_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    logger.info("已同步 skill %s -> %s", skill_name, dest)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="持续监听 Git 仓库 main 分支，有更新时自动拉取。",
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="仓库路径（本地目录）或 clone URL（如 https://github.com/xxx/yyy.git）。默认为当前目录。",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="当 --repo 为 URL 时，本地克隆/使用的目录；默认根据 URL 命名为当前目录下的子目录（如 xxx.git -> xxx）。",
    )
    parser.add_argument(
        "--branch",
        default="main",
        help="要监听的远程分支名，默认 main。",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=60.0,
        help="轮询间隔（秒），默认 60。",
    )
    parser.add_argument(
        "--checkout-main",
        action="store_true",
        help="拉取前先 checkout 到该分支（保证更新的是该分支而非当前分支）。",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别，默认 INFO。",
    )
    parser.add_argument(
        "--openclaw-skills-dir",
        type=Path,
        default=OPENCLAW_SKILLS_DIR,
        help="拉取后若有 skills 变更，同步到此目录（默认 ~/.openclaw/workspace/skills）。",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(__name__)
    repo_dir: Path
    if is_clone_url(args.repo):
        work_dir = args.work_dir
        if work_dir is None:
            work_dir = Path.cwd() / default_workdir_from_url(args.repo)
        work_dir = work_dir.resolve()
        if not work_dir.exists() or not (work_dir / ".git").exists():
            logger.info("正在克隆 %s 到 %s ...", args.repo, work_dir)
            clone(args.repo, work_dir)
        repo_dir = work_dir
    else:
        repo_dir = Path(args.repo).resolve()
    if not (repo_dir / ".git").exists():
        logger.error("不是 Git 仓库: %s", repo_dir)
        sys.exit(1)
    logger.info("开始监听仓库 %s 的 %s 分支，间隔 %.1f 秒。按 Ctrl+C 退出。", repo_dir, args.branch, args.interval)
    try:
        while True:
            try:
                if fetch_and_is_behind(repo_dir, args.branch):
                    head_before = get_current_commit(repo_dir, "HEAD")
                    logger.info("检测到 origin/%s 有新提交，正在拉取...", args.branch)
                    if pull(repo_dir, args.branch, checkout_first=args.checkout_main):
                        logger.info("拉取成功。")
                        changed_skills = get_skills_changed_since(repo_dir, head_before)
                        if changed_skills:
                            args.openclaw_skills_dir.mkdir(parents=True, exist_ok=True)
                            for name in changed_skills:
                                sync_skill_to_openclaw(repo_dir, name, args.openclaw_skills_dir, logger)
                    else:
                        logger.warning("拉取失败，请检查冲突或网络。")
                else:
                    logger.debug("当前已是最新，跳过拉取。")
            except subprocess.TimeoutExpired:
                logger.warning("Git 命令超时，下一轮再试。")
            except subprocess.CalledProcessError as e:
                logger.warning("Git 命令执行失败: %s", e)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        logger.info("已退出监听。")


if __name__ == "__main__":
    main()
