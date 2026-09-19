"""复盘引擎 — 加载数据，执行 Skill 复盘，解析 LLM 输出，更新状态."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Any

import yaml

from data_manager import DataManager
import log

logger = logging.getLogger(__name__)


class ReviewEngine:
    """复盘引擎 — 用户触发，LLM 自主决策."""

    def __init__(self) -> None:
        self.dm = DataManager()

    def run(self, domain: str) -> dict:
        """执行复盘，自动调用 LLM 并解析结果."""
        log.log("INFO", "engine.review", "review_start",
                f"Review start for domain '{domain}'", detail={"domain": domain})
        domain_dir = Path("config") / "domains" / domain
        if not domain_dir.exists():
            log.log("ERROR", "engine.review", "domain_not_found",
                    f"Domain not found: {domain}", detail={"domain": domain})
            raise FileNotFoundError(f"Domain not found: {domain}")

        config_file = domain_dir / "config.yaml"
        skill_file = domain_dir / "SKILL.md"
        review_file = domain_dir / "review.md"

        if not config_file.exists():
            log.log("ERROR", "engine.review", "config_not_found",
                    f"config.yaml not found for domain: {domain}", detail={"domain": domain})
            raise FileNotFoundError(f"config.yaml not found for domain: {domain}")

        with open(config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        skill_md = ""
        if skill_file.exists():
            skill_md = skill_file.read_text(encoding="utf-8")

        review_md = ""
        if review_file.exists():
            review_md = review_file.read_text(encoding="utf-8")

        subs = self.dm.load_subscriptions(domain)
        blacklist = self.dm.load_blacklist(domain)
        reports = self.dm.list_review_reports(domain, limit=3)

        prompt = self._build_prompt(skill_md, review_md, subs, blacklist, reports)

        # 自动调用 LLM
        llm_output = self._call_llm(prompt, domain)

        # 解析 LLM 输出
        parsed = self.parse_llm_output(llm_output if llm_output else "")

        # 应用评分调整
        self._apply_score_changes(domain, subs, parsed.get("score_changes", []))

        # 应用黑名单
        self._apply_blacklist(domain, subs, parsed.get("blacklists", []))

        # 保存复盘报告
        report_content = llm_output or prompt
        self.dm.save_review_report(domain, report_content, metadata={
            "domain": domain,
            "subs": len(subs),
            "blacklist": len(blacklist),
            "generated_at": datetime.now().isoformat(),
        })

        log.log("INFO", "engine.review", "review_complete",
                f"Review complete for '{domain}': {len(subs)} subs, {len(blacklist)} blacklisted",
                detail={"domain": domain, "subs": len(subs), "blacklist": len(blacklist),
                        "score_changes": len(parsed.get("score_changes", [])),
                        "new_blacklists": len(parsed.get("blacklists", []))})

        return {
            "status": "ok",
            "prompt": prompt,
            "llm_output": llm_output,
            "parsed": parsed,
            "score_changes": len(parsed.get("score_changes", [])),
            "new_blacklists": len(parsed.get("blacklists", [])),
        }

    def _call_llm(self, prompt: str, domain: str) -> str | None:
        """调用系统 claude CLI 执行复盘."""
        system_prompt = f"你是 {domain} 领域的复盘分析师。请基于数据完成复盘任务，按格式输出。"
        try:
            result = subprocess.run(
                ["claude", "-p", prompt, "--prelude", system_prompt],
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
            logger.warning(f"claude CLI returned non-zero: {result.returncode}, stderr: {result.stderr}")
        except FileNotFoundError:
            logger.warning("claude CLI not found, skipping LLM execution")
        except subprocess.TimeoutExpired:
            logger.warning("claude CLI timed out")
        return None

    def _apply_score_changes(self, domain: str, subs: list[dict], score_changes: list[dict]) -> None:
        """应用评分调整."""
        from tools import ToolRegistry
        for change in score_changes:
            author = change.get("author", "")
            new_score_str = change.get("new_score", "0")
            try:
                new_score = float(new_score_str)
            except (ValueError, TypeError):
                continue
            if author:
                ToolRegistry.call("update_subscription_score",
                                  domain=domain, author=author, score=new_score)

    def _apply_blacklist(self, domain: str, subs: list[dict], blacklists: list[dict]) -> None:
        """应用黑名单建议."""
        from tools import ToolRegistry
        for bl in blacklists:
            author = bl.get("author", "")
            reason = bl.get("reason", "复盘自动拉黑")
            if author:
                ToolRegistry.call("blacklist_author",
                                  domain=domain, author=author, reason=reason)

    def _build_prompt(self, skill_md: str, review_md: str, subs: list[dict], blacklist: list[dict], reports: list[dict]) -> str:
        """构建复盘 prompt."""
        lines = []

        if skill_md:
            lines.append(skill_md)

        lines.append("\n## 当前数据\n")

        lines.append("### 订阅作者状态\n")
        for sub in subs:
            author = sub.get("author", {})
            lines.append(
                f"- **{author.get('name', '?')}** ({author.get('platform', '?')}) "
                f"评分: {sub.get('score', 0):.2f} | 分析: {sub.get('total_analyses', 0)}"
                + (f" [黑名单]" if sub.get("is_blacklisted") else "")
            )
            tags = sub.get("tags", [])
            if tags:
                lines.append(f"  标签: {', '.join(tags)}")

        if not subs:
            lines.append("(暂无订阅)")

        if blacklist:
            lines.append("\n### 黑名单\n")
            for b in blacklist:
                lines.append(f"- {b.get('author', {}).get('name', '?')}: {b.get('reason', '无')}")

        if reports:
            lines.append("\n### 最近复盘\n")
            for r in reports:
                lines.append(f"- {r['file']}")

        lines.append("\n## 可用工具\n")
        lines.append("你可以通过 [TOOL]工具名(参数)[/TOOL] 格式调用内置工具获取更多数据。")
        lines.append("工具结果会被自动执行并注入到下一次分析中。")
        lines.append("\n## 任务\n")
        lines.append("1. 使用工具获取更多信息（如股票数据/趋势等）")
        lines.append("2. 评估每位作者的近期内容质量和可靠性")
        lines.append("3. 输出评分调整、黑名单建议、领域趋势")
        lines.append("4. 按以下格式输出:")
        lines.append("""
### 评分调整
| 作者 | 原分 | 新分 | 变动 | 理由 |
|------|------|------|------|------|
| 老李 | 0.5 | 0.7 | +0.2 | 近期分析深度提升 |

### 黑名单
| 作者 | 理由 |
|------|------|
| xxx | 长期低质 |

### 领域趋势
- 关键词趋势变化
- 整体分析质量评价
""")

        return "\n".join(lines)

    def parse_llm_output(self, llm_text: str) -> dict:
        """解析 LLM 输出的结构化结果."""
        result: dict[str, Any] = {
            "score_changes": [],
            "blacklists": [],
            "trend": "",
        }

        # Check for Chinese header words that indicate table headers
        _header_words = {"作者", "原分", "新分", "变动", "理由", "评分调整", "日期", "数量", "价格"}

        in_score_table = False
        for line in llm_text.split("\n"):
            if "评分调整" in line and ("#" in line or "|" in line):
                in_score_table = True
                continue
            if in_score_table and line.strip().startswith("|") and "---" not in line:
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if len(cells) >= 4 and not any(w in cells[0] for w in _header_words):
                    result["score_changes"].append({
                        "author": cells[0],
                        "old_score": cells[1],
                        "new_score": cells[2],
                        "change": cells[3],
                        "reason": cells[4] if len(cells) > 4 else "",
                    })
            if "黑名单" in line and "|" in line and "###" not in line and "---" not in line:
                in_score_table = False
            if "黑名单" in line and "###" in line:
                in_score_table = True
                continue
            if in_score_table and "### 领域趋势" not in line:
                pass

        in_bl_table = False
        for line in llm_text.split("\n"):
            if "黑名单" in line and "###" in line:
                in_bl_table = True
                continue
            if in_bl_table and line.strip().startswith("|") and "---" not in line:
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if len(cells) >= 2 and not any(w in cells[0] for w in _header_words):
                    result["blacklists"].append({
                        "author": cells[0],
                        "reason": cells[1],
                    })
            if "### 领域趋势" in line:
                in_bl_table = False

        in_trend = False
        for line in llm_text.split("\n"):
            if "### 领域趋势" in line:
                in_trend = True
                continue
            if in_trend:
                if line.startswith("###"):
                    break
                result["trend"] += line + "\n"

        return result