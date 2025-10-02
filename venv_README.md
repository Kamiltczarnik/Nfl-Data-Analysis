# Virtual Environment Setup

This project uses a Python virtual environment to manage dependencies.

## Setup Instructions

1. **Activate the virtual environment:**
   ```bash
   source venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Deactivate when done:**
   ```bash
   deactivate
   ```

## Dependencies Installed

- **nflreadpy**: NFL data access library
- **pandas**: Data manipulation
- **pyarrow**: Parquet file support
- **numpy**: Numerical computing
- **requests**: HTTP requests
- **tenacity**: Retry logic
- **pyyaml**: YAML configuration
- **click**: CLI framework
- **pydantic**: Data validation
- **jsonschema**: JSON schema validation
- **diskcache**: Local caching

## Verification

To verify the setup is working:

```bash
source venv/bin/activate
python3 -c "import nflreadpy; print('nflreadpy version:', nflreadpy.__version__)"
```

This should print the nflreadpy version without errors.

