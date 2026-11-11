# Contributing to FoxMCP

Bug reports, focused fixes, features, documentation and tests are welcome.

## Code of Conduct

Be respectful and inclusive, welcome newcomers, and keep feedback constructive.
Respect different viewpoints and experiences.

## How to Contribute

### Reporting Issues

Search existing issues first. For a new report, use a descriptive title and
include reproduction steps, expected and actual behavior, your OS, Firefox and
Python versions, and relevant logs. Report security vulnerabilities through the
process in [SECURITY.md](SECURITY.md).

### Submitting Changes

1. Fork the repository and create a feature branch from `master`.
2. Keep the change focused on one feature or fix and follow the
   [architecture requirements](#architecture-review).
3. Add tests for new functionality and bug fixes, covering success and error
   cases. Update affected product references in `docs/` and add notable changes
   to the Unreleased section of `CHANGELOG.md`.
4. Run the relevant checks described in [Testing](#testing).
5. Commit with the [message format below](#commit-messages), push to your fork,
   and open a PR.

### Pull Request Guidelines

Explain the problem, resulting behavior and validation performed, including any
checks you could not run. State the architecture-review result and disclose any
violations or proposed design changes as described below. All required CI checks
must pass before merge.

### Design Principles

Prefer content scripts for features they can implement while meeting the
requirements and respecting browser permissions, execution contexts and script
consent. First consider the existing script execution and predefined-script
mechanisms for page-level behavior. When privileged extension APIs, background
state or server work are necessary, explain the content-script limitation in
the proposal or PR and keep those responsibilities in their existing components.

Prefer generic, reusable solutions. Solve the underlying class of problems with
small, composable capabilities that work across sites and workflows. Keep
site-specific selectors, domain rules and workflow details in scripts or caller
configuration. Reuse or extend existing mechanisms before adding specialized
MCP tools, protocol actions or parallel implementations. Keep abstractions
proportionate to the actual requirements.

### Architecture Review

Every change must follow the existing design described in
[architecture.md](docs/architecture.md), especially its
[system diagram and source-symbol map](docs/architecture.md#system-overview).
Compare the diff with the diagram and [component responsibilities](docs/files.md),
including ownership, dependency directions, process boundaries, startup roles
and data flow. Passing tests alone does not establish architecture alignment.

State the architecture-review result explicitly, including when no mismatch is
found. Explicitly describe any architecture violation or proposed design change
in the PR description and/or the relevant commit-message body. For changes
submitted without a PR, include this explanation in the commit-message body.
For each violation or proposed architecture change, identify:

- The affected diagram component, connection or process boundary.
- What the current architecture requires and what the PR does instead, with
  file/line references.
- The impact and the correction needed, or the proposed design change and its
  rationale.

Call out intentional architecture changes as changes to the agreed design.
Resolve them through the project's design discussion and update the diagram,
source-symbol map and affected references before merge. Do not silently change
the diagram to make a violation appear compliant.

## Development Setup

Install Python 3.10 or later and Firefox Developer Edition. The full test suite
installs an unsigned extension, which Firefox Release and Beta refuse to load.
Set `FIREFOX_PATH` to your Developer Edition executable, replacing the example
path below.

```bash
git clone https://github.com/your-username/foxmcp.git
cd foxmcp
git checkout -b feature/your-feature-name
make dev
FIREFOX_PATH=/path/to/firefox-developer-edition/firefox make test
```

See the [development guide](docs/development.md) for prerequisites, build
commands and loading the extension, and the
[CI setup](docs/development.md#continuous-integration) for Firefox details.
`make build` copies the extension into `dist/extension/`; `make package` creates
the installable XPI and server ZIP. The full test command builds packages first.

## Coding Standards

Follow the surrounding code style. Keep functions focused, use descriptive names
and explain complex logic.

- **Python:** Follow PEP 8, use type hints for function parameters and return
  values, and document public functions and classes. See the
  [formatting and lint commands](docs/development.md#code-style) and existing
  [browser-profile implementation](server/browser_profile.py).
- **JavaScript:** Use modern JavaScript and async/await, with two-space
  indentation. See the existing [settings controller](extension/settings.js).
- **Documentation:** Use clear language and working examples. Update product
  references when behavior changes; link to existing references rather than
  repeating them.

### Tool Descriptions

Keep model-visible tool descriptions concise, preferably one brief paragraph
covering the purpose and essential usage constraints. Put parameter details in
argument descriptions and longer explanations or examples in the API reference.
Avoid repeating the signature, parameter list or documentation in the summary.

Review the actual MCP `tools/list` output, including automatically appended
guidance, when adding or expanding a description. Remove repetition while
preserving information needed to call the tool correctly.

### Testing

Use descriptive test names and test the behavior affected by your change.
Use `example.org` for test URLs. Follow the existing fixtures and Firefox setup
in the [test guide](tests/README.md); its
[fixture example](tests/README.md#using-server_with_extension) and
[tab-move tests](tests/integration/test_tab_move_end_to_end.py) show real usage.

```bash
make test-unit  # unit checks without Firefox
FIREFOX_PATH=/path/to/firefox-developer-edition/firefox make test
```

Run the full suite before submitting code changes. It takes about fifteen to
twenty minutes. CI also checks that every required test module ran successfully
and no tests were skipped; see the
[test report requirements](docs/development.md#continuous-integration).

Coverage above 80% is a project target. See the
[coverage instructions](tests/README.md#coverage) to measure the current checkout
and add meaningful coverage for your change.

## Protocol Compatibility

Increase the checked protocol ID when modifying or removing an existing API
between the extension and MCP server. Update the protocol documentation and
compatibility tests with the change.

Increase at most once per release, using the previous released tag as the
baseline. Retain its ID when existing contracts remain compatible; otherwise
use exactly that ID plus one. All incompatible unreleased changes share this
single increment. Do not increment again for each PR or intermediate candidate.
The complete rule is in
[Protocol ID compatibility policy](docs/protocol.md#protocol-id-compatibility-policy).

## Commit Messages

Use a descriptive subject of 50 characters or less. Separate the body with a
blank line and explain the problem and change when needed. Every line must be
at most 80 characters; check line lengths before committing. These limits also
apply to merge and squash messages.

Explicitly describe architecture violations or design changes in the PR
description and/or commit-message body, following
[Architecture Review](#architecture-review). Changes without a PR must include
that explanation in the commit-message body.

## Release Process

Maintainers own release version selection, version bumps, tagging and publishing.
Contributors should record notable changes under Unreleased in `CHANGELOG.md`
and identify compatibility impacts in the PR; leave release version bumps to
maintainers.

Before tagging or publishing, maintainers must review changes since the previous
released tag and record whether the protocol ID must increase, with a rationale
for retaining it. Follow the [release checklist](docs/development.md#release-process).

## Getting Help

Start with the [development guide](docs/development.md) and
[test guide](tests/README.md), then search existing issues and PR discussions.
If your question remains unanswered, open an issue with the relevant context.

## License

Contributions are licensed under the project's [MIT License](LICENSE).
