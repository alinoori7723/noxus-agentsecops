// Minimal typed API client. Same-origin in production (FastAPI serves the SPA);
// proxied to the backend in dev (see vite.config.ts). API keys are sent only in
// the POST body of /api/assessments/run and never stored or logged here.

import type {
  AssessmentResponse,
  HealthPayload,
  ProofIndicators,
  RunAssessmentRequest,
  SampleInputs,
} from "../types/noxus";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseError(res: Response): Promise<never> {
  let message = `Request failed (${res.status})`;
  try {
    const body = await res.json();
    if (body && typeof body.detail === "string") message = body.detail;
  } catch {
    // non-JSON error body; keep the generic message
  }
  throw new ApiError(res.status, message);
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
