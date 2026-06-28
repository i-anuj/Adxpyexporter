# ADX Exporter

An Azure Function that runs every 5 minutes, queries Azure Data Explorer (ADX/Kusto), and pushes the results as metrics to Datadog.

---

## Project structure

```
adx-exporter/
├── .github/
│   └── workflows/
│       ├── ci.yml          # Runs on push to kql/**: lint, scan, test, auto-PR
│       └── deploy.yml      # Runs on merge to main: deploy to Azure Functions
├── queries/
│   ├── __init__.py         # QUERIES list — all query definitions live here
│   ├── begin_pour_no_ticket.kql
│   ├── truckless_concrete_status.kql
│   ├── ticket_received_count.kql
│   ├── unknown_location_status.kql
│   ├── unknown_location_status_unknown_trucks.kql
│   └── geofence_request_count.kql
├── tests/
│   └── test_function_app.py
├── function_app.py          # Azure Function entry point
├── host.json                # Azure Functions runtime config
├── requirements.txt         # Python dependencies
├── .funcignore
└── .gitignore
```

---

## Pre-commit hooks (run on your machine before every commit)

Install once:
```bash
pip install pre-commit
pre-commit install
```

After that, every `git commit` automatically runs:

| Hook | What it checks | Auto-fixes? |
|---|---|---|
| `trailing-whitespace` | Trailing spaces on any line | Yes |
| `end-of-file-fixer` | Every file ends with a newline | Yes |
| `check-yaml` | Your `.yml` workflow files are valid | No — you fix |
| `check-ast` | Python syntax is valid | No — you fix |
| `debug-statements` | No `print()` or `breakpoint()` left in code | No — you fix |
| `check-merge-conflict` | No `<<<<<<<` conflict markers left in files | No — you fix |
| `check-added-large-files` | No files over 500kb committed | No — you fix |
| `gitleaks` | No secrets, API keys or tokens in code | No — you fix |
| `ruff` | Lint issues (unused imports, bad style) | Auto-fixes safe ones |
| `ruff-format` | Code formatting (spacing, quotes, line length) | Yes |

If a hook **auto-fixes** your file, just `git add` the fixed file and `git commit` again.
If a hook **blocks** your commit, read the error, fix it manually, then commit again.

---

## How to add a new query

**Step 1** — Make sure you are on latest main:
```bash
git checkout main
git pull origin main
```

**Step 2** — Create a new branch for your query:
```bash
git checkout -b kql/your_query_name
```

**Step 3** — Create a `.kql` file in `queries/`:
```
queries/your_query_name.kql
```

**Step 4** — Add an entry to `QUERIES` in `queries/__init__.py`:
```python
{
    "name": "your_query_name",
    "metric_name": "your_query_name",
    "metric_value_col": "YourNumericColumn",
    "tags_fn": lambda row: [
        safe_tag("account", row.get("Account", "unknown")),
        "env:test-verifi-python",
    ],
    "kql": _load("your_query_name.kql"),
},
```

**Step 5** — Commit both files together and push:
```bash
git add queries/your_query_name.kql queries/__init__.py
git commit -m "add query: your_query_name"
git push -u origin kql/your_query_name
```

CI kicks off automatically. Once all checks pass, a PR is auto-created. Get it approved and merged → deploy fires.

> Always branch off `main`, not off another `kql/` branch, so your PR diff is clean.
> Always commit both files together — CI will fail if `__init__.py` is not updated alongside the `.kql` file.

**Step 6** — Clean up after merge:
```bash
git branch -d kql/your_query_name
```

---

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the function locally (requires Azure Functions Core Tools)
func start
```

Set environment variables in `local.settings.json` (never commit this file):
```json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "ADX_CLUSTER_URL": "https://yourcluster.westeurope.kusto.windows.net",
    "DD_API_KEY": "your-datadog-api-key"
  }
}
```

---

## Metrics sent to Datadog

| Metric | Type | Description |
|---|---|---|
| `adx.prd.<metric_name>` | gauge | Value from each query row |
| `adx.prd.function_heartbeat` | gauge | `1.0` = all ok, `0.0` = one or more queries failed |
| `adx.prd.function_duration_seconds` | gauge | Total function execution time |

All metrics are tagged with `env:test-verifi-python` and `source:adx-exporter`.
