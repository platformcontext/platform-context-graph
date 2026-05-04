# Repositoryidentity

## Purpose

Single home for canonical repository identity. Collectors, projectors, and
graph writers all derive the same `repository:r_<hash>` ID and `org/repo`
slug from the same remote URL plus local path inputs.

## Ownership boundary

Owns remote URL normalization, slug extraction, and canonical ID hashing for
git-style repos. Discovery, fact emission, and graph writes call into this
package rather than rolling their own.

## Exported surface

- `Metadata` value with `ID`, `Name`, `RepoSlug`, `RemoteURL`, `LocalPath`,
  `HasRemote`.
- `MetadataFor(name, localPath, remoteURL)` constructor.
- `NormalizeRemoteURL(remoteURL)` for SSH and HTTPS git remote folding.
- `RepoSlugFromRemoteURL(remoteURL)` for the `org/repo` slug.
- `CanonicalRepositoryID(remoteURL, localPath)` for the stable repo ID.

## Dependencies

Standard library only.

## Telemetry

None.

## Gotchas / invariants

- `CanonicalRepositoryID` requires a non-empty `localPath` when the remote URL
  is empty. Empty inputs produce an error rather than a silent ID.
- `NormalizeRemoteURL` lower-cases the host and path, strips a trailing `.git`,
  and drops trailing slashes. SSH `git@host:org/repo.git` and HTTPS
  `https://host/org/repo.git` collapse to the same canonical form.
- The hash is SHA-1 truncated to 8 hex characters. It is identity-stable but
  not cryptographically authoritative.
- Local paths are resolved with `filepath.Abs`, so callers should pass paths
  in the form they intend to be canonical (no trailing slash, etc.).

## Related docs

- `docs/docs/architecture.md`
- `go/internal/collector/README.md` for upstream callers
