import subprocess
from typing import Dict, Any, Optional
from pathlib import Path
from pydantic import BaseModel
import yaml


class ProtocolIntegrityResult(BaseModel):
    declared_protocol: Dict[str, Any]
    current_git_commit: Optional[str]
    integrity_status: str  # "VERIFIED" | "MODIFIED" | "UNVERSIONED"
    is_frozen_baseline: bool
    notes: str


class ProtocolVerifier:
    """Verifies runtime repository state against declared freeze protocol metadata."""

    DEFAULT_HOLDOUT_PROTOCOL = Path(__file__).resolve().parent.parent.parent / "benchmark_corpus" / "holdout" / "holdout_protocol.yaml"

    @classmethod
    def get_current_git_commit(cls) -> Optional[str]:
        try:
            res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
                cwd=str(Path(__file__).resolve().parent.parent.parent)
            )
            return res.stdout.strip()
        except Exception:
            return None

    @classmethod
    def verify_holdout_protocol(cls, protocol_path: Optional[Path | str] = None) -> ProtocolIntegrityResult:
        p_path = Path(protocol_path) if protocol_path else cls.DEFAULT_HOLDOUT_PROTOCOL
        if not p_path.exists():
            return ProtocolIntegrityResult(
                declared_protocol={},
                current_git_commit=cls.get_current_git_commit(),
                integrity_status="UNVERSIONED",
                is_frozen_baseline=False,
                notes="No protocol file found."
            )

        data = yaml.safe_load(p_path.read_text(encoding="utf-8"))
        declared_commit = data.get("freeze_commit", "")
        current_commit = cls.get_current_git_commit()

        if not current_commit:
            return ProtocolIntegrityResult(
                declared_protocol=data,
                current_git_commit=None,
                integrity_status="UNVERSIONED",
                is_frozen_baseline=False,
                notes="Git repository commit could not be determined at runtime."
            )

        if declared_commit and (current_commit.startswith(declared_commit[:7]) or declared_commit.startswith(current_commit[:7])):
            return ProtocolIntegrityResult(
                declared_protocol=data,
                current_git_commit=current_commit,
                integrity_status="VERIFIED",
                is_frozen_baseline=True,
                notes="Repository matches the declared freeze commit baseline exactly."
            )
        else:
            return ProtocolIntegrityResult(
                declared_protocol=data,
                current_git_commit=current_commit,
                integrity_status="MODIFIED",
                is_frozen_baseline=False,
                notes=f"Active commit ({current_commit[:8]}) differs from declared freeze ({declared_commit[:8] if declared_commit else 'none'})."
            )
