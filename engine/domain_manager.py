"""领域管理器 — 创建/运行领域 Skill."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Any

import yaml

from engine.discover import DiscoverEngine
from engine.monitor import MonitorEngine
from engine.review import ReviewEngine
import log

logger = logging.getLogger(__name__)


class DomainManager:
    """领域管理器 — create / run / skill 解析."""

    def __init__(self) -> None:
        self.discover_engine = DiscoverEngine()
        self.monitor_engine = MonitorEngine()
        self.review_engine = ReviewEngine()

    # ── 创建领域 ───────────────────────────────────────────

    def create(self, domain_name: str, user_intent: str, template_name: str = "stock") -> dict:
        """创建新领域 Skill，返回生成的文件路径."""
        log.log("INFO", "engine.domain_manager", "domain_create",
                f"Creating domain '{domain_name}' from template '{template_name}'",
                detail={"domain": domain_name, "intent": user_intent, "template": template_name})
        domain_dir = Path("config") / "domains" / domain_name
        domain_dir.mkdir(parents=True, exist_ok=True)

        # 加载模板
        template_dir = Path("config") / "domains" / template_name
        if not template_dir.exists():
            template_name = "stock"
            template_dir = Path("config") / "domains" / template_name
            if not template_dir.exists():
                raise FileNotFoundError(f"Template not found: {template_dir}")

        skill_md = ""
        config_yaml = ""
        review_md = ""

        skill_file = template_dir / "SKILL.md"
        if skill_file.exists():
            skill_md = skill_file.read_text(encoding="utf-8")

        config_file = template_dir / "config.yaml"
        if config_file.exists():
            config_yaml = config_file.read_text(encoding="utf-8")

        review_file = template_dir / "review.md"
        if review_file.exists():
            review_md = review_file.read_text(encoding="utf-8")

        # 生成 SKILL.md
        new_skill = self._generate_skill_via_llm(user_intent, skill_md, domain_name)
        (domain_dir / "SKILL.md").write_text(new_skill, encoding="utf-8")

        # 生成 config.yaml
        new_config = self._generate_config_via_llm(user_intent, config_yaml, domain_name)
        (domain_dir / "config.yaml").write_text(new_config, encoding="utf-8")

        # 生成 review.md
        (domain_dir / "review.md").write_text(review_md or self._generate_review_via_llm(user_intent), encoding="utf-8")

        # 初始化 data 目录
        data_dir = Path("data") / domain_name
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "subscriptions.json").write_text("[]", encoding="utf-8")
        (data_dir / "blacklist.json").write_text("[]", encoding="utf-8")

        return {
            "domain": domain_name,
            "files": [
                str(domain_dir / "SKILL.md"),
                str(domain_dir / "config.yaml"),
                str(domain_dir / "review.md"),
                str(data_dir / "subscriptions.json"),
                str(data_dir / "blacklist.json"),
            ],
        }

    # ── 运行领域 ───────────────────────────────────────────

    def run(self, domain: str, action: str) -> dict:
        """运行领域操作."""
        log.log("INFO", "engine.domain_manager", f"domain_{action}",
                f"Running {action} for domain '{domain}'", detail={"domain": domain, "action": action})
        if action == "discover":
            candidates = self.discover_engine.run(domain)
            return {"status": "ok", "action": "discover", "candidates": candidates}

        elif action == "monitor":
            result = self.monitor_engine.run(domain)
            return {"status": "ok", "action": "monitor", **result}

        elif action == "review":
            return self.review_engine.run(domain)

        else:
            log.log("ERROR", "engine.domain_manager", "unknown_action",
                    f"Unknown action: {action}", detail={"action": action})
            return {"status": "error", "message": f"Unknown action: {action}"}

    # ── LLM 生成 ──────────────────────────────────────────

    def _generate_skill_via_llm(self, intent: str, template: str, domain: str) -> str:
        """通过 LLM 生成 SKILL.md."""
        prompt = f"""你正在创建一个领域 Skill。

用户意图: {intent}
领域名称: {domain}

参考模板:
{template}

请生成适配 {domain} 领域的 SKILL.md，使用 YAML frontmatter 格式：
---
name: {domain}-domain
description: {intent}
---

保持与模板相同的工作流结构（发现/监控/复盘），但将内容调整为 {domain} 领域。"""

        return self._call_llm(prompt)

    def _generate_config_via_llm(self, intent: str, template: str, domain: str) -> str:
        """通过 LLM 生成 config.yaml."""
        prompt = f"""你正在创建 {domain} 领域的配置文件。

用户意图: {intent}

参考模板:
{template}

请生成适配 {domain} 领域的 config.yaml，关键词根据领域调整。"""

        text = self._call_llm(prompt)
        for prefix in ["```yaml", "```"]:
            text = text.replace(prefix, "").strip()
        return text

    def _generate_review_via_llm(self, intent: str) -> str:
        """通过 LLM 生成 review.md."""
        prompt = f"""你正在为 {intent} 创建复盘模板。

请生成一个 review.md 文件，包含：
- 复盘任务描述
- 评分标准
- 输出格式要求"""

        return prompt

    def _call_llm(self, prompt: str) -> str:
        """调用系统 claude CLI 生成内容."""
        try:
            result = subprocess.run(
                ["claude", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                return result.stdout
        except FileNotFoundError:
            logger.warning("claude CLI not found, returning prompt as-is")
        except subprocess.TimeoutExpired:
            logger.warning("claude CLI timed out")
        return prompt

    # ── 查询 ──────────────────────────────────────────────

    def list_domains(self) -> list[dict]:
        """列出所有领域."""
        domains_dir = Path("config") / "domains"
        if not domains_dir.exists():
            return []
        result = []
        for d in domains_dir.iterdir():
            if d.is_dir():
                config_file = d / "config.yaml"
                desc = ""
                if config_file.exists():
                    try:
                        cfg = yaml.safe_load(config_file.read_text(encoding="utf-8"))
                        desc = cfg.get("description", "") if cfg else ""
                    except Exception:
                        pass
                result.append({"name": d.name, "description": desc})
        return result
