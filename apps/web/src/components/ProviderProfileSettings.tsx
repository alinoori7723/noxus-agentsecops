import { Lock, Activity } from "lucide-react";
import type { AgentRole, ProviderCatalog, ProviderConfig } from "../types/noxus";
import { ProviderSettings, ProviderDiagnostics, type ProviderTestState } from "./ProviderSettings";
interface Props {
    catalog: ProviderCatalog | null;
    error: string | null;
    profile: string;
    onProfileChange: (profile: string) => void;
    manual: boolean;
    onManualChange: (manual: boolean) => void;
    provider: ProviderConfig;
    onProviderChange: (provider: ProviderConfig) => void;
    testState: ProviderTestState;
    onTest: (roles: AgentRole[]) => void;
}
export function ProviderProfileSettings(props: Props) {
    const { catalog, error, profile, onProfileChange, manual, onManualChange, testState, onTest } = props;
    return (<div className="space-y-4">
      <div className="card space-y-4 p-5">
        <div className="flex items-center gap-2">
          <Lock size={18} className="text-emerald-600"/>
          <h3 className="font-bold text-slate-900">Server-managed credentials</h3>
        </div>
        <p className="text-sm leading-relaxed text-slate-600">
          Select a provider profile configured by the operator. Credentials and model settings
          stay on the server; your browser sends only the profile name.
        </p>
        {error && <p role="alert" className="text-sm text-rose-700">{error}</p>}
        {catalog?.manual_keys_enabled && (<label className="flex items-center gap-2 text-sm text-slate-600">
            <input type="checkbox" checked={manual} onChange={(event) => onManualChange(event.target.checked)}/>
            Use a manual key for local development
          </label>)}
        {!manual && (<>
            <label className="block text-sm font-semibold text-slate-700">
              Provider profile
              <select className="field mt-2" value={profile} onChange={(event) => onProfileChange(event.target.value)} disabled={!catalog?.profiles.length}>
                <option value="">Select a profile</option>
                {catalog?.profiles.map((item) => <option key={item.name} value={item.name}>{item.name}</option>)}
              </select>
            </label>
            {catalog && catalog.profiles.length === 0 && (<p className="text-sm text-slate-500">No provider profiles are configured. Deterministic assessments remain available.</p>)}
            <button type="button" className="btn-primary" disabled={!profile || testState.status === "testing"} onClick={() => onTest(["red", "judge", "tuning"])}>
              <Activity size={15}/> {testState.status === "testing" ? "Testing…" : "Test provider connection"}
            </button>
            <p className="text-xs text-slate-500">Testing contacts the configured provider and may incur usage charges.</p>
          </>)}
      </div>
      {manual && catalog?.manual_keys_enabled ? (<ProviderSettings provider={props.provider} onChange={props.onProviderChange} testState={testState} onTest={onTest}/>) : <ProviderDiagnostics testState={testState}/>}
    </div>);
}
