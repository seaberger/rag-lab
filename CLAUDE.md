# RAG Lab Repository - CLAUDE.md

This file provides repository-wide context and navigation guidance for Claude Code development sessions.

## 🚨 CRITICAL: OpenAI Models Configuration

**ALWAYS use these exact model names - NO variations:**
- **Vision Model**: `gpt-4.1` (NOT gpt-4o, NOT gpt-4-vision, NOT gpt-4.1-test)
- **Keyword Model**: `gpt-4.1-mini` (NOT gpt-4o-mini)
- **Embedding Model**: `text-embedding-3-small`

## 🎯 Current Development Focus: Enterprise Multi-Tenant Platform

**Active Area**: `src/pipeline_v3/` - Production-ready document processing system
**Future Vision**: Enterprise multi-tenant platform with PostgreSQL, API authentication, and advanced search
**Detailed Context**: [Pipeline v3 CLAUDE.md](src/pipeline_v3/CLAUDE.md)
**Enterprise Vision**: [Enterprise Implementation Guide](src/pipeline_v3/docs/ENTERPRISE_MULTI_TENANT_IMPLEMENTATION.md)
**Status**: Core functionality complete, planning enterprise migration

### Quick Start for Pipeline v3:
```bash
# Navigate to Pipeline v3
cd src/pipeline_v3

# Follow Pipeline v3 CLAUDE.md for detailed context
# Primary CLI: uv run python -m src.pipeline_v3.cli_main
```

### 🚀 Enterprise Features Roadmap (Issues #77-#85):
- **PostgreSQL Migration** (#77) - Replace SQLite for multi-tenant concurrency
- **API Authentication** (#78) - Secure API keys with rate limiting
- **Document Security** (#79) - Fine-grained access control
- **MCP Servers** (#81) - Per-tenant servers for agentic workflows
- **Multi-Vector Search** (#84) - ColBERT, SPLADE, BGE-M3 support
- **Adaptive Optimization** (#85) - Usage-based search tuning

## 📊 Project Status Overview

### ✅ **Production Ready Components**
- **Pipeline v3**: Enterprise document processing with OpenAI Vision API (gpt-4.1)
- **Storage System**: JSONL artifacts with full datasheet parsing
- **Search Engine**: Hybrid vector + keyword search with advanced fusion
- **Queue Management**: Scalable concurrent processing
- **Office Documents**: Word & PowerPoint support (.docx, .pptx)
- **URL Batch Processing**: Web document collections from markdown/JSON files

### 🎯 **Development Planning**
For current priorities and active issues, see:
- **[ROADMAP.md](ROADMAP.md)** - Active development priorities and issue tracking
- **[ISSUES.md](ISSUES.md)** - Comprehensive architecture gap analysis
- **[GitHub Issues](https://github.com/seaberger/rag-lab/issues)** - Live issue tracking

## 🗂️ Repository Architecture

### **Pipeline Components**
```
rag_lab/
├── src/
│   ├── pipeline_v3/           ⭐ CURRENT FOCUS
│   │   ├── CLAUDE.md          📋 Detailed v3 context
│   │   ├── cli_main.py        🖥️ Production CLI
│   │   ├── cli_v3.py          ⚠️ Legacy CLI (Issue #9)
│   │   └── [complete v3 system]
│   │
│   ├── parsing/refactored_2_1/ 📚 Reference implementation
│   │   ├── CLAUDE.md          📋 v2.1 context
│   │   └── [stable v2.1 pipeline]
│   │
│   └── [other utilities and experiments]
│
├── data/
│   ├── sample_docs/           📄 7 test datasheets
│   └── lmc_docs/datasheets/   📄 30 production datasheets
│
└── [storage and cache directories]
```

### **Key Data Locations**
- **Test Documents**: `data/sample_docs/` (7 PDFs)
- **Production Documents**: `data/lmc_docs/datasheets/` (30 PDFs)
- **Total Available**: 37 technical datasheets for testing

## 🧭 Navigation Guide

### **For Pipeline v3 Development** (Primary Focus)
→ **[src/pipeline_v3/CLAUDE.md](src/pipeline_v3/CLAUDE.md)** - Complete v3 context
- Current issues and priorities
- CLI commands and environment setup
- Development debugging workflows
- Architecture and component details

### **For v2.1 Reference**
→ **[src/parsing/refactored_2_1/CLAUDE.md](src/parsing/refactored_2_1/CLAUDE.md)** - Stable reference
- Working implementation patterns
- Proven parsing approaches
- Cache management examples

### **For Project Status**
→ **[src/pipeline_v3/DEVELOPMENT_STATUS.md](src/pipeline_v3/DEVELOPMENT_STATUS.md)** - Detailed status
→ **[GitHub Issues](https://github.com/seaberger/rag-lab/issues)** - Active issue tracking

## ⚙️ Environment & Setup

### **Critical Environment Requirements**
- **Working Directory**: Always use project root (`/Users/seanbergman/Repositories/rag_lab`)
- **Package Manager**: `uv` for dependency management
- **Environment File**: `.env` at project root with `OPENAI_API_KEY`

### **Quick Environment Check**
```bash
# Verify you're in project root
pwd  # Should show: /Users/seanbergman/Repositories/rag_lab

# Test Pipeline v3
uv run python -m src.pipeline_v3.cli_main --help
```


## 📚 Documentation Hierarchy

### **Repository Level** (This File)
- High-level project context and navigation
- Current focus and priorities
- Component relationships

### **Component Level**
- **Pipeline v3**: `src/pipeline_v3/CLAUDE.md` (Detailed v3 context)
- **Pipeline v2.1**: `src/parsing/refactored_2_1/CLAUDE.md` (Reference)

### **Status & Reference**
- **Development Status**: `src/pipeline_v3/DEVELOPMENT_STATUS.md`
- **User Manual**: `src/pipeline_v3/USER_MANUAL.md`
- **Quick Reference**: `src/pipeline_v3/QUICK_REFERENCE.md`

## 🚀 Quick Start Scenarios

### **"I want to work on Pipeline v3"**
1. `cd src/pipeline_v3`
2. Read `CLAUDE.md` for detailed context
3. Check current issues at top of file

### **"I want to test document processing"**
1. Follow Pipeline v3 setup
2. Use: `uv run python -m src.pipeline_v3.cli_main add data/sample_docs/[file].pdf`
3. Verify: `ls storage_data_v3/` for artifacts

### **"I want to understand the project evolution"**
1. Review this file for current state
2. Check `src/parsing/refactored_2_1/CLAUDE.md` for v2.1 approach
3. Compare architectures and lessons learned

## 🧪 Testing & CI/CD

### **CI/CD Pipeline Architecture** (Updated January 8, 2025)

We have optimized our CI/CD pipelines to minimize OpenAI API costs while maintaining thorough testing:

#### **Quick CI** (`./run_local_quickci.sh` / `.github/workflows/quick-ci.yml`)
- **Purpose**: Fast feedback on every commit/PR
- **Runtime**: ~5-10 minutes
- **Features**:
  - All unit tests (no API calls)
  - All security tests (no API calls)
  - Optimized integration test processing only 2 documents
  - PostgreSQL multi-tenant database setup
  - Stops early on failures (`--maxfail=5`)
- **Triggers**: Every push/PR to main branches

#### **Comprehensive CI** (`./run_local_ci.sh` / `.github/workflows/comprehensive-ci.yml`)
- **Purpose**: Extended validation for release readiness
- **Runtime**: ~15-30 minutes
- **Features**:
  - Only tests marked with `@pytest.mark.comprehensive`
  - Heavy document processing (5+ documents)
  - Edge cases and stress testing
  - No duplication with Quick CI tests
- **Triggers**:
  - Manual workflow dispatch
  - PR label: `comprehensive-ci`
  - Release tags (v*)
- **Cost Savings**: ~80% reduction in unnecessary API calls

### **⚠️ IMPORTANT: Timeout Configuration for Claude Code**

When running these scripts in Claude Code, you MUST override the default 2-minute bash timeout:

```
# For Quick CI (set 10 minute timeout = 600000ms)
Bash command: ./run_local_quickci.sh
Timeout: 600000

# For Comprehensive CI (set 30 minute timeout = 1800000ms)
Bash command: ./run_local_ci.sh
Timeout: 1800000
```

**Why this matters:**
- Claude Code's default bash timeout is 120 seconds (2 minutes)
- Quick CI typically needs 5-10 minutes
- Comprehensive CI needs 15-30 minutes
- Without timeout override, tests will be killed mid-execution

### **Test Coverage**

Both scripts include:
- **Unit Tests**: 289 tests for core components
- **Security Tests**: 33 tests (29 comprehensive + 4 SQL injection)
- **Integration Tests**: Multiple categories (smoke, lightweight, server, e2e)
- **Code Quality**: Ruff linting and formatting
- **Coverage Reports**: HTML and XML formats

## 🔗 External Links

- **GitHub Repository**: [rag-lab](https://github.com/seaberger/rag-lab)
- **Active Issues**: [Open Issues](https://github.com/seaberger/rag-lab/issues)
- **Latest Commits**: [Commit History](https://github.com/seaberger/rag-lab/commits/main)

## 📝 GitHub Issue Creation Guidelines

### Available Labels (Use ONLY these):
- **bug** - Something isn't working
- **documentation** - Improvements or additions to documentation
- **duplicate** - This issue or pull request already exists
- **enhancement** - New feature or request
- **good first issue** - Good for newcomers
- **help wanted** - Extra attention is needed
- **invalid** - This doesn't seem right
- **question** - Further information is requested
- **wontfix** - This will not be worked on

### When Creating Issues:
- **DO NOT** create custom labels like "security", "infrastructure", "critical", etc.
- **DO** use only the standard GitHub labels listed above
- **DO** use "enhancement" for all new features (including enterprise features)
- **DO** use "bug" for security vulnerabilities and critical issues
- **DO** use clear issue titles that describe the feature/fix

---

**🎯 For Pipeline v3 work, go directly to:** [src/pipeline_v3/CLAUDE.md](src/pipeline_v3/CLAUDE.md)

**📊 Current Status**: Production-ready with core functionality, enterprise features, and reliability improvements
**🔄 Development Planning**: See [ROADMAP.md](ROADMAP.md) for current priorities
**📋 Architecture Gaps**: See [ISSUES.md](ISSUES.md) for comprehensive analysis
**🏢 Enterprise Vision**: See [Enterprise Implementation Guide](src/pipeline_v3/docs/ENTERPRISE_MULTI_TENANT_IMPLEMENTATION.md)
