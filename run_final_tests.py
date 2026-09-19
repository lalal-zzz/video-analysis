"""运行所有测试验证重构后的代码。"""
import subprocess
import sys

PYTHON = "/d/Anconda/python.exe"

def run_test(name, cmd):
    print(f'\n{"=" * 60}')
    print(f'TEST: {name}')
    print(f'{"=" * 60}')
    # 替换 python 为完整路径
    cmd = cmd.replace("python ", f"{PYTHON} ")
    cmd = cmd.replace("python -m", f"{PYTHON} -m")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
    if result.stdout:
        print(result.stdout[-1500:])
    if result.stderr:
        stderr = result.stderr[-500:]
        if "Traceback" in stderr or "Error" in stderr:
            print(stderr)
    passed = result.returncode == 0
    print(f"{'✓ PASS' if passed else '✗ FAIL'} (exit code {result.returncode})")
    return passed

if __name__ == "__main__":
    results = {}
    
    # 1. 语法检查
    results["syntax_check"] = run_test("语法检查",
        'python -c "import py_compile; py_compile.compile(\'scrapers/youtube.py\', doraise=True); py_compile.compile(\'scrapers/bilibili.py\', doraise=True); py_compile.compile(\'scrapers/douyin.py\', doraise=True); py_compile.compile(\'tools/author.py\', doraise=True); py_compile.compile(\'tools/scraper.py\', doraise=True); print(\'All syntax OK\')"')
    
    # 2. 模块导入测试
    results["imports"] = run_test("模块导入",
        'python -c "import sys; sys.path.insert(0, \'.\'); from scrapers import YouTubeScraper, BilibiliScraper, DouyinScraper; from tools.author import get_video_author; from tools.registry import ToolRegistry; print(f\'Import OK - {len(ToolRegistry.list_all())} tools registered\')"')
    
    # 3. 已有集成测试
    results["integration"] = run_test("集成测试（含数据层、引擎、工具）",
        'python tests/run_external.py')
    
    # 4. Web路由测试 (pytest)
    results["web_routes"] = run_test("Web路由测试",
        'python -m pytest tests/test_web_routes.py -v --tb=short 2>&1')
    
    # 打印总结
    print(f'\n{"=" * 60}')
    print(f'测试结果汇总')
    print(f'{"=" * 60}')
    for name, passed in results.items():
        print(f'  {"✓" if passed else "✗"} {name}')
    
    all_pass = all(results.values())
    print(f'\n{"全部通过! 🎉" if all_pass else "部分失败 😢"}')
    sys.exit(0 if all_pass else 1)