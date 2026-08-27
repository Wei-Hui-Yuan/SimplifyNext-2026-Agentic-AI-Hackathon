# AGENTS.md

## Project Overview

NUS Life OS is an agentic system designed to help NUS students plan,
execute, and adapt toward long-term academic and career goals.

This repository is a shared project. Changes should be small, intentional,
reviewable, and aligned with the current product goal.

## Contribution Rules

- Read the relevant documentation before making changes.
- Do not modify application code unless the task explicitly requires it.
- Prefer small, focused changes over large refactors.
- Do not introduce dependencies without a clear reason.
- Keep secrets, API keys, credentials, and personal student data out of Git.
- Update documentation when behavior or development workflows change.
- Do not assume an external integration exists; verify it before building against it.
- Preserve existing functionality unless the task explicitly calls for a change.

## Branches

Use a dedicated branch for each piece of work.

Recommended naming:

- `feat/<short-description>` — new functionality
- `fix/<short-description>` — bug fixes
- `docs/<short-description>` — documentation
- `chore/<short-description>` — tooling or maintenance
- `refactor/<short-description>` — refactoring

Do not develop directly on `main`.

Keep branches focused and avoid mixing unrelated changes.

## Pull Requests

Every pull request should:

1. Have a clear, concise title.
2. Explain what changed and why.
3. Describe how the changes were tested.
4. Call out any known limitations or follow-up work.
5. Keep unrelated changes out of the PR.

Before requesting review:

- Ensure the project builds successfully.
- Run the relevant test suite.
- Check for accidental secrets or credentials.
- Review the diff for unintended changes.

At least one other contributor should review changes before they are merged
into `main`, unless the team explicitly agrees otherwise.

## Setup

> TODO: Document local development setup.

Include:

- Required language/runtime versions
- Required dependencies
- Environment variables
- AWS configuration
- External services
- Installation commands

## Running

> TODO: Document how to run NUS Life OS locally.

Include:

- Development server commands
- Agent/runtime commands
- Required services
- Environment configuration

## Testing

> TODO: Document how to run the test suite.

Include:

- Unit tests
- Integration tests
- Agent evaluations
- MCP/tool tests
- End-to-end tests

## Development Philosophy

NUS Life OS is intended to be an agent that can:

1. Understand a student's goals and current state.
2. Plan actions toward those goals.
3. Execute permitted actions.
4. Observe outcomes.
5. Adapt its plan over time.

The system should prioritize student benefit, user control, safety,
observability, and explainability over unnecessary autonomy.