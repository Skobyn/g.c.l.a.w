# Code Review Skill — Examples

## Example 1: Local diff with a security finding

**Input:**
```diff
 def authenticate(token: str) -> User:
+    if token == "debug-bypass":
+        return User(id="admin", roles=["*"])
     decoded = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
     return User(**decoded)
```

**Output:**
```markdown
## Code Review — local diff (uncommitted)

**Verdict:** block

### Critical & High findings
- **critical** `src/gclaw/auth/middleware.py:42` — hardcoded `debug-bypass` token grants admin role unconditionally. Fix: remove entirely, or gate behind `settings.firebase_auth_enabled is False` and a dev-only env var.

### What's good
- The rest of the function correctly decodes JWTs via the shared secret.

### What's missing
- No test covering the bypass path — indicates this was added quickly for local debugging. Add a regression test that asserts unknown tokens raise, once the bypass is removed.
```

## Example 2: PR diff with medium + nit findings

**Input:** `gh pr view 42` → a refactoring PR that renames `get_user` → `fetch_user` across 6 files.

**Output:**
```markdown
## Code Review — PR #42 "rename get_user to fetch_user"

**Verdict:** approve with comments

### Medium findings
- **medium** `src/gclaw/api/app.py:88` — the rename misses an import alias: `from gclaw.auth import get_user`. Will cause an `ImportError` at app startup. Fix: update the import to `fetch_user`.

### Low / nit findings
- **nit** `tests/test_auth.py:15` — docstring still references the old name. Fix: update to match.

### What's good
- Rename is consistent across all call sites the linter caught.
- Tests were updated in lockstep with the source changes.

### What's missing
- No mention in CHANGELOG of the public-API rename — if external callers use `gclaw.auth.get_user`, they'll break. Add a migration note or a re-export shim for one release.
```

## Example 3: Clean diff

**Input:** a 15-line bugfix with a regression test.

**Output:**
```markdown
## Code Review — local diff (uncommitted)

**Verdict:** approve

### What's good
- Root cause is correctly identified in `src/gclaw/heartbeat/service.py:94` (the `None` check was on the wrong variable).
- New test in `tests/test_heartbeat_service.py::test_heartbeat_consolidation_skips_on_missing_board` reproduces the original bug and pins the fix.
- Change is minimal and doesn't touch anything unrelated.
```
