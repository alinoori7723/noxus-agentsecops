// Minimal typed API client. Same-origin in production (FastAPI serves the SPA);
// proxied to the backend in dev (see vite.config.ts). API keys are sent only in
// the POST body of /api/assessments/run and never stored or logged here.

import type {
  AssessmentResponse,
  HealthPayload,
  ProofIndicators,
  ProviderConfig,
  ProviderTestResponse,
  RunAssessmentRequest,
  SampleInputs,
} from "../types/noxus";

export class ApiError extends Error {
  status: number;
  // Structured, safe error detail (e.g. policy-schema errors). Never a key.
  data: unknown;
  constructor(status: number, message: string, data?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

async function parseError(res: Response): Promise<never> {
  let message = `Request failed (${res.status})`;
  let data: unknown;
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (typeof detail === "string") {
      message = detail;
    } else if (detail && typeof detail === "object") {
      // Structured (coded) error — never contains an API key.
      data = detail;
      if (typeof detail.message === "string") message = detail.message;
    }
  } catch {
    // non-JSON error body; keep the generic message
  }
  throw new ApiError(res.status, message, data);
}

export async function getHealth(): Promise<HealthPayload> {
  const res = await fetch("/api/health");
  if (!res.ok) return parseError(res);
  return res.json();
}

export async function getProof(): Promise<ProofIndicators> {
  const res = await fetch("/api/proof");
  if (!res.ok) return parseError(res);
  return res.json();
}

export async function getSampleInputs(): Promise<SampleInputs> {
  const res = await fetch("/api/sample-inputs");
  if (!res.ok) return parseError(res);
  return res.json();
}

export async function runAssessment(
  req: RunAssessmentRequest,
): Promise<AssessmentResponse> {
  const res = await fetch("/api/assessments/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) return parseError(res);
  return res.json();
}

export async function testProvider(
  provider_config: ProviderConfig,
  models_to_test: ("red" | "judge" | "tuning")[],
): Promise<ProviderTestResponse> {
  const res = await fetch("/api/providers/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider_config, models_to_test }),
  });
  if (!res.ok) return parseError(res);
  return res.json();
}
