"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { api, Branch, Job, Repo, User } from "../lib/api";

type Message = {
  id: string;
  role: "assistant" | "user";
  content: string;
  isStreaming?: boolean;
};

const STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  cloning: "Cloning repository",
  analyzing: "Analyzing files",
  fixing: "Applying fixes",
  committing: "Committing changes",
  creating_pr: "Creating pull request",
  completed: "Completed",
  failed: "Failed"
};

const GithubIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
    <path
      fillRule="evenodd"
      clipRule="evenodd"
      d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.699-2.782.603-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.464-1.11-1.464-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.831.092-.646.35-1.086.636-1.336-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.578 9.578 0 0112 6.836c.85.004 1.705.114 2.504.336 1.909-1.294 2.747-1.025 2.747-1.025.546 1.379.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48C19.138 20.161 22 16.416 22 12c0-5.523-4.477-10-10-10z"
    />
  </svg>
);

function SearchableDropdown({
  items,
  value,
  onChange,
  placeholder,
  searchPlaceholder,
  disabled
}: {
  items: { id: string; label: string }[];
  value: string;
  onChange: (val: string) => void;
  placeholder: string;
  searchPlaceholder: string;
  disabled?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const popoverRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }

    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen]);

  const filtered = items.filter(item => item.label.toLowerCase().includes(query.toLowerCase()));
  const selectedLabel = items.find(item => item.id === value)?.label;

  return (
    <div className={`custom-dropdown ${disabled ? "disabled" : ""}`} ref={popoverRef}>
      <div
        className="dropdown-trigger"
        onClick={() => !disabled && setIsOpen(!isOpen)}
        tabIndex={disabled ? -1 : 0}
      >
        <span className={selectedLabel ? "" : "placeholder"}>{selectedLabel || placeholder}</span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polyline points="6 9 12 15 18 9"></polyline>
        </svg>
      </div>

      {isOpen && (
        <div className="dropdown-popover animate-fade-in-slide">
          <div className="dropdown-search-box">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
            <input
              autoFocus
              className="dropdown-search-input"
              placeholder={searchPlaceholder}
              value={query}
              onChange={e => setQuery(e.target.value)}
            />
          </div>
          <div className="dropdown-list">
            {filtered.length === 0 ? (
              <div className="dropdown-empty">No results found.</div>
            ) : (
              filtered.map(item => (
                <div
                  key={item.id}
                  className={`dropdown-item ${item.id === value ? "selected" : ""}`}
                  onClick={() => {
                    onChange(item.id);
                    setIsOpen(false);
                    setQuery("");
                  }}
                >
                  <svg
                    className="repo-icon"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
                    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
                  </svg>
                  <span>{item.label}</span>
                  {item.id === value && (
                    <svg
                      className="check-icon"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="3"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function HomePage() {
  const [user, setUser] = useState<User | null>(null);
  const [repos, setRepos] = useState<Repo[]>([]);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [latestJob, setLatestJob] = useState<Job | null>(null);
  const [selectedRepo, setSelectedRepo] = useState("");
  const [selectedBranch, setSelectedBranch] = useState("");
  const [prompt, setPrompt] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "Hello! I'm RepoAgent. Connect your GitHub account and tell me what you'd like to fix or optimize in your repository."
    }
  ]);
  const [loadingRepos, setLoadingRepos] = useState(false);
  const [busy, setBusy] = useState(false);
  const [mergingPr, setMergingPr] = useState(false);
  const [error, setError] = useState("");
  const [jobProgress, setJobProgress] = useState("");
  const chatRef = useRef<HTMLDivElement>(null);
  const pollAbortRef = useRef(false);

  const connected = Boolean(user);
  const connectUrl = "/auth/github/login";

  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages, busy]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const authError = params.get("auth_error");
    if (authError) {
      setError(`GitHub authentication failed: ${authError}`);
      setTimeout(() => setError(""), 5000);
    }
    if (params.has("connected") || params.has("auth_error")) {
      window.history.replaceState({}, "", "/");
    }
    void loadSession();

    return () => {
      pollAbortRef.current = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedRepo || !connected) return;
    void loadBranches(selectedRepo);
  }, [selectedRepo, connected]);

  const canSubmit = connected && selectedRepo && selectedBranch && prompt.trim().length > 0 && !busy;

  async function loadSession() {
    try {
      const me = await api.me();
      setUser(me);
      await loadRepos();
      setError("");
    } catch {
      setUser(null);
      setRepos([]);
      setBranches([]);
    }
  }

  async function loadRepos() {
    setLoadingRepos(true);
    try {
      const repoList = await api.repos();
      setRepos(repoList);
      if (repoList.length > 0) {
        setSelectedRepo(current => current || repoList[0].full_name);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to load repositories.");
    } finally {
      setLoadingRepos(false);
    }
  }

  async function loadBranches(fullName: string) {
    try {
      const branchList = await api.branches(fullName);
      setBranches(branchList);
      if (branchList.length > 0) {
        setSelectedBranch(current => {
          if (branchList.some(entry => entry.name === current)) return current;
          const fallback = repos.find(entry => entry.full_name === fullName)?.default_branch;
          return fallback && branchList.some(entry => entry.name === fallback) ? fallback : branchList[0].name;
        });
      } else {
        setSelectedBranch("");
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to load branches.");
    }
  }

  async function handleLogout() {
    pollAbortRef.current = true;
    await api.logout();
    setUser(null);
    setRepos([]);
    setBranches([]);
    setSelectedRepo("");
    setSelectedBranch("");
    setPrompt("");
    setJobProgress("");
    setLatestJob(null);
    setBusy(false);
    setMessages([
      {
        id: "welcome",
        role: "assistant",
        content: "Connect GitHub to start an automated repair run."
      }
    ]);
  }

  function formatStepLine(message: string) {
    return message.startsWith("> ") ? message : `> ${message}`;
  }

  function buildCompletionMessage(job: Job) {
    if (job.merged_at) {
      return `\n\nPull request merged successfully.${job.pr_url ? `\n${job.pr_url}` : ""}`;
    }
    if (job.pr_url) {
      return `\n\nPull request created:\n${job.pr_url}`;
    }
    if (job.summary?.fixed_count) {
      return `\n\nCompleted with ${job.summary.fixed_count} validated fix(s).`;
    }
    return "\n\nCompleted. No pull request was created.";
  }

  async function monitorJob(jobId: string, streamingMessageId: string) {
    let lastLogCount = 0;

    while (!pollAbortRef.current) {
      const job = await api.getJob(jobId);
      setLatestJob(job);
      setJobProgress(STATUS_LABELS[job.status] ?? `Working: ${job.status}`);

      if (job.logs.length > lastLogCount) {
        const nextLines = job.logs.slice(lastLogCount).map(formatStepLine).join("\n");
        lastLogCount = job.logs.length;
        setMessages(current =>
          current.map(message =>
            message.id === streamingMessageId && message.isStreaming
              ? { ...message, content: message.content ? `${message.content}\n${nextLines}` : nextLines }
              : message
          )
        );
      }

      if (job.status === "completed") {
        setMessages(current =>
          current.map(message =>
            message.id === streamingMessageId
              ? { ...message, content: `${message.content}${buildCompletionMessage(job)}`, isStreaming: false }
              : message
          )
        );
        setBusy(false);
        setJobProgress("");
        return;
      }

      if (job.status === "failed") {
        const failureText = job.error ? `\n\nError: ${job.error}` : "\n\nError: Job failed unexpectedly.";
        setMessages(current =>
          current.map(message =>
            message.id === streamingMessageId
              ? { ...message, content: `${message.content}${failureText}`, isStreaming: false }
              : message
          )
        );
        setBusy(false);
        setJobProgress("");
        return;
      }

      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }

  async function handleSubmit(event?: FormEvent<HTMLFormElement>) {
    if (event) event.preventDefault();
    if (!canSubmit) return;

    pollAbortRef.current = true;
    pollAbortRef.current = false;

    const nextUserMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: prompt.trim()
    };
    const streamingMessageId = crypto.randomUUID();
    const streamingMessage: Message = {
      id: streamingMessageId,
      role: "assistant",
      content: "",
      isStreaming: true
    };

    setMessages(current => [...current, nextUserMessage, streamingMessage]);
    setBusy(true);
    setLatestJob(null);
    setError("");
    setJobProgress("Starting job");

    try {
      const payload = await api.createJob({
        repository_full_name: selectedRepo,
        branch: selectedBranch,
        prompt: prompt.trim()
      });

      setPrompt("");
      await monitorJob(payload.id, streamingMessageId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not start the repair job.");
      setMessages(current => current.filter(message => message.id !== streamingMessageId));
      setBusy(false);
      setJobProgress("");
      setTimeout(() => setError(""), 5000);
    }
  }

  async function handleMergePullRequest() {
    if (!latestJob?.id || !latestJob.pr_url || latestJob.merged_at || mergingPr) {
      return;
    }

    setMergingPr(true);
    setError("");
    try {
      const mergedJob = await api.mergeJobPullRequest(latestJob.id);
      setLatestJob(mergedJob);
      setMessages(current => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: `Pull request merged successfully.\n${mergedJob.pr_url ?? ""}`.trim()
        }
      ]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not merge the pull request.");
      setTimeout(() => setError(""), 5000);
    } finally {
      setMergingPr(false);
    }
  }

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSubmit();
    }
  };

  const selectedRepoObject = useMemo(
    () => repos.find(entry => entry.full_name === selectedRepo) ?? null,
    [repos, selectedRepo]
  );
  const canMergeLatestPr = Boolean(latestJob?.pr_url) && !latestJob?.merged_at;

  const repoItems = repos.map(repo => ({ id: repo.full_name, label: repo.full_name }));
  const branchItems = branches.map(branch => ({ id: branch.name, label: branch.name }));

  return (
    <div className="app-layout">
      {error && <div className="error-toast animate-fade-in">{error}</div>}

      <div className="workspace-frame">
        <section className="app-shell">
          <header className="top-nav">
            <div className="nav-brand">
              <div className="nav-brand-mark">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                  <path d="M12 3L19 7V17L12 21L5 17V7L12 3Z" stroke="currentColor" strokeWidth="1.8" />
                  <path d="M9 12L11 14L15 10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <span className="nav-brand-icon">RepoAgent</span>
            </div>

            <div className="nav-actions">
              {connected && user ? (
                <>
                  <div className="user-avatar" title={user.login}>
                    {user.login.slice(0, 2).toUpperCase()}
                  </div>
                  <button className="btn-secondary" onClick={handleLogout}>
                    Disconnect
                  </button>
                </>
              ) : (
                <a className="github-btn" href={connectUrl}>
                  <GithubIcon />
                  Connect GitHub
                </a>
              )}
            </div>
          </header>

          <main className="main-content chat-centered">
            <section className="chat-container">
              <div className="chat-thread" ref={chatRef}>
                {messages.map((message, index) => (
                  <div key={message.id} className={`chat-bubble ${message.role} animate-fade-in delay-${(index % 3) * 100}`}>
                    <div className="bubble-content">
                      {message.role === "assistant" && message.id === "welcome" ? (
                        <p className="welcome-copy">{message.content}</p>
                      ) : (
                        <pre className="stream-text">
                          {message.content}
                          {message.isStreaming && <span className="typing-cursor"></span>}
                        </pre>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              <div className="sticky-input-bar">
                <div className="input-container-width">
                  <form className="input-wrapper" onSubmit={handleSubmit}>
                    <div className="unified-input-box">
                      <div className="context-bar">
                        <div className="repo-slash-branch">
                          <SearchableDropdown
                            items={repoItems}
                            value={selectedRepo}
                            onChange={setSelectedRepo}
                            placeholder={connected ? (loadingRepos ? "Loading repos..." : "Select repository") : "Connect GitHub first"}
                            searchPlaceholder="Search repos..."
                            disabled={!connected || loadingRepos}
                          />
                          <SearchableDropdown
                            items={branchItems}
                            value={selectedBranch}
                            onChange={setSelectedBranch}
                            placeholder={connected ? "Select branch" : "Branch locked"}
                            searchPlaceholder="Search branches..."
                            disabled={!connected || !selectedRepoObject || branches.length === 0}
                          />
                        </div>
                      </div>

                      <textarea
                        className="main-prompt-input"
                        rows={1}
                        value={prompt}
                        onChange={event => {
                          event.target.style.height = "auto";
                          event.target.style.height = `${event.target.scrollHeight}px`;
                          setPrompt(event.target.value);
                        }}
                        onKeyDown={handleKeyDown}
                        placeholder={connected ? "Ask RepoAgent to fix, refactor, or optimize..." : "Connect GitHub to start using RepoAgent..."}
                        spellCheck={false}
                        disabled={!connected}
                      />

                      <div className="input-action-bar">
                        <div className="hint-text">
                          {busy
                            ? jobProgress || "Working..."
                            : latestJob?.merged_at
                              ? "Pull request merged."
                              : !connected
                                ? "Connect GitHub to unlock repositories and run tasks."
                                : null}
                        </div>
                        <div className="action-buttons">
                          {canMergeLatestPr && (
                            <button type="button" className="merge-button" onClick={handleMergePullRequest} disabled={mergingPr}>
                              {mergingPr ? "Merging..." : "Merge PR"}
                            </button>
                          )}
                          <button type="submit" className="run-button" disabled={!canSubmit}>
                            {busy ? (
                              "Running..."
                            ) : (
                              <>
                                Run
                                <svg
                                  width="14"
                                  height="14"
                                  viewBox="0 0 24 24"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth="2.2"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                >
                                  <line x1="22" y1="2" x2="11" y2="13"></line>
                                  <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                                </svg>
                              </>
                            )}
                          </button>
                        </div>
                      </div>
                    </div>
                  </form>
                </div>
              </div>
            </section>
          </main>
        </section>
      </div>
    </div>
  );
}
