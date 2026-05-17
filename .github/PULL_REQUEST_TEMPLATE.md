# Pull Request

## Description
<!-- Provide a brief description of the changes in this PR -->

## Type of Change
<!-- Mark the relevant option with an "x" -->
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] New feature (non-breaking change which adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Code refactoring
- [ ] Performance improvement
- [ ] Test coverage improvement
- [ ] Build/CI configuration change

## Related Issues
<!-- Link to related issues using #issue_number -->
Closes #

## Changes Made
<!-- List the specific changes made in this PR -->
- 
- 
- 

## Testing
<!-- Describe the tests you ran to verify your changes -->
- [ ] Tested locally
- [ ] Added/updated unit tests
- [ ] Added/updated integration tests
- [ ] Manual testing performed

### Test Configuration
<!-- Describe your test configuration if relevant -->
* OS: 
* Python version:
* Dependencies version:

## Screenshots
<!-- If applicable, add screenshots to demonstrate the changes -->

## Checklist
<!-- ⚠️ ALL steps below are MANDATORY -->

### Testing

- [ ] Verified new buttons are contained in array vor visibility on ribbon menu
- [ ] Verified the newly implementation is correct (the function are called in all variations without the GUI locally, caller functions calls them with correct parameters).
- [ ] Verified that no duplicated code was introduced.
- [ ] Verified no dead code.
- [ ] Verified nothing breaks by running `pytest tests/pytests -v` and the change doesn't violate the current requirements.
- [ ] Verified that tests touching external integrations (AD, VCS, email) mock all subprocess and blocking-dialog calls so no real process is spawned and the suite passes on Linux CI.
- [ ] Created new tests for the change are running without errors.
- [ ] Updated test documentation:
  - [ ] Updated `tests/pytests/README.md`.
  - [ ] Updated the relevant `tests/pytests/documentation/test_spec_*.html` file and stats (Total, Passed, Skipped, Failed, Modules); update `tests/pytests/documentation/index.html` grand-total stats if the overall count changed.

### Requirements Management

- (!) The requirement ids and dsi ids shall not be re-used if removed. If a requirement content changes a new requirement with a new id has to be created.
- [ ] Verified that the change doesn't break requirements nor dsis.
- [ ] Added new requirements to DSF (`documentation/requirements/dsf/`), use sub chapters like in `documentation\requirements\dsf\PO_01_overview.dsf`, verified that they are located correctly in the sub chapters (if not possible create new sub chapters).
  - [ ] Validated DSF files with `python tools/validate_dsf.py` — no errors reported.
- [ ] Regenerated requirements database:
  - [ ] Run `tools/regenerate_requirements.py` (runs rxml → dsi in the correct order).
- [ ] Check that dsis aren't broken.

### Documentation

- [ ] Updated technical documentation:
  - [ ] Updated `documentation/architecture.md`.
  - [ ] Created/updated relevant markdown files in `documentation/`.
- [ ] Updated presentation materials:
  - [ ] Presentation updated in `documentation/presentation/`.
  - [ ] Created new HTML screenshots in `documentation/presentation/`.
- [ ] Updated user documentation:
  - [ ] User documentation updated and new html files created in `documentation/user_documentation/` if new modules are added
    - [ ] Created new HTML screenshots in `documentation/user_documentation/`.
- [ ] Verified HTML files by running `python tools/playwright_review_html.py --all` → check `tests/documentation/playwright_review_html_all.html`.
- [ ] Updated `todo.txt`.

### SFX / Installer

- [ ] Verified that newly added files are contained in SConstruct.
- [ ] Verified that a sfx / installer can be build.

## Additional Notes
<!-- Add any additional context or notes for reviewers -->
