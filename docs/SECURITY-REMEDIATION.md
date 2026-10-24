# Credential exposure remediation

This is a record of what was removed, what was checked, and what still cannot be certified.
It is not a declaration that every copy of the former repository has been erased.

## Completed

- The owner explicitly authorized rewriting affected branch and tag history, without rotating credentials.
- Seventeen branch references and two tag references were updated atomically with exact old-value leases.
- A fresh download of the rewritten branch/tag history was checked across 922 reachable blob, commit and tag objects. No identified historical sensitive value remained in that scope.
- Two editable GitHub text bodies containing copied private data were sanitized. Issue, comment and release text was checked for the identified values afterward.
- Repository visibility remains private; no forks were reported during the check.
- The browser configuration was moved out of source in the security remediation PR. Its runtime endpoint exposes only an explicitly classified anon configuration, never administrative configuration. This remains subject to security review before deployment.
- The secret guard no longer skips large first-party text files. Its size-limit regression test failed before the correction and passed afterward.

## Production protection

`SUPABASE_URL` and `SUPABASE_ANON_KEY` are configured in Coolify for production and preview at runtime, not build time. They were migrated, not rotated.

Automatic deployment on `main` was enabled when the cleanup began. It was paused before rewriting remote history, without stopping the running application. Keep it paused until the browser runtime migration is reviewed and deployed deliberately.

**Do not redeploy a redacted historical snapshot expecting its former embedded defaults.** The tested runtime migration is in PR #28; a missing or privileged configuration fails closed. A health response alone does not establish that interactive login works after a new deployment.

## Remaining exposure boundaries

### GitHub-controlled references and cached views

Rewriting ordinary branches and tags does not delete GitHub's read-only PR references, cached commit views or copies in other clones. Fifteen PRs were identified as affected: #13, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27 and #28.

Follow [GitHub's sensitive-data removal procedure](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository) and contact Support privately with:

- repository owner and name;
- the affected PR count;
- the first changed commit reported by `git-filter-repo`;
- any orphaned LFS object report, if present.

GitHub determines whether assistance is applicable, including whether credential rotation would mitigate the risk. No Support request or server-side garbage collection has been completed by this work. Do not claim those caches have been removed.

### Release downloads

The owner separately authorized deleting `QuantLlamalInstaller1.8.1.exe` (913 MB) from `QuantLlama_0.1.1.8`. The API confirmed that the legacy release now has no downloadable assets; its notes remain. The installer was removed, not certified clean. Previously downloaded copies are outside this operation.

### Existing clones and local backups

The working checkout was resynchronized while preserving human working files. Existing local stashes, old unreachable objects and other clones may retain former data. Do not push old histories back to GitHub or publish a backup. Coordinate cleanup or replacement of other clones separately.

### Unavailable proof

The independent verifier failed without a verdict. The writer's tests and CI are not a substitute for independent security approval. Keep the remediation PR unmerged and production deployment held until this is resolved by the maintainer.

## Credential policy

No credential was revoked or rotated, per the owner's instruction. A functioning credential is not evidence that no one copied it. The Supabase anon key is public browser configuration by design; that is distinct from an administrative key, signing secret, broker password or exchange API secret. Strict database access policies remain necessary.

The pattern-based secret guard and the known-value historical scan have different scopes and neither proves the absence of every possible secret. Keep the repository private until the remaining boundaries above are resolved.
