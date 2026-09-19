import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "../App";
import { providerTestSuccess } from "./fixtures";
let manualAllowed = false;
let catalogFails = false;
const posted: {
    url: string;
    body: Record<string, unknown>;
}[] = [];
beforeEach(() => {
    manualAllowed = false;
    catalogFails = false;
    posted.length = 0;
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === "POST") {
            posted.push({ url, body: JSON.parse(String(init.body)) });
            if (url === "/api/providers/test")
                return Response.json(providerTestSuccess);
            return Response.json({ detail: "Assessment temporarily unavailable." }, { status: 503 });
        }
        if (url === "/api/providers") {
            if (catalogFails)
                return Response.json({}, { status: 503 });
            return Response.json({ profiles: [{ name: "gemini-test", provider_type: "gemini_native" }], manual_keys_enabled: manualAllowed });
        }
        if (url === "/api/health")
            return Response.json({ ok: true });
        if (url === "/api/proof")
            return Response.json({ max_tuning_iterations: 2 });
        return Response.json({ system_prompt: "Synthetic support assistant", security_policy_yaml: "{}", business_context: "Synthetic case" });
    }));
});
afterEach(() => vi.unstubAllGlobals());
async function openProfiles() {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Provider Settings" }));
    await screen.findByRole("option", { name: "gemini-test" });
}
function selectProfile() {
    fireEvent.change(screen.getByLabelText("Provider profile"), { target: { value: "gemini-test" } });
}
function openAgentAssessment() {
    fireEvent.click(screen.getByRole("button", { name: "Assessment" }));
    fireEvent.click(screen.getByRole("button", { name: /Agent-Assisted Mode/ }));
}
describe("Server provider workflow", () => {
    it("defaults to profiles without exposing manual credential fields", async () => {
        await openProfiles();
        expect(screen.queryByLabelText("API key")).not.toBeInTheDocument();
        expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Test provider connection" })).toBeDisabled();
    });
    it("sends only a profile name for provider diagnostics", async () => {
        await openProfiles();
        selectProfile();
        fireEvent.click(screen.getByRole("button", { name: "Test provider connection" }));
        await waitFor(() => expect(posted).toHaveLength(1));
        expect(posted[0]).toEqual({ url: "/api/providers/test", body: { provider_profile: "gemini-test", models_to_test: ["red", "judge", "tuning"] } });
        await screen.findByText("all models ok");
    });
    it("sends a profile for agent assessments and displays API failures", async () => {
        await openProfiles();
        selectProfile();
        openAgentAssessment();
        fireEvent.click(screen.getByRole("button", { name: "Run Readiness Assessment" }));
        await screen.findByText("Assessment temporarily unavailable.");
        expect(posted[0].body.provider_profile).toBe("gemini-test");
        expect(posted[0].body).not.toHaveProperty("provider_config");
        expect(JSON.stringify(posted[0].body)).not.toContain("api_key");
    });
    it("requires an explicit profile before agent calls", async () => {
        await openProfiles();
        openAgentAssessment();
        expect(screen.getByRole("button", { name: "Configure a provider in Provider Settings to run" })).toBeDisabled();
        expect(posted).toHaveLength(0);
    });
    it("clears manual credentials when returning to server profiles", async () => {
        manualAllowed = true;
        await openProfiles();
        fireEvent.click(screen.getByRole("checkbox"));
        fireEvent.change(screen.getByLabelText("API key"), { target: { value: "synthetic-manual-key" } });
        fireEvent.click(screen.getByRole("checkbox"));
        selectProfile();
        fireEvent.click(screen.getByRole("button", { name: "Test provider connection" }));
        await waitFor(() => expect(posted).toHaveLength(1));
        expect(JSON.stringify(posted)).not.toContain("synthetic-manual-key");
        fireEvent.click(screen.getByRole("checkbox"));
        expect(screen.getByLabelText("API key")).toHaveValue("");
    });
    it("reports catalog failures without enabling credentials", async () => {
        catalogFails = true;
        render(<App />);
        fireEvent.click(screen.getByRole("button", { name: "Provider Settings" }));
        expect(await screen.findByRole("alert")).toHaveTextContent("Provider profiles could not be loaded.");
        expect(screen.getByLabelText("Provider profile")).toBeDisabled();
    });
    it("omits provider configuration for deterministic assessments", async () => {
        await openProfiles();
        selectProfile();
        fireEvent.click(screen.getByRole("button", { name: "Assessment" }));
        fireEvent.click(screen.getByRole("button", { name: "Run Readiness Assessment" }));
        await waitFor(() => expect(posted).toHaveLength(1));
        expect(posted[0].body.mode).toBe("deterministic");
        expect(posted[0].body).not.toHaveProperty("provider_profile");
        expect(posted[0].body).not.toHaveProperty("provider_config");
        await screen.findByText("Assessment temporarily unavailable.");
    });
});
