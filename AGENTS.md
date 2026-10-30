# Repository instructions

These instructions apply throughout `esp32-p4-llm-cluster-research`. Follow the
user's task scope and applicable approval rules. This file does not authorize
new experiments, device changes, publications or background jobs.

## Language and starting points

- Write public documentation, Wiki content and new agent instructions in English.
- Start with [README.md](README.md) and the [research index](docs/RESEARCH_INDEX.md).
  Use [methods](docs/METHODS.md), [hardware](docs/HARDWARE.md) and the
  [reproduction guide](docs/REPRODUCIBILITY.md) for the relevant evidence limits.
- Keep sources and evidence dates traceable. Summarize established findings
  without promoting proposed work or unresolved questions to completed results.

## Evidence and board boundaries

- Distinguish physical measurements, host/native reference checks, recorded-data
  analysis, simulations, source reviews, visual observations and plans.
- State the model, firmware, workload, conditions and timing boundary for new
  performance claims. Compare compatible workloads; do not combine unrelated
  speed ratios or count reused observations as fresh evidence.
- Runtime/reference agreement does not establish factual answer quality.
  Simulated node counts do not establish physical hardware results. Visible
  markings and fitted parts do not establish electrical ratings or measured
  behavior. Keep PCB revision distinct from silicon revision.
- Apply Board 1 visual findings only to Board 1. Board 2 visual identification
  and photo documentation remain deferred until the user requests that work.
  Preserve the scope of existing two-board research separately.
- Keep unresolved component identities, supply/current limits and unperformed
  measurements explicit. Use the maintained [Board 1 record](https://github.com/Mcgee1704/waveshare-esp32-p4-wifi6-poe-eth/blob/4912e345487cf12f354f4469e0417a9324b9271d/docs/08-board1-visual-record.md)
  as the dated visual source; record later evidence as an update.

## Preserve original evidence

- Preserve raw streams, frozen protocols, original references, ratings, provenance
  and historical checksums. Do not alter them or relax integrity guards to make
  a new result pass. Put new experiments and derived analyses in separate records.
- Keep failures, uncertain judgments, output caps, reused data and study
  limitations visible. Correcting a report must leave a traceable explanation.
- Keep private keys, provisioned binaries, model weights, original private photos,
  device identifiers, private Drive links and local session records out of public
  changes. Keep generated/local state under ignored `.local/`.
- Inspect the working tree before editing and preserve other ongoing work.

## Offline verification

From the repository root, use the existing device-free archive checker:

```text
python tools/verify_public_snapshot.py .
```

Use an installed Python 3.12 or later. The checker uses the standard library and
saved records; it needs no model weights, credentials or devices. It verifies
archive integrity and recorded calculations, not fresh inference or independent
semantic quality. Also check Markdown links and the final diff for documentation
changes. Run relevant existing tests for code changes and report actual outcomes.
Do not install dependencies, contact boards, download models or run deployment
scripts merely to validate documentation.

## Publication and device actions

- Keep project/device data local by default. Local Git commits are allowed.
- Before an external transfer, stop other work and send a separate warning headed
  `STOPP: ONLINE-UEBERTRAGUNG GEPLANT`. Identify the exact destination, repository,
  branch or destination path, and the files/data to be transferred.
- Proceed only after a separate, exact user confirmation in this format:

  ```text
  JA, ONLINE-UPLOAD ZU <EXACT TARGET> FREIGEGEBEN
  ```

  A general yes or continue is insufficient. If destination, branch, scope or
  transfer type changes, obtain a new confirmation. Approval for a Wiki upload
  does not authorize changes to the main repository or other destinations.
- Flashing, model replacement, peer/wiring changes, power tests and other device
  operations require a task that explicitly covers the affected devices and
  actions. A documentation request does not authorize them.
- Do not start cloud-agent tasks, schedules, monitoring or other background
  automation without an explicit user request for that work.
