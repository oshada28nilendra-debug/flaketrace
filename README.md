# FlakeTrace

An offline JUnit report comparison tool for developers investigating inconsistent test outcomes. Groups repeated runs by explicit commit identifiers, flags same-commit mixed pass/fail candidates, and exports reviewable HTML and JSON with linked evidence. **One failure does not prove flakiness.**

## Run

Python 3.12+, standard library only. No installation, model downloads, external services or paid APIs.

```sh
python flaketrace.py examples/runs.json --out output
python -m unittest discover -s tests -v
```

Open `output/index.html`; click run links to inspect `evidence.html`. `report.json` contains counts, observed rates, outcomes, run identifiers, source filenames, source SHA-256 hashes and extracted failure/error details. Output directory must be new; reports are never silently overwritten. Included `evaluation/` reports were generated from the synthetic examples.

## Input contract

Manifest is a JSON array, one XML file per run:

```json
[{"commit":"full-commit-sha","run":"unique-ci-run-id","file":"run1.xml"}]
```

All fields are nonempty strings. Run IDs must be globally unique. Commit identifiers are explicit, opaque values: use full SHAs consistently; the tool does not validate them against GitHub. Files must resolve within the manifest directory, including symlink resolution. Missing files or malformed reports stop the build rather than being treated as missing tests. The same XML file can be referenced by multiple explicit run IDs, but that does not establish independent execution: the hashes expose identical evidence for review.

Supported JUnit subset: UTF-8 `testsuite` or `testsuites` root, nested suites, optional XML namespaces, `testcase` with required `name` and optional `classname`. Identity is the pair `(classname, name)`, **not** suite name. Duplicate identities within a run are rejected (including parameterized tests that fail to encode parameters in names). Aggregate suite counters are ignored in favor of testcase outcomes. A testcase with `failure` or `error` is fail; `skipped` is skipped; otherwise pass. Conflicting skip/fail outcomes are rejected. Vendor-specific retry elements and disabled attributes are not interpreted; normalize these reports before use. DTD/entity declarations, NUL bytes and XML files over 5 MB are rejected. This is not a hardened multi-tenant upload service; use trusted small local reports.

## Semantics

- Compare only runs whose commit strings match exactly.
- Candidate = at least one pass AND one fail within that commit. This means mixed observed outcomes; it does not require strict pass/fail/pass chronological alternation. Manifest order is display order, not a timestamp ordering claim.
- Observed failure rate = fail / (pass + fail). Skipped and missing are excluded. Rate is null/N/A when no executed outcomes exist.
- Missing = a test observed in at least one run for the commit but absent in another supplied run. A test absent from every run cannot be discovered without an external inventory.
- Empty valid suites are accepted; missing counts are relative to the union of observed tests in the commit. Missing tests may reflect filters or incomplete suites rather than defects.
- Errors count as failures for the rate, but original failure/error details remain in evidence.

Same commit does not imply same environment, dependencies, order, seed, configuration or infrastructure. A candidate requires investigation; its rate is descriptive of supplied runs, not an estimated future failure probability. No automatic quarantine or issue creation.

## Architecture

`parse_xml` validates and extracts test identities/outcomes; `load_runs` resolves the manifest and hashes evidence; `analyze` groups by commit and emits per-run evidence for each test; `render` produces escaped static HTML with generated internal anchors. No JavaScript or network is needed to view results. Evidence pages contain extracted details and source hashes, not a copy of the entire original XML. Keep originals if audit reproduction is needed. Failure text may contain private paths or secrets; review reports before sharing.

For each commit, output size is O(number of runs × union of observed tests), with all data in memory. Use small collections; there is no streaming, database, live CI integration or cross-environment statistical model.

## Measured fixture and tests

The four hand-authored XML runs are **synthetic fixtures**, not production logs. They produce five commit/test groups and exactly one candidate: `Demo/mixed` on `synthetic-a`, 2 passes/1 fail, observed failure rate 1/3. Other groups demonstrate stable failure, skipped-only outcomes, missing tests, and a single failure on another commit. The labelled candidate assertion passes; no real-world accuracy or adoption claim is made.

Ten unit/integration tests cover expected counts, commit isolation, skipped/missing semantics, nested namespaces, malformed XML, duplicate tests/runs, unsafe paths, XML declaration restrictions, HTML escaping, evidence anchors and CLI overwrite refusal. Browser visual layout has not been inspected. The included GitHub Actions workflow runs the tests and sample export on pushes and pull requests. See the PR checks for current status.

## Interview explanation

“I made test identity and same-commit grouping explicit, separated missing/skipped outcomes from executed tests, and attached evidence to every rate. I treated mixed outcomes as investigation candidates rather than claiming a single failure proves flakiness.”
