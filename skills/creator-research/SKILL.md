---
name: creator-research
description: Track fixed creators across Bilibili, YouTube and Douyin, collect new videos, transcribe them, and produce evidence-based research reports.
---

# Fixed creator research

Use a creator watchlist for stable monitoring. Each creator must have a
platform and a direct profile URL or channel URL; display names alone are not
reliable identifiers.

## Workflow

1. Use `manage_creator_watchlist` to create or update a named list.
2. Run `research_creator_watchlist` to collect the latest videos. Preserve the
   returned `complete`, `source`, and per-creator statuses; a partial feed is
   not a complete account history.
3. Submit the returned `transcription_items` to `batch_transcribe`.
4. Poll `get_job` until it is terminal, read every transcript artifact, and
   call `analyze_videos` with a concrete research question.
5. Save the evidence-backed report with `save_analysis`.

## Research rules

- Keep creator identity, platform, publish time, and source URL with every
  finding.
- Separate what the video says from independently verified facts.
- Mark missing subtitles, failed downloads, platform restrictions, and partial
  following results as research gaps.
- Do not treat login as a universal fix for search, captcha, rate limits, or
  dynamic-signature failures.
- For investment or other high-impact topics, label opinions and uncertainty;
  do not turn creator statements into financial or other professional advice.

## Suggested report structure

Use `templates/research-report.md` and include: executive summary, creator-by-
creator claims, evidence and dates, agreement/disagreement, changes over time,
unknowns, and follow-up questions.
