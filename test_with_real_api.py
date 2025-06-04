#!/usr/bin/env python3
"""
Test the pipeline with real OpenAI API using .env file.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add src directory to path
project_root = Path(__file__).parent
src_dir = project_root / "src" / "parsing" / "refactored_2_1"
sys.path.insert(0, str(src_dir))

async def test_with_real_api():
    """Test pipeline components with real OpenAI API."""
    
    print("🚀 Testing Pipeline with Real OpenAI API")
    print("=" * 60)
    
    # Load environment
    print("🔧 1. Setting up environment...")
    try:
        from utils.env_utils import setup_environment
        env_success = setup_environment(str(project_root))
        
        if not env_success:
            print("❌ Environment setup failed")
            return False
            
        print("✅ Environment setup successful")
        
    except ImportError:
        # Fallback to manual .env loading
        print("   Using fallback .env loading...")
        try:
            from dotenv import load_dotenv
            env_path = project_root / ".env"
            if env_path.exists():
                load_dotenv(env_path)
                print(f"   ✅ Loaded .env from {env_path}")
            else:
                print(f"   ❌ .env not found at {env_path}")
                return False
        except ImportError:
            print("   ❌ python-dotenv not installed")
            return False
    
    # Verify API key
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found in environment")
        return False
    
    print(f"✅ API key found: {api_key[:10]}...")
    
    # Test document
    doc_path = project_root / "data" / "sample_docs" / "pm10k-plus-ds.pdf"
    if not doc_path.exists():
        print(f"❌ Test document not found: {doc_path}")
        return False
    
    print(f"📄 Testing with: {doc_path.name}")
    
    # Test PDF to data URI conversion
    print("\n🖼️ 2. Converting PDF to images...")
    try:
        import base64
        import io
        from pdf2image import convert_from_path
        import shutil
        
        # Find Poppler
        exe = shutil.which("pdfinfo")
        poppler_path = str(Path(exe).parent) if exe else None
        
        # Convert PDF (all pages for complete analysis)
        images = convert_from_path(
            str(doc_path),
            dpi=150,
            poppler_path=poppler_path
        )
        
        if not images:
            print("❌ No images generated from PDF")
            return False
        
        # Convert all pages to data URIs
        data_uris = []
        for i, image in enumerate(images):
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=85)
            img_bytes = buf.getvalue()
            
            base64_string = base64.b64encode(img_bytes).decode('utf-8')
            data_uri = f"data:image/jpeg;base64,{base64_string}"
            data_uris.append(data_uri)
        
        total_chars = sum(len(uri) for uri in data_uris)
        print(f"✅ PDF converted: {len(images)} pages, {total_chars:,} total chars")
        
    except Exception as e:
        print(f"❌ PDF conversion failed: {e}")
        return False
    
    # Test OpenAI API call
    print("\n🤖 3. Testing OpenAI Responses API...")
    try:
        from openai import OpenAI
        
        client = OpenAI()
        
        # Prepare request using our enhanced prompt structure
        prompt = """# CRITICAL PARSING INSTRUCTIONS - FOLLOW EXACTLY

These documents contain technical information about laser power meters, laser energy meters, and laser beam diagnostics products.

When you are parsing a technical product datasheet, always:
1. Follow table formatting rules
2. Extract pairs of model names and part numbers

## PAIR EXTRACTION RULES:

Extract model/part number pairs from the document. Look for:
- Product model names (like PM10K+, PM10K+ USB, etc.)
- Corresponding part numbers (usually 7-digit numbers)
- Cable types that should be appended to model names

## FINAL OUTPUT FORMAT:

Ensure the final output strictly follows this format if pairs are found:

Metadata: {
    'pairs': [
        ('Model Name', 'PartNumber'),
        ('Another Model', 'AnotherPartNumber')
    ]
}

Then provide the full document content as GitHub-flavored Markdown."""

        parts = [
            {
                "type": "input_text", 
                "text": (
                    f"{prompt}\n\n"
                    "## ADDITIONAL INSTRUCTIONS\n"
                    "Return **one Markdown document** with two clearly-separated sections:\n"
                    "1. `Metadata:` with the JSON structure containing extracted pairs\n"
                    "2. The **entire datasheet** translated into GitHub-flavoured Markdown\n"
                )
            }
        ]
        
        # Add all images to the request
        for i, data_uri in enumerate(data_uris):
            parts.append({
                "type": "input_image",
                "image_url": data_uri
            })
        
        print("   📤 Sending request to OpenAI...")
        
        response = client.responses.create(
            model="gpt-4o",
            input=[{"role": "user", "content": parts}],
            temperature=0.0,
        )
        
        # Extract response
        result_text = response.output[0].content[0].text
        
        print(f"✅ API call successful: {len(result_text):,} chars received")
        
        # Parse the response
        print("\n📄 4. Parsing response...")
        
        lines = result_text.split('\n', 1)
        first_line = lines[0] if lines else ""
        
        pairs = []
        if first_line.startswith("Metadata:"):
            try:
                import json
                import re
                
                # Extract JSON from metadata line
                json_match = re.search(r'\{.*?\}', first_line, re.DOTALL)
                if json_match:
                    json_str = json_match.group().replace("'", '"')
                    metadata = json.loads(json_str)
                    pairs = metadata.get('pairs', [])
                    
                    print(f"✅ Extracted {len(pairs)} model/part pairs:")
                    for model, part in pairs:
                        print(f"   • {model}: {part}")
                        
            except (json.JSONDecodeError, Exception) as e:
                print(f"⚠️ Metadata parsing issue: {e}")
        
        # Get clean markdown
        markdown_content = lines[1] if len(lines) > 1 else result_text
        print(f"✅ Markdown extracted: {len(markdown_content):,} chars")
        
        # Show sample of the content
        print("\n📝 5. Sample of extracted content:")
        print("-" * 40)
        sample = markdown_content[:500] + "..." if len(markdown_content) > 500 else markdown_content
        print(sample)
        print("-" * 40)
        
        # Create artifact
        print("\n💾 6. Creating document artifact...")
        
        artifact = {
            "doc_id": "pm10k_real_test",
            "source": str(doc_path),
            "pairs": pairs,
            "markdown": markdown_content,
            "parse_version": 2,
            "metadata": {
                "source_type": "datasheet_pdf",
                "extracted_pairs": len(pairs),
                "api_model": "gpt-4o"
            },
            "created_at": "2024-12-19T12:00:00Z",
            "markdown_length": len(markdown_content),
            "pairs_count": len(pairs)
        }
        
        import json
        jsonl = json.dumps(artifact, ensure_ascii=False)
        print(f"✅ Artifact created: {len(jsonl):,} chars")
        
        # Save results for inspection
        output_file = project_root / "test_results.json"
        with open(output_file, 'w') as f:
            json.dump(artifact, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Results saved to: {output_file}")
        
        print("\n🎉 REAL API TEST SUCCESSFUL!")
        print("\n📊 Final Summary:")
        print(f"   📄 Document: {doc_path.name}")
        print(f"   🔢 Pairs extracted: {len(pairs)}")
        print(f"   📝 Content length: {len(markdown_content):,} chars")
        print(f"   🤖 Model used: gpt-4o")
        print(f"   💰 API call: 1 request completed")
        
        return True
        
    except Exception as e:
        print(f"❌ OpenAI API test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_with_real_api())
    sys.exit(0 if success else 1)