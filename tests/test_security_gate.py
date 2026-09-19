import runpy
from pathlib import Path

import pytest

blockers = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/check_trivy.py"))[
    "blockers"
]


@pytest.mark.parametrize(
    "severity,fixed,blocked",
    [
        ("CRITICAL", "1.2", True),
        ("HIGH", "1.2", True),
        ("MEDIUM", "1.2", False),
        ("LOW", "1.2", False),
        ("CRITICAL", "", True),
    ],
)
def test_vulnerability_gate_rejects_high_severity_even_without_fixes(severity, fixed, blocked):
    report = {
        "Results": [
            {
                "Target": "runtime",
                "Vulnerabilities": [
                    {
                        "Severity": severity,
                        "FixedVersion": fixed,
                        "VulnerabilityID": "test-advisory",
                        "PkgName": "test-package",
                    }
                ],
            }
        ]
    }
    assert bool(blockers(report)) is blocked


@pytest.mark.parametrize(
    "severity,status,blocked",
    [
        ("CRITICAL", "FAIL", True),
        ("HIGH", "FAIL", True),
        ("HIGH", "PASS", False),
        ("LOW", "FAIL", False),
    ],
)
def test_configuration_gate_rejects_high_severity_failures(severity, status, blocked):
    report = {
        "Results": [
            {
                "Target": "Dockerfile",
                "Misconfigurations": [
                    {
                        "Severity": severity,
                        "Status": status,
                        "ID": "test-check",
                        "Title": "test finding",
                    }
                ],
            }
        ]
    }
    assert bool(blockers(report)) is blocked
