"""Regression guards for least-privilege GitHub Actions checkout behavior."""
from pathlib import Path


def test_ci_workflow_grants_only_read_contents_permission():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yaml").read_text()
    lines = workflow.splitlines()
    start = lines.index("permissions:")
    block = []
    for line in lines[start + 1:]:
        if line and not line.startswith(" "):
            break
        if line.strip():
            block.append(line.strip())
    assert block == ["contents: read"]


def test_every_checkout_step_disables_persisted_git_credentials():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yaml").read_text()
    lines = workflow.splitlines()
    checkout_indexes = [
        index for index, line in enumerate(lines)
        if line.strip() == "- uses: actions/checkout@v4"
    ]
    assert len(checkout_indexes) == 3

    for start in checkout_indexes:
        block = []
        for line in lines[start + 1:]:
            indent = len(line) - len(line.lstrip())
            if line.strip() and indent <= 6:
                break
            block.append(line.strip())
        assert "persist-credentials: false" in block
