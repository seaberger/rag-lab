# GitHub Secret Setup Guide

Follow these steps to add your OPENAI_API_KEY as a GitHub secret:

## 📸 Visual Guide

1. **Go to your repository on GitHub**
   - Navigate to: https://github.com/seaberger/rag_lab

2. **Open Settings**
   - Click the "Settings" tab (you need admin access)
   - If you don't see Settings, you may need repository permissions

3. **Navigate to Secrets**
   - In the left sidebar, scroll down to "Security"
   - Click on "Secrets and variables"
   - Click on "Actions"

4. **Add New Secret**
   - Click the green "New repository secret" button
   - Fill in:
     - **Name**: `OPENAI_API_KEY` (must be exactly this)
     - **Secret**: `sk-proj-YOUR-ACTUAL-API-KEY-HERE`
   - Click "Add secret"

## ✅ Verification

After adding the secret:
1. You should see `OPENAI_API_KEY` in the secrets list
2. It will show as `•••••` (hidden)
3. Last updated timestamp will be shown

## 🔒 Security Notes

- The secret is encrypted and only exposed to GitHub Actions during workflow runs
- It's never visible in logs (GitHub masks it automatically)
- Only repository admins can view/modify secrets
- The secret is not accessible to forked repositories

## 🧪 Test Your Setup

Create a test PR to verify:
1. Make a small change (e.g., add a comment to any file)
2. Create a pull request
3. Check the "Actions" tab to see if workflows run
4. Look for green checkmarks on your PR

If you see errors about missing OPENAI_API_KEY, double-check the secret name.
