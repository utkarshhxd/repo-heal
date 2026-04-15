#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const DEFAULT_HEALIGNORE = `node_modules/
dist/
build/
coverage/
.git/
.github/workflows/
package-lock.json
.env
`;

function printHelp() {
  console.log(`
repo-heal

Usage:
  repo-heal setup      Install Repo Heal config into the current repository
  repo-heal scan       Report static website issues without changing files
  repo-heal fix        Run deterministic static website fixes
  repo-heal run        Detect and repair issues in the current repository
  repo-heal help       Show this help

Environment:
  GEMINI_API_KEY       Required for AI repair
  GEMINI_MODEL         Optional comma-separated Gemini model fallback list
`);
}

function writeFileIfMissing(filePath, content) {
  if (fs.existsSync(filePath)) {
    console.log(`Skipped existing ${path.relative(process.cwd(), filePath)}`);
    return;
  }

  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, content);
  console.log(`Created ${path.relative(process.cwd(), filePath)}`);
}

function getWorkflow(packageName) {
  return `name: Repo Heal

on:
  workflow_dispatch:
  pull_request:
    branches:
      - main

permissions:
  contents: write
  pull-requests: write

concurrency:
  group: repo-heal-\${{ github.ref }}
  cancel-in-progress: true

jobs:
  heal:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Install project dependencies
        shell: bash
        run: |
          if [ -f package-lock.json ]; then
            npm ci
          elif [ -f package.json ]; then
            npm install
          else
            echo "No package.json found; skipping project dependency install."
          fi

      - name: Run Repo Heal
        env:
          GEMINI_API_KEY: \${{ secrets.GEMINI_API_KEY }}
          GEMINI_MODEL: gemini-2.5-flash,gemini-2.5-flash-lite,gemini-flash-latest
        run: npx ${packageName} run

      - name: Generate repair summary
        run: npx ${packageName} summary > pr_body.md
        continue-on-error: true

      - name: Create repair pull request
        uses: peter-evans/create-pull-request@v6
        with:
          commit-message: "fix: apply repo-heal repairs"
          title: "Repo Heal: automated repairs"
          body-path: pr_body.md
          branch: "repo-heal/automated-repairs"
          delete-branch: true
`;
}

function runSetup() {
  const packageJson = require('../package.json');
  const workflowPath = path.join(process.cwd(), '.github', 'workflows', 'repo-heal.yml');
  const healIgnorePath = path.join(process.cwd(), '.healignore');
  const envExamplePath = path.join(process.cwd(), '.env.repo-heal.example');

  writeFileIfMissing(workflowPath, getWorkflow(packageJson.name));
  writeFileIfMissing(healIgnorePath, DEFAULT_HEALIGNORE);
  writeFileIfMissing(
    envExamplePath,
    'GEMINI_API_KEY=paste_your_gemini_api_key_here\nGEMINI_MODEL=gemini-2.5-flash,gemini-2.5-flash-lite,gemini-flash-latest\n'
  );

  console.log('\nRepo Heal is set up. Add GEMINI_API_KEY to your local .env or GitHub Actions secrets.');
}

function ensureGitWorktree() {
  try {
    execSync('git rev-parse --is-inside-work-tree', { stdio: 'ignore' });
    return true;
  } catch (error) {
    console.error('Repo Heal run requires a git repository so failed repairs can be rolled back safely.');
    console.error('Run this command from the root of the repository you want to repair.');
    return false;
  }
}

async function main() {
  const command = process.argv[2] || 'help';

  if (command === 'setup') {
    runSetup();
    return;
  }

  if (command === 'scan') {
    const { runDetect } = require('./heal/detect');
    const issues = runDetect();
    if (issues.length === 0) {
      console.log('No static website issues detected.');
      return;
    }

    issues.forEach((issue) => {
      console.log(`${issue.file}:${issue.line || 1}:${issue.column || 1} ${issue.tool} ${issue.message}`);
    });
    process.exitCode = 1;
    return;
  }

  if (command === 'fix') {
    const { runStaticAutofix } = require('./heal/static-fixer');
    runStaticAutofix();
    return;
  }

  if (command === 'run' || command === 'heal') {
    if (!ensureGitWorktree()) {
      process.exitCode = 1;
      return;
    }
    const { runHealingLoop } = require('./heal');
    await runHealingLoop();
    return;
  }

  if (command === 'summary') {
    require('./heal/generate-pr-summary');
    return;
  }

  if (command === 'help' || command === '--help' || command === '-h') {
    printHelp();
    return;
  }

  console.error(`Unknown command: ${command}`);
  printHelp();
  process.exitCode = 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
