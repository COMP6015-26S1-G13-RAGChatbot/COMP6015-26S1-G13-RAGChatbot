# Blind Audit Set v2

This file contains 50 frozen audit cases: 25 `no_issue` cases and 25 positive
cases. It is separate from `holdout_audit_set.json`, which has already been used
for iterative development.

Before the first scored run:

1. Have a domain reviewer verify the labels and authoritative wording.
2. Commit or record the SHA-256 hash of `blind_audit_set_v2.json`.
3. Run the benchmark once with `--summary`.
4. Do not tune rules or thresholds against this file. Move any inspected failure
   into a development regression set and replace it with a newly reviewed case.

Command:

```bash
./venv/bin/python -m backend.scripts.run_evaluation \
  --dataset tests/blind_audit_set_v2.json --summary
```
