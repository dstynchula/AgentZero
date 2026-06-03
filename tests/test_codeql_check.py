import json

import tools.codeql_check as codeql_check


def test_skip_when_env_set(monkeypatch):
    monkeypatch.setenv("AGENTZERO_SKIP_CODEQL", "1")
    assert codeql_check.main() == 0


def test_fails_without_codeql_cli(monkeypatch):
    monkeypatch.delenv("AGENTZERO_SKIP_CODEQL", raising=False)
    monkeypatch.setattr(codeql_check, "resolve_codeql", lambda: None)
    assert codeql_check.main() == 1


def test_collect_findings_filters_scan_roots(tmp_path, monkeypatch):
    sarif = {
        "runs": [
            {
                "tool": {
                    "driver": {
                        "rules": [
                            {
                                "id": "py/path-injection",
                                "shortDescription": {"text": "Uncontrolled data used in path expression"},
                            }
                        ]
                    }
                },
                "results": [
                    {
                        "ruleId": "py/path-injection",
                        "level": "error",
                        "message": {"text": "This path depends on a user-provided value."},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "agentzero/generate/cover_letter.py"},
                                    "region": {"startLine": 40},
                                }
                            }
                        ],
                    },
                    {
                        "ruleId": "py/path-injection",
                        "level": "error",
                        "message": {"text": "outside scope"},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": "node_modules/evil.js"},
                                    "region": {"startLine": 1},
                                }
                            }
                        ],
                    },
                ],
            }
        ]
    }
    sarif_path = tmp_path / "results.sarif"
    monkeypatch.setattr(codeql_check, "SARIF_PATH", sarif_path)
    sarif_path.write_text(json.dumps(sarif), encoding="utf-8")
    findings = codeql_check._collect_findings()
    assert len(findings) == 1
    assert "cover_letter.py" in findings[0]
