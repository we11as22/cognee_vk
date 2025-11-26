## Repository Guidelines

This document summarizes how to work with the cognee repository: how it’s organized, how to build, test, lint, and contribute. It mirrors our actual tooling and CI while providing quick commands for local development.

## Project Structure & Module Organization

- `cognee/`: Core Python library and API.
  - `api/`: FastAPI application and versioned routers (add, cognify, memify, search, delete, users, datasets, responses, visualize, settings, sync, update, checks).
  - `cli/`: CLI entry points and subcommands invoked via `cognee` / `cognee-cli`.
  - `infrastructure/`: Databases, LLM providers, embeddings, loaders, and storage adapters.
  - `modules/`: Domain logic (graph, retrieval, ontology, users, processing, observability, etc.).
  - `tasks/`: Reusable tasks (e.g., code graph, web scraping, storage). Extend with new tasks here.
  - `eval_framework/`: Evaluation utilities and adapters.
  - `shared/`: Cross-cutting helpers (logging, settings, utils).
  - `tests/`: Unit, integration, CLI, and end-to-end tests organized by feature.
  - `__main__.py`: Entrypoint to route to CLI.
- `cognee-mcp/`: Model Context Protocol server exposing cognee as MCP tools (SSE/HTTP/stdio). Contains its own README and Dockerfile.
- `cognee-frontend/`: Next.js UI for local development and demos.
- `distributed/`: Utilities for distributed execution (Modal, workers, queues).
- `examples/`: Example scripts demonstrating the public APIs and features (graph, code graph, multimodal, permissions, etc.).
- `notebooks/`: Jupyter notebooks for demos and tutorials.
- `alembic/`: Database migrations for relational backends.

Notes:
- Co-locate feature-specific helpers under their respective package (`modules/`, `infrastructure/`, or `tasks/`).
- Extend the system by adding new tasks, loaders, or retrievers rather than modifying core pipeline mechanisms.

## Build, Test, and Development Commands

Python (root) – requires Python >= 3.10 and < 3.14. We recommend `uv` for speed and reproducibility.

- Create/refresh env and install dev deps:
```bash
uv sync --dev --all-extras --reinstall
```

- Run the CLI (examples):
```bash
uv run cognee-cli add "Cognee turns documents into AI memory."
uv run cognee-cli cognify
uv run cognee-cli search "What does cognee do?"
uv run cognee-cli -ui   # Launches UI, backend API, and MCP server together
```

- Start the FastAPI server directly:
```bash
uv run python -m cognee.api.client
```

- Run tests (CI mirrors these commands):
```bash
uv run pytest cognee/tests/unit/ -v
uv run pytest cognee/tests/integration/ -v
```

- Lint and format (ruff):
```bash
uv run ruff check .
uv run ruff format .
```

- Optional static type checks (mypy):
```bash
uv run mypy cognee/
```

MCP Server (`cognee-mcp/`):

- Install and run locally:
```bash
cd cognee-mcp
uv sync --dev --all-extras --reinstall
uv run python src/server.py               # stdio (default)
uv run python src/server.py --transport sse
uv run python src/server.py --transport http --host 127.0.0.1 --port 8000 --path /mcp
```

- API Mode (connect to a running Cognee API):
```bash
uv run python src/server.py --transport sse --api-url http://localhost:8000 --api-token YOUR_TOKEN
```

- Docker quickstart (examples): see `cognee-mcp/README.md` for full details
```bash
docker run -e TRANSPORT_MODE=http --env-file ./.env -p 8000:8000 --rm -it cognee/cognee-mcp:main
```

Frontend (`cognee-frontend/`):
```bash
cd cognee-frontend
npm install
npm run dev     # Next.js dev server
npm run lint    # ESLint
npm run build && npm start
```

## Coding Style & Naming Conventions

Python:
- 4-space indentation, modules and functions in `snake_case`, classes in `PascalCase`.
- Public APIs should be type-annotated where practical.
- Use `ruff format` before committing; `ruff check` enforces import hygiene and style (line-length 100 configured in `pyproject.toml`).
- Prefer explicit, structured error handling. Use shared logging utilities in `cognee.shared.logging_utils`.

MCP server and Frontend:
- Follow the local `README.md` and ESLint/TypeScript configuration in `cognee-frontend/`.

## Testing Guidelines

- Place Python tests under `cognee/tests/`.
  - Unit tests: `cognee/tests/unit/`
  - Integration tests: `cognee/tests/integration/`
  - CLI tests: `cognee/tests/cli_tests/`
- Name test files `test_*.py`. Use `pytest.mark.asyncio` for async tests.
- Avoid external state; rely on test fixtures and the CI-provided env vars when LLM/embedding providers are required. See CI workflows under `.github/workflows/` for expected environment variables.
- When adding public APIs, provide/update targeted examples under `examples/python/`.

## Commit & Pull Request Guidelines

- Use clear, imperative subjects (≤ 72 chars) and conventional commit styling in PR titles. Our CI validates semantic PR titles (see `.github/workflows/pr_lint`). Examples:
  - `feat(graph): add temporal edge weighting`
  - `fix(api): handle missing auth cookie`
  - `docs: update installation instructions`
- Reference related issues/discussions in the PR body and provide brief context.
- PRs should describe scope, list local test commands run, and mention any impacts on MCP server or UI if applicable.
- Sign commits and affirm the DCO (see `CONTRIBUTING.md`).

## CI Mirrors Local Commands

Our GitHub Actions run the same ruff checks and pytest suites shown above (`.github/workflows/basic_tests.yml` and related workflows). Use the commands in this document locally to minimize CI surprises.



## MCP as Code Runtime for Agents (API Mode Rules)

These rules define how coding agents should use the Cognee MCP server as a **code runtime memory** in **API mode** (MCP ↔ FastAPI on port 8000) for **any, constantly changing codebase**.

- **Connection & Transport**
  - Assume the MCP server is exposed via SSE at `http://localhost:8001/sse` (host → MCP container port `8001:8000`).
  - Never call the Cognee FastAPI (`http://localhost:8000`) directly from the agent. All interaction must go through MCP tools.

- **Source of truth for code**
  - The **agent’s view of the filesystem** (the user’s workspace in the IDE) is the ground truth for code.
  - Cognee’s memory is a **derived, eventually consistent index**. If there is a conflict between what you see in files and what Cognee returns, trust the files and refresh Cognee.

- **Role separation: MCP = search/memory, main LLM = reasoning/code**
  - Treat Cognee MCP strictly as:
    - a **search / retrieval / memory layer** over code and documents,
    - not as the component that “decides” how to change code.
  - Use the IDE’s main LLM/agent for:
    - planning changes,
    - writing or editing code,
    - making architectural decisions.
  - Use Cognee MCP only to:
    - find relevant files, functions, and contexts,
    - surface relationships and summaries,
    - recall past interactions and developer rules.

- **How to ingest code (any repo, changing over time)**
  - For any task that needs semantic/code‑graph context, first ensure the relevant code is ingested:
    - Build a **text snapshot** from the current filesystem:
      - Prefer scoping to the **minimal relevant set** of files (e.g. current project, module, or changed files), not the entire monorepo.
      - Explicitly include file paths and short headers, e.g.:
        - `File app/api/users.py:\n<contents>\n\nFile app/models/user.py:\n<contents>\n...`
    - Call MCP tool `cognify` with:
      - `data`: the snapshot text,
      - `instruction_type="nl2code"` for “natural language ↔ code” workflows.
  - For **incremental updates**:
    - On edits, re‑ingest only the **changed files or modules** rather than the whole repo.
    - It is acceptable to send updated snapshots of the same file; Cognee will de‑duplicate/merge internally.
  - Do **not** assume Cognee automatically tracks live file changes — ingestion must be triggered explicitly by the agent via `cognify`.

- **How to navigate the codebase**
  - Use MCP `search` as the primary navigation primitive over ingested code:
    - `search_type="CODE"`:
      - For finding definitions, usages, related files, architectural relationships.
      - Use when you need “where is X implemented/used and what else is related to it?”.
    - `search_type="CHUNKS"`:
      - For text‑level queries (“find this snippet / symbol / string / comment”).
    - `search_type="GRAPH_COMPLETION"` with `instruction_type="nl2code"`:
      - For higher‑level reasoning over the codebase (design, data‑flow, responsibilities).
  - Before relying on search results, ensure that:
    - the files you care about have been ingested **after** their last change;
    - if not sure, re‑run `cognify` on those paths first.

- **Tool availability and expectations in API mode**
  - **Fully supported in API mode** and recommended for code workflows:
    - `cognify` — transforms added data into a structured knowledge graph.
    - `cognee_add_developer_rules` — ingests rule/config files (including `AGENTS.md`, `.cursorrules`, etc.).
    - `search` — all search types, including `CODE`, `GRAPH_COMPLETION`, `CHUNKS`, `SUMMARIES`, `CYPHER`, `FEELING_LUCKY`.
    - `list_data`, `delete`, `prune`, `save_interaction`.
  - **API‑mode limitations (do NOT build control flow on these):**
    - `cognify_status` / `codify_status`:
      - In API mode, they only report that pipeline status is not available (no HTTP endpoint exists yet).
      - Do not rely on them for progress tracking; treat `cognify` as fire‑and‑forget.
    - `codify`:
      - In API mode, returns an explicit “codify is not available” message.
      - Use `cognify(data=code_snapshot) + search(search_type="CODE")` as the standard pattern for code navigation instead.

- **Safety and data management**
  - Prefer:
    - `list_data` to inspect what datasets/data are present.
    - `delete(mode="soft")` to remove specific outdated snapshots.
  - Use `prune` **only** when intentionally resetting the entire memory (e.g. switching to a completely different long‑running workspace).
  - When working across multiple projects:
    - Encode the project/root path in your snapshots’ headers so search results remain distinguishable (e.g. `Project: project_a`, `File project_a/app/main.py: ...`).

- **Goal for agents**
  - Treat Cognee MCP as a **long‑lived, code‑aware runtime memory layer**:
    - Continuously keep the currently relevant parts of the user’s codebase in sync via `cognify` (initial and incremental snapshots).
    - Use `search` (especially `CODE` and `GRAPH_COMPLETION`) as your primary interface to that memory when:
      - answering questions about the code,
      - gathering context for planned edits or refactors,
      - selecting the right locations to modify,
      - but leave the actual code generation and decision‑making to the main LLM/agent, not to this MCP server.


