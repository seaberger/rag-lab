# Security Best Practices for RAG Lab

This document outlines security measures to protect sensitive information, particularly API keys.

## 🔒 API Key Protection

### Multiple Layers of Protection

1. **Environment Variables** ✅
   - API keys are NEVER hardcoded in source files
   - All keys loaded from environment variables
   - `.env` file is gitignored (line 131 in `.gitignore`)

2. **Pre-commit Hooks** ✅
   - `detect-private-key`: Catches private keys before commit
   - `detect-secrets`: Comprehensive secret detection
   - `bandit`: Python security scanning
   - Install with: `uv run pre-commit install`

3. **CI/CD Security Scanning** ✅
   - Automated security checks on every PR
   - Prevents accidental key exposure
   - Security reports generated

4. **Code Patterns** ✅
   - Centralized API client configuration
   - Proper validation and error handling
   - No keys in logs or error messages

## 🚀 Quick Security Check

Before pushing to GitHub, run:

```bash
# Install pre-commit hooks (one time)
uv run pre-commit install

# Manual security scan
uv run detect-secrets scan
uv run bandit -r src/

# Check for exposed secrets in git history
git log -p -S"sk-" --all  # Check for OpenAI keys
git log -p -S"OPENAI" --all  # Check for env var names
```

## 📝 Setting Up Your Environment

1. **Copy the example file**:
   ```bash
   cp .env.example .env
   ```

2. **Add your API key**:
   ```bash
   # Edit .env and add your key
   OPENAI_API_KEY=sk-proj-YOUR-ACTUAL-KEY
   ```

3. **Verify protection**:
   ```bash
   # This should show .env is ignored
   git status --ignored | grep .env
   ```

## 🛡️ What's Protected

### Files That Are Gitignored:
- `.env` - Environment variables
- `*.pyc` - Compiled Python files
- `.coverage` - Test coverage data
- `htmlcov/` - Coverage reports
- Database files (`*.db`, `*.sqlite`)
- Cache directories

### Security Tools Active:
- **detect-secrets**: Uses `.secrets.baseline` to track known safe patterns
- **bandit**: Configured via `.bandit` file
- **GitHub Actions**: Runs security scans on every PR

## ⚠️ If You Accidentally Commit a Secret

1. **Immediately revoke the key** in your OpenAI dashboard
2. **Remove from history**:
   ```bash
   # Use BFG Repo-Cleaner or git filter-branch
   # See: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
   ```
3. **Generate a new key** and update `.env`
4. **Run security scan** to verify removal

## 🔍 Regular Security Checks

### Weekly:
- Review OpenAI API usage for anomalies
- Check for new dependencies with vulnerabilities
- Update security tools

### Monthly:
- Rotate API keys
- Review access logs
- Update dependencies

### Before Major Releases:
- Full security audit with `uv run detect-secrets audit`
- Dependency vulnerability scan
- Review all environment variables

## 📚 Additional Resources

- [GitHub Secret Scanning](https://docs.github.com/en/code-security/secret-scanning)
- [OpenAI API Key Best Practices](https://platform.openai.com/docs/guides/safety-best-practices)
- [Python Security](https://python.readthedocs.io/en/latest/library/secrets.html)

## 🤝 Security Contact

If you discover a security vulnerability, please:
1. Do NOT open a public issue
2. Email the maintainer directly
3. Allow time for a patch before disclosure

---

**Remember**: Security is everyone's responsibility. When in doubt, ask!
