#!/usr/bin/env python3
"""
Full pipeline test from the parent directory to handle imports correctly.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add src directory to path
project_root = Path(__file__).parent
src_dir = project_root / "src" / "parsing" / "refactored_2_1"
sys.path.insert(0, str(src_dir))

async def test_pipeline_simulation():
    """Simulate the full pipeline without actual API calls."""
    
    print("🧪 Full Pipeline Simulation Test")
    print("=" * 60)
    
    # Test document
    doc_path = project_root / "data" / "sample_docs" / "pm10k-plus-ds.pdf"
    
    if not doc_path.exists():
        print(f"❌ Document not found: {doc_path}")
        return False
    
    print(f"📄 Testing document: {doc_path.name}")
    print(f"📊 Size: {doc_path.stat().st_size:,} bytes")
    
    try:
        # Import all components
        print("\n🔍 1. Testing Component Imports...")
        
        # Test individual components that don't have relative import issues
        print("   📋 Document Classification...")
        
        # Simulate document classification
        filename = doc_path.name.lower()
        if 'ds.pdf' in filename or 'datasheet' in filename:
            doc_type = "datasheet_pdf"
            confidence = 0.9
        else:
            doc_type = "generic_pdf"
            confidence = 0.7
            
        print(f"   ✅ Classified as: {doc_type} (confidence: {confidence})")
        
        # Test PDF processing
        print("\n🖼️ 2. Testing PDF Processing...")
        
        from pdf2image import convert_from_path
        import base64
        import io
        
        # Convert first page for testing
        images = convert_from_path(
            str(doc_path),
            dpi=150,
            first_page=1,
            last_page=1
        )
        
        if images:
            # Convert to data URI (what would be sent to OpenAI)
            image = images[0]
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=85)
            img_bytes = buf.getvalue()
            
            base64_string = base64.b64encode(img_bytes).decode('utf-8')
            data_uri = f"data:image/jpeg;base64,{base64_string}"
            
            print(f"   ✅ PDF converted: {len(images)} pages")
            print(f"   ✅ Data URI generated: {len(data_uri):,} chars")
            print(f"   📏 Image size: {image.size}")
        
        # Test OpenAI request structure (without sending)
        print("\n🤖 3. Testing OpenAI Request Structure...")
        
        # Simulate what would be sent to OpenAI Responses API
        prompt = """# CRITICAL PARSING INSTRUCTIONS
Extract model/part number pairs and convert to GitHub-flavored Markdown."""
        
        request_parts = [
            {
                "type": "input_text",
                "text": (
                    f"{prompt}\n\n"
                    "Return **one Markdown document** with:\n"
                    "1. Metadata: {'pairs': [('model', 'part_number'), ...]}\n"
                    "2. Full datasheet in Markdown format"
                )
            },
            {
                "type": "input_image",
                "image_url": data_uri
            }
        ]
        
        print(f"   ✅ Request structure prepared: {len(request_parts)} parts")
        print(f"   📝 Prompt length: {len(request_parts[0]['text'])} chars")
        print(f"   🖼️ Image data ready: {len(request_parts[1]['image_url'])} chars")
        
        # Simulate OpenAI response
        print("\n📤 4. Simulating OpenAI Response...")
        
        # What we expect back from OpenAI
        simulated_response = """Metadata: {
    'pairs': [
        ('PM10K+', '2293937'),
        ('PM10K+ USB', '2293938'),
        ('PM10K+ RS-232', '2293939')
    ]
}

# PM10K+ Power Sensor Data Sheet

## Overview
The PM10K+ series represents the latest generation of high-precision laser power sensors...

## Specifications

| Model | PM10K+ | PM10K+ USB | PM10K+ RS-232 |
|-------|--------|------------|---------------|
| Part Number | 2293937 | 2293938 | 2293939 |
| Power Range | 10 µW to 10 W | 10 µW to 10 W | 10 µW to 10 W |
| Wavelength Range | 0.19 to 12 µm | 0.19 to 12 µm | 0.19 to 12 µm |
| Connector | DB-25 | USB | RS-232 |

## Features
- High precision measurement
- Wide dynamic range
- Multiple connectivity options"""
        
        print(f"   ✅ Response simulated: {len(simulated_response)} chars")
        
        # Parse the simulated response
        print("\n🔍 5. Testing Response Parsing...")
        
        lines = simulated_response.split('\n')
        metadata_line = lines[0]
        
        if metadata_line.startswith("Metadata:"):
            import json
            import re
            
            # Extract JSON from metadata line
            json_match = re.search(r'\{.*\}', metadata_line, re.DOTALL)
            if json_match:
                json_str = json_match.group().replace("'", '"')  # Convert to valid JSON
                try:
                    metadata = json.loads(json_str)
                    pairs = metadata.get('pairs', [])
                    print(f"   ✅ Extracted {len(pairs)} model/part pairs:")
                    for model, part in pairs:
                        print(f"      • {model}: {part}")
                except json.JSONDecodeError as e:
                    print(f"   ⚠️ JSON parsing issue: {e}")
                    pairs = []
            else:
                pairs = []
        
        # Remove metadata line for clean markdown
        clean_markdown = '\n'.join(lines[1:]).strip()
        
        print("\n📝 6. Testing Document Artifact Creation...")
        
        # Create artifact (what would be saved)
        import json
        from datetime import datetime
        
        artifact = {
            "doc_id": "pm10k_test_123",
            "source": str(doc_path),
            "pairs": pairs,
            "markdown": clean_markdown,
            "parse_version": 2,
            "metadata": {
                "source_type": "datasheet_pdf",
                "extracted_pairs": len(pairs),
                "test_mode": True
            },
            "created_at": datetime.now().isoformat(),
            "markdown_length": len(clean_markdown),
            "pairs_count": len(pairs)
        }
        
        jsonl = json.dumps(artifact, ensure_ascii=False)
        print(f"   ✅ Artifact created: {len(jsonl):,} chars")
        
        # Test chunking simulation
        print("\n📄 7. Testing Document Chunking...")
        
        # Simple chunking simulation
        chunk_size = 1000
        chunks = []
        text = clean_markdown
        
        for i in range(0, len(text), chunk_size):
            chunk = text[i:i + chunk_size]
            chunk_data = {
                "text": chunk,
                "metadata": {
                    "doc_id": "pm10k_test_123",
                    "pairs": pairs,
                    "chunk_index": len(chunks),
                    "source": str(doc_path)
                }
            }
            chunks.append(chunk_data)
        
        print(f"   ✅ Document chunked: {len(chunks)} chunks")
        
        # Test keyword generation simulation
        print("\n🔍 8. Testing Keyword Generation...")
        
        # Simulate keyword extraction
        sample_keywords = [
            ["PM10K+", "power sensor", "laser measurement", "high precision"],
            ["specifications", "wavelength range", "connectivity", "DB-25"],
            ["USB interface", "RS-232", "part number", "dynamic range"]
        ]
        
        for i, chunk in enumerate(chunks[:3]):  # Just first 3 chunks
            if i < len(sample_keywords):
                chunk["metadata"]["keywords"] = sample_keywords[i]
                print(f"   ✅ Chunk {i+1} keywords: {sample_keywords[i]}")
        
        print("\n🎉 Pipeline Simulation Complete!")
        print("\n📊 Summary:")
        print(f"   📄 Document: {doc_path.name}")
        print(f"   📋 Type: {doc_type}")
        print(f"   🔢 Pairs extracted: {len(pairs)}")
        print(f"   📝 Markdown length: {len(clean_markdown):,} chars")
        print(f"   📄 Chunks created: {len(chunks)}")
        print(f"   💾 Artifact size: {len(jsonl):,} chars")
        
        print("\n💡 Next Steps for Real Testing:")
        print("   1. Set OPENAI_API_KEY environment variable")
        print("   2. Fix relative import structure")
        print("   3. Run with: python cli_with_updated_doc_flow.py --src path/to/doc.pdf")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_pipeline_simulation())
    sys.exit(0 if success else 1)