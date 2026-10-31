# SignalRoot AI — 100-case synthetic evaluation (research preview)

This package **does not constitute an independent benchmark**. It is a reproducible set of **100 hand-specified / programmatically expanded synthetic cases**. Template variants are correlated and labels were chosen by the developer. It is suitable for regression and adversarial smoke testing, not for publication claims about production accuracy.

## Scenario distribution

- 25 deployment regressions
- 25 database degradation scenarios
- 25 upstream dependency degradation scenarios
- 25 insufficient/conflicting-evidence scenarios

Labels for the 50 database and dependency cases are grouped as `Dependency or database degradation` because the existing v0.9.0 engine uses that coarse taxonomy. `label_rationale`, `scenario_family`, and `limitations` are provided for each case. Labels describe the **synthetically stipulated scenario**, not a verified root cause from realistic noisy telemetry.

## Windows commands (from project root)

```powershell
python -m pytest -q
python research\run.py --engine baseline
```

For live AI comparison, enter your API key privately in your existing project terminal:

```powershell
$secret = Read-Host "OpenAI API key" -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new("", $secret).Password
Remove-Variable secret
$env:SIGNALROOT_MODEL="gpt-4o-mini"
python research\run.py --engine ai --max-calls 5 --confirm-paid
```

If the five-case run succeeds and costs are acceptable, intentionally increase `--max-calls` (up to 100). **These are billable requests** and the script does not enforce a dollar-denominated budget. The existing OpenAI project budget controls and a small initial run are recommended. The script does not expose prompts or API keys in saved reports, but it stores model explanations, which should contain only synthetic data. Reports are local and excluded from Git.

**Warning:** Cases are sorted by category, so `--max-calls 5` evaluates only deployment cases; use the all-category pilot command below for diverse samples:

```powershell
python research\pilot.py --engine ai --confirm-paid
```

The pilot evaluates one case from each of four strata (4 requests), with an explicit opt-in. The same four cases can be evaluated with `--engine baseline` free of charge. The full evaluation covers 100 calls. No automatic paid AI calls occur from tests or baseline commands.

## Evaluation integrity

- The dataset is SHA-256-fingerprinted in `manifest.json`, and evaluation checks it before running.
- Label distributions, confusion matrix, coverage, abstention, citation ID validity, and provider errors are recorded.
- Citation ID validity checks **existence only**, not whether the evidence supports the claim.
- The existing model prompt includes the baseline guess for comparison. This can bias model behavior and should be removed or controlled for in a publication-quality evaluation.
- Do not tune rules against these 100 cases and then report their accuracy as held-out evaluation.
- Next: obtain consented, sanitized public incident reports; independent reviewers; blinded labels; a truly held-out split; replicated LLM runs; token/cost accounting; semantic evidence auditing.
