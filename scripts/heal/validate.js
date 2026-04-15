const { execSync } = require('child_process');
const { runDetect } = require('./detect');

function canUseGitRestore() {
    try {
        execSync('git rev-parse --is-inside-work-tree', { stdio: 'ignore' });
        return true;
    } catch (e) {
        return false;
    }
}

/**
 * Validates the fix using Confidence Scoring.
 * If the issues on a modified file INCREASE after AI patching, it rolls back using git restore.
 */
function validateFixes(modifiedFiles, issuesBeforeMap) {
    if (modifiedFiles.length === 0) return 0;
    
    const gitRestoreAvailable = canUseGitRestore();
    
    // Re-detect on the workspace
    const newIssues = runDetect();
    
    let totalConfidenceScore = 0;

    for (const file of modifiedFiles) {
        const issuesBefore = issuesBeforeMap[file] || 0;
        
        const newIssuesOnFile = newIssues.filter(iss => iss.file === file).length;
        
        const score = issuesBefore - newIssuesOnFile; // Positive means we removed bugs
        
        if (score < 0 || newIssuesOnFile > issuesBefore) {
            console.error(`[Validation Failed] AI introduced MORE bugs to ${file}. Rolling back.`);
            if (!gitRestoreAvailable) {
                console.error(`Could not restore ${file}: not inside a git repository.`);
                continue;
            }
            try {
                execSync(`git restore -- "${file}"`);
            } catch(e) {
                console.error(`Could not restore ${file}`, e);
            }
        } else if (score === 0 && issuesBefore > 0) {
            console.warn(`[Validation Warning] AI failed to fix bugs in ${file}. Exact same number of bugs exist. Rolling back.`);
            if (!gitRestoreAvailable) {
                console.error(`Could not restore ${file}: not inside a git repository.`);
                continue;
            }
             try {
                execSync(`git restore -- "${file}"`);
            } catch(e) {}
        } else {
            totalConfidenceScore += score;
        }
    }
    
    return totalConfidenceScore;
}

module.exports = { validateFixes };
