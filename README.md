# Repo Heal

Repo Heal is a static website repair tool. Install or run it in a target repo, set a Gemini API key, and let it scan HTML, CSS, and browser JavaScript files. It applies deterministic fixes first and only escalates harder issues to an LLM fallback.

## Use In Any Repo

```sh
npx repo-heal setup
```

The setup command creates:

- `.github/workflows/repo-heal.yml`
- `.healignore`
- `.env.repo-heal.example`

Then add `GEMINI_API_KEY` to your local `.env` file or to GitHub Actions secrets.

## Run Locally

```sh
npx repo-heal run
```

To report issues without changing files:

```sh
npx repo-heal scan
```

To apply only deterministic static website fixes:

```sh
npx repo-heal fix
```

For local development inside this package:

```sh
npm run setup
npm run heal
```

## Commands

- `repo-heal setup`: install config into the current repository
- `repo-heal scan`: report static website issues without changing files
- `repo-heal fix`: run deterministic HTML/CSS/JS repairs
- `repo-heal run`: scan and repair the current repository
- `repo-heal summary`: print a markdown summary from the latest run metrics
- `repo-heal help`: show CLI help

## Notes

Repo Heal works on the current working directory. It is meant to be used from the root of the static website repository you want to repair, not from a bundled demo app.
