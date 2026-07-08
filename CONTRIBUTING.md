# Contributing to Mino

Thanks for helping out. Mino is small on purpose, so most changes are quick to run and easy to review.

## Local setup

You need Python 3.13 and Node. Run the backend and frontend in two terminals:

```bash
# backend
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
AUTH_SECRET=dev-secret ENCRYPTION_KEY=dev-key DATABASE_URL="sqlite:///./oncall.db" \
  uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000

# frontend (new terminal)
cd frontend && npm install && npm run dev
```

Open http://localhost:5173 and create the owner account. The full walkthrough is in the
[getting-started tutorial](docs/tutorials/getting-started.md).

## Before you push

Run the quality gates. They compile the Python, run `svelte-check`, build the frontend, and validate
the Compose file.

```bash
./scripts/checks     # run the gates, stop at the first failure
./scripts/signoff    # run the gates on a clean repo, then stamp the commit on GitHub
```

To block a bad push automatically, turn on the pre-push hook once per clone. See
[Sign off before pushing](docs/how-to/sign-off-before-pushing.md).

## Opening a pull request

- Branch off `main`. `main` is protected and needs one approving review before it can merge.
- Keep pull requests small and focused so they are easy to review.
- Write commit messages as [Conventional Commits](https://www.conventionalcommits.org/):
  `fix:`, `feat:`, `docs:`, `refactor:`, `chore:`.
- Fill in the pull request template: what changed, the issue it closes, and how you tested it.

## Filing issues

Use the bug or feature templates. Issues are labeled by **type** (`bug`, `enhancement`,
`documentation`, `refactor`) and **difficulty** (`difficulty: easy`, `difficulty: medium`,
`difficulty: hard`). New here? Start with a
[`good first issue`](https://github.com/obakeng-develops/mino/labels/good%20first%20issue).
