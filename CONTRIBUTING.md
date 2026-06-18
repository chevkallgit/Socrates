# Contributing

## Branching strategy

We use a simplified Git Flow:

```
main          ← stable, always deployable
  └── dev     ← integration branch, PRs merge here first
        └── feature/your-feature-name
        └── fix/short-description
        └── chore/short-description
```

**Rules:**
- Never commit directly to `main` or `dev`
- Branch off `dev`, merge back to `dev` via PR
- `main` only receives merges from `dev` after testing

### Branch naming

| Type    | Pattern                      | Example                        |
|---------|------------------------------|--------------------------------|
| Feature | `feature/short-description`  | `feature/pdf-chapter-detection`|
| Bug fix | `fix/short-description`      | `fix/footer-filter-logic`      |
| Chore   | `chore/short-description`    | `chore/add-ci-workflow`        |

---

## Commit messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <short summary in present tense>

[optional body explaining why, not what]
```

**Types:** `feat`, `fix`, `chore`, `docs`, `test`, `refactor`

```bash
# Good
feat: add position-based footer filtering to extract.py
fix: close pdf file handle after extraction
docs: update README quickstart instructions

# Bad
git commit -m "stuff"
git commit -m "fixed it"
git commit -m "WIP"
```

---

## Pull request workflow

1. Branch off `dev`: `git checkout -b feature/your-feature dev`
2. Make your changes with good commits
3. Push and open a PR against `dev`
4. Fill out the PR template
5. CI must pass before merging
6. Squash merge preferred for clean history

---

## Local setup

### Python pipeline

```bash
cd pipeline
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Running tests

```bash
cd pipeline
pytest tests/ -v
```

### Linting

```bash
ruff check .
```
