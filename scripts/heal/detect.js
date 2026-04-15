const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const IGNORE_PATH = path.join(process.cwd(), '.healignore');
const IGNORE_FLAG = fs.existsSync(IGNORE_PATH) ? `--ignore-path ${IGNORE_PATH}` : '';
const ESLINT_BIN = path.join(path.dirname(require.resolve('eslint/package.json')), 'bin', 'eslint.js');
const PRETTIER_BIN = require.resolve('prettier/bin/prettier.cjs');
const HTMLHINT_BIN = require.resolve('htmlhint/bin/htmlhint');
const ESLINT_BASE_ARGS = '--env browser,es2021 --parser-options ecmaVersion:2022';
const STATIC_GLOBS = ['**/*.html', '**/*.htm', '**/*.css', '**/*.js'];

function runNodeBin(binPath, args, options = {}) {
  return execSync(`node "${binPath}" ${args}`, options);
}

function quoteGlob(glob) {
  return `"${glob}"`;
}

function runDetect() {
  const issues = [];
  
  // ESLint
  try {
    // --no-error-on-unmatched-pattern prevents crash if no files found
    const eslintOut = runNodeBin(ESLINT_BIN, `${STATIC_GLOBS.filter((glob) => glob.endsWith('.js')).map(quoteGlob).join(' ')} ${ESLINT_BASE_ARGS} --format json ${IGNORE_FLAG} --no-error-on-unmatched-pattern`, { encoding: 'utf-8' });
    parseEslint(eslintOut, issues);
  } catch (err) {
    if (err.stdout) parseEslint(err.stdout, issues);
  }

  // HTMLHint
  try {
    // Note: htmlhint doesn't natively support full ignore path the same way, usually config-driven, but we'll try standard args 
    // Format JSON wrapper for htmlhint
    runNodeBin(HTMLHINT_BIN, `"**/*.html" "**/*.htm" --format json`, { encoding: 'utf-8' });
  } catch (err) {
    if (err.stdout) {
      try {
        const parsed = JSON.parse(err.stdout);
        parsed.forEach(file => {
          file.messages.forEach(msg => {
            issues.push({
              tool: 'htmlhint',
              file: file.file,
              line: msg.line,
              column: msg.col,
              message: msg.message,
              severity: msg.type === 'error' ? 'critical' : 'medium'
            });
          });
        });
      } catch(e) {}
    }
  }

  return issues;
}

function parseEslint(out, issuesList) {
  try {
    const data = JSON.parse(out);
    data.forEach(file => {
      if (file.errorCount === 0 && file.warningCount === 0) return;
      file.messages.forEach(msg => {
        let severity = 'low';
        if (msg.severity === 2) severity = msg.fatal ? 'critical' : 'medium';
        
        issuesList.push({
          tool: 'eslint',
          file: file.filePath,
          line: msg.line,
          column: msg.column,
          message: msg.message,
          ruleId: msg.ruleId,
          severity: severity
        });
      });
    });
  } catch(e) {
    console.error("Detect JS parse error", e);
  }
}

function runAutofix() {
  try {
    runNodeBin(PRETTIER_BIN, `--write ${STATIC_GLOBS.map(quoteGlob).join(' ')} ${IGNORE_FLAG}`, { stdio: 'ignore' });
    runNodeBin(ESLINT_BIN, `${STATIC_GLOBS.filter((glob) => glob.endsWith('.js')).map(quoteGlob).join(' ')} ${ESLINT_BASE_ARGS} --fix ${IGNORE_FLAG} --no-error-on-unmatched-pattern`, { stdio: 'ignore' });
  } catch (e) {
    // Ignore autofix tool errors
  }
}

module.exports = { runDetect, runAutofix };
