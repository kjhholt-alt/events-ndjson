# PyPI publishing — handoff (5-min, web UI only)

This repo's `release.yml` workflow publishes `events-ndjson` (the
Python library) to PyPI on every `v*.*.*` tag using **PyPI Trusted
Publishing**. No API tokens in GitHub Secrets.

You do this **once**. After that, every tag publishes automatically.

## One-time PyPI setup

1. **Create a PyPI account** if you don't have one: https://pypi.org/account/register/
2. **Reserve the project name** (one-time, before the first publish):
   - Go to https://pypi.org/manage/account/publishing/
   - Click *"Add a new pending publisher"*.
   - Fill in:
     - **PyPI Project Name:** `events-ndjson`
     - **Owner:** `kjhholt-alt`
     - **Repository name:** `events-ndjson`
     - **Workflow name:** `release.yml`
     - **Environment name:** `pypi`
   - Save.

3. **Configure the GitHub environment** (so the workflow can use OIDC):
   - On GitHub: https://github.com/kjhholt-alt/events-ndjson/settings/environments
   - Click *"New environment"* → name it `pypi`
   - (Optional but recommended) Enable *"Required reviewers"* and add
     yourself.

## Cutting a release

```bash
git tag v0.1.0
git push origin v0.1.0
```

The `release` workflow fires:
1. Builds wheel + sdist from `libraries/python/`.
2. Runs `twine check`.
3. Uploads artifacts (kept 7 days).
4. Pauses for environment review (if enabled) → publishes.

After publish, drop the PEP 508 git URL in operator-core's `[specs]`
extra and replace with:

```toml
specs = [
    "status-spec>=1.0",
    "events-ndjson>=0.1",
]
```

## Bumping the version

Edit `libraries/python/pyproject.toml`:

```toml
[project]
version = "0.1.1"
```

Tag and push:

```bash
git tag v0.1.1 && git push origin v0.1.1
```

## TypeScript publishing (npm)

The `libraries/typescript/` package is a separate publishing track.
Not covered here -- npm needs its own trusted publisher setup.
