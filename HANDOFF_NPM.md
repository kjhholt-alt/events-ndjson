# npm publishing -- handoff (5-min, web UI only)

This repo's `release-npm.yml` workflow publishes the events-ndjson
typescript library to npm on every `tsv*.*.*` tag. Uses npm Trusted
Publishing (OIDC) -- no `NPM_TOKEN` in GitHub Secrets.

You do this **once**. After that, every `tsv*` tag publishes
automatically.

> Why a separate `tsv` tag prefix and not `v`? The python package is
> tagged `v*.*.*` and is handled by `release.yml`. Keeping the prefixes
> distinct means the ts and python packages can version independently
> without one publish triggering the other.

## One-time npm setup

1. Create an npm account if you don't have one: https://www.npmjs.com/signup
2. **Reserve the package name** by publishing a `0.0.0` placeholder
   ONCE manually (this is the only way to register the name; npm has no
   "pending package" flow yet):

   ```bash
   cd libraries/typescript
   npm version 0.0.0 --no-git-tag-version
   npm publish --access public
   git checkout package.json   # discard the version bump
   ```

   Or, if you prefer not to publish a placeholder, just push the first
   `tsv0.1.0` tag and the workflow will create the package on first
   publish (this works because you own the name implicitly through
   trusted publishing once configured).

3. **Configure trusted publisher on npmjs.com:**
   - Go to https://www.npmjs.com/package/events-ndjson/access (after
     placeholder publish), or your account's "Granular access tokens"
     page if you skipped the placeholder.
   - Click *"Trusted publishers"* -> *"Add trusted publisher"*.
   - Fill in:
     - **Publisher:** `GitHub Actions`
     - **Repository owner:** `kjhholt-alt`
     - **Repository name:** `events-ndjson`
     - **Workflow filename:** `release-npm.yml`
     - **Environment name:** `npm`
   - Save.

4. **Configure the GitHub environment:**
   - https://github.com/kjhholt-alt/events-ndjson/settings/environments
   - Click *"New environment"* -> name it `npm`
   - (Optional) Enable *"Required reviewers"* and add yourself.

## Cutting a release

```bash
# Bump version in libraries/typescript/package.json first.
# Then tag and push.
git tag tsv0.1.0
git push origin tsv0.1.0
```

The `release-npm` workflow fires:
1. `npm ci` + `npm run build` + `npm test` from `libraries/typescript/`.
2. `npm pack --dry-run` to validate the tarball shape.
3. Pauses for environment review (if enabled) -> `npm publish --provenance --access public`.

`--provenance` emits an attestation tying the published artifact back
to this exact workflow run, viewable on the npm package page.

## Bumping the version

Edit `libraries/typescript/package.json`:

```json
{
  "version": "0.1.1"
}
```

Tag and push:

```bash
git tag tsv0.1.1 && git push origin tsv0.1.1
```

## Rollback

npm allows unpublish only within 72 hours of publish. After that:

1. **Deprecate** the broken version: `npm deprecate events-ndjson@0.1.1 "broken, use 0.1.2"`.
2. **Bump** + republish.

Unpublish docs: https://docs.npmjs.com/policies/unpublish
