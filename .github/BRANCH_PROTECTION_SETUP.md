# Branch Protection Setup

How to configure GitHub branch protection and naming rules using the `gh` CLI.

## 1. Protect `main` (PRs only, no direct push)

**bash / Git Bash:**

```bash
gh api --method PUT repos/RolandKaechele/ProjectOffline/branches/main/protection \
  --input - <<'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["Run tests with coverage (3.12)"]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
EOF
```

**PowerShell:**

```powershell
@'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["Run tests with coverage (3.12)"]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
'@ | gh api --method PUT repos/RolandKaechele/ProjectOffline/branches/main/protection --input -
```

This enforces:

- At least 1 PR approval before merging
- CI must pass before merge (`Run tests with coverage (3.12)`)
- Stale approvals dismissed on new push
- No force push or deletion of `main`
- Applies to admins too (`enforce_admins: true`)


## 2. Enforce branch naming convention (GitHub Action)

> ⚠️ The GitHub Rulesets `branch_name_pattern` rule requires **GitHub Team or Enterprise**.
> For free accounts, branch naming is enforced via a **GitHub Actions workflow** instead.

The workflow is at `.github/workflows/branch_name_check.yml` and runs automatically on every PR targeting `main` or `develop`.

Required pattern: `^(feature|bugfix|hotfix|release)/[a-zA-Z0-9-]+_[a-zA-Z0-9_]+`

Pattern breakdown:

- `feature/jira-sync_add_oauth` ✅
- `bugfix/gantt-scroll_fix_zoom_jump` ✅
- `hotfix/crash_on_save` ✅
- `my-branch` ❌ (no prefix)
- `feature/nounderscore` ❌ (missing `_<comment>`)

To make this check **required before merging**, add `"Validate branch name"` to the branch protection status checks (step 1):

```json
"contexts": ["Run tests with coverage (3.12)", "Validate branch name"]
```


## 3. Protect `develop`

**PowerShell:**

```powershell
@'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["Run tests with coverage (3.12)"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
'@ | gh api --method PUT repos/RolandKaechele/ProjectOffline/branches/develop/protection --input -
```

This enforces:

- CI must pass before merge (`Run tests with coverage (3.12)`)
- No force push or deletion of `develop`
- No PR approval required (less strict than `main`)

## 4. Verify rules are active

```powershell
# Check branch protection on main
gh api repos/RolandKaechele/ProjectOffline/branches/main/protection

# List rulesets
gh api repos/RolandKaechele/ProjectOffline/rulesets
```

## 5. Remove rules (if needed)

```powershell
# Remove branch protection
gh api --method DELETE repos/RolandKaechele/ProjectOffline/branches/main/protection

# Delete a ruleset (replace <id> with ID from list rulesets)
gh api --method DELETE repos/RolandKaechele/ProjectOffline/rulesets/<id>
```
