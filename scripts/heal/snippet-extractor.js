const fs = require('fs');

/**
 * Extracts a specific snippet of code around a problematic line.
 * Provides enough context for the AI without passing the whole file.
 */
function extractSnippet(filePath, targetLine, extraLines = 10) {
  try {
    const content = fs.readFileSync(filePath, 'utf-8');
    const lines = content.split('\n');
    
    // 1-indexed lines to 0-indexed array
    const targetIdx = targetLine - 1;
    
    const startIdx = Math.max(0, targetIdx - extraLines);
    const endIdx = Math.min(lines.length - 1, targetIdx + extraLines);
    
    const snippet = lines.slice(startIdx, endIdx + 1).join('\n');
    return {
      snippet,
      startLine: startIdx + 1,
      endLine: endIdx + 1,
      fullContent: content
    };
  } catch (error) {
    console.error(`Failed to extract snippet for ${filePath}: ${error}`);
    return null;
  }
}

/**
 * Replaces a snippet of lines back into the full file content.
 */
function replaceSnippet(fullContent, startLine, endLine, newSnippet) {
  const lines = fullContent.split('\n');
  const startIdx = startLine - 1;
  const endIdx = endLine - 1;
  
  // Remove old lines and insert new snippet
  const newSnippetLines = newSnippet.split('\n');
  lines.splice(startIdx, (endIdx - startIdx) + 1, ...newSnippetLines);
  
  return lines.join('\n');
}

module.exports = { extractSnippet, replaceSnippet };
