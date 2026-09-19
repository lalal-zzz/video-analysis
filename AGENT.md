# Developer guidance

The supported interface is `skills/video-analysis/SKILL.md` plus the local
`video-analysis-mcp` STDIO server. There is no project Web UI or interactive CLI.

- Python 3.10+, type annotations, Pydantic models at core module boundaries.
- `mcp_server/server.py` exposes tools; `service.py` implements workflows;
  `auth.py`, `media.py`, `jobs.py`, `storage.py` handle their named responsibilities.
- Runtime paths must come from `Paths`; default to platformdirs, never the plugin
  install directory. `VIDEO_ANALYSIS_DATA_DIR` and `VIDEO_ANALYSIS_STATE_DIR` override.
- Cookies stay domain scoped in the state directory, outside artifacts and logs.
  yt-dlp receives a private per-operation jar. Do not return raw downloader errors.
- Public operations try without mandatory login. `auth_required` is distinct
  from rate limits and network failures; login is not a universal cure.
- Restrict concurrency per platform. Batch tools return job IDs; persist item results.
  Do not report success without a non-empty media file or transcription.
- Use cache for search/transcription; preserve source metadata. Keep saved sessions
  out of cache output. Login-state changes must invalidate search cache.
- The host assistant normally analyzes saved transcripts. External analyzer CLIs
  are optional; never silently select a different model/provider.
- Keep the core scraper/transcriber/analyzer/cache abstractions. Legacy engine and
  ToolRegistry modules remain library compatibility surfaces, not MCP entrypoints.
- Test with temporary data directories, mocked platforms and subprocesses. Normal
  pytest must not access networks, accounts, local browsers, or tracked data fixtures.
- Run `python -m pytest -q`, package validation, and actual MCP STDIO tests. Unit
  success does not establish live-platform download success. Report both separately.
- `DEV_PLAN.md` records historical phases and is not current runtime guidance.

## Live login and platform caveats

- Login must open a platform-owned page in an isolated Chrome/Edge profile. Never
  read the user's everyday browser profile or print cookie values.
- Google/YouTube may force Windows Hello/Passkey. The managed profile cannot use
  personal Windows Hello credentials; tell the user to choose another sign-in
  method, or support an explicit cookie-file import instead of bypassing MFA.
- Bilibili login is verified against its `nav` endpoint. Douyin login is only
  best-effort (`session_detected`) and must be followed by endpoint validation.
- Douyin's web search endpoint can return `invalid_app`/`params_check` even with
  valid cookies because it requires dynamic device/signature parameters. Do not
  report an empty search as a successful download; use a browser-search fallback
  or require a direct video URL.
- Douyin following results are page-visible and partial; scrolling is not a
  complete, cursor-paginated following API. Always preserve `complete=false`.
