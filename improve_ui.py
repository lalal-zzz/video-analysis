"""Improve the web UI for search page."""
import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# 1. Update search.html with loading spinner and nicer UI
search_html_path = PROJECT_ROOT / "web" / "views" / "search.html"
content = search_html_path.read_text(encoding="utf-8")

# Add hx-indicator to form
content = content.replace(
    '<form hx-post="/search/execute" hx-target="#search-results"',
    '<form hx-post="/search/execute" hx-target="#search-results" hx-indicator="#search-spinner"',
)

# Add spinner and better button area
old_button_end = '</button>\n            </div>\n        </form>\n    </div>\n\n    <!-- 搜索结果 -->\n    <div id="search-results"'
new_with_spinner = """</button>
            </div>
            <!-- Loading spinner -->
            <div id="search-spinner" class="htmx-indicator flex items-center gap-2 text-sm text-gray-500">
                <svg class="animate-spin h-5 w-5 text-blue-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span>搜索中...</span>
            </div>
        </form>
    </div>

    <!-- 搜索结果 -->
    <div id="search-results" class="space-y-3""""
content = content.replace(old_button_end, new_with_spinner)

# Better empty state
content = content.replace(
    '<div class="text-center text-gray-400 py-12">\n            输入关键词开始搜索\n        </div>',
    '<div class="text-center text-gray-400 py-16">\n            <div class="text-5xl mb-4">🔍</div>\n            <p class="text-lg">输入关键词开始搜索视频</p>\n            <p class="text-sm mt-2">支持 Bilibili / YouTube / 抖音 三大平台</p>\n        </div>',
)

search_html_path.write_text(content, encoding="utf-8")
print("✅ search.html - added spinner, better UI")

# 2. Update base.html with htmx-indicator CSS
base_html_path = PROJECT_ROOT / "web" / "views" / "base.html"
if base_html_path.exists():
    base_content = base_html_path.read_text(encoding="utf-8")
    if "htmx-indicator" not in base_content:
        old_style = "</style>"
        new_style = """        .htmx-indicator { opacity: 0; transition: opacity 0.3s ease; }\n        .htmx-request .htmx-indicator { opacity: 1; }\n        .htmx-request.htmx-indicator { opacity: 1; }\n    </style>"""
        base_content = base_content.replace(old_style, new_style)
        base_html_path.write_text(base_content, encoding="utf-8")
        print("✅ base.html - added htmx-indicator CSS")

# 3. Fix search.py route
search_route_path = PROJECT_ROOT / "web" / "routers" / "search.py"
route_content = search_route_path.read_text(encoding="utf-8")

# Fix 1: Remove lambda/api_key from YouTubeScraper
route_content = route_content.replace(
    '"youtube": lambda: YouTubeScraper(api_key="")',
    '"youtube": YouTubeScraper',
)

# Fix 2: Add FormData import if missing
if "from litestar.datastructures import FormData" not in route_content:
    route_content = route_content.replace(
        "from litestar.response import Template",
        "from litestar.response import Template\nfrom litestar.datastructures import FormData",
    )

# Fix 3: Change handler signature
route_content = route_content.replace(
    "async def execute_search(data: dict[str, str]) -> str:",
    "async def execute_search(data: FormData) -> str:",
)

search_route_path.write_text(route_content, encoding="utf-8")
print("✅ search.py - fixed YouTubeScraper, FormData handler")

# 4. Run web tests
print()
print("=" * 60)
print("Running web route tests...")
print("=" * 60)
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_web_routes.py", "-v", "--tb=short"],
    capture_output=True, text=True, timeout=60,
)
print(result.stdout)
if result.stderr:
    for line in result.stderr.split("\n"):
        if "FAILED" in line or "passed" in line or "ERROR" in line:
            print(line)

if result.returncode == 0:
    print("\n✅ ALL WEB TESTS PASSED")
else:
    print(f"\n❌ {result.returncode} test(s) failed")

print()
print("Improvements applied:")
print("  ✓ Loading spinner indicator (shows during search)")
print("  ✓ Better UI styling and empty state")
print("  ✓ YouTubeScraper fixed (no api_key)")
print("  ✓ FormData handler for HTMX")
print("  ✓ htmx-indicator CSS animation")
print()
print("Restart the web server and refresh your browser to see changes.")

sys.exit(result.returncode)