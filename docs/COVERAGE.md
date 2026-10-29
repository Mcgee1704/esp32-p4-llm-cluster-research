# Research log and coverage

The source research checkpoint is `a0bf3bd9f9ceb5546f06703a1e4c17464db955d9`. Original private Git history
and personal commit metadata are not published. Original report filenames below
are identifiers of local records, not additional public files. The English reports
consolidate their scientific content; this is not a word-for-word translation.

| Original record identifier | English coverage |
| --- | --- |
| `docs/JOURNAL.md` | [COVERAGE.md](COVERAGE.md) |
| `docs/automatische-aufnahme.md` | [PRIOR_WORK_AND_PLANS.md](PRIOR_WORK_AND_PLANS.md) |
| `docs/board1-inbetriebnahme.md` | [HARDWARE.md](HARDWARE.md) |
| `docs/board2-inbetriebnahme.md` | [HARDWARE.md](HARDWARE.md) |
| `docs/firmware-inbetriebnahme.md` | [HARDWARE.md](HARDWARE.md) |
| `docs/firmware-pruefstand.md` | [RESEARCH_REPORT.md](RESEARCH_REPORT.md) |
| `docs/github-einsatzideen.md` | [PRIOR_WORK_AND_PLANS.md](PRIOR_WORK_AND_PLANS.md) |
| `docs/poe-usb-pruefung.md` | [HARDWARE.md](HARDWARE.md) |
| `docs/research/dispatcher-2026-10-29.md` | [RESEARCH_REPORT.md](RESEARCH_REPORT.md) |
| `docs/research/firmware-umsetzung.md` | [RESEARCH_REPORT.md](RESEARCH_REPORT.md) |
| `docs/research/forschungsplan.md` | [PRIOR_WORK_AND_PLANS.md](PRIOR_WORK_AND_PLANS.md) |
| `docs/research/lan-optimierung-2026-10-29.md` | [RESEARCH_REPORT.md](RESEARCH_REPORT.md) |
| `docs/research/parallelbetrieb-2026-10-29.md` | [RESEARCH_REPORT.md](RESEARCH_REPORT.md) |
| `docs/research/prospektive-pruefung-2026-10-29.md` | [SIMULATION.md](SIMULATION.md) |
| `docs/research/rechenkern-v2-2026-10-29.md` | [RESEARCH_REPORT.md](RESEARCH_REPORT.md) |
| `docs/research/rechenkern-v3-2026-10-29.md` | [RESEARCH_REPORT.md](RESEARCH_REPORT.md) |
| `docs/research/simulation-datenbasis.md` | [SIMULATION.md](SIMULATION.md) |
| `docs/research/simulation-v1-2026-10-29.md` | [SIMULATION.md](SIMULATION.md) |
| `docs/research/textmodell-naechste-stufe.md` | [MODELS_AND_QUALITY.md](MODELS_AND_QUALITY.md) |
| `docs/research/textmodell-sft-2026-10-29.md` | [MODELS_AND_QUALITY.md](MODELS_AND_QUALITY.md) |
| `docs/research/textqualitaet-v1-2026-10-29.md` | [MODELS_AND_QUALITY.md](MODELS_AND_QUALITY.md) |
| `docs/research/upstream-befunde.md` | [PRIOR_WORK_AND_PLANS.md](PRIOR_WORK_AND_PLANS.md) |
| `docs/research/zweier-test-2026-10-29.md` | [RESEARCH_REPORT.md](RESEARCH_REPORT.md) |

## Scientific milestones

- Initial research and bring-up: portable numerical reference, two revision-1.3
  boards, complete original model on both, working sequential split, negative scaling.
- Transport: instrument first, NODELAY, then reuse; preserve correctness and error checks.
- Independent parallel requests, then master-owned queue/dispatcher with recovery checks.
- Kernel V2: pause scheduling, then both CPU cores; controlled direct/cluster comparisons.
- Kernel V3: internal vectors and four-row reuse; same-firmware controls on both nodes.
- Real mixed-workload calibration/validation records, frozen scenario V1, prospective check.
- Static capacity/architecture audit; different compatible SFT checkpoint of the same size.
- Ten new English tasks, complete token checks and frozen masked qualitative review.

Future electrical qualification, factory onboarding, SD persistence, a physical
third lane, larger-model capacity, broader quality evaluation and fault-injection
remain separate work. Test claims describe their recorded scope, not blanket
release approval. Numerical raw data is retained even for negative/unfavourable results.
