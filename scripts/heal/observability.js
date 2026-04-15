const fs = require('fs');
const path = require('path');

const METRICS_DIR = path.join(process.cwd(), '.heal_metrics');

class Observability {
  constructor() {
    this.currentIteration = 0;
    this.logs = {
      iterations: []
    };
    if (!fs.existsSync(METRICS_DIR)) {
      fs.mkdirSync(METRICS_DIR, { recursive: true });
    }
  }

  startIteration(iterNumber) {
    this.currentIteration = iterNumber;
    this.logs.iterations[iterNumber] = {
      iteration: iterNumber,
      startTime: Date.now(),
      issuesBefore: 0,
      issuesAfter: 0,
      toolsUsed: [],
      filesTargeted: {},
      aiCalls: 0,
      successScore: 0,
    };
  }

  logDetect(issuesCount, stage = 'before') {
    if (stage === 'before') {
      this.logs.iterations[this.currentIteration].issuesBefore = issuesCount;
    } else {
      this.logs.iterations[this.currentIteration].issuesAfter = issuesCount;
    }
  }

  logAiCall(file, severity) {
    this.logs.iterations[this.currentIteration].aiCalls += 1;
    if (!this.logs.iterations[this.currentIteration].filesTargeted[file]) {
      this.logs.iterations[this.currentIteration].filesTargeted[file] = { attempts: 0, severity };
    }
    this.logs.iterations[this.currentIteration].filesTargeted[file].attempts += 1;
  }

  logToolUsage(toolName) {
    if (!this.logs.iterations[this.currentIteration].toolsUsed.includes(toolName)) {
      this.logs.iterations[this.currentIteration].toolsUsed.push(toolName);
    }
  }

  endIteration(score) {
    const iterData = this.logs.iterations[this.currentIteration];
    iterData.successScore = score;
    iterData.endTime = Date.now();
    iterData.durationMs = iterData.endTime - iterData.startTime;
    
    fs.writeFileSync(
      path.join(METRICS_DIR, `iteration_${this.currentIteration}.json`),
      JSON.stringify(iterData, null, 2)
    );
  }

  exportFinalLogs() {
    fs.writeFileSync(
      path.join(METRICS_DIR, `final_run_summary.json`),
      JSON.stringify(this.logs, null, 2)
    );
  }
}

module.exports = new Observability();
