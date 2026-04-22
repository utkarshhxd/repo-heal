export type User = {
  id: number;
  github_user_id: number;
  login: string;
  name?: string | null;
  avatar_url?: string | null;
};

export type Repo = {
  id: number;
  name: string;
  full_name: string;
  private: boolean;
  default_branch: string;
  owner_login: string;
};

export type Branch = {
  name: string;
};

export type Job = {
  id: string;
  status: string;
  repo_full_name: string;
  base_branch: string;
  fix_branch?: string | null;
  pr_number?: number | null;
  prompt: string;
  summary?: {
    fixed_count: number;
    skipped_count: number;
    fixed_files: string[];
    skipped_issues: string[];
  } | null;
  pr_url?: string | null;
  merged_at?: string | null;
  merge_commit_sha?: string | null;
  error?: string | null;
  logs: string[];
  created_at: string;
  updated_at: string;
};

function normalizeApiBaseUrl() {
  const configuredBaseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "").trim();

  if (!configuredBaseUrl) {
    return "";
  }

  if (typeof window === "undefined") {
    return configuredBaseUrl.replace(/\/$/, "");
  }

  try {
    const resolved = new URL(configuredBaseUrl, window.location.origin);
    return resolved.origin === window.location.origin ? resolved.pathname.replace(/\/$/, "") : "";
  } catch {
    return "";
  }
}

const API_BASE_URL = normalizeApiBaseUrl();

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {})
    }
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with status ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export const api = {
  baseUrl: API_BASE_URL,
  me: () => request<User>("/api/me"),
  repos: () => request<Repo[]>("/api/repos"),
  branches: (fullName: string) => {
    const [owner, repo] = fullName.split("/");
    return request<Branch[]>(`/api/repos/${owner}/${repo}/branches`);
  },
  createJob: (payload: { repository_full_name: string; branch: string; prompt: string }) =>
    request<Job>("/api/jobs", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  getJob: (jobId: string) => request<Job>(`/api/jobs/${jobId}`),
  mergeJobPullRequest: (jobId: string) =>
    request<Job>(`/api/jobs/${jobId}/merge`, {
      method: "POST"
    }),
  logout: () =>
    request<{ ok: boolean }>("/auth/logout", {
      method: "POST"
    })
};
