# GitHub Secrets Setup for CI/CD

The CI/CD pipeline requires certain secrets to be configured in your GitHub repository.

## Required Secrets

### 1. OPENAI_API_KEY
The OpenAI API key is required for running integration tests that use the OpenAI Vision API.

**To set up:**
1. Go to your repository on GitHub
2. Navigate to Settings → Secrets and variables → Actions
3. Click "New repository secret"
4. Name: `OPENAI_API_KEY`
5. Value: Your OpenAI API key
6. Click "Add secret"

## Optional Secrets

### 2. CODECOV_TOKEN (Future Enhancement)
If you want to use Codecov for coverage reporting:
1. Sign up at [codecov.io](https://codecov.io)
2. Add your repository
3. Copy the token
4. Add as `CODECOV_TOKEN` secret

### 3. SLACK_WEBHOOK_URL (Future Enhancement)
For CI/CD notifications to Slack:
1. Create a Slack webhook
2. Add as `SLACK_WEBHOOK_URL` secret

## Environment Variables

The following are set automatically by the workflow:
- `PYTHON_VERSION`: 3.12
- `UV_VERSION`: 0.4.18
- `MIN_COVERAGE`: 70%

## Testing Secrets

To test if your secrets are properly configured:

1. **Create a test PR** with a small change
2. **Check the Actions tab** to see if the workflow runs
3. **Look for errors** related to missing secrets

## Security Best Practices

1. **Never commit secrets** to the repository
2. **Rotate keys regularly** (every 90 days recommended)
3. **Use least privilege** - create API keys with minimal required permissions
4. **Monitor usage** - check your OpenAI dashboard for unexpected activity

## Local Development

For local development, create a `.env` file (already in .gitignore):

```bash
# .env
OPENAI_API_KEY=your-key-here
```

Then load it in your shell:
```bash
source .env
# or
export $(cat .env | xargs)
```

## Troubleshooting

### "Error: OPENAI_API_KEY not found"
- Ensure the secret is named exactly `OPENAI_API_KEY`
- Check that the secret has a value
- Verify you're looking at the correct repository

### Tests fail due to API errors
- Check your OpenAI API key is valid
- Ensure you have sufficient credits
- Consider mocking API calls for unit tests
