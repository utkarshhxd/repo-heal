require('dotenv').config({ quiet: true });

const { runDetect, runAutofix } = require('./detect');
const { triageIssues, groupIssuesByFile } = require('./triage');
const { executeAgenticFix } = require('./fix');
const { validateFixes } = require('./validate');
const { runStaticAutofix } = require('./static-fixer');
const observability = require('./observability');

const DEFAULT_MAX_ITERATIONS = 3;

async function runHealingLoop(options = {}) {
  const maxIterations = Number(options.maxIterations || process.env.REPO_HEAL_MAX_ITERATIONS || DEFAULT_MAX_ITERATIONS);

  console.log('=== Initializing Repo Heal for static websites ===');

  let issuesResolved = false;

  for (let iter = 1; iter <= maxIterations; iter++) {
    console.log(`\n--- Starting Iteration ${iter}/${maxIterations} ---`);
    observability.startIteration(iter);

    // 1. Detect
    const issues = runDetect();
    observability.logDetect(issues.length, 'before');
    
    if (issues.length === 0) {
      console.log('No static website issues detected. Exiting loop.');
      issuesResolved = true;
      observability.endIteration(0);
      break;
    }

    // 2. Triage
    const targetIssues = triageIssues(issues);
    if (targetIssues.length === 0) {
       console.log('Remaining issues are ignored or outside static-site repair scope.');
       // Try a general autofix just in case
       runAutofix();
       break;
    }

    // Attempt deterministic static-site fixes FIRST.
    if (iter === 1) {
        const staticModifiedFiles = runStaticAutofix();
        if (staticModifiedFiles.length > 0) {
          observability.logToolUsage('static-autofix');
        }
        runAutofix();
        observability.logToolUsage('eslint/prettier-autofix');
    }

    const issuesAfterAutofix = runDetect();
    if (issuesAfterAutofix.length === 0) {
      observability.logDetect(0, 'after');
      observability.endIteration(issues.length);
      issuesResolved = true;
      break;
    }

    // 3. Fix (Agentic Escalation)
    const groupedIssues = groupIssuesByFile(triageIssues(issuesAfterAutofix));
    const modifiedFiles = [];
    
    for (const [file, fileIssues] of Object.entries(groupedIssues)) {
      const wasModified = await executeAgenticFix(file, fileIssues, observability);
      if (wasModified) modifiedFiles.push(file);
    }

    // 4. Validate & Score
    let confidenceScore = 0;
    if (modifiedFiles.length > 0) {
      // We map the initial count of targeted issues per file 
      const issuesBeforeMap = {};
      Object.keys(groupedIssues).forEach(f => { issuesBeforeMap[f] = groupedIssues[f].length; });
      confidenceScore = validateFixes(modifiedFiles, issuesBeforeMap);
    }
    
    // Final check for this iter
    const closingIssues = runDetect();
    observability.logDetect(closingIssues.length, 'after');
    observability.endIteration(confidenceScore);
    
    if (closingIssues.length === 0) {
      issuesResolved = true;
      break;
    }
  }

  // Export final logs for PR generation
  observability.exportFinalLogs();
  
  if (issuesResolved) {
    console.log('\n=== Success! Static website checks are clean. ===');
  } else {
    console.log('\n=== Loop Finished. Some issues may require manual review. ===');
  }

  return { issuesResolved };
}

if (require.main === module) {
  runHealingLoop().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}

module.exports = { runHealingLoop };
