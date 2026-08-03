# Local-cohort diagnostics

These files preserve invalid infrastructure attempts from the issue #32 local
cohort. They are not included by `validate-results` or any reported score.

- `invalid-*-ctx4096.jsonl`: Ollama rejected all 56 specialized calls before
  inference because the approximately 11,333-token prompts exceeded its default
  4,096-token context.
- `invalid-*-timeout-partial.jsonl`: a three-record warm-up after increasing the
  context to 16,384. Its first record exceeded the harness's 300-second client
  timeout while the server populated its prompt cache; the run was stopped and
  restarted from zero.
- `retry-common-22-case.jsonl` and `retry-common-22-result.jsonl`: the frozen
  case and targeted replacement for the sole timeout in the otherwise complete
  scored run. The retry selected `turn_options` and executed successfully but
  omitted `Prone`, so it remains a substantive first-call failure. The canonical
  scored record retains the full frozen-corpus digest.

No invalid attempt changed the model, prompt content, cases, scorer, temperature,
output cap, or decision thresholds.
