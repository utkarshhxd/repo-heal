const fs = require('fs');
const { extractSnippet, replaceSnippet } = require('./snippet-extractor');
const crypto = require('crypto');
const { GoogleGenAI } = require('@google/genai');

const MAX_AI_CALLS_PER_RUN = 10;
let globalAiCalls = 0;

// Simple Idempotency cache: hash(issueKey) -> previousFailedSnippetHash
const idempotencyCache = {};

async function executeAgenticFix(file, issues, observabilityTracker) {
  if (globalAiCalls >= MAX_AI_CALLS_PER_RUN) {
    console.warn("MAX_AI_CALLS_PER_RUN reached. Halting further escalations.");
    return false;
  }

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey || apiKey === 'paste_your_gemini_api_key_here') {
    console.error("GEMINI_API_KEY not found in environment.");
    return false;
  }

  const models = (process.env.GEMINI_MODEL || 'gemini-2.5-flash,gemini-2.5-flash-lite,gemini-flash-latest')
    .split(',')
    .map((model) => model.trim())
    .filter(Boolean);
  const ai = new GoogleGenAI({ apiKey });
  
  let fileWasModified = false;
  let currentFileContent = fs.readFileSync(file, 'utf-8');

  for (const issue of issues) {
    if (globalAiCalls >= MAX_AI_CALLS_PER_RUN) break;

    const issueKey = `${file}:${issue.line}:${issue.ruleId}`;
    
    // Extract localized snippet
    const snippetData = extractSnippet(file, issue.line, 7);
    if (!snippetData) continue;

    console.log(`[AI Fix] Escalating issue in ${file}:${issue.line} to Gemini...`);

    const prompt = `
You are an autonomous MCP code repair agent. A linter found this issue:
Error [${issue.severity}]: ${issue.message}

Here is the source code snippet around line ${issue.line}:
\`\`\`
${snippetData.snippet}
\`\`\`

You must call your internal 'patch' tool. Reply EXACTLY with a JSON object in this format, and NOTHING ELSE (no markdown blocks, no text):
{
  "startLine": ${snippetData.startLine},
  "endLine": ${snippetData.endLine},
  "replacementCode": "// The fully corrected snippet to drop in"
}
`;

    try {
      let response;
      let lastModelError;

      for (const model of models) {
        if (globalAiCalls >= MAX_AI_CALLS_PER_RUN) break;

        try {
          globalAiCalls++;
          observabilityTracker.logAiCall(file, issue.severity);

          response = await ai.models.generateContent({
            model,
            contents: prompt,
            config: {
              // Force JSON parsing logic so it does not hallucinate markdown.
              responseMimeType: 'application/json'
            }
          });
          break;
        } catch (modelError) {
          lastModelError = modelError;
          const message = String(modelError.message || modelError);
          const canTryNextModel = message.includes('"code":503') || message.includes('"code":404');

          if (!canTryNextModel) {
            throw modelError;
          }

          console.warn(`[AI Fix] ${model} unavailable, trying next configured Gemini model...`);
        }
      }

      if (!response) {
        throw lastModelError || new Error('No Gemini models are configured.');
      }

      const responseText = response.text;
      const patchCommand = JSON.parse(responseText);

      // Check idempotency: If we generated this exact code for this exact issue last time, we are in a loop
      const snippetHash = crypto.createHash('md5').update(patchCommand.replacementCode).digest('hex');
      if (idempotencyCache[issueKey] === snippetHash) {
          console.warn(`Idempotency trigger: AI suggested the exact same failing patch for ${issueKey}. Skipping.`);
          continue;
      }
      idempotencyCache[issueKey] = snippetHash;

      // Apply the patch locally
      currentFileContent = replaceSnippet(
          currentFileContent, 
          patchCommand.startLine, 
          patchCommand.endLine, 
          patchCommand.replacementCode
      );
      
      fs.writeFileSync(file, currentFileContent);
      fileWasModified = true;

    } catch (e) {
      console.error(`AI Patch failed for ${issueKey}:`, e.message);
    }
  }

  return fileWasModified;
}

module.exports = { executeAgenticFix };
