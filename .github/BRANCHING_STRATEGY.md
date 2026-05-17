# Git Branching Strategy

This document outlines the branching strategy and version control workflow for the Project Offline repository.

## Branch Structure

### Main Branches

- **`main`** (or `master`) — Production-ready code
  - Always stable and deployable
  - Protected branch requiring pull request reviews
  - Automatically triggers test workflows on push
  - Tagged releases are created from this branch

- **`develop`** — Integration branch for features
  - Contains the latest development changes
  - Used for integrating feature branches
  - Automatically triggers test workflows
  - Merged into `main` when ready for release

### Supporting Branches

- **`feature/*`** — New features or enhancements
  - Branch from: `develop`
  - Merge back into: `develop`
  - Naming: `feature/short-description` (e.g., `feature/jira-sync`, `feature/email-export`)
  - Deleted after merging

- **`bugfix/*`** — Bug fixes for the next release
  - Branch from: `develop`
  - Merge back into: `develop`
  - Naming: `bugfix/issue-description` (e.g., `bugfix/gantt-scroll-jump`)
  - Deleted after merging

- **`hotfix/*`** — Urgent fixes for production
  - Branch from: `main`
  - Merge back into: `main` AND `develop`
  - Naming: `hotfix/critical-issue` (e.g., `hotfix/crash-on-save`)
  - Deleted after merging
  - Tagged immediately after merging to `main`

- **`release/*`** — Preparing for a new production release
  - Branch from: `develop`
  - Merge back into: `main` AND `develop`
  - Naming: `release/v{version}` (e.g., `release/v2026.05.10`)
  - Used for final testing, documentation updates, version bumps
  - Deleted after merging

## Workflow

### 1. Feature Development

```bash
# Create feature branch from develop
git checkout develop
git pull origin develop
git checkout -b feature/my-new-feature

# Work on feature, commit changes
git add .
git commit -m "Add feature: description"

# Push to remote
git push origin feature/my-new-feature

# Create pull request to develop
# After review and approval, merge and delete branch
```

### 2. Bug Fixes

```bash
# Create bugfix branch from develop
git checkout develop
git pull origin develop
git checkout -b bugfix/fix-description

# Fix bug, commit changes
git add .
git commit -m "Fix: description of bug fix"

# Push and create pull request
git push origin bugfix/fix-description
```

### 3. Preparing a Release

```bash
# Create release branch from develop
git checkout develop
git pull origin develop
git checkout -b release/v2026.05.10

# Update version in src/_version.py (if needed)
# Update CHANGELOG.md
# Final testing and documentation

# Merge to main
git checkout main
git merge --no-ff release/v2026.05.10
git tag -a v2026.05.10 -m "Release version 2026.05.10"
git push origin main --tags

# Merge back to develop
git checkout develop
git merge --no-ff release/v2026.05.10
git push origin develop

# Delete release branch
git branch -d release/v2026.05.10
```

### 4. Hotfix for Production

```bash
# Create hotfix branch from main
git checkout main
git pull origin main
git checkout -b hotfix/critical-fix

# Fix the issue
git add .
git commit -m "Hotfix: critical issue description"

# Merge to main
git checkout main
git merge --no-ff hotfix/critical-fix
git tag -a v2026.05.10.1 -m "Hotfix: critical issue"
git push origin main --tags

# Merge to develop
git checkout develop
git merge --no-ff hotfix/critical-fix
git push origin develop

# Delete hotfix branch
git branch -d hotfix/critical-fix
```

## Version Tagging

### Tag Format

- **Major release:** `vYYYY.MM.DD` (e.g., `v2026.05.10`)
- **Hotfix/Patch:** `vYYYY.MM.DD.N` (e.g., `v2026.05.10.1`)
- **Semantic version:** `vMAJOR.MINOR.PATCH` (e.g., `v1.0.0`) — optional alternative

### Creating Tags

```bash
# Annotated tag (recommended for releases)
git tag -a v2026.05.10 -m "Release version 2026.05.10"

# Push tag to remote
git push origin v2026.05.10

# Push all tags
git push origin --tags
```

## Commit Message Convention

Use clear, descriptive commit messages following this format:

```
<type>: <subject>

<body (optional)>

<footer (optional)>
```

### Types

- **feat:** New feature
- **fix:** Bug fix
- **docs:** Documentation changes
- **style:** Code style changes (formatting, no logic change)
- **refactor:** Code refactoring
- **test:** Adding or updating tests
- **chore:** Maintenance tasks (dependencies, build, CI/CD)
- **perf:** Performance improvements

### Examples

```bash
git commit -m "feat: add Jira synchronization module"
git commit -m "fix: prevent gantt scroll jump on zoom"
git commit -m "docs: update README with installation instructions"
git commit -m "chore: upgrade PyQt5 to 5.15.10"
```

## Pull Request Guidelines

### Before Creating a PR

1. Ensure your branch is up to date with the target branch
2. Run tests locally: `pytest tests/`
3. Check code style and formatting
4. Update documentation if needed

### PR Title Format

Follow the same convention as commit messages:

- `feat: Add email export functionality`
- `fix: Resolve gantt chart scrolling issue`
- `docs: Update API documentation`

### PR Description

Use the provided pull request template (`.github/PULL_REQUEST_TEMPLATE.md`) to:

- Describe the changes
- Link related issues
- List testing performed
- Check all applicable items in the checklist

### Review Process

- At least one approval required before merging
- All CI checks must pass (tests, build, coverage)
- Resolve all review comments
- Keep PRs focused and reasonably sized

## Protected Branches

### `main` Branch Protection Rules

- Require pull request before merging
- Require at least 1 approval
- Require status checks to pass (tests, build)
- Require branches to be up to date before merging
- Restrict force push
- Restrict deletion

### `develop` Branch Protection Rules

- Require pull request before merging (optional but recommended)
- Require status checks to pass
- Allow force push for maintainers only

## Migration from SVN

If you're migrating from SVN to Git:

1. **Clean up SVN artifacts:**

   ```bash
   # Remove .svn directories (if not already in .gitignore)
   find . -name ".svn" -type d -exec rm -rf {} +
   ```

2. **Initialize Git repository:**

   ```bash
   git init
   git add .
   git commit -m "chore: initial commit from SVN migration"
   ```

3. **Set up remote and push:**

   ```bash
   git remote add origin https://github.com/RolandKaechele/ProjectOffline.git
   git branch -M main
   git push -u origin main
   
   # Create develop branch
   git checkout -b develop
   git push -u origin develop
   ```

4. **Configure branch protection rules on GitHub**

## Continuous Integration

### Automated Workflows

- **Tests** (`.github/workflows/tests.yml`)
  - Runs on: push to `main`, `develop`; pull requests
  - Matrix: Python 3.9, 3.10, 3.11, 3.12
  - Includes: unit tests, integration tests, UI tests
  - Generates coverage reports

- **Release** (`.github/workflows/release.yml`)
  - Runs on: tag push (v*)
  - Creates draft GitHub Release with auto-generated notes
  - Extracts changelog from commits since last tag
  - Requires manual upload of signed installer before publishing

### Status Badges

Add these badges to your README.md:

```markdown
[![Tests](https://github.com/RolandKaechele/ProjectOffline/workflows/Tests/badge.svg)](https://github.com/RolandKaechele/ProjectOffline/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
```

## FAQ

**Q: When should I create a feature branch vs. working directly on develop?**

A: Always create a feature branch. This allows for code review via pull requests and keeps develop stable.

**Q: How do I handle merge conflicts?**

A: Update your branch with the latest changes from the target branch and resolve conflicts locally before creating/updating your PR.

```bash
git checkout feature/my-feature
git fetch origin
git merge origin/develop
# Resolve conflicts
git add .
git commit -m "Merge develop and resolve conflicts"
git push
```

**Q: What if I need to update my branch after a PR is created?**

A: Simply push additional commits to your feature branch; the PR will update automatically.

**Q: How do I delete merged branches?**

A: GitHub can automatically delete branches after PR merge. Locally:

```bash
git branch -d feature/my-feature  # delete local
git push origin --delete feature/my-feature  # delete remote
```

**Q: Can I squash commits when merging?**

A: Yes, use "Squash and merge" on GitHub for feature branches to keep main/develop history clean. Use "Create a merge commit" for release/hotfix branches to preserve history.
