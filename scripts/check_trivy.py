from __future__ import annotations

import json
import sys
from pathlib import Path


def blockers(report: dict) -> list[str]:
    failures = []
    for result in report.get("Results", []):
        for vulnerability in result.get("Vulnerabilities", []):
            if vulnerability.get("Severity") in {"HIGH", "CRITICAL"}:
                failures.append(
                    f"{result['Target']}: {vulnerability['VulnerabilityID']} ({vulnerability['PkgName']})"
                )
        for config in result.get("Misconfigurations", []):
            if config.get("Severity") in {"HIGH", "CRITICAL"} and config.get("Status") == "FAIL":
                failures.append(f"{result['Target']}: {config['ID']} {config['Title']}")
    return failures


def main() -> int:
    report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if report.get("SchemaVersion") != 2 or "ArtifactName" not in report:
        raise ValueError("Unexpected or incomplete Trivy report")
    failures = blockers(report)
    for failure in failures:
        print(failure)
    print(
        f"High/critical vulnerabilities and high/critical configuration failures: {len(failures)}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
