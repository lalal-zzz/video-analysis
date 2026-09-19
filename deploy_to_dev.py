"""
deploy_to_dev.py
================
使用方法:
    python deploy_to_dev.py zip001.txt --password 123456

功能:
    1. 合并 zip00*.txt 分块并 AES 解密解压
    2. 将解压内容覆盖合并到项目根目录
    3. 切换到 dev 分支并提交 + 推送
    4. 清理临时目录

可选参数:
    --password   解密密码 (默认读取环境变量 PASSWORD)
    --branch     目标分支 (默认 dev)
    --message    commit 信息 (默认自动生成)
    --no-push    只提交不推送
    --keep-zip   保留解压临时目录
"""

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import zipfile
import base64
import io
import re
import hashlib

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
except ImportError:
    print("❌ 缺少依赖，请先运行: pip install pycryptodome")
    sys.exit(1)


# ── 解密 / 解压 ───────────────────────────────────────────────────────────

def _derive_key(password: str) -> bytes:
    return hashlib.sha256(password.encode("utf-8")).digest()


def _decrypt(data: bytes, password: str) -> bytes:
    key = _derive_key(password)
    iv = data[:16]
    ct = data[16:]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return unpad(cipher.decrypt(ct), AES.block_size)


def extract_chunks(txt_path: Path, output_dir: Path, password: str) -> bool:
    """把 zip00*.txt 分块合并 -> 解密 -> 解压到 output_dir，成功返回 True"""
    base_dir = txt_path.parent

    match = re.match(r"^(.*?)\.?(\d{3})\.txt$", txt_path.name)
    if match:
        base_stem = match.group(1)
    else:
        base_stem = txt_path.stem
        m2 = re.match(r"^(.*?)\.?(\d{3})$", base_stem)
        base_stem = m2.group(1) if m2 else base_stem

    pattern = re.compile(r"^" + re.escape(base_stem) + r"\.?(\d{3})\.txt$")
    chunk_files = []
    for f in sorted(base_dir.iterdir()):
        m = pattern.match(f.name)
        if m:
            chunk_files.append((int(m.group(1)), f))
    chunk_files.sort()

    if not chunk_files:
        print(f"❌ 未找到分块文件 (前缀: {base_stem})")
        return False

    print(f"📦 找到 {len(chunk_files)} 个分块文件")

    b64_parts = []
    for idx, cf in chunk_files:
        content = cf.read_text(encoding="utf-8")
        if idx == 1 and content.startswith("---CHUNKED:"):
            _, _, rest = content.partition("\n")
            b64_parts.append(rest)
        else:
            b64_parts.append(content)
    b64_str = "".join(b64_parts)

    zip_data = base64.b64decode(b64_str)

    if password:
        try:
            zip_data = _decrypt(zip_data, password)
            print("🔓 AES 解密成功")
        except Exception as e:
            print(f"❌ 解密失败: {e}")
            return False

    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        zf.extractall(output_dir)
    print(f"✅ 解压完成 -> {output_dir}")
    return True


# ── Git 操作 ──────────────────────────────────────────────────────────────

def run_git(args, cwd: Path):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)


def deploy(txt_path: Path, password: str, branch: str,
           commit_msg: str, push: bool, keep_zip: bool):

    root = txt_path.parent.resolve()
    tmp_dir = root / "_deploy_tmp"

    # 1. 解压
    print("\n🔄 步骤 1/4 — 解压分块文件...")
    if not extract_chunks(txt_path, tmp_dir, password):
        sys.exit(1)

    # 2. 切换到目标分支
    print(f"\n🌿 步骤 2/4 — 切换到分支 [{branch}]...")
    r = run_git(["checkout", branch], root)
    if r.returncode != 0:
        r2 = run_git(["checkout", "-b", branch], root)
        if r2.returncode != 0:
            print(f"❌ 无法切换/创建分支 {branch}:\n{r2.stderr}")
            sys.exit(1)
        print(f"  ✨ 新建分支 {branch}")
    else:
        print(f"  ✔ 已切换到 {branch}")

    # 3. 复制文件到根目录
    print("\n📂 步骤 3/4 — 将解压内容合并到项目根目录...")
    copied = 0
    for src in tmp_dir.rglob("*"):
        if src.is_file():
            rel = src.relative_to(tmp_dir)
            dst = root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
    print(f"  ✔ 共复制 {copied} 个文件")

    if not keep_zip:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print("  🗑 已清理临时目录")

    # 4. Git add + commit + push
    print("\n📤 步骤 4/4 — 提交并推送...")
    run_git(["add", "--all"], root)

    # 排除分块 txt 和临时目录
    for pattern in ["zip0*.txt", "_deploy_tmp"]:
        run_git(["reset", "HEAD", "--", pattern], root)

    if not commit_msg:
        commit_msg = f"feat: update dev codebase [{datetime.now().strftime('%Y-%m-%d %H:%M')}]"

    r = run_git(["commit", "-m", commit_msg], root)
    if r.returncode != 0:
        if "nothing to commit" in r.stdout:
            print("  ℹ️  没有需要提交的变更")
        else:
            print(f"❌ commit 失败:\n{r.stderr}")
            sys.exit(1)
    else:
        print(f"  ✔ commit: {commit_msg}")

    if push:
        r = run_git(["push", "origin", branch], root)
        if r.returncode != 0:
            print(f"❌ push 失败:\n{r.stderr}")
            sys.exit(1)
        print(f"  🚀 已推送到 origin/{branch}")

    print(f"\n✅ 全部完成！分支 [{branch}] 已更新。")


# ── 入口 ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="解压 zip 分块并自动部署到 Git 分支")
    parser.add_argument("txt_file", help="第一个分块文件，如 zip001.txt")
    parser.add_argument("--password", default=os.environ.get("PASSWORD", ""),
                        help="AES 解密密码 (默认读取环境变量 PASSWORD)")
    parser.add_argument("--branch", default="dev", help="目标 Git 分支 (默认: dev)")
    parser.add_argument("--message", default="", help="自定义 commit 信息")
    parser.add_argument("--no-push", action="store_true", help="只提交，不推送")
    parser.add_argument("--keep-zip", action="store_true", help="保留解压临时目录")
    args = parser.parse_args()

    txt_path = Path(args.txt_file).resolve()
    if not txt_path.is_file():
        print(f"❌ 文件不存在: {txt_path}")
        sys.exit(1)

    if not args.password:
        print("❌ 请通过 --password 参数或环境变量 PASSWORD 提供解密密码")
        sys.exit(1)

    deploy(
        txt_path=txt_path,
        password=args.password,
        branch=args.branch,
        commit_msg=args.message,
        push=not args.no_push,
        keep_zip=args.keep_zip,
    )


if __name__ == "__main__":
    main()
