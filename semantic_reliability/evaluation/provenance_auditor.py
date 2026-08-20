"""Mechanical Provenance Verification Engine.

Audits external repository sourcing claims against ground-truth upstream repositories
to mechanically prevent confabulations, non-existent files, and fabricated test assertions.
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
import re
import yaml
import subprocess
import shutil
import tempfile
from pydantic import BaseModel, Field


class ProvenanceClaim(BaseModel):
    """Extracted provenance claim from YAML comments or contract metadata."""
    source_file: str
    repository: str
    organization: Optional[str] = None
    reference_path: Optional[str] = None
    commit_sha: Optional[str] = None
    claimed_symbols: List[str] = Field(default_factory=list)


class ProvenanceAuditResult(BaseModel):
    """Result of auditing a provenance claim against ground-truth upstream repository."""
    claim: ProvenanceClaim
    repo_accessible: bool
    file_exists: bool
    verified_symbols: List[str]
    missing_symbols: List[str]
    passed: bool
    reason: str


class ProvenanceAuditor:
    """Mechanical auditor for external provenance citations."""

    @staticmethod
    def extract_claims_from_yaml(file_path: Path) -> List[ProvenanceClaim]:
        """Extracts provenance claims from YAML comment headers or schema fields."""
        text = file_path.read_text(encoding="utf-8")
        claims: List[ProvenanceClaim] = []

        # 1. Check structured YAML if valid
        try:
            data = yaml.safe_load(text)
            if isinstance(data, dict):
                prov = data.get("provenance")
                if isinstance(prov, dict) and prov.get("repository"):
                    claims.append(ProvenanceClaim(
                        source_file=str(file_path),
                        repository=prov.get("repository"),
                        organization=prov.get("organization"),
                        reference_path=prov.get("reference_path"),
                        commit_sha=prov.get("commit_sha"),
                        claimed_symbols=prov.get("verified_symbols", []),
                    ))
        except Exception:
            pass

        # 2. Check comment headers: # Provenance: ...
        if not claims and "# Provenance:" in text:
            repo_match = re.search(r"#\s*Repository:\s*(\S+)", text)
            ref_match = re.search(r"#\s*Reference:\s*(.+)", text)
            org_match = re.search(r"#\s*Organization:\s*(.+)", text)

            if repo_match:
                repo_url = repo_match.group(1).strip()
                ref_path = ref_match.group(1).strip() if ref_match else None
                org_name = org_match.group(1).strip() if org_match else None

                # Extract declared column and value names from the YAML to verify against upstream
                symbols = []
                try:
                    data = yaml.safe_load(text)
                    if isinstance(data, dict) and "models" in data:
                        for m in data.get("models", []):
                            for col in m.get("columns", []):
                                if "name" in col:
                                    symbols.append(col["name"])
                                for t in col.get("tests", []):
                                    if isinstance(t, dict) and "accepted_values" in t:
                                        vals = t["accepted_values"].get("values", [])
                                        symbols.extend([str(v) for v in vals])
                except Exception:
                    pass

                claims.append(ProvenanceClaim(
                    source_file=str(file_path),
                    repository=repo_url,
                    organization=org_name,
                    reference_path=ref_path,
                    claimed_symbols=symbols,
                ))

        return claims

    @classmethod
    def verify_claim(cls, claim: ProvenanceClaim, cache_dir: Optional[Path] = None) -> ProvenanceAuditResult:
        """Clones or checks cached upstream repo to mechanically verify files and symbols."""
        # Sanitize repository URL
        repo_url = claim.repository
        if not repo_url.startswith("http") and "/" in repo_url:
            repo_url = f"https://github.com/{repo_url}"

        # Setup local cache
        base_cache = cache_dir or Path(tempfile.gettempdir()) / "sre_provenance_cache"
        base_cache.mkdir(parents=True, exist_ok=True)
        repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
        local_repo_dir = base_cache / repo_name

        # Clone or update shallow clone
        try:
            if not (local_repo_dir / ".git").exists():
                subprocess.run(
                    ["git", "clone", "--depth", "1", repo_url, str(local_repo_dir)],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            repo_accessible = True
        except Exception as e:
            return ProvenanceAuditResult(
                claim=claim,
                repo_accessible=False,
                file_exists=False,
                verified_symbols=[],
                missing_symbols=claim.claimed_symbols,
                passed=False,
                reason=f"Repository {repo_url} could not be cloned/accessed: {e}",
            )

        # Check reference path if specified
        file_exists = True
        matching_content = ""
        if claim.reference_path:
            # reference_path might be comma-separated or multiple files
            sub_paths = [p.strip() for p in claim.reference_path.split(",")]
            found_any = False
            for sp in sub_paths:
                target_file = local_repo_dir / sp
                if target_file.exists():
                    found_any = True
                    matching_content += target_file.read_text(encoding="utf-8", errors="ignore") + "\n"

            if not found_any:
                file_exists = False
                return ProvenanceAuditResult(
                    claim=claim,
                    repo_accessible=True,
                    file_exists=False,
                    verified_symbols=[],
                    missing_symbols=claim.claimed_symbols,
                    passed=False,
                    reason=f"Claimed reference file `{claim.reference_path}` does not exist in {repo_name}.",
                )
        else:
            # Concatenate all yml and sql files in the cloned repo to search
            for ext in ("*.yml", "*.yaml", "*.sql"):
                for p in local_repo_dir.rglob(ext):
                    matching_content += p.read_text(encoding="utf-8", errors="ignore") + "\n"

        # Verify symbols (columns, enum values, tests)
        verified: List[str] = []
        missing: List[str] = []
        for sym in claim.claimed_symbols:
            if sym in matching_content:
                verified.append(sym)
            else:
                missing.append(sym)

        if missing:
            return ProvenanceAuditResult(
                claim=claim,
                repo_accessible=True,
                file_exists=file_exists,
                verified_symbols=verified,
                missing_symbols=missing,
                passed=False,
                reason=f"Symbols {missing} claimed from {repo_name} were not found in {claim.reference_path or 'repository'}.",
            )

        return ProvenanceAuditResult(
            claim=claim,
            repo_accessible=True,
            file_exists=file_exists,
            verified_symbols=verified,
            missing_symbols=[],
            passed=True,
            reason=f"Successfully verified against {repo_name} ({len(verified)} symbols matched).",
        )

    @classmethod
    def audit_directory(cls, directory_path: Path) -> List[ProvenanceAuditResult]:
        """Audits all YAML and contract files in a directory."""
        results: List[ProvenanceAuditResult] = []
        for ext in ("*.yml", "*.yaml", "*.json"):
            for f in directory_path.rglob(ext):
                claims = cls.extract_claims_from_yaml(f)
                for claim in claims:
                    res = cls.verify_claim(claim)
                    results.append(res)
        return results

    @classmethod
    def audit_latex_bibliography(cls, tex_path: Path) -> Dict[str, Any]:
        """Audits LaTeX bibliography entries to ensure citations are resolvable and well-formed."""
        text = tex_path.read_text(encoding="utf-8")
        
        # 1. Extract all \cite{key1, key2}
        cited_keys = set()
        for m in re.finditer(r"\\cite\{([^}]+)\}", text):
            for k in m.group(1).split(","):
                cited_keys.add(k.strip())

        # 2. Extract all \bibitem{key}
        declared_keys = set()
        bibitem_blocks = []
        for m in re.finditer(r"\\bibitem\{([^}]+)\}(.*?)(?=\\bibitem\{|\\end\{thebibliography\}|$)", text, re.DOTALL):
            k = m.group(1).strip()
            content = m.group(2).strip()
            declared_keys.add(k)
            bibitem_blocks.append({"key": k, "content": content})

        missing_declarations = cited_keys - declared_keys
        unused_declarations = declared_keys - cited_keys

        # Check entries for year and author structure
        entry_details = []
        for b in bibitem_blocks:
            k = b["key"]
            cnt = b["content"]
            has_year = bool(re.search(r"\b(19|20)\d{2}\b", cnt))
            has_author = bool(re.search(r"[A-Z]\.~[A-Z]", cnt) or "Anthropic" in cnt or "et~al" in cnt)
            entry_details.append({
                "key": k,
                "has_year": has_year,
                "has_author": has_author,
                "valid": has_year and has_author,
            })

        passed = (len(missing_declarations) == 0) and all(e["valid"] for e in entry_details)

        return {
            "passed": passed,
            "cited_count": len(cited_keys),
            "declared_count": len(declared_keys),
            "missing_declarations": sorted(list(missing_declarations)),
            "unused_declarations": sorted(list(unused_declarations)),
            "entry_details": entry_details,
        }

