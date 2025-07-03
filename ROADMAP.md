# RAG Lab Development Roadmap

This document provides the current development priorities and active issues for the RAG Lab project. It serves as the single source of truth for development planning.

**Last Updated:** January 2, 2025
**Active GitHub Issues:** 20 (14 existing + 6 new)
**Critical Architecture Gaps:** 12 (see [ISSUES.md](ISSUES.md))

## 🚨 Immediate Priorities (Security & Stability)

### Security Vulnerabilities (CRITICAL)
Must be addressed before any production deployment:
- **[Issue #61](https://github.com/seaberger/rag-lab/issues/61)**: Security Audit & Fixes: SQL Injection, Path Traversal, and SSRF Protection
- **[Issue #62](https://github.com/seaberger/rag-lab/issues/62)**: Input Validation Framework and Secrets Management

### Quality Assurance (HIGH)
Enable automated quality control:
- **[Issue #63](https://github.com/seaberger/rag-lab/issues/63)**: Implement CI/CD Pipeline with GitHub Actions and Security Testing

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

## 🏢 Advanced Features (Future)

### Multi-User Support
- **[Issue #56](https://github.com/seaberger/rag-lab/issues/56)**: Multi-tenant collection support for business groups

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

### Performance (LOW)
- **[Issue #5](https://github.com/seaberger/rag-lab/issues/5)**: Upgrade to Qdrant server (when scale requires it)

## ✅ Recently Completed (Last 60 Days)

### Infrastructure & Reliability
- **[Issue #27](https://github.com/seaberger/rag-lab/issues/27)**: Cross-System Consistency Guarantees ✅
- **[Issue #26](https://github.com/seaberger/rag-lab/issues/26)**: Database Schema Versioning ✅
- **[Issue #25](https://github.com/seaberger/rag-lab/issues/25)**: Top-Level Error Handling ✅
- **[Issues #28-29](https://github.com/seaberger/rag-lab/issues/28)**: OpenAI API hardening ✅

### Features
- **[Issue #31](https://github.com/seaberger/rag-lab/issues/31)**: Word & PowerPoint support ✅
- **[Issue #33](https://github.com/seaberger/rag-lab/issues/33)**: Directory parsing with filtering ✅
- **[Issue #45](https://github.com/seaberger/rag-lab/issues/45)**: URL batch processing ✅

### UX Improvements
- **[Issue #36](https://github.com/seaberger/rag-lab/issues/36)**: CLI parameter consistency ✅
- **[Issue #46](https://github.com/seaberger/rag-lab/issues/46)**: Large document timeout workaround ✅
- **[PR #60](https://github.com/seaberger/rag-lab/pull/60)**: README improvements ✅

## 📊 Progress Summary

### What's Working Well ✅
- Core document processing pipeline
- Queue-based batch processing
- Multiple document formats (PDF, Word, PowerPoint)
- Hybrid search (vector + keyword)
- Error handling and reliability

### What Needs Work 🔧
- **Security vulnerabilities** (SQL injection, path traversal, SSRF)
- **No automated testing** or CI/CD
- **Search filtering** could be more powerful
- **Chunking strategies** are basic

### What's Nice to Have 💭
- Multi-tenant support
- Batch API integration
- Advanced web scraping
- Performance optimizations

## 🚀 Getting Started

For developers looking to contribute:

1. **Security First**: Review and help fix security vulnerabilities
2. **Add Tests**: Help set up GitHub Actions and write tests
3. **Improve Search**: Work on metadata filtering improvements
4. Check [CLAUDE.md](CLAUDE.md) for project setup
5. See [ISSUES.md](ISSUES.md) for detailed architecture gaps
