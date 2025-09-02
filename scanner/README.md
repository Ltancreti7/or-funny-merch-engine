# Momentum Print Scanner

This script queries the [Polygon](https://polygon.io) API for top gaining U.S. equities and prints a ranked trade plan table.

## Setup

1. Create a virtual environment with Python 3.9+
2. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy the example environment file and provide your API key:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and replace `YOUR_KEY_HERE` with a valid `POLYGON_API_KEY`.

## Usage

Run the scanner:

```bash
python momentum_print_scan.py
```

The script prints a table containing ticker details, trade plan, and catalyst headlines.
