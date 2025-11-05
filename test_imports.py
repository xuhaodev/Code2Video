#!/usr/bin/env python3
"""
Test script to validate that all essential dependencies are properly installed
and can be imported without errors.
"""

import sys
import importlib

# Track test results
passed = []
failed = []
skipped = []

def test_import(module_name, required=True, note=""):
    """Test if a module can be imported"""
    try:
        importlib.import_module(module_name)
        passed.append(f"✓ {module_name}" + (f" ({note})" if note else ""))
        return True
    except ImportError as e:
        if required:
            failed.append(f"✗ {module_name}: {e}" + (f" ({note})" if note else ""))
        else:
            skipped.append(f"⊘ {module_name}: {e}" + (f" - {note}" if note else ""))
        return False

print("=" * 70)
print("DEPENDENCY IMPORT TEST")
print("=" * 70)
print()

# Test Core API Dependencies
print("Testing Core API Dependencies...")
test_import("openai", note="LLM API client")
test_import("requests", note="HTTP requests")
test_import("numpy", note="Numerical operations")
test_import("scipy", note="Statistical functions")
test_import("scipy.stats", note="Statistics module")
test_import("psutil", note="System monitoring")
test_import("dotenv", note="Environment variables")
print()

# Test Data Processing
print("Testing Data Processing Libraries...")
test_import("json", note="Built-in")
test_import("re", note="Built-in")
test_import("pathlib", note="Built-in")
test_import("dataclasses", note="Built-in")
test_import("concurrent.futures", note="Built-in")
print()

# Test HTTP and Networking
print("Testing HTTP and Networking...")
test_import("urllib3", note="HTTP client")
test_import("certifi", note="SSL certificates")
test_import("charset_normalizer", note="Character encoding")
test_import("idna", note="Domain names")
test_import("httpcore", note="HTTP core")
test_import("httpx", note="Modern HTTP client")
test_import("anyio", note="Async I/O")
print()

# Test Data Validation
print("Testing Data Validation...")
test_import("pydantic", note="Data validation")
test_import("pydantic_core", note="Pydantic core")
test_import("annotated_types", note="Type annotations")
test_import("typing_extensions", note="Extended typing")
print()

# Test Parsing and Markup
print("Testing Parsing Libraries...")
test_import("bs4", note="BeautifulSoup4")
test_import("yaml", note="YAML parsing")
test_import("PIL", note="Pillow image library")
test_import("PIL.Image", note="Image processing")
print()

# Test CLI and Terminal
print("Testing CLI and Terminal...")
test_import("click", note="CLI framework")
test_import("rich", note="Terminal formatting")
test_import("tqdm", note="Progress bars")
print()

# Test Manim dependencies (may not be installed in minimal test)
print("Testing Manim Dependencies (may be skipped)...")
test_import("manim", required=False, note="Animation framework - needs system packages")
test_import("manimpango", required=False, note="Text rendering - needs pangocairo")
print()

# Test packages that should NOT be present
print("Verifying Removed Dependencies (should fail)...")
removed_deps = [
    ("torch", "PyTorch - deep learning"),
    ("transformers", "Hugging Face transformers"),
    ("accelerate", "Training acceleration"),
    ("qwen_vl_utils", "Qwen VL utilities"),
]

print("These should NOT import (confirming cleanup):")
for module, desc in removed_deps:
    try:
        importlib.import_module(module)
        failed.append(f"✗ {module} should NOT be installed but is present!")
    except ImportError:
        passed.append(f"✓ {module} correctly NOT installed ({desc})")
print()

# Test actual source code imports
print("Testing Source Code Imports...")
sys.path.insert(0, 'src')

try:
    # Test utils module
    from utils import (
        extract_json_from_markdown,
        extract_answer_from_response,
        get_optimal_workers,
        topic_to_safe_name
    )
    passed.append("✓ utils module imports (extract_json_from_markdown, get_optimal_workers, etc.)")
except ImportError as e:
    failed.append(f"✗ utils module: {e}")

try:
    # Test that gpt_request can be imported (may fail if openai client config is wrong, but import should work)
    import gpt_request
    passed.append("✓ gpt_request module imports")
except ImportError as e:
    failed.append(f"✗ gpt_request module: {e}")

try:
    # Test external_assets
    from external_assets import SmartSVGDownloader
    passed.append("✓ external_assets module imports (SmartSVGDownloader)")
except ImportError as e:
    failed.append(f"✗ external_assets module: {e}")

try:
    # Test scope_refine
    from scope_refine import ManimCodeErrorAnalyzer, ScopeRefineFixer, GridPositionExtractor
    passed.append("✓ scope_refine module imports (ManimCodeErrorAnalyzer, etc.)")
except ImportError as e:
    failed.append(f"✗ scope_refine module: {e}")

print()

# Summary
print("=" * 70)
print("TEST SUMMARY")
print("=" * 70)
print(f"PASSED: {len(passed)}")
print(f"FAILED: {len(failed)}")
print(f"SKIPPED: {len(skipped)}")
print()

if passed:
    print("PASSED TESTS:")
    for p in passed:
        print(f"  {p}")
    print()

if failed:
    print("FAILED TESTS:")
    for f in failed:
        print(f"  {f}")
    print()

if skipped:
    print("SKIPPED TESTS (Optional dependencies):")
    for s in skipped:
        print(f"  {s}")
    print()

# Exit code
if failed:
    print("❌ Some tests failed!")
    sys.exit(1)
else:
    print("✅ All required tests passed!")
    if skipped:
        print("ℹ️  Some optional dependencies were skipped (expected for Manim system packages)")
    sys.exit(0)
