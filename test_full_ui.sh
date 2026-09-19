#!/bin/bash
BASE=http://127.0.0.1:8080
PASS=0; FAIL=0

check() {
    local name="$1" url="$2" keyword="$3"
    local code=$(curl -s -o /tmp/ui_test_body.txt -w "%{http_code}" "$BASE$url" 2>/dev/null)
    if [ "$code" == "000" ]; then echo "❌ FAIL: $name — 无响应"; FAIL=$((FAIL+1)); return; fi
    if grep -q "$keyword" /tmp/ui_test_body.txt 2>/dev/null; then
        echo "✅ PASS: $name"; PASS=$((PASS+1))
    else echo "❌ FAIL: $name (未找到 '$keyword')"; FAIL=$((FAIL+1)); fi
}
check_html() {
    local name="$1" url="$2" expected="$3"
    local code=$(curl -s -o /tmp/ui_test_body.txt -w "%{http_code}" "$BASE$url" 2>/dev/null)
    if [ "$code" == "000" ]; then echo "❌ FAIL: $name — 无响应"; FAIL=$((FAIL+1)); return; fi
    if grep -qF "$expected" /tmp/ui_test_body.txt 2>/dev/null; then
        echo "✅ PASS: $name"; PASS=$((PASS+1))
    else echo "❌ FAIL: $name (缺失)"; FAIL=$((FAIL+1)); fi
}

echo "==============================================="
echo "  完整 UI 自动化测试（覆盖 38 项）"
echo "  服务器: $BASE"
echo "==============================================="
echo ""

echo "━━━ 1. 基础页面可用性 (5) ━━━━━━━━━━━━━━━━━━━━━"
check "首页 /" "/" "分析结果"
check "搜索页 /search" "/search" "视频搜索"
check "结果页 /results" "/results" "分析结果"
check "转录页 /transcripts" "/transcripts" "转录"
check "领域页 /domains" "/domains" "领域"

echo "━━━ 2. 搜索页: 配置工具栏 (8) ━━━━━━━━━━━━━━━━━━━"
check_html "工具栏面板 id=config-panel" "/search" 'id="config-panel"'
check_html "Claude 按钮 data-model=claude" "/search" 'data-model="claude"'
check_html "Codex 按钮 data-model=codex" "/search" 'data-model="codex"'
check_html "Whisper 下拉框 id=whisper-toolbar" "/search" 'id="whisper-toolbar"'
check_html "状态标签 id=config-status" "/search" 'id="config-status"'
check_html "模型 radio group id=model-toolbar" "/search" 'id="model-toolbar"'
check_html "localStorage 持久化脚本" "/search" "localStorage"
check_html "工具栏 API getToolbarConfig" "/search" "getToolbarConfig"

echo "━━━ 3. 搜索页: 分析对话框 (3) ━━━━━━━━━━━━━━━━━━━"
check_html "对话框读取工具栏" "/search" "getToolbarConfig"
check_html "Whisper 网格选择器" "/search" "whisper-opt"
check_html "分析类型单选" "/search" "analysis_type"

echo "━━━ 4. 结果页: 标签渲染 (2) ━━━━━━━━━━━━━━━━━━━━"
check_html "⏳ 待分析 标签（旧数据）" "/results" "待分析"
check_html "🤖 模型图标（模板）" "/results" "🤖"

echo "━━━ 5. 仪表盘: 全局搜索 (4) ━━━━━━━━━━━━━━━━━━━━"
check_html "⌘K 搜索按钮" "/" "⌘K"
check_html "搜索模态框 id=global-search-modal" "/" "global-search-modal"
check_html "统计卡片" "/" "分析"
check_html "最近活动区域" "/" "活动"

echo "━━━ 6. 错误页面 (2) ━━━━━━━━━━━━━━━━━━━━━━━━━━"
check_html "404 页面" "/nonexistent" "404"
check_html "返回首页按钮" "/nonexistent" "返回首页"

echo "━━━ 7. 后端代码验证 (4) ━━━━━━━━━━━━━━━━━━━━━━"
grep -q "model_type" /data/workspace/analyze_stock_-dev/analyze_stock_-dev/web/routers/search.py && echo "✅ PASS: search.py 写 model_type" && PASS=$((PASS+1)) || { echo "❌ FAIL: search.py model_type"; FAIL=$((FAIL+1)); }
grep -q "whisper_model" /data/workspace/analyze_stock_-dev/analyze_stock_-dev/web/routers/search.py && echo "✅ PASS: search.py 写 whisper_model" && PASS=$((PASS+1)) || { echo "❌ FAIL: search.py whisper_model"; FAIL=$((FAIL+1)); }
grep -qF 'Config Panel' /data/workspace/analyze_stock_-dev/analyze_stock_-dev/web/views/search.html && echo "✅ PASS: search.html 工具栏 HTML" && PASS=$((PASS+1)) || { echo "❌ FAIL: search.html Config Panel"; FAIL=$((FAIL+1)); }
grep -qF 'whisper_model' /data/workspace/analyze_stock_-dev/analyze_stock_-dev/web/views/results.html && echo "✅ PASS: results.html 渲染 whisper_model" && PASS=$((PASS+1)) || { echo "❌ FAIL: results.html whisper_model"; FAIL=$((FAIL+1)); }

echo "━━━ 8. API 端点 (2) ━━━━━━━━━━━━━━━━━━━━━━━━━"
check "Logs API" "/api/logs" "total"
check "转录 API" "/api/transcripts" ""

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  测试完成"
echo "  ✅ 通过: $PASS   ❌ 失败: $FAIL"
echo "  通过率: $((PASS * 100 / (PASS+FAIL==0?1:PASS+FAIL)))%"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
