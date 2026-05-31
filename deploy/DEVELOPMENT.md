# 💻 Development Guide

This guide covers setting up the development environment and contributing to the Narrative Evolution Agent.

## Local Development Setup

### 1. Clone Repository

```bash
git clone https://github.com/yourusername/KairoAgent.git
cd KairoAgent
```

### 2. Create Virtual Environment

```bash
# macOS/Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install Development Dependencies

```bash
pip install -r requirements.txt
pip install pytest black flake8 mypy ipython
```

### 4. Set Up Pre-commit Hooks

```bash
pip install pre-commit
pre-commit install
```

### 5. Configure IDE

#### VS Code

Create `.vscode/settings.json`:

```json
{
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black",
  "[python]": {
    "editor.defaultFormatter": "ms-python.python",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.organizeImports": true
    }
  }
}
```

## Project Structure

```
KairoAgent/
├── app.py                      # Main Streamlit app
├── narrative_engine.py         # Core narrative detection
├── narrative_tracker.py        # Narrative persistence
├── elasticsearch_manager.py    # ES operations
├── utils.py                    # Helper functions
├── config.py                   # Configuration
├── example.py                  # Example/test script
├── ingest.py                   # Data ingestion
├── requirements.txt            # Python dependencies
├── Dockerfile                  # Docker build
├── docker-compose.yml          # Docker compose
├── README.md                   # Documentation
├── ARCHITECTURE.md             # System design
├── DEPLOYMENT.md               # Deployment guide
├── QUICKSTART.md               # Quick start guide
├── data/
│   └── transactions.json       # Sample whale data
├── .streamlit/
│   ├── config.toml            # Streamlit config
│   └── secrets.toml           # Secrets (git ignored)
├── .env.example               # Environment template
├── .gitignore                 # Git ignore rules
└── tests/
    ├── test_narrative_engine.py
    ├── test_elasticsearch_manager.py
    └── test_narrative_tracker.py
```

## Development Workflow

### 1. Code Style

Use Black for formatting:

```bash
black app.py narrative_engine.py --line-length 100
```

Check with Flake8:

```bash
flake8 app.py --max-line-length=100
```

Type checking:

```bash
mypy app.py --ignore-missing-imports
```

### 2. Testing

Create tests in `tests/` directory:

```bash
# Run tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=. --cov-report=html
```

### 3. Logging

```python
import logging

logger = logging.getLogger(__name__)

logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
```

Configure logging in app:

```python
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

## Adding Features

### Adding a New Narrative Detection Method

1. Update `narrative_engine.py`:

```python
def detect_narratives_advanced(self, whale_activity, **kwargs):
    """New detection method with additional context."""
    # Implementation
    pass
```

2. Add tests in `tests/test_narrative_engine.py`:

```python
def test_detect_narratives_advanced():
    engine = NarrativeEngine(api_key)
    result = engine.detect_narratives_advanced(test_data)
    assert len(result) > 0
    assert 'name' in result[0]
```

3. Update UI in `app.py`:

```python
if st.button("🔍 Advanced Detection"):
    narratives = engine.detect_narratives_advanced(whale_activity)
```

### Adding a New Elasticsearch Query

1. Add method to `elasticsearch_manager.py`:

```python
def get_whale_clusters(self, min_cluster_size=3):
    """Get whale wallets that trade together."""
    response = self.es.search(
        index=self.whale_transactions_index,
        body={
            "aggs": {
                "wallet_pairs": {
                    "terms": {"field": "wallet"}
                }
            }
        }
    )
    # Process and return
```

2. Add test in `tests/test_elasticsearch_manager.py`:

```python
def test_get_whale_clusters():
    es = ElasticsearchManager(url, user, pwd)
    clusters = es.get_whale_clusters()
    assert isinstance(clusters, list)
```

3. Use in `narrative_engine.py` if needed

## Debugging

### Debug Mode

Enable debug logging:

```bash
export DEBUG=true
export LOG_LEVEL=DEBUG
streamlit run app.py
```

### Interactive Development

Use IPython for testing code:

```bash
ipython

In [1]: from narrative_engine import NarrativeEngine
In [2]: engine = NarrativeEngine(api_key)
In [3]: engine.detect_narratives(test_data)
```

### Streamlit Debugging

Add debug output to app:

```python
with st.expander("🐛 Debug Info"):
    st.json(whale_activity)
    st.write(f"Transactions count: {len(transactions)}")
```

## Performance Optimization

### Profiling

Profile Streamlit app:

```bash
streamlit run app.py --logger.level=debug
```

Profile specific functions:

```python
import cProfile
import pstats

pr = cProfile.Profile()
pr.enable()

# Code to profile
detect_narratives(data)

pr.disable()
ps = pstats.Stats(pr)
ps.sort_stats('cumulative')
ps.print_stats(10)
```

### Caching

Use Streamlit caching:

```python
@st.cache_data
def get_transactions():
    return es_manager.get_recent_transactions()

@st.cache_resource
def init_services():
    return ElasticsearchManager(url, user, pwd)
```

## Documentation

### Adding Docstrings

Use Google-style docstrings:

```python
def detect_narratives(
    self,
    whale_activity: Dict[str, Any],
    historical_narratives: List[Dict] = None
) -> List[Dict[str, Any]]:
    """
    Detect emerging narratives from whale activity using Gemini.

    Args:
        whale_activity: Dictionary of grouped whale transactions
        historical_narratives: Previous narratives for momentum analysis

    Returns:
        List of detected narratives with metadata

    Raises:
        ValueError: If whale_activity is empty
        APIError: If Gemini API call fails

    Example:
        >>> engine = NarrativeEngine(api_key)
        >>> narratives = engine.detect_narratives(activity)
        >>> len(narratives)
        3
    """
```

### Adding Comments

```python
# Bad: Obvious what the code does
x = x + 1  # Increment x

# Good: Explains WHY
# Account for 0-indexed arrays in ES response
x = x + 1
```

## Commits & Pull Requests

### Commit Message Format

```
[TYPE] Brief description

Longer explanation of changes made

Fixes #123
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `refactor`: Code refactoring
- `perf`: Performance improvement
- `test`: Adding tests
- `chore`: Maintenance

### Example

```
[feat] Add narrative confidence volatility tracking

- Calculate standard deviation of confidence over time
- Add volatility metric to narrative metadata
- Display volatility in dashboard

Fixes #45
```

## Testing Checklist

Before submitting PR:

- [ ] All tests pass: `pytest tests/`
- [ ] Code formatted: `black .`
- [ ] No linting issues: `flake8 .`
- [ ] Type checking passes: `mypy .`
- [ ] New tests added for new code
- [ ] Documentation updated
- [ ] No secrets in commits
- [ ] Feature tested manually

## CI/CD

### GitHub Actions

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest tests/
      - run: black --check .
      - run: flake8 .
```

## Common Issues

### "No module named 'narrative_engine'"

Ensure you're in the right directory:

```bash
cd KairoAgent
python -c "from narrative_engine import NarrativeEngine"
```

### Streamlit caching issues

Clear cache:

```bash
streamlit cache clear
```

### Elasticsearch connection timeout

Check if ES is running:

```bash
curl http://localhost:9200
```

Or use docker-compose:

```bash
docker-compose up -d elasticsearch
```

## Resources

- [Streamlit Docs](https://docs.streamlit.io)
- [Elasticsearch Python Client](https://www.elastic.co/guide/en/elasticsearch/client/python-api/current/)
- [Google Gemini API](https://ai.google.dev/)
- [Python Style Guide (PEP 8)](https://www.python.org/dev/peps/pep-0008/)

## Getting Help

- Check existing [GitHub Issues](https://github.com/yourusername/KairoAgent/issues)
- Read [Architecture](ARCHITECTURE.md)
- Review [README](README.md)
- Ask in discussions

## Releases

Versioning follows [Semantic Versioning](https://semver.org/):

- MAJOR: Breaking changes
- MINOR: New features
- PATCH: Bug fixes

To release:

```bash
git tag -a v1.0.0 -m "Release version 1.0.0"
git push origin v1.0.0
```
