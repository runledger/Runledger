# Regression templates

Each folder contains only the files that differ from `main`.

Example workflow:

```bash
git checkout -b regression-schema
cp -r regressions/regression-schema/* .
git add -A
git commit -m "Regression: schema required field"
```

Repeat for `regression-tools` and `regression-budget`.
