#!/usr/bin/env python3
"""
Setup helper for Narrative Evolution Agent.
Validates configuration and provides setup guidance.
"""

import os
import sys
from pathlib import Path

def check_python():
    """Check Python version."""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 9):
        print(f"❌ Python 3.9+ required (you have {version.major}.{version.minor})")
        return False
    print(f"✅ Python {version.major}.{version.minor}.{version.micro}")
    return True

def check_venv():
    """Check if virtual environment is active."""
    in_venv = hasattr(sys, 'real_prefix') or (
        hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
    )
    if not in_venv:
        print("❌ Virtual environment not active")
        print("   Run: source .venv/bin/activate")
        return False
    print("✅ Virtual environment active")
    return True

def check_dependencies():
    """Check if dependencies are installed."""
    required = [
        'streamlit',
        'elasticsearch',
        'google.generativeai',
        'pandas',
        'plotly',
        'dotenv'
    ]
    
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    
    if missing:
        print(f"❌ Missing dependencies: {', '.join(missing)}")
        print("   Run: pip install -r requirements.txt")
        return False
    
    print("✅ All dependencies installed")
    return True

def check_credentials():
    """Check if credentials are configured."""
    secrets_path = Path('.streamlit/secrets.toml')
    
    print("\n📋 Configuration Status:")
    
    # Check environment variables
    env_vars = {
        'ES_URL': os.getenv('ES_URL'),
        'ES_USERNAME': os.getenv('ES_USERNAME'),
        'ES_PASSWORD': os.getenv('ES_PASSWORD'),
        'GEMINI_KEY': os.getenv('GEMINI_KEY')
    }
    
    env_set = any(env_vars.values())
    if env_set:
        print("✅ Environment variables configured")
    
    # Check secrets file
    secrets_exist = secrets_path.exists()
    if secrets_exist:
        print("✅ .streamlit/secrets.toml exists")
    elif not env_set:
        print("❌ No credentials found")
        print("\n📝 Setup Instructions:\n")
        print("1. Create .streamlit/secrets.toml:")
        print("   mkdir -p .streamlit")
        print("   cat > .streamlit/secrets.toml << 'EOF'")
        print("   ES_URL = \"https://your-es-cluster.es.region.gcp.elastic.cloud:443\"")
        print("   ES_USERNAME = \"elastic\"")
        print("   ES_PASSWORD = \"your-password\"")
        print("   GEMINI_KEY = \"your-gemini-api-key\"")
        print("   EOF")
        print("\n2. Or set environment variables:")
        print("   export ES_URL=\"...\"")
        print("   export ES_USERNAME=\"elastic\"")
        print("   export ES_PASSWORD=\"...\"")
        print("   export GEMINI_KEY=\"...\"")
        print("\n3. Then run: streamlit run app.py")
        return False
    
    return True

def check_elasticsearch():
    """Check Elasticsearch connectivity."""
    try:
        from elasticsearch import Elasticsearch
        
        es_url = os.getenv('ES_URL')
        if not es_url:
            print("⏭️  Skipping ES check (no ES_URL configured)")
            return None
        
        es = Elasticsearch(
            es_url,
            basic_auth=('elastic', os.getenv('ES_PASSWORD', ''))
        )
        es.info()
        print("✅ Elasticsearch connection successful")
        return True
    except Exception as e:
        print(f"⚠️  Elasticsearch connection failed: {str(e)[:50]}...")
        print("   Make sure your Elasticsearch instance is running and credentials are correct")
        return False

def check_gemini():
    """Check Gemini API key."""
    try:
        import google.generativeai as genai
        
        api_key = os.getenv('GEMINI_KEY')
        if not api_key:
            print("⏭️  Skipping Gemini check (no GEMINI_KEY configured)")
            return None
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        # Don't actually call the API, just verify configuration
        print("✅ Gemini API key configured")
        return True
    except Exception as e:
        print(f"⚠️  Gemini API issue: {str(e)[:50]}...")
        return False

def main():
    """Run all checks."""
    print("\n🔮 Narrative Evolution Agent - Setup Check\n")
    print("=" * 50)
    
    checks = [
        ("Python Version", check_python),
        ("Virtual Environment", check_venv),
        ("Dependencies", check_dependencies),
        ("Credentials", check_credentials),
        ("Elasticsearch", check_elasticsearch),
        ("Gemini API", check_gemini),
    ]
    
    results = {}
    for name, check_func in checks:
        print(f"\n📌 {name}:")
        try:
            results[name] = check_func()
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            results[name] = False
    
    print("\n" + "=" * 50)
    print("\n📊 Summary:")
    
    passed = sum(1 for v in results.values() if v is True)
    total = len(results)
    
    print(f"Checks passed: {passed}/{total}")
    
    if passed == total:
        print("\n✅ All checks passed! Run: streamlit run app.py")
    elif results.get('Credentials') is False:
        print("\n⚠️  Configure credentials first (see instructions above)")
    else:
        print("\n⚠️  Please fix the issues above before running the app")

if __name__ == "__main__":
    main()
