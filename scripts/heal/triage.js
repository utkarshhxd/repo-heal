/**
 * Filters the raw issues to only those we want the AI to handle.
 * Prevents AI from touching files listed as protected beyond CLI ignores.
 */
function triageIssues(allIssues) {
  const IGNORED_RULES = ['no-console', 'prettier/prettier'];
  
  // Hardcoded protected boundary checking just in case CLI ignore fails
  const PROTECTED_SUBSTRINGS = ['node_modules', 'package.json', '.github', 'dist'];

  return allIssues.filter(issue => {
    // 1. Remove rules already fixed by prettier/eslint autofix or rules we don't care to AI-fix
    if (IGNORED_RULES.includes(issue.ruleId)) {
        return false;
    }

    // 2. Protected file boundary
    if (PROTECTED_SUBSTRINGS.some(sub => issue.file.includes(sub))) {
        return false;
    }
    
    // 3. We only escalate Medium and Critical issues to the expensive LLM.
    if (issue.severity === 'low') {
        return false;
    }

    return true;
  });
}

function groupIssuesByFile(issues) {
    const grouped = {};
    issues.forEach(iss => {
        if (!grouped[iss.file]) grouped[iss.file] = [];
        grouped[iss.file].push(iss);
    });
    return grouped;
}

module.exports = { triageIssues, groupIssuesByFile };
