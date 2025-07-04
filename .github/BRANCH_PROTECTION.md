# Branch Protection Configuration

This document explains how to configure branch protection rules for the RAG Lab repository to enforce CI/CD quality gates.

## Setting Up Branch Protection

1. **Navigate to Repository Settings**
   - Go to your repository on GitHub
   - Click on "Settings" → "Branches"

2. **Add Branch Protection Rule**
   - Click "Add rule"
   - Branch name pattern: `main` (or `master`)

3. **Configure Protection Settings**

   ### ✅ Required Status Checks
   Enable "Require status checks to pass before merging" and select:
   - `test / Test Suite`
   - `code-quality / Code Quality`
   - `security / Security Scanning`
   - `build-verification / Build Verification`
   - `summary / CI Summary`

   ### ✅ PR Review Requirements
   - **Require pull request reviews before merging**: Yes
   - **Dismiss stale pull request approvals**: Yes
   - **Require review from CODEOWNERS**: Optional

   ### ✅ Additional Protections
   - **Require branches to be up to date**: Yes
   - **Require conversation resolution**: Yes
   - **Require signed commits**: Optional (recommended)
   - **Include administrators**: Yes (recommended)
   - **Restrict who can push**: Optional

## Working with CodeRabbit

Since CodeRabbit is already configured, the workflow is:

1. **Developer creates PR**
2. **Automated checks run in parallel:**
   - GitHub Actions CI/CD pipeline
   - CodeRabbit AI review
3. **Both must complete successfully:**
   - CI/CD: All checks must pass (tests, linting, security)
   - CodeRabbit: Review must be complete (not necessarily approved)
4. **Human review** considers both automated results

## Quality Gates Summary

| Check Type | Tool | Enforcement |
|------------|------|-------------|
| Unit/Integration Tests | pytest | Required - blocks merge |
| Code Coverage | pytest-cov | Required - min 70% |
| Linting | ruff | Required - blocks merge |
| Type Checking | mypy | Required - blocks merge |
| Security Scan | bandit/pip-audit | Required - blocks merge |
| AI Code Review | CodeRabbit | Advisory - provides feedback |

## PR Workflow

1. **Create feature branch** from main
2. **Make changes** and commit
3. **Push branch** and create PR
4. **Automated checks** run immediately:
   - CI/CD pipeline executes all checks
   - CodeRabbit performs AI review
5. **Review feedback**:
   - Fix any CI/CD failures
   - Consider CodeRabbit suggestions
6. **Human review** once automated checks pass
7. **Merge** when all requirements are met

## Monitoring CI/CD

- **PR Comments**: Each CI job posts results as PR comments
- **GitHub Actions Tab**: View detailed logs and artifacts
- **Status Checks**: See all check statuses on the PR page
- **CodeRabbit Comments**: AI review feedback inline and summarized

## Local Development

Before pushing, run checks locally:

```bash
# Install pre-commit hooks
uv run pre-commit install

# Run all checks manually
uv run pre-commit run --all-files

# Run specific checks
uv run ruff check .
uv run mypy src/pipeline_v3
uv run pytest src/pipeline_v3/tests/
uv run bandit -r src/pipeline_v3
```

## Troubleshooting

### CI Failures
- Check the GitHub Actions logs for detailed error messages
- Download artifacts for test reports and coverage data
- Run the same commands locally to reproduce

### CodeRabbit Issues
- CodeRabbit reviews are advisory, not blocking
- If CodeRabbit seems stuck, check the `.coderabbit.yaml` configuration
- Contact support if persistent issues occur

### Performance
- CI runs in parallel for faster feedback
- Cache is used for dependencies to speed up builds
- Consider using `[skip ci]` in commit messages for documentation-only changes
