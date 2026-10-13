# Public repository privacy review

Reviewed on 2026-10-02 before publishing the latest changes.

The review covered tracked files, reachable Git history, commit metadata,
both configured remote repositories, readable strings in compiled files,
and legacy encoded archives where they could be decoded.

## Findings and cleanup

- GitHub commit metadata contained a personal email address. Author and
  committer addresses are replaced with the account's GitHub noreply address.
  Future local commits use that address as well.
- Legacy GitCode history included encoded archives, an archive password
  script and compiled Python caches. These exposed local paths; one archive
  also contained a presentation unrelated to the published source. The
  archives, conversion scripts and caches are removed from remote branch
  history while retaining source development history.
- Some historical archives were incomplete or corrupt. They cannot be
  certified free of private content and are removed with the other archives.
- Token, private-key, JWT and credential-pattern scanning did not identify
  live account credentials in the inspected readable content. Credential-like
  strings in tests are synthetic fixtures and invalid-input examples.

Platform sessions, cookies and current personal research outputs are kept in
the service's OS user data directory, outside this repository. Existing tracked
mock transcripts and mock analysis examples are synthetic test data.

## Limits

This is a scoped repository review, not a guarantee that every possible secret
format can be detected. Rewriting and replacing branch history does not erase
copies already downloaded by other users or all hosting-provider caches.
Local recovery backups are retained outside the repository and are not pushed.
Any credential discovered to have been exposed should be revoked separately.

## Creator catalog and branch check (2026-10-13)

The current public catalog under `html/skills/` and embedded in `github.html`
contains financial creators' public profiles and video metadata only. It does
not retain the user's following relationships or non-financial interests.
The original personal snapshot is kept in ignored local storage, not staged.
The export helper uses a field allowlist and does not query follows by default.

Read-only branch-head checks confirmed GitHub has `main`; GitCode has `dev`
and `master`. The histories reachable from those advertised heads contain
neither personal author emails nor the legacy encoded archive/cache paths
checked here. This is a scoped check, not a blanket guarantee about secrets.

Local `dev` still reaches old commits with a personal author email, encoded
archives and compiled caches; local `master` still reaches encoded archives.
These local branches differ from the sanitized remote histories. Do not push
them with `--all` or merge their old history into the public branch. No remote
history was rewritten or old local branch deleted during this check.

Check repository visibility and remote branch heads after pushing. Avoid
reintroducing old commits or encoded archives from an earlier clone.
