# RAG Lab Development Roadmap

This document provides the current development priorities and active issues for the RAG Lab project. It serves as the single source of truth for development planning.

> **🚀 NEW: Enterprise Multi-Tenant Focus** - RAG Lab is evolving from a single-user system to a full enterprise platform with PostgreSQL, API authentication, per-tenant MCP servers, and advanced search capabilities. See the new [Enterprise Implementation Guide](src/pipeline_v3/docs/ENTERPRISE_MULTI_TENANT_IMPLEMENTATION.md) for the complete vision.

**Last Updated:** January 7, 2025
**Active GitHub Issues:** 27 open (including 9 new enterprise features)
**Critical Architecture Gaps:** 10 (see [ISSUES.md](ISSUES.md))
**Enterprise Implementation Guide:** [ENTERPRISE_MULTI_TENANT_IMPLEMENTATION.md](src/pipeline_v3/docs/ENTERPRISE_MULTI_TENANT_IMPLEMENTATION.md)
**Database Setup Guide:** [DATABASE_SETUP_GUIDE.md](DATABASE_SETUP_GUIDE.md)

## ✅ All Critical Security & Infrastructure Issues Resolved!

### ~~Security Vulnerabilities (CRITICAL)~~ ✅ **COMPLETED**
~~Must be addressed before any production deployment:~~
- ~~**[Issue #61](https://github.com/seaberger/rag-lab/issues/61)**: Security Audit & Fixes: SQL Injection, Path Traversal, and SSRF Protection~~ ✅ **COMPLETED (July 5, 2025)**
- ~~**[Issue #62](https://github.com/seaberger/rag-lab/issues/62)**: Input Validation Framework and Secrets Management~~ ✅ **COMPLETED (July 5, 2025)**
  - **Resolution:** Implemented comprehensive security utilities module with path traversal protection, SSRF prevention, input sanitization, and secrets masking
  - Added 40 security tests integrated into CI pipeline
  - JSON metadata preserved while maintaining security

### ~~Infrastructure Issues (HIGH)~~ ✅ **COMPLETED**
~~Blocking automated CI/CD validation:~~
- ~~**[Issue #75](https://github.com/seaberger/rag-lab/issues/75)**: CI/CD Pipeline Failures on GitHub Actions~~ ✅ **COMPLETED (July 5, 2025)**
  - ~~Qdrant container health check failures in GitHub Actions environment~~
  - ~~Missing OpenAI API key configuration in remote testing~~
  - ~~Local testing works perfectly (359 tests pass), remote infrastructure needs fixes~~
  - **Resolution:** Fixed environment variable pollution in tests where test cleanup was overriding real API keys

### ~~Infrastructure & Scalability (HIGH)~~ ✅ **COMPLETED**
~~Critical for production deployment and concurrent usage:~~
- ~~**[Issue #71](https://github.com/seaberger/rag-lab/issues/71)**: Implement Qdrant Server Mode for Production Scalability~~ ✅ **COMPLETED (July 4, 2025)**
  - ~~Resolves test isolation issues and enables concurrent access~~
  - ~~Required for multi-tenant/business group support~~
  - ~~Docker-based deployment for production environments~~

### ~~Quality Assurance (HIGH)~~ ✅ **COMPLETED**
~~Enable automated quality control:~~
- ~~**[Issue #63](https://github.com/seaberger/rag-lab/issues/63)**: Implement CI/CD Pipeline with GitHub Actions and Security Testing~~ ✅ **COMPLETED (July 3, 2025)**

## 🔍 Core Feature Improvements

### Search Enhancements (HIGH)
Make search more powerful and accurate:
- **[Issue #53](https://github.com/seaberger/rag-lab/issues/53)**: Implement proper LlamaIndex MetadataFilters
- **[Issue #54](https://github.com/seaberger/rag-lab/issues/54)**: Implement pairs metadata filtering logic
- **[Issue #23](https://github.com/seaberger/rag-lab/issues/23)**: Enhanced Search Filtering System

### Document Processing (MEDIUM)
Improve how documents are parsed and chunked:
- **[Issue #14](https://github.com/seaberger/rag-lab/issues/14)**: Document-type aware chunking strategies
- **[Issue #15](https://github.com/seaberger/rag-lab/issues/15)**: Proper table extraction and LlamaIndex nodes
- **[Issue #13](https://github.com/seaberger/rag-lab/issues/13)**: Hybrid PDF parsing (VLM vs Docling based on type)
- **[Issue #12](https://github.com/seaberger/rag-lab/issues/12)**: Page-level content classification for mixed document types

## 🏢 Enterprise Multi-Tenant Infrastructure (NEW CRITICAL PATH)

### ✅ Foundation: Database Migration (**MAJOR PROGRESS - January 2025**)
- **[Issue #77](https://github.com/seaberger/rag-lab/issues/77)**: PostgreSQL Migration for Multi-Tenancy (**80% COMPLETE**)
  - ✅ **Complete PostgreSQL migration** with all schemas and tables
  - ✅ **Row-level security (RLS)** enabled for tenant isolation
  - ✅ **Multi-tenant architecture** with session-based context
  - ✅ **Comprehensive database setup documentation** and automation scripts
  - ✅ **Fixed critical tenant filtering bug** in vector search
  - 🔄 **Remaining:** API authentication integration and production hardening
  - **Priority:** CRITICAL | **Effort:** 20% remaining (~3-5 days)
  - **📋 Setup Guide:** [DATABASE_SETUP_GUIDE.md](DATABASE_SETUP_GUIDE.md)

### 🗄️ Infrastructure & Cache System (HIGH PRIORITY)
- **[Issue #88](https://github.com/seaberger/rag-lab/issues/88)**: Cache System Not Tenant-Aware and References Obsolete Database Files
  - API response cache lacks tenant isolation (security risk)
  - CacheCleaner references obsolete SQLite/local Qdrant files
  - Need tenant-aware cache paths: `cache_v3/{tenant_id}/`
  - Consider PostgreSQL-based caching for full isolation
  - **Priority:** HIGH | **Effort:** Medium (3-5 days)

### 🔐 Security & Authentication (HIGH PRIORITY)
- **[Issue #78](https://github.com/seaberger/rag-lab/issues/78)**: API Key & Authentication System for Multi-Tenant Access
  - API key generation and management
  - Rate limiting per tenant
  - RBAC implementation
  - Audit logging
  - **Priority:** HIGH | **Effort:** Medium (1 week)

- **[Issue #79](https://github.com/seaberger/rag-lab/issues/79)**: Document Security Framework for Access Control
  - Document-level security (public, internal, restricted)
  - Group-based permissions
  - Encryption at rest for sensitive docs
  - Compliance support (GDPR, HIPAA)
  - **Priority:** HIGH | **Effort:** Medium (1 week)

- **[Issue #80](https://github.com/seaberger/rag-lab/issues/80)**: Secure Search Implementation with Access Control
  - Filter search results by permissions
  - Maintain performance with security
  - Audit trail for sensitive searches
  - **Priority:** HIGH | **Effort:** Medium (1 week)

### 🤖 Advanced Platform Features
- **[Issue #81](https://github.com/seaberger/rag-lab/issues/81)**: MCP Server Implementation Per Tenant
  - Model Context Protocol servers for agentic workflows
  - Dynamic document ingestion
  - Tenant-specific tools
  - Service discovery and orchestration
  - **Priority:** HIGH | **Effort:** Large (2 weeks)

- **[Issue #82](https://github.com/seaberger/rag-lab/issues/82)**: Tenant-Specific Search Pipeline Configuration
  - Configurable search strategies per tenant
  - Industry-specific optimizations
  - A/B testing framework
  - Pipeline templates
  - **Priority:** HIGH | **Effort:** Medium (1.5 weeks)

- **[Issue #83](https://github.com/seaberger/rag-lab/issues/83)**: Agentic Workflow Framework with MCP Integration
  - Multi-step workflows with state management
  - Dynamic tool calling
  - Industry-specific templates
  - Error recovery and monitoring
  - **Priority:** MEDIUM | **Effort:** Large (2 weeks)

### 🔍 Next-Generation Search
- **[Issue #84](https://github.com/seaberger/rag-lab/issues/84)**: Multi-Vector Search Support (ColBERT, SPLADE, BGE-M3)
  - Token-level search with ColBERT
  - Learned sparse representations (SPLADE)
  - Multi-representation models (BGE-M3)
  - Advanced fusion strategies
  - **Priority:** MEDIUM | **Effort:** Large (2-3 weeks)

- **[Issue #85](https://github.com/seaberger/rag-lab/issues/85)**: Adaptive Search Optimization with Usage-Based Learning
  - Automatic pipeline tuning
  - Performance monitoring
  - A/B testing automation
  - Cross-tenant insights
  - **Priority:** MEDIUM | **Effort:** Large (2 weeks)

## 🏢 Advanced Features (Future)

### Enhanced Multi-User Support
- **[Issue #56](https://github.com/seaberger/rag-lab/issues/56)**: Multi-tenant collection support for business groups
  - **Note:** Basic implementation exists. See [MULTI_TENANT_ARCHITECTURE.md](src/pipeline_v3/docs/MULTI_TENANT_ARCHITECTURE.md)
  - Enterprise enhancements covered in issues #77-#85 above

### Cost Optimization
- **[Issue #47](https://github.com/seaberger/rag-lab/issues/47)**: OpenAI Batch API for bulk processing

### Advanced Web Processing
- **[Issue #32](https://github.com/seaberger/rag-lab/issues/32)**: Hierarchical site navigation and extraction

## 🔧 Technical Debt & Operations

### System Improvements (MEDIUM)
- **[Issue #40](https://github.com/seaberger/rag-lab/issues/40)**: IndexManager Production-Ready Enhancements
- **[Issue #34](https://github.com/seaberger/rag-lab/issues/34)**: FingerprintManager: Design limitations prevent full atomic operation support
- **[Issue #24](https://github.com/seaberger/rag-lab/issues/24)**: Comprehensive Review: Document Tracking and Update System

### Data Protection (MEDIUM)
- **[Issue #64](https://github.com/seaberger/rag-lab/issues/64)**: Implement Automated Backup System and Disaster Recovery Procedures

### Error Handling & Reliability (MEDIUM)
- **[Issue #65](https://github.com/seaberger/rag-lab/issues/65)**: Standardize Error Handling and Fix Temporary File Security

### Observability (LOW)
- **[Issue #66](https://github.com/seaberger/rag-lab/issues/66)**: Implement Structured JSON Logging with Operation Tracking

### Code Quality (LOW)
- **[Issue #68](https://github.com/seaberger/rag-lab/issues/68)**: Clean up lazy imports (PLC0415) - 101 instances of imports inside functions

### ~~Performance (LOW)~~ ✅ **COMPLETED**
- ~~**[Issue #5](https://github.com/seaberger/rag-lab/issues/5)**: Upgrade to Qdrant server~~ ✅ **COMPLETED via Issue #71**

## ✅ Recently Completed (Last 30 Days)

### Multi-Tenant Infrastructure & Database Migration (January 2025)
- **CI/CD Pipeline Optimization** ✅ (January 8)
  - Separated Quick CI and Comprehensive CI to minimize OpenAI API costs
  - Quick CI runs on every commit with optimized 2-document test
  - Comprehensive CI runs on-demand (label/manual/release) for heavy tests
  - Added `comprehensive` pytest marker for test categorization
  - Both pipelines include PostgreSQL multi-tenant database setup
  - Estimated 80%+ reduction in unnecessary API calls
  - No test duplication between Quick and Comprehensive pipelines
- **Database Setup Documentation & Automation** ✅ (January 7)
  - Complete PostgreSQL setup guide with step-by-step instructions
  - Automated setup script (`setup_databases.sh`) for fresh installations
  - Migration files verified and documented in correct execution order
  - Database verification and testing scripts
  - Comprehensive troubleshooting documentation
- **Critical Tenant Filtering Bug Fix** ✅ (January 7)
  - Fixed vector search tenant isolation - was completely bypassed in certain conditions
  - Tenant filtering now works correctly for both keyword and vector search
  - CLI `--tenant-id` parameter now functions properly
  - Complete tenant data isolation verified and tested
- **Multi-Tenant PostgreSQL Architecture** ✅ (January 7)
  - All database schemas migrated to PostgreSQL with RLS policies
  - Tenant context management with session-based isolation
  - Row-level security enforced on all tables
  - Test tenants created and verified working
  - Both server and local Qdrant modes supported

### Security & Reliability (July 2025)
- **[Issue #61](https://github.com/seaberger/rag-lab/issues/61)**: Security Audit & Fixes ✅ (July 5)
  - Implemented comprehensive security utilities module (`utils/security.py`)
  - Path traversal protection with validation and allowed directories
  - SSRF prevention with URL validation and private IP blocking
  - Input sanitization for metadata and search queries
  - API key masking in logs and outputs
- **[Issue #62](https://github.com/seaberger/rag-lab/issues/62)**: Input Validation Framework ✅ (July 5)
  - Enhanced input validation across CLI and management interfaces
  - JSON metadata preservation for model names and part numbers
  - SQL injection protection with query sanitization
  - 40 comprehensive security tests integrated into CI
  - Fixed critical issue where JSON metadata was being broken by over-aggressive sanitization

### Infrastructure & Scalability (July 2025)
- **[Issue #71](https://github.com/seaberger/rag-lab/issues/71)**: Implement Qdrant Server Mode for Production Scalability ✅ (July 4)
  - Server mode is now the DEFAULT configuration
  - Docker-based Qdrant server with management scripts
  - Dual-mode support (server for production, local for development)
  - Test infrastructure updated to use server mode
  - Comprehensive documentation updates
  - Dashboard available at http://localhost:6333/dashboard
  - Fixed critical chunk deletion issue in server mode:
    - Server mode now uses filter-based deletion to ensure all chunks are removed
    - Prevents orphaned chunks when documents are updated with `--force`
    - Maintains data consistency during document lifecycle operations

### Quality Assurance & CI/CD (July 2025)
- **[Issue #63](https://github.com/seaberger/rag-lab/issues/63)**: Implement CI/CD Pipeline with GitHub Actions ✅ (July 3)
  - Comprehensive Pipeline v3 CI with full test coverage
  - Quick CI for fast PR feedback (~3 minutes)
  - Pre-commit hooks for code quality
  - Test isolation and resource cleanup
- **[Issue #72](https://github.com/seaberger/rag-lab/issues/72)**: Fix failing quick CI/CD workflow ✅ (July 3)
- **[Issue #75](https://github.com/seaberger/rag-lab/issues/75)**: CI/CD Pipeline Failures on GitHub Actions ✅ (July 5)
  - Fixed environment variable pollution in test cleanup
  - Added missing pytest-asyncio decorators for async tests
  - Removed debugging artifacts from CI workflows
  - Both CI workflows now pass consistently on main branch

### Infrastructure & Reliability (June 2025)
- **[Issue #27](https://github.com/seaberger/rag-lab/issues/27)**: Cross-System Consistency Guarantees ✅
- **[Issue #26](https://github.com/seaberger/rag-lab/issues/26)**: Database Schema Versioning ✅
- **[Issue #25](https://github.com/seaberger/rag-lab/issues/25)**: Top-Level Error Handling ✅
- **[Issues #28-29](https://github.com/seaberger/rag-lab/issues/28)**: OpenAI API hardening ✅

### Features (June 2025)
- **[Issue #31](https://github.com/seaberger/rag-lab/issues/31)**: Word & PowerPoint support ✅
- **[Issue #33](https://github.com/seaberger/rag-lab/issues/33)**: Directory parsing with filtering ✅
- **[Issue #45](https://github.com/seaberger/rag-lab/issues/45)**: URL batch processing ✅

### UX Improvements (June 2025)
- **[Issue #36](https://github.com/seaberger/rag-lab/issues/36)**: CLI parameter consistency ✅
- **[Issue #46](https://github.com/seaberger/rag-lab/issues/46)**: Large document timeout workaround ✅
- **[PR #60](https://github.com/seaberger/rag-lab/pull/60)**: README improvements ✅

## 📊 Progress Summary

### What's Working Well ✅
- Core document processing pipeline
- Queue-based batch processing
- Multiple document formats (PDF, Word, PowerPoint)
- Hybrid search (vector + keyword) with proper tenant isolation
- Error handling and reliability
- **Multi-tenant PostgreSQL architecture** with Row-Level Security
- **Complete tenant isolation** in both vector and keyword search
- **Automated database setup** with comprehensive documentation
- **CI/CD pipeline** with dual workflows (quick + comprehensive)
- **Pre-commit hooks** for code quality
- **Test coverage** tracking (currently 88%, excellent improvement from 26%)
- **Qdrant server mode** as default for production scalability
- **Docker-based deployment** for vector database

### What Needs Work 🔧
- **API authentication system** for secure multi-tenant access (Issue #78)
- **Document security framework** for access control (Issue #79)
- **Search filtering** could be more powerful (Issues #53, #54, #23)
- **Chunking strategies** are basic (Issues #14, #15)
- **Type checking** (247 mypy errors need cleanup)

### What's Nice to Have 💭
- Batch API integration
- Advanced web scraping
- Visual search capabilities
- Cross-language support

## 🚀 Getting Started

For developers looking to contribute:

1. **Authentication System**: Implement API key management and tenant authentication (#78) - NEW CRITICAL PATH
2. **Document Security**: Build access control framework (#79)
3. **Improve Search**: Work on metadata filtering improvements (#53, #54, #23)
4. **Type Safety**: Help fix mypy errors (247 issues)
5. **Database Setup**: Use [DATABASE_SETUP_GUIDE.md](DATABASE_SETUP_GUIDE.md) for local development
6. Check [CLAUDE.md](src/pipeline_v3/CLAUDE.md) for project setup
7. See [ISSUES.md](ISSUES.md) for detailed architecture gaps
8. Review [ENTERPRISE_MULTI_TENANT_IMPLEMENTATION.md](src/pipeline_v3/docs/ENTERPRISE_MULTI_TENANT_IMPLEMENTATION.md) for the complete vision

### Development Workflow
- Pre-commit hooks run automatically on commit
- Quick CI provides feedback in ~3 minutes
- Comprehensive CI runs full test suite
- All PRs require passing CI checks
