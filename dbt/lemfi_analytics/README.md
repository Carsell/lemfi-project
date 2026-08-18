# LemFi analytics dbt project

The models read the cleaned CSV files created by `python run.py` and build three small marts
in DuckDB. From the repository root:

```bash
pip install -r requirements-dev.txt
python run.py
cd dbt/lemfi_analytics
dbt build --profiles-dir .
```

`dbt build` creates the staging views and marts, then runs the generic and singular tests.
The committed local profile means no external database or `~/.dbt` configuration is needed.
