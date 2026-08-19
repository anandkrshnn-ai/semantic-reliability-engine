from typing import List, Optional
from pathlib import Path

from semantic_reliability.drift.rules import SemanticDrift, DriftSeverity
from semantic_reliability.harness.quality_harness import MutationBenchmark


class Reporter:
    """Generates human-readable terminal reports and GitHub PR comment markdown."""

    @staticmethod
    def generate_pr_comment_markdown(
        drifts: List[SemanticDrift],
        model_name: str = "SQL Model",
        metric_name: Optional[str] = None,
    ) -> str:
        """Generate formatted GitHub PR comment highlighting semantic drift."""
        if not drifts:
            return (
                f"### ✅ Semantic Reliability Check: `{model_name}`\n\n"
                f"No semantic drift or logic mutations detected against canonical metric definition."
            )

        highest_severity = max(
            [d.severity for d in drifts],
            key=lambda s: ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL", "FATAL"].index(s.value)
        )

        badge_emoji = {
            "FATAL": "🛑",
            "CRITICAL": "🚨",
            "HIGH": "⚠️",
            "MEDIUM": "🔍",
            "LOW": "ℹ️",
            "INFO": "📝",
        }.get(highest_severity.value, "⚠️")

        lines = [
            f"## {badge_emoji} Semantic Drift Alert: `{model_name}`",
            f"**Highest Severity:** `{highest_severity.value}` | **Drifts Identified:** `{len(drifts)}`"
            + (f" | **Target Metric:** `{metric_name}`" if metric_name else ""),
            "",
            "> ⚠️ **Warning:** This PR modifies SQL logic that alters the mathematical calculation, population filter, or reporting grain of downstream metrics.",
            "",
            "### 🔍 Detailed Drift Breakdown",
            "",
            "| Severity | Drift Type | Component | Business Impact |",
            "| :--- | :--- | :--- | :--- |",
        ]

        for d in drifts:
            lines.append(f"| **`{d.severity.value}`** | `{d.drift_type.value}` | {d.component} | {d.business_impact} |")

        lines.extend([
            "",
            "---",
            "### 📋 Exact AST Differences & Remediation",
            "",
        ])

        for idx, d in enumerate(drifts, 1):
            lines.extend([
                f"#### #{idx} - [{d.severity.value}] {d.summary}",
                f"- **Component:** `{d.component}`",
                f"- **Details:** {d.details}",
                f"- **Business Impact:** {d.business_impact}",
            ])
            if d.original_snippet or d.candidate_snippet:
                lines.extend([
                    "```diff",
                    f"- Baseline:  {d.original_snippet or '[NONE]'}",
                    f"+ Candidate: {d.candidate_snippet or '[NONE]'}",
                    "```",
                ])
            if d.remediation:
                lines.append(f"- **Recommended Action:** {d.remediation}")
            lines.append("")

        lines.extend([
            "---",
            "*Generated automatically by [Semantic Reliability Engine](https://github.com/monika/semantic-reliability-engine)*",
        ])

        return "\n".join(lines)

    @staticmethod
    def generate_benchmark_report_markdown(benchmark: MutationBenchmark, model_name: str = "SQL Model") -> str:
        """Generate comprehensive Markdown report for Chaos Mutation benchmark."""
        lines = [
            f"# 🧬 Semantic Mutation Benchmark Report: `{model_name}`",
            f"**Mutation Score:** **`{benchmark.mutation_score_pct}%`** ({benchmark.caught_mutations}/{benchmark.total_mutations} mutations caught)\n",
            "---",
            "## 📊 Mutation Catch Rate Summary",
            "",
            "| Metric | Value | Meaning |",
            "| :--- | :--- | :--- |",
            f"| **Total Injected Mutations** | `{benchmark.total_mutations}` | Number of AST-level bugs introduced |",
            f"| **Caught Mutations** | `{benchmark.caught_mutations}` | Mutations successfully caught by test suite |",
            f"| **Uncaught Mutations (Blind Spots)** | `{benchmark.uncaught_mutations}` | Mutations that produced 'silent green builds' |",
            f"| **Semantic Mutation Score** | **`{benchmark.mutation_score_pct}%`** | Overall contract robustness score |",
            "",
            "---",
            "## 🧪 Mutation Evaluations & Blind Spots",
            "",
        ]

        for idx, ev in enumerate(benchmark.evaluations, 1):
            status = "✅ CAUGHT" if ev.caught else "🚨 BLIND SPOT (UNCAUGHT)"
            mut = ev.mutation
            lines.extend([
                f"### #{idx}: {status} - `{mut.mutation_type.value}`",
                f"- **Category:** `{mut.mutation_category}`",
                f"- **Description:** {mut.description}",
                f"- **Target AST Node:** `{mut.target_node}`",
                "",
                "```sql",
                f"-- Mutated SQL Snippet",
                f"{mut.mutated_sql}",
                "```",
                "",
                "**Data Check Responses:**",
            ])
            for check_name, res in ev.check_results.items():
                chk_icon = "🛡️" if "CAUGHT" in res else ("✅" if "PASS" in res else "❌")
                lines.append(f"- {chk_icon} **{check_name}:** `{res}`")
            lines.append("")

        return "\n".join(lines)
