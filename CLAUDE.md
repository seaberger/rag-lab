# RAG Lab Repository - CLAUDE.md

This file provides repository-wide context and navigation guidance for Claude Code development sessions.

## 🎯 Current Development Focus: Pipeline v3

**Active Area**: `src/pipeline_v3/` - Production-ready document processing system  
**Detailed Context**: [Pipeline v3 CLAUDE.md](src/pipeline_v3/CLAUDE.md)  
**Status**: Core functionality complete, optimization phase

### Quick Start for Pipeline v3:
```bash
# Navigate to Pipeline v3
cd src/pipeline_v3

# Follow Pipeline v3 CLAUDE.md for detailed context
# Primary CLI: uv run python -m src.pipeline_v3.cli_main
```

## 📊 Project Status Overview

### ✅ **Production Ready Components**
- **Pipeline v3**: Enterprise document processing with OpenAI Vision API
- **Storage System**: JSONL artifacts with full datasheet parsing
- **Search Engine**: Hybrid vector + keyword search
- **Queue Management**: Scalable concurrent processing

### 🎯 **Completed Major Milestones**
- **✅ Issue #9**: CLI interface consolidation (**COMPLETED & MERGED**)
  - Single production CLI with full v2.1 feature parity
  - Document classification modes (datasheet/generic/auto)
  - Batch processing with concurrent workers
  - URL support and custom prompt files
  - Rich progress reporting with emoji indicators

### 🔄 **Active Issues and Priorities**

#### **CRITICAL Production Readiness Issues** 🚨
- **Issue #25**: No Top-Level Error Handling in CLI Entry Point
  - Application crashes on unhandled exceptions
  - No graceful error messages for users
  - Essential for basic reliability
- **Issue #26**: No Database Schema Versioning or Migration Framework
  - Breaking changes on upgrades cause data loss
  - No safe path for system evolution
  - Blocks production deployments
- **Issue #27**: No Cross-System Consistency Guarantees
  - Data corruption across storage systems (SQLite, Qdrant, JSONL)
  - Partial failures leave system in inconsistent state
  - Critical for data integrity

#### **HIGH Priority Issues** 🔥  
- **Issue #7**: Fix model/part number pair extraction (BOTH V2.1 & V3)
  - Multi-line JSON metadata not parsed correctly
  - Only extracts first line: `"Metadata: {"` instead of full JSON block
  - All datasheet pair extraction currently broken
- **Issue #14**: Document-type aware chunking strategies
  - Page-based chunking for datasheets (1 page = 1 chunk)
  - Semantic chunking for regular documents
  - Better context preservation for technical specs

#### **MEDIUM Priority Issues** ⚡
- **Issue #13**: Hybrid PDF parsing (VLM for datasheets, Docling for regular docs)
  - Cost savings by using Docling for non-technical documents
  - Performance improvements for simple text extraction
- **Issue #15**: Proper table extraction and LlamaIndex node handling
  - TableNode creation for structured data
  - Table-aware chunking strategies
- **Issue #12**: Page-level content classification for mixed documents

#### **LOW Priority Issues** 📋
- **Issue #8**: System status monitoring (Low priority)
- **Issue #5**: Performance optimizations (Low priority)

#### **📋 Comprehensive Architecture Review**
**See**: [ISSUES.md](ISSUES.md) - Complete analysis of 28 fundamental architecture gaps across security, error handling, data persistence, configuration, testing, and observability

### 📋 **Recent Achievements**
- ✅ **Issue #16 Resolved**: Keyword enhancement restored - storage artifacts now contain keyword-enhanced markdown
- ✅ **Issue #9 Resolved**: CLI consolidation complete - single production interface
- ✅ **Issue #6 Resolved**: Storage artifacts now created correctly
- ✅ **Issue #4 Resolved**: Document state management fixed
- ✅ **Issue #3 Resolved**: Vector embedding generation working
- ✅ **Issue #11 Resolved**: Configurable timeout handling implemented (merged to main)

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

## 🎯 Development Priorities

### **URGENT: Production Readiness** 🚨
**Focus**: Address fundamental architecture gaps before feature development
1. **Issue #25**: Add top-level error handling (CRITICAL)
   - Essential for basic system reliability
   - Quick fix with immediate impact
2. **Issue #26**: Implement database schema versioning (CRITICAL)
   - Required for safe system evolution
   - Prevents data loss on upgrades
3. **Issue #27**: Add cross-system consistency guarantees (CRITICAL)
   - Prevents data corruption
   - Essential for production deployments

### **Next Sprint Focus**
1. **Production Foundation**: Address Issues #25-27 for basic reliability
2. **Data Quality**: Fix pair extraction (Issue #7) and enhance chunking (Issue #14)
3. **Architecture Review**: Systematically address gaps from [ISSUES.md](ISSUES.md)

### **Architecture Improvement Roadmap**
**Phase 1 (Critical)**: Core reliability and data integrity
- Error handling framework (Issue #25)
- Database migrations (Issue #26)  
- Transaction consistency (Issue #27)

**Phase 2 (High)**: Security and input validation
- SQL injection protection
- Path traversal fixes
- Input sanitization framework

**Phase 3 (Medium)**: Testing and observability
- Formal testing framework with CI/CD
- Metrics collection and monitoring
- Structured logging and tracing

**See [ISSUES.md](ISSUES.md) for complete 28-issue analysis and implementation roadmap**

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

## 🔗 External Links

- **GitHub Repository**: [rag-lab](https://github.com/seaberger/rag-lab)
- **Active Issues**: [Open Issues](https://github.com/seaberger/rag-lab/issues)
- **Latest Commits**: [Commit History](https://github.com/seaberger/rag-lab/commits/main)

---

**🎯 For Pipeline v3 work, go directly to:** [src/pipeline_v3/CLAUDE.md](src/pipeline_v3/CLAUDE.md)

**📊 Current Status**: Core functionality complete, requires architecture improvements for production  
**🔄 Active Focus**: Production readiness (Issues #25-27) and systematic architecture gap resolution  
**📋 Architecture Review**: [ISSUES.md](ISSUES.md) identifies 28 gaps across reliability, security, and maintainability