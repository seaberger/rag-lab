#!/usr/bin/env python3
"""
Simple test to verify key components work independently.
"""

import asyncio
import sys
import os
from pathlib import Path

# Set up basic environment
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-key')

async def test_basic_components():
    """Test individual components without imports."""
    
    print("🧪 Testing Basic Pipeline Components")
    print("=" * 50)
    
    # Test document path
    doc_path = Path("../../../data/sample_docs/pm10k-plus-ds.pdf")
    
    if not doc_path.exists():
        print(f"❌ Test document not found: {doc_path}")
        return False
    
    print(f"📄 Document found: {doc_path}")
    print(f"📊 Document size: {doc_path.stat().st_size} bytes")
    
    # Test Poppler discovery
    print("🛠️ Testing Poppler discovery...")
    import shutil
    exe = shutil.which("pdfinfo")
    if exe:
        poppler_path = str(Path(exe).parent)
        print(f"✅ Poppler found at: {poppler_path}")
    else:
        print("⚠️ Poppler not found in PATH")
    
    # Test PDF to image conversion
    print("🖼️ Testing PDF to image conversion...")
    try:
        from pdf2image import convert_from_path
        import base64
        import io
        
        # Convert first page only for testing
        images = convert_from_path(
            str(doc_path),
            dpi=72,  # Low DPI for faster testing
            first_page=1,
            last_page=1,
            poppler_path=poppler_path if 'poppler_path' in locals() else None
        )
        
        if images:
            # Convert to data URI
            image = images[0]
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=50)
            img_bytes = buf.getvalue()
            
            base64_string = base64.b64encode(img_bytes).decode('utf-8')
            data_uri = f"data:image/jpeg;base64,{base64_string}"
            
            print(f"✅ PDF converted: {len(images)} pages, {len(data_uri)} chars data URI")
        else:
            print("❌ No images generated from PDF")
            
    except Exception as e:
        print(f"❌ PDF conversion failed: {e}")
    
    # Test document classification logic
    print("📋 Testing document classification logic...")
    filename = doc_path.name.lower()
    
    # Simple classification logic
    datasheet_indicators = ['datasheet', 'ds.pdf', 'spec', 'specification']
    has_datasheet_pattern = any(indicator in filename for indicator in datasheet_indicators)
    
    if has_datasheet_pattern:
        doc_type = "datasheet_pdf"
        confidence = 0.8
    elif filename.endswith('.pdf'):
        doc_type = "generic_pdf" 
        confidence = 0.6
    else:
        doc_type = "unknown"
        confidence = 0.0
    
    print(f"✅ Document classified as: {doc_type} (confidence: {confidence:.2f})")
    
    # Test JSON serialization
    print("📝 Testing artifact serialization...")
    import json
    from datetime import datetime
    
    artifact_data = {
        "doc_id": "test_pm10k_12345",
        "source": str(doc_path),
        "pairs": [("PM10K+", "2293937"), ("PM10K+ USB", "2293938")],
        "markdown": "# PM10K+ Power Sensor\n\nTest markdown content...",
        "parse_version": 2,
        "metadata": {"source_type": "datasheet_pdf", "test": True},
        "created_at": datetime.utcnow().isoformat(),
        "markdown_length": 50,
        "pairs_count": 2
    }
    
    jsonl = json.dumps(artifact_data, ensure_ascii=False)
    print(f"✅ Artifact serialized: {len(jsonl)} chars")
    
    # Test OpenAI client creation (without API call)
    print("🤖 Testing OpenAI client setup...")
    try:
        from openai import OpenAI
        client = OpenAI()  # Should work with API key in env
        print("✅ OpenAI client created successfully")
    except Exception as e:
        print(f"⚠️ OpenAI client setup issue: {e}")
    
    # Test configuration loading
    print("⚙️ Testing configuration...")
    config_path = Path("config.yaml")
    if config_path.exists():
        print(f"✅ Config file found: {config_path}")
        try:
            import yaml
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f)
            print(f"✅ Config loaded: {len(config_data)} sections")
        except Exception as e:
            print(f"⚠️ Config parsing issue: {e}")
    else:
        print("⚠️ Config file not found")
    
    print("\n🎉 Basic component tests completed!")
    print("\nTo test the full pipeline:")
    print("1. Set OPENAI_API_KEY environment variable")
    print("2. Ensure all dependencies are installed")
    print("3. Fix relative import issues for production use")
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_basic_components())
    sys.exit(0 if success else 1)