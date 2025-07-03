# GitHub CI/CD Configuration

This directory contains the CI/CD pipeline configuration for RAG Lab.

## 📁 Directory Structure

```
.github/
├── workflows/
│   └── ci.yml              # Main CI/CD pipeline
├── BRANCH_PROTECTION.md    # How to configure branch protection
├── CI_CD_OVERVIEW.md       # Comprehensive pipeline documentation
├── SETUP_SECRETS.md        # Required secrets configuration
└── README.md               # This file
```

## 🚀 Quick Start

1. **Add Secrets**: Follow [SETUP_SECRETS.md](SETUP_SECRETS.md) to configure `OPENAI_API_KEY`
2. **Enable Protection**: Follow [BRANCH_PROTECTION.md](BRANCH_PROTECTION.md) to protect main branch
3. **Create PR**: The pipeline will automatically run on all pull requests

## 📋 Pipeline Overview

The CI/CD pipeline includes:
- ✅ Automated testing with pytest
- ✅ Code coverage enforcement (70% minimum)
- ✅ Code quality checks (ruff, mypy)
- ✅ Security scanning (bandit, pip-audit)
- ✅ Build verification
- ✅ PR auto-commenting with results

Works alongside CodeRabbit for comprehensive code review.

## 📚 Documentation

- **[CI_CD_OVERVIEW.md](CI_CD_OVERVIEW.md)** - Complete pipeline documentation
- **[BRANCH_PROTECTION.md](BRANCH_PROTECTION.md)** - Branch protection setup
- **[SETUP_SECRETS.md](SETUP_SECRETS.md)** - Secrets configuration

## 🛠️ Maintenance

To update the pipeline:
1. Edit `workflows/ci.yml`
2. Test changes in a PR
3. Update documentation if needed

---
**Issue**: #63 - CI/CD Implementation
