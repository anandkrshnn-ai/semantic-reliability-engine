import sys
import os
import json
from pathlib import Path
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

# Force UTF-8 on Windows consoles to prevent cp1252 charmap encoding errors
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

console = Console(force_terminal=True, legacy_windows=False)

from semantic_reliability.compiler.compiler import MetricCompiler
from semantic_reliability.compiler.contracts import SemanticContractValidator
from semantic_reliability.drift.detector import SemanticDriftDetector
from semantic_reliability.drift.rules import DriftSeverity
from semantic_reliability.mutations.engine import MutationEngine
from semantic_reliability.assertions.registry import AssertionSuite
from semantic_reliability.harness.duckdb_runner import (
    DuckDBFixtureRunner,
    MutationClassification,
)
from semantic_reliability.harness.quality_harness import QualityHarness
from semantic_reliability.harness.sarif_exporter import SARIFExporter
from semantic_reliability.harness.reporter import Reporter


@click.group()
@click.version_option(version="0.1.0")
def main():
    """Semantic Reliability Engine - Mutation Testing and Drift Detection for Data Pipelines."""
    pass


@main.command()
@click.option("--base", type=click.Path(exists=True), help="Baseline / Ground-truth SQL file")
@click.option("--candidate", type=click.Path(exists=True), required=True, help="Candidate / PR SQL file")
@click.option("--metric", type=click.Path(exists=True), help="Ground-truth metric YAML definition")
@click.option("--dialect", type=str, default=None, help="SQL dialect (e.g. snowflake, bigquery, postgres)")
@click.option("--sarif", type=click.Path(), default=None, help="Output path for GitHub Code Scanning SARIF JSON")
@click.option("--fail-on-drift/--no-fail", default=False, help="Exit with non-zero code if critical drift detected")
def check(base, candidate, metric, dialect, sarif, fail_on_drift):
    """Detect semantic drift between baseline/metric and candidate SQL."""
    if not base and not metric:
        console.print("[bold red]Error:[/bold red] You must provide either --base <sql> or --metric <yaml>")
        sys.exit(1)

    cand_sql = Path(candidate).read_text(encoding="utf-8")
    metric_name = None
    compiler = None

    if metric:
        compiler = MetricCompiler.from_yaml_file(metric)
        base_sql = compiler.get_ground_truth_sql()
        metric_name = compiler.definition.metric
    else:
        base_sql = Path(base).read_text(encoding="utf-8")

    console.print(Panel(
        f"[bold cyan]Comparing Candidate SQL:[/bold cyan] {candidate}\n"
        f"[bold cyan]Against Baseline:[/bold cyan] {metric or base}"
        + (f" [bold magenta]({metric_name})[/bold magenta]" if metric_name else ""),
        title="[bold green]Semantic Reliability Engine — Drift Inspection[/bold green]",
        border_style="cyan"
    ))

    drifts = SemanticDriftDetector.analyze(base_sql, cand_sql, dialect=dialect)

    # Validate declared invariant contracts if present
    contract_violations = []
    if compiler and compiler.definition.invariants:
        contract_res = SemanticContractValidator.validate(cand_sql, compiler.definition, dialect=dialect)
        if not contract_res.passed:
            contract_violations = contract_res.violations

    if not drifts and not contract_violations:
        console.print("\n[bold green]✓ No Semantic Drift Detected.[/bold green] Candidate SQL matches baseline relational logic and contracts.\n")
        return

    if drifts:
        table = Table(title=f"🚨 Detected {len(drifts)} Semantic Drift Anomaly(ies)", show_header=True, header_style="bold magenta")
        table.add_column("Severity", style="bold", width=12)
        table.add_column("Drift Type", width=25)
        table.add_column("Component", width=30)
        table.add_column("Business Impact", width=45)

        severity_colors = {
            DriftSeverity.FATAL: "red on black",
            DriftSeverity.CRITICAL: "bold red",
            DriftSeverity.HIGH: "yellow",
            DriftSeverity.MEDIUM: "cyan",
            DriftSeverity.LOW: "blue",
            DriftSeverity.INFO: "dim",
        }

        for d in drifts:
            color = severity_colors.get(d.severity, "white")
            table.add_row(
                f"[{color}]{d.severity.value}[/{color}]",
                d.drift_type.value,
                d.component,
                d.business_impact,
            )
        console.print(table)

    if contract_violations:
        c_table = Table(title=f"📜 Invariant Contract Violations ({len(contract_violations)})", show_header=True, header_style="bold red")
        c_table.add_column("Category", width=25)
        c_table.add_column("Rule", width=30)
        c_table.add_column("Details", width=50)
        for cv in contract_violations:
            c_table.add_row(cv.invariant_category, cv.invariant_rule, cv.details)
        console.print(c_table)

    if sarif:
        SARIFExporter.export_to_file(drifts, sarif, file_path=candidate)
        console.print(f"[bold green]Saved SARIF 2.1.0 report to:[/bold green] {sarif}")

    if fail_on_drift and (
        any(d.severity in (DriftSeverity.FATAL, DriftSeverity.CRITICAL, DriftSeverity.HIGH) for d in drifts)
        or len(contract_violations) > 0
    ):
        sys.exit(1)


@main.command()
@click.option("--sql", type=click.Path(exists=True), required=True, help="Target SQL file to mutate")
@click.option("--output-dir", type=click.Path(), default="mutations_output", help="Directory to save mutated SQL files")
@click.option("--dialect", type=str, default=None, help="SQL dialect")
def mutate(sql, output_dir, dialect):
    """Generate AST chaos mutations for data pipeline testing."""
    sql_text = Path(sql).read_text(encoding="utf-8")
    mutator = MutationEngine(sql_text, dialect=dialect)
    mutations = mutator.generate_all_mutations()

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    console.print(Panel(
        f"[bold green]Generating Chaos Mutations for:[/bold green] {sql}\n"
        f"[bold green]Output Directory:[/bold green] {output_dir}\n"
        f"[bold green]Mutations Generated:[/bold green] {len(mutations)}",
        title="[bold yellow]SQL AST Mutation Engine[/bold yellow]"
    ))

    manifest = []
    for idx, mut in enumerate(mutations, 1):
        filename = f"mutation_{idx:02d}_{mut.mutation_type.value.lower()}.sql"
        file_path = out_path / filename
        file_path.write_text(mut.mutated_sql, encoding="utf-8")

        manifest.append({
            "index": idx,
            "filename": filename,
            "mutation_type": mut.mutation_type.value,
            "category": mut.mutation_category,
            "description": mut.description,
            "target_node": mut.target_node,
        })
        console.print(f"  [cyan]✓ Injected #{idx:02d}:[/cyan] [{mut.mutation_type.value}] -> {filename}")

    manifest_path = out_path / "mutations_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    console.print(f"\n[bold green]Saved manifest to:[/bold green] {manifest_path}\n")


@main.command()
@click.option("--sql", type=click.Path(exists=True), required=True, help="Target SQL model to evaluate")
@click.option("--assertions", type=click.Path(exists=True), default=None, help="YAML assertions suite file")
@click.option("--compare/--no-compare", default=False, help="Run comparative benchmark: Standard dbt checks vs Semantic suite")
@click.option("--dialect", type=str, default=None, help="SQL dialect")
@click.option("--report", type=click.Path(), default=None, help="Optional Markdown report output file")
def benchmark(sql, assertions, compare, dialect, report):
    """Benchmark test suite catch rate against injected AST mutations."""
    sql_text = Path(sql).read_text(encoding="utf-8")
    mutator = MutationEngine(sql_text, dialect=dialect)
    mutations = mutator.generate_all_mutations()
    runner = DuckDBFixtureRunner()

    if compare:
        # Run head-to-head comparison
        dbt_suite = AssertionSuite.get_standard_structural_suite()
        semantic_suite = AssertionSuite.get_semantic_assertion_suite()

        dbt_rep = runner.run_assertion_benchmark(sql_text, mutations, dbt_suite)
        sem_rep = runner.run_assertion_benchmark(sql_text, mutations, semantic_suite)

        console.print(Panel(
            f"[bold red]Standard Data Quality Suite (dbt-style):[/bold red] Catch Score: [bold]{dbt_rep.effective_catch_score_pct}%[/bold] "
            f"({dbt_rep.detected_by_assertions_count}/{dbt_rep.valid_defects_count} caught, [bold red]{dbt_rep.surviving_defects_count} surviving defects[/bold red])\n"
            f"[bold green]Semantic Reliability Suite:[/bold green] Catch Score: [bold]{sem_rep.effective_catch_score_pct}%[/bold] "
            f"({sem_rep.detected_by_assertions_count}/{sem_rep.valid_defects_count} caught, [bold green]{sem_rep.surviving_defects_count} surviving defects[/bold green])",
            title="[bold yellow]🔥 Comparative Benchmark: Standard Data Tests vs Semantic Mutations[/bold yellow]"
        ))

        table = Table(title="Mutation Detection Breakdown (Head-to-Head)", show_header=True, header_style="bold cyan")
        table.add_column("Mutation", width=18)
        table.add_column("Row Δ", width=8)
        table.add_column("Variance %", width=12)
        table.add_column("Standard Tests", width=18)
        table.add_column("Semantic Tests", width=22)

        for d_eval, s_eval in zip(dbt_rep.evaluations, sem_rep.evaluations):
            std_status = "[bold green]CAUGHT[/bold green]" if d_eval.classification != MutationClassification.VALID_DEFECT_SURVIVED else "[bold red]SURVIVED (PASSED)[/bold red]"
            sem_status = "[bold green]CAUGHT[/bold green]" if s_eval.classification != MutationClassification.VALID_DEFECT_SURVIVED else "[bold red]SURVIVED[/bold red]"
            if d_eval.classification == MutationClassification.EQUIVALENT_ON_FIXTURE:
                std_status = "[dim]EQUIVALENT[/dim]"
                sem_status = "[dim]EQUIVALENT[/dim]"

            table.add_row(
                d_eval.mutation_type,
                f"{d_eval.row_count_delta:+d}",
                f"{d_eval.empirical_variance_pct:.1f}%",
                std_status,
                sem_status,
            )
        console.print(table)

        if dbt_rep.surviving_defects_count > 0:
            console.print("\n[bold red]🚨 Critical Surviving Defects in Standard Test Suite:[/bold red]")
            for s in dbt_rep.surviving_defect_summaries:
                console.print(f"  • {s}")
        return

    # Single suite benchmark
    suite = AssertionSuite.from_yaml_file(assertions) if assertions else AssertionSuite.get_standard_structural_suite()
    rep = runner.run_assertion_benchmark(sql_text, mutations, suite)

    console.print(Panel(
        f"[bold]Assertion Suite:[/bold] {rep.suite_name}\n"
        f"[bold]Total Mutations Generated:[/bold] {rep.total_mutations_generated}\n"
        f"[bold cyan]Equivalent Mutations (Zero Variance):[/bold cyan] {rep.equivalent_mutations_count}\n"
        f"[bold]Executable Valid Defects (Denominator):[/bold] {rep.valid_defects_count}\n"
        f"[bold green]Detected by Assertions:[/bold green] {rep.detected_by_assertions_count}\n"
        f"[bold red]Surviving Undetected Defects:[/bold red] {rep.surviving_defects_count}\n"
        f"[bold yellow]Effective Catch Score:[/bold yellow] [bold]{rep.effective_catch_score_pct}%[/bold]",
        title=f"[bold cyan]Assertion-Aware Mutation Benchmark: {rep.suite_name}[/bold cyan]"
    ))

    table = Table(title="Evaluated Mutations", show_header=True, header_style="bold cyan")
    table.add_column("ID", width=8)
    table.add_column("Mutation Type", width=20)
    table.add_column("Classification", width=25)
    table.add_column("Row Δ", width=8)
    table.add_column("Variance %", width=12)
    table.add_column("Summary", width=40)

    for ev in rep.evaluations:
        class_style = {
            MutationClassification.VALID_DEFECT_DETECTED: "bold green",
            MutationClassification.RUNTIME_ERROR: "green",
            MutationClassification.VALID_DEFECT_SURVIVED: "bold red",
            MutationClassification.EQUIVALENT_ON_FIXTURE: "dim",
        }.get(ev.classification, "white")

        table.add_row(
            ev.mutation_id,
            ev.mutation_type,
            f"[{class_style}]{ev.classification.value}[/{class_style}]",
            f"{ev.row_count_delta:+d}",
            f"{ev.empirical_variance_pct:.1f}%",
            ev.summary,
        )
    console.print(table)

    if rep.surviving_defects_count > 0:
        console.print(f"\n[bold red]Surviving Defects ({rep.surviving_defects_count}):[/bold red]")
        for s in rep.surviving_defect_summaries:
            console.print(f"  • [red]{s}[/red]")

    if report:
        sim_res = QualityHarness.evaluate_model(sql_text, dialect=dialect)
        md = Reporter.generate_benchmark_report_markdown(sim_res, model_name=Path(sql).name)
        Path(report).write_text(md, encoding="utf-8")
        console.print(f"\n[bold green]Report saved to:[/bold green] {report}\n")


@main.command(name="benchmark-corpus")
@click.option("--corpus", type=click.Path(exists=True), default="benchmark_corpus", help="Path to benchmark corpus directory")
@click.option("--split", type=click.Choice(["all", "dev", "holdout"]), default="all", help="Corpus track to evaluate")
@click.option("--error-analysis", is_flag=True, default=False, help="Display surviving defect root-cause error analysis")
@click.option("--json-out", type=click.Path(), default=None, help="Machine-readable JSON output path")
@click.option("--report", type=click.Path(), default=None, help="Markdown report output path")
def benchmark_corpus(corpus, split, error_analysis, json_out, report):
    """Execute multi-model cross-evaluation across Development and Frozen Holdout benchmark tracks."""
    corpus_p = Path(corpus)

    from semantic_reliability.adapters.dbt_adapter import DBTTestAdapter
    from semantic_reliability.harness.fixture_adequacy import FixtureAdequacyChecker
    from semantic_reliability.compiler.coverage import SemanticCoverageCalculator
    from semantic_reliability.harness.validity import BenchmarkValidityEvaluator
    from semantic_reliability.harness.protocol_verifier import ProtocolVerifier
    from semantic_reliability.harness.error_analysis import SurvivingDefectTaxonomy

    proto_res = ProtocolVerifier.verify_holdout_protocol()
    proto_badge = f"[{'bold green' if proto_res.integrity_status == 'VERIFIED' else 'bold yellow'}]{proto_res.integrity_status}[/]"

    tracks = []
    if split in ("dev", "all") and (corpus_p / "dev").exists():
        tracks.append(("Development Track (8 Models)", sorted([d for d in (corpus_p / "dev").iterdir() if d.is_dir()])))
    if split in ("holdout", "all") and (corpus_p / "holdout").exists():
        tracks.append(("Frozen Holdout Track (6 Models)", sorted([d for d in (corpus_p / "holdout").iterdir() if d.is_dir()])))

    # Fallback if corpus directory structure is flat
    if not tracks:
        tracks.append(("Benchmark Corpus", sorted([d for d in corpus_p.iterdir() if d.is_dir()])))

    console.print(Panel(
        f"[bold cyan]Corpus Root:[/bold cyan] {corpus_p}\n"
        f"[bold cyan]Track Selection:[/bold cyan] {split.upper()}\n"
        f"[bold cyan]Freeze Integrity:[/bold cyan] {proto_badge} ({proto_res.notes})\n"
        f"[bold cyan]Scientific Policy:[/bold cyan] Validity Policy v1.0 (OASIS Analytics Standard)",
        title="[bold yellow]🏆 Multi-Model Semantic Mutation Benchmark & Scientific Validity[/bold yellow]"
    ))

    matrix_rows = []

    for track_title, model_dirs in tracks:
        table = Table(title=f"Benchmark Matrix: {track_title}", show_header=True, header_style="bold magenta")
        table.add_column("Model / Metric", width=22)
        table.add_column("Mut (Valid)", width=12, justify="right")
        table.add_column("Std Catch", width=14, justify="right")
        table.add_column("Sem Catch", width=14, justify="right")
        table.add_column("Gain (Δ)", width=10, justify="right")
        table.add_column("Contract", width=9, justify="right")
        table.add_column("Adequacy", width=9, justify="right")
        table.add_column("Validity & Confidence", width=22)

        track_std_catches = []
        track_sem_catches = []
        track_gains = []

        for m_dir in model_dirs:
            sql_files = list(m_dir.glob("model_*.sql"))
            csv_files = list(m_dir.glob("*.csv"))
            sem_yaml = m_dir / "semantic_assertions.yaml"
            dbt_yaml = m_dir / "schema.yml"
            contract_yaml = m_dir / "contract.yaml"

            if not sql_files or not csv_files:
                continue

            sql_file = sql_files[0]
            csv_file = csv_files[0]
            model_id = m_dir.name
            table_name = csv_file.stem
            sql_text = sql_file.read_text(encoding="utf-8")

            # 1. Load runner and audit fixture adequacy
            runner = DuckDBFixtureRunner(fixtures={table_name: csv_file})
            ad_report = FixtureAdequacyChecker.audit_fixture(runner.con, table_name=table_name)

            # 2. Evaluate contract coverage
            contract_cov = 50.0
            if contract_yaml.exists():
                comp = MetricCompiler.from_yaml_file(contract_yaml)
                cov_rep = SemanticCoverageCalculator.evaluate_contract(comp.definition)
                contract_cov = cov_rep.coverage_score_pct

            # 3. Run mutations & assertion suites
            mutator = MutationEngine(sql_text)
            mutations = mutator.generate_all_mutations()

            dbt_audit = DBTTestAdapter.parse_schema_yml_with_audit(dbt_yaml) if dbt_yaml.exists() else None
            dbt_suite = dbt_audit.suite if dbt_audit else AssertionSuite.get_standard_structural_suite()
            sem_suite = AssertionSuite.from_yaml_file(sem_yaml) if sem_yaml.exists() else AssertionSuite.get_semantic_assertion_suite()

            dbt_rep = runner.run_assertion_benchmark(sql_text, mutations, dbt_suite)
            sem_rep = runner.run_assertion_benchmark(sql_text, mutations, sem_suite)

            # 4. Evaluate scientific validity & incremental gain
            val_eval = BenchmarkValidityEvaluator.evaluate(
                model_id=model_id,
                standard_catch_pct=dbt_rep.effective_catch_score_pct,
                semantic_catch_pct=sem_rep.effective_catch_score_pct,
                fixture_adequacy_pct=ad_report.adequacy_score_pct,
                contract_coverage_pct=contract_cov,
                total_mutations_generated=dbt_rep.total_mutations_generated,
                executable_mutations_count=dbt_rep.executable_mutations_count,
                equivalent_mutations_count=dbt_rep.equivalent_mutations_count,
                valid_defects_count=dbt_rep.valid_defects_count,
                standard_detected_count=dbt_rep.detected_by_assertions_count,
                standard_surviving_count=dbt_rep.surviving_defects_count,
                semantic_detected_count=sem_rep.detected_by_assertions_count,
                semantic_surviving_count=sem_rep.surviving_defects_count,
            )

            gain_str = f"+{val_eval.incremental_gain_pct:.1f}%" if val_eval.incremental_gain_pct > 0 else f"{val_eval.incremental_gain_pct:.1f}%"
            val_badge = f"[{'green' if val_eval.validity.value == 'CONCLUSIVE' else 'yellow'}]{val_eval.validity.value}[/] ({val_eval.confidence.value})"

            table.add_row(
                model_id.replace("_", " ").title(),
                f"{dbt_rep.valid_defects_count} / {dbt_rep.total_mutations_generated}",
                f"{dbt_rep.effective_catch_score_pct:.1f}% ({dbt_rep.detected_by_assertions_count} caught)",
                f"{sem_rep.effective_catch_score_pct:.1f}% ({sem_rep.detected_by_assertions_count} caught)",
                f"[bold cyan]{gain_str}[/bold cyan]",
                f"{contract_cov:.0f}%",
                f"{ad_report.adequacy_score_pct:.0f}%",
                val_badge,
            )

            track_std_catches.append(dbt_rep.effective_catch_score_pct)
            track_sem_catches.append(sem_rep.effective_catch_score_pct)
            track_gains.append(val_eval.incremental_gain_pct)

            matrix_rows.append({
                "track": track_title,
                "model": model_id,
                "mutations_generated": dbt_rep.total_mutations_generated,
                "valid_defects": dbt_rep.valid_defects_count,
                "equivalent_on_fixture": dbt_rep.equivalent_mutations_count,
                "standard_catch_pct": dbt_rep.effective_catch_score_pct,
                "semantic_catch_pct": sem_rep.effective_catch_score_pct,
                "incremental_gain_pct": val_eval.incremental_gain_pct,
                "contract_coverage_pct": contract_cov,
                "fixture_adequacy_pct": ad_report.adequacy_score_pct,
                "confidence": val_eval.confidence.value,
                "validity": val_eval.validity.value,
                "standard_surviving_defects": dbt_rep.surviving_defects_count,
                "semantic_surviving_defects": sem_rep.surviving_defects_count,
                "skipped_dbt_tests": dbt_audit.skipped_test_names if dbt_audit else [],
            })

        avg_std = sum(track_std_catches) / len(track_std_catches) if track_std_catches else 0.0
        avg_sem = sum(track_sem_catches) / len(track_sem_catches) if track_sem_catches else 0.0
        avg_gain = sum(track_gains) / len(track_gains) if track_gains else 0.0

        table.add_section()
        table.add_row(
            "[bold]Track Average[/bold]",
            "-",
            f"[bold]{avg_std:.1f}%[/bold]",
            f"[bold]{avg_sem:.1f}%[/bold]",
            f"[bold cyan]+{avg_gain:.1f}%[/bold cyan]",
            "-",
            "-",
            "[bold green]SUMMARY[/bold green]",
        )
        console.print(table)
        console.print()

    if error_analysis:
        ea_table = Table(title="🔍 Holdout Surviving Defect Root-Cause Taxonomy & Remediation", show_header=True, header_style="bold yellow")
        ea_table.add_column("Mutation ID", width=14)
        ea_table.add_column("Model", width=22)
        ea_table.add_column("Operator", width=16)
        ea_table.add_column("Root Cause Category", width=20)
        ea_table.add_column("Severity", width=10)
        ea_table.add_column("Recommended Remediation", width=36)

        for d in SurvivingDefectTaxonomy.get_defect_analysis():
            sev_color = "red" if d.severity.value in ("CRITICAL", "HIGH") else "yellow"
            ea_table.add_row(
                d.mutation_id,
                d.model.replace("_", " ").title(),
                d.operator,
                f"[cyan]{d.root_cause_category.value}[/cyan]\n[dim]{d.root_cause_code}[/dim]",
                f"[{sev_color}]{d.severity.value}[/]",
                d.recommended_assertion,
            )
        console.print(ea_table)
        console.print()

    if json_out:
        Path(json_out).write_text(json.dumps(matrix_rows, indent=2), encoding="utf-8")
        console.print(f"[bold green]Saved machine-readable JSON results to:[/bold green] {json_out}")

    if report:
        lines = [
            "# Multi-Model Scientific Semantic Mutation Benchmark Report\n",
            "| Track | Model | Valid Defects | Standard Catch | Semantic Catch | Incremental Gain | Contract Cov | Fixture Adequacy | Validity & Confidence |",
            "| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | :--- |",
        ]
        for r in matrix_rows:
            gain = f"+{r['incremental_gain_pct']:.1f}%" if r['incremental_gain_pct'] > 0 else f"{r['incremental_gain_pct']:.1f}%"
            lines.append(f"| {r['track']} | {r['model']} | {r['valid_defects']} | {r['standard_catch_pct']:.1f}% | {r['semantic_catch_pct']:.1f}% | {gain} | {r['contract_coverage_pct']:.0f}% | {r['fixture_adequacy_pct']:.0f}% | {r['validity']} ({r['confidence']}) |")
        Path(report).write_text("\n".join(lines), encoding="utf-8")
        console.print(f"[bold green]Saved Markdown report to:[/bold green] {report}\n")


@main.command(name="evaluate-agent")
@click.option("--sql", type=click.Path(exists=True), required=True, help="Path to agent-generated SQL file")
@click.option("--contract", type=click.Path(exists=True), required=True, help="Path to semantic metric contract YAML")
@click.option("--fixture", type=click.Path(exists=True), default=None, help="Path to test fixture CSV")
@click.option("--assertions", type=click.Path(exists=True), default=None, help="Path to semantic assertions YAML")
def evaluate_agent(sql, contract, fixture, assertions):
    """Evaluate agent-generated SQL against declared business semantic contracts and assertion test suites."""
    from semantic_reliability.evaluation.agent_eval import AgentSQLEvaluator
    from semantic_reliability.compiler.compiler import MetricCompiler
    from semantic_reliability.assertions.registry import AssertionSuite

    sql_text = Path(sql).read_text(encoding="utf-8")
    compiler = MetricCompiler.from_yaml_file(contract)
    metric_def = compiler.definition

    fixtures = {Path(fixture).stem: fixture} if fixture else None
    suite = AssertionSuite.from_yaml_file(assertions) if assertions else None

    report = AgentSQLEvaluator.evaluate(
        candidate_sql=sql_text,
        metric_def=metric_def,
        fixtures=fixtures,
        assertion_suite=suite,
    )

    color = "green" if report.verdict == "ACCEPTED_SEMANTICALLY_COMPLIANT" else "red"
    console.print(Panel(
        f"[bold]Metric ID:[/bold] {report.metric_id}\n"
        f"[bold]Verdict:[/bold] [{color}]{report.verdict}[/{color}]\n"
        f"[bold]Semantic Risk:[/bold] {report.semantic_risk.value}\n"
        f"[bold]Execution Success:[/bold] {report.execution_success} ({report.row_count} rows)\n"
        f"[bold]Contract Compliant:[/bold] {report.contract_compliant}",
        title=f"🤖 [bold yellow]Agentic Analytics SQL Semantic Evaluation[/bold yellow]"
    ))

    if report.violations:
        console.print("[bold red]Contract Invariant Violations:[/bold red]")
        for v in report.violations:
            console.print(f"  ❌ {v}")
        console.print()

    if report.assertion_failures:
        console.print("[bold yellow]Data Assertion Failures:[/bold yellow]")
        for a in report.assertion_failures:
            console.print(f"  ⚠️ {a}")
        console.print()

    if report.unsupported_assumptions:
        console.print("[bold magenta]Unsupported Agent Assumptions:[/bold magenta]")
        for ua in report.unsupported_assumptions:
            console.print(f"  💡 {ua}")
        console.print()


@main.command(name="pr-comment")
@click.option("--base", type=click.Path(exists=True), help="Baseline SQL file")
@click.option("--candidate", type=click.Path(exists=True), required=True, help="Candidate / PR SQL file")
@click.option("--metric", type=click.Path(exists=True), help="Metric YAML file")
@click.option("--output", type=click.Path(), default="pr_comment.md", help="Output markdown path")
def pr_comment(base, candidate, metric, output):
    """Generate GitHub PR Review bot markdown comment."""
    if not base and not metric:
        console.print("[bold red]Error:[/bold red] You must provide either --base <sql> or --metric <yaml>")
        sys.exit(1)

    cand_sql = Path(candidate).read_text(encoding="utf-8")
    metric_name = None

    if metric:
        compiler = MetricCompiler.from_yaml_file(metric)
        base_sql = compiler.get_ground_truth_sql()
        metric_name = compiler.definition.metric
    else:
        base_sql = Path(base).read_text(encoding="utf-8")

    drifts = SemanticDriftDetector.analyze(base_sql, cand_sql)
    md = Reporter.generate_pr_comment_markdown(drifts, model_name=Path(candidate).name, metric_name=metric_name)

    Path(output).write_text(md, encoding="utf-8")
    console.print(f"[bold green]PR Review comment written to:[/bold green] {output}")


@main.command()
@click.option("--metric", type=click.Path(exists=True), required=True, help="Metric YAML file")
@click.option("--target-dialect", type=str, default=None, help="Target transpilation dialect")
def compile(metric, target_dialect):
    """Compile canonical metric definition into standard SQL."""
    comp = MetricCompiler.from_yaml_file(metric)
    sql_out = comp.get_ground_truth_sql(target_dialect=target_dialect)

    console.print(Panel(
        f"[bold]Metric:[/bold] {comp.definition.metric}\n"
        f"[bold]Owner:[/bold] {comp.definition.owner}\n"
        f"[bold]Grain:[/bold] {comp.definition.grain}\n"
        f"[bold]Dialect:[/bold] {target_dialect or comp.definition.dialect}",
        title="[bold green]Compiled Business Metric[/bold green]"
    ))
@main.command()
@click.option("--contract", type=click.Path(exists=True), required=True, help="Metric YAML definition with declarative probes")
@click.option("--fixture", type=click.Path(exists=True), required=True, help="CSV fixture or DuckDB snapshot table")
@click.option("--table-name", type=str, default="transactions", help="Database table name (default: transactions)")
@click.option("--fail-on-critical/--no-fail", default=False, help="Exit non-zero on CRITICAL probe signal")
def probe(contract, fixture, table_name, fail_on_critical):
    """Execute declarative statistical probes to detect silent upstream data reality shifts."""
    import yaml
    import duckdb
    from semantic_reliability.compiler.schema import MetricDefinition
    from semantic_reliability.probes.engine import StatisticalProbeEngine

    data = yaml.safe_load(Path(contract).read_text(encoding="utf-8"))
    metric_def = MetricDefinition(**data)

    console.print(f"\n🔍 [bold cyan]Scanning Semantic Reality for metric '{metric_def.metric}' against {Path(fixture).name}...[/bold cyan]\n")

    con = duckdb.connect(":memory:")
    con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM read_csv_auto('{fixture}')")

    engine = StatisticalProbeEngine(conn=con, table_name=table_name)
    alerts = engine.run_all(metric_def)

    if not alerts:
        console.print(f"[bold green]✅ Semantic Reality Stable for metric '{metric_def.metric}'[/bold green]\n")
        con.close()
        return

    console.print(f"[bold red]🚨 {len(alerts)} Semantic Probe Alert(s) for metric '{metric_def.metric}':[/bold red]\n")
    for alert in alerts:
        border_color = "red" if alert.confidence == "high" else "yellow"
        causes_text = "\n".join(f"- {c}" for c in alert.likely_causes)
        console.print(Panel(
            f"[bold]Baseline:[/bold] {alert.baseline:.2%}\n"
            f"[bold]Current Rate:[/bold] {alert.current:.2%}\n"
            f"[bold]Relative Change:[/bold] {alert.relative_change:+.1f}%\n"
            f"[bold]Action Required:[/bold] {alert.action_required}\n\n"
            f"[italic bold]Likely Causes:[/italic bold]\n{causes_text}",
            title=f"[{alert.confidence.upper()}] {alert.signal_type}",
            border_style=border_color
        ))
        console.print()

    con.close()

@main.command(name="export-gym")
@click.option("--corpus", required=True, type=click.Path(exists=True), help="Directory containing YAML metric contracts")
@click.option("--split", "split_name", required=True, type=click.Choice(["train", "validation", "holdout", "all"], case_sensitive=False), default="all", help="Structured split filter")
@click.option("--format", "fmt", required=True, type=click.Choice(["dpo", "sft", "rlhf"], case_sensitive=False), default="dpo", help="Training dataset format")
@click.option("--output", required=True, type=click.Path(), default="datasets/sre-train.jsonl", help="Output JSONL filepath")
def export_gym(corpus, split_name, fmt, output):
    """Export contract-grounded preference and alignment datasets for AI agents."""
    from semantic_reliability.gym.generator import GymGenerator
    from semantic_reliability.gym.formatters import get_formatter

    generator = GymGenerator(corpus, policy_version="v1.0.0-phase8.4")
    examples = generator.generate(split_name)
    formatter = get_formatter(fmt)

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(formatter.format(ex)) + "\n")

    console.print(f"[bold green]✅ Exported {len(examples)} pairs to {out_path}[/bold green]\n")
    console.print("[bold]Rejection Summary:[/bold]")
    for reason, count in generator.rejection_counts.items():
        val = reason.value if hasattr(reason, "value") else str(reason)
        console.print(f"  {val}: {count}")


@main.command(name="audit-gym")
@click.option("--dataset", required=True, type=click.Path(exists=True), help="Path to exported JSONL dataset")
@click.option("--output", "json_out", type=click.Path(), default=None, help="Optional JSON audit report output path")
def audit_gym_cli(dataset, json_out):
    """Run formal static and statistical audit on exported Semantic Gym dataset."""
    from semantic_reliability.gym.auditor import audit_gym_dataset

    console.print(f"\n🔍 [bold cyan]Auditing Semantic Gym Dataset:[/bold cyan] [bold]{Path(dataset).name}[/bold]...\n")
    report = audit_gym_dataset(dataset)

    status_color = "bold green" if report.is_clean else "bold red"
    status_text = "PASSED (CLEAN)" if report.is_clean else "FAILED (ANOMALIES DETECTED)"

    console.print(f"[{status_color}]Audit Status: {status_text}[/{status_color}]\n")
    console.print(f"[bold]Integrity & Leakage Checks:[/bold]")
    console.print(f"  Total records: {report.total_records}")
    console.print(f"  Duplicate example IDs: {report.duplicate_example_ids}")
    console.print(f"  Duplicate evidence hashes: {report.duplicate_evidence_hashes}")
    console.print(f"  Conflicting preference labels: {report.conflicting_preference_labels}")
    console.print(f"  Chosen/rejected identical: {report.chosen_rejected_identical}")
    console.print(f"  Missing evidence: {report.missing_evidence}")
    console.print(f"  Mutation-family leakage: {report.mutation_family_leakage}")
    console.print(f"  Metric-family leakage: {report.metric_family_leakage}")
    console.print(f"  Domain leakage: {report.domain_leakage}")

    console.print(f"\n[bold]Mutation Distribution:[/bold]")
    for k, v in report.mutation_distribution.items():
        console.print(f"  {k}: {v:.1f}%")

    console.print(f"\n[bold]Difficulty Distribution:[/bold]")
    for k, v in report.difficulty_distribution.items():
        console.print(f"  {k}: {v:.1f}%")

    console.print(f"\n[bold]Split Distribution:[/bold]")
    for k, v in report.split_distribution.items():
        console.print(f"  {k}: {v:.1f}%")

    if json_out:
        out_p = Path(json_out)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(report.model_dump(), indent=2), encoding="utf-8")
        console.print(f"\n[green]Audit report saved to:[/green] [bold]{json_out}[/bold]")

    console.print()
    if not report.is_clean:
        sys.exit(1)


@main.command(name="bq-evaluate")
@click.option("--sql", required=True, help="Path to SQL file or raw SQL string")
@click.option("--contract", required=True, type=click.Path(exists=True), help="Metric contract YAML")
@click.option("--project-id", default=None, help="GCP Project ID (optional)")
def bq_evaluate(sql, contract, project_id):
    """Evaluate SQL against BigQuery dry-run and semantic contract."""
    from semantic_reliability.adapters.bigquery import BigQueryDryRunAdapter
    from semantic_reliability.compiler.compiler import MetricCompiler

    contract_text = Path(contract).read_text(encoding="utf-8")
    compiler = MetricCompiler.from_yaml_str(contract_text)
    metric = compiler.definition

    sql_path = Path(sql)
    if sql_path.exists():
        sql_content = sql_path.read_text(encoding="utf-8")
    else:
        sql_content = sql

    adapter = BigQueryDryRunAdapter(project_id=project_id)
    result = adapter.evaluate(sql_content, metric, dialect="bigquery")

    click.echo(json.dumps(result, indent=2))

    if result["decision"] == "DENY":
        sys.exit(1)
    elif result["decision"] == "REQUIRE_REVIEW":
        sys.exit(2)
    sys.exit(0)


@main.command(name="dbt-check")
@click.option("--manifest", required=True, type=click.Path(exists=True), help="Path to target/manifest.json")
@click.option("--model", required=True, help="dbt model name to check")
@click.option("--contract", required=True, type=click.Path(exists=True), help="Metric contract YAML")
@click.option("--fail-on", type=click.Choice(["critical", "high", "any"]), default="critical")
@click.option("--output-json", type=click.Path(), default=None)
@click.option("--output-sarif", type=click.Path(), default=None)
def dbt_check(manifest, model, contract, fail_on, output_json, output_sarif):
    """Check a compiled dbt model for semantic drift against a metric contract."""
    from semantic_reliability.adapters.dbt_integration import DbtSreChecker
    from semantic_reliability.harness.sarif_exporter import SARIFExporter
    from semantic_reliability.drift.rules import DriftSeverity, SemanticDrift

    checker = DbtSreChecker(manifest)
    result = checker.check(model, contract)

    drifts = [SemanticDrift(**d) for d in result["drift_alerts"]]

    if output_json:
        out_p = Path(output_json)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(result, indent=2), encoding="utf-8")
        click.echo(f"JSON report written to {output_json}")

    if output_sarif:
        SARIFExporter.export_to_file(drifts, output_sarif, file_path=f"models/{model}.sql")
        click.echo(f"SARIF report written to {output_sarif}")

    sev_rank = {
        "critical": DriftSeverity.CRITICAL,
        "high": DriftSeverity.HIGH,
        "any": DriftSeverity.LOW,
    }
    threshold = sev_rank[fail_on]

    sev_order = {
        DriftSeverity.INFO: 0,
        DriftSeverity.LOW: 1,
        DriftSeverity.MEDIUM: 2,
        DriftSeverity.HIGH: 3,
        DriftSeverity.CRITICAL: 4,
        DriftSeverity.FATAL: 5,
    }

    if any(sev_order.get(d.severity, 0) >= sev_order.get(threshold, 0) for d in drifts):
        click.echo(f"❌ CI BLOCKED: Semantic drift detected at or above {threshold.value} severity.")
        sys.exit(1)

    click.echo(f"✅ dbt model '{model}' is semantically compliant with contract '{result['contract']}'.")
    sys.exit(0)


@main.command(name="mcp-serve")
@click.option("--contracts", default="benchmark_corpus", help="Path to SCOS contracts directory")
def mcp_serve(contracts):
    """Start the standard JSON-RPC 2.0 SCOS Model Context Protocol (MCP) Server."""
    from semantic_reliability.mcp.server import ScosMcpServer
    from semantic_reliability.firewall.engine import ContractRegistry

    registry = ContractRegistry()
    c_path = Path(contracts)
    if c_path.exists():
        for y_path in c_path.rglob("*.yaml"):
            try:
                from semantic_reliability.compiler.compiler import MetricCompiler
                comp = MetricCompiler.from_yaml_file(y_path)
                registry.register(comp.definition)
            except Exception:
                pass

    server = ScosMcpServer(registry=registry)
    server.run_stdio()


@main.command(name="benchmark-replay")
@click.option("--trajectories", required=True, help="Path to input JSONL trajectories file")
@click.option("--contracts", default="benchmark_corpus", help="Path to SCOS contracts directory")
@click.option("--artifacts-dir", default="artifacts/benchmark", help="Path to local raw SQL artifacts directory")
@click.option("--output", default=None, help="Optional output JSON scorecard file")
def benchmark_replay(trajectories, contracts, artifacts_dir, output):
    """Replay recorded agent trajectories against active SCOS contracts."""
    from semantic_reliability.benchmark.replay import load_trajectories, TrajectoryReplayEngine
    from semantic_reliability.benchmark.scenarios import SCENARIOS
    from semantic_reliability.firewall.engine import ContractRegistry
    from semantic_reliability.compiler.compiler import MetricCompiler

    registry = ContractRegistry()
    c_path = Path(contracts)
    if c_path.exists():
        for y_path in c_path.rglob("*.yaml"):
            try:
                comp = MetricCompiler.from_yaml_file(y_path)
                registry.register(comp.definition)
            except Exception:
                pass

    trajs = load_trajectories(trajectories)
    engine = TrajectoryReplayEngine(registry=registry, raw_artifacts_dir=artifacts_dir)
    res = engine.replay_trajectories(trajs, SCENARIOS)

    click.echo(f"Replayed {res['total_replayed']} trajectories.")
    click.echo(f"Unreplayable Artifacts: {res.get('unreplayable_artifacts_count', 0)}")
    scorecard = res.get("scorecard", {})
    if scorecard:
        click.echo(f"Semantic Lift: {scorecard.get('semantic_lift')}")
        click.echo(f"Net Governance Benefit: {scorecard.get('net_governance_benefit')}")

    if output:
        out_p = Path(output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(res, indent=2), encoding="utf-8")
        click.echo(f"Replay report written to {output}")


@main.command(name="benchmark-live")
@click.option("--contracts", default="benchmark_corpus", help="Path to SCOS contracts directory")
@click.option("--output", default="benchmark_scorecard.json", help="Path for output scorecard JSON")
@click.option("--trajectories-out", default="runs/trajectories.jsonl", help="Path for exported JSONL trajectories")
@click.option("--artifacts-dir", default="artifacts/benchmark", help="Local directory to store raw SQL artifacts")
@click.option("--provider", default="mock", help="LLM Provider: mock, openai, anthropic, ollama, vllm")
@click.option("--model", default="gpt-4o", help="Model identifier (e.g. gpt-4o, claude-3-5-sonnet, llama3)")
@click.option("--api-key", default=None, help="API key for LLM provider (or via env var)")
@click.option("--api-base", default=None, help="Base URL for LLM endpoint")
@click.option("--rollouts", default=3, help="Number of rollouts per scenario per condition")
def benchmark_live(contracts, output, trajectories_out, artifacts_dir, provider, model, api_key, api_base, rollouts):
    """Run agent benchmark with paired blind & governed conditions across stochastic rollouts."""
    import duckdb
    from semantic_reliability.benchmark.protocol import FrozenProtocolConfig, NetGovernancePolicy
    from semantic_reliability.benchmark.scenarios import SCENARIOS
    from semantic_reliability.benchmark.adapters import LiveGovernedAgentAdapter, DeterministicBaselineAdapter
    from semantic_reliability.benchmark.oracle import OracleValidator
    from semantic_reliability.benchmark.evaluator import BenchmarkEvaluator
    from semantic_reliability.benchmark.replay import export_trajectories
    from semantic_reliability.benchmark.llm_client import LiveLLMClient
    from semantic_reliability.mcp.handlers import ScosMcpHandlers
    from semantic_reliability.firewall.engine import ContractRegistry
    from semantic_reliability.compiler.compiler import MetricCompiler

    is_synthetic = provider.lower() == "mock"

    if is_synthetic:
        console.print(Panel(
            "[bold yellow]⚠️ RUNNING IN SYNTHETIC SCAFFOLDING / SIMULATION MODE[/bold yellow]\n"
            "[dim]No external LLM provider was configured. The run evaluates the benchmark evaluation harness, "
            "oracle logic, and trajectory replay loop rather than a live model checkpoint.[/dim]\n"
            "To evaluate a live model, specify [cyan]--provider openai|anthropic|ollama --model <model_id>[/cyan].",
            title="[bold yellow]🧪 SCOS Benchmark Harness[/bold yellow]",
            border_style="yellow",
        ))
    else:
        console.print(f"[bold green]🚀 Running live benchmark with provider:[/bold green] {provider} (Model: {model})")

    registry = ContractRegistry()
    c_path = Path(contracts)
    if c_path.exists():
        for y_path in c_path.rglob("*.yaml"):
            try:
                comp = MetricCompiler.from_yaml_file(y_path)
                registry.register(comp.definition)
            except Exception:
                pass

    handlers = ScosMcpHandlers(registry=registry)
    cfg = FrozenProtocolConfig(model_id=model, num_rollouts=rollouts)

    model_fn = None if is_synthetic else LiveLLMClient(provider=provider, model=model, api_key=api_key, api_base=api_base)
    gov_adapter = LiveGovernedAgentAdapter(config=cfg, mcp_handlers=handlers, model_fn=model_fn)
    blind_adapter = DeterministicBaselineAdapter(model_id=f"{model}-blind")
    conn = duckdb.connect(":memory:")
    oracle = OracleValidator(conn=conn, registry=registry)
    evaluator = BenchmarkEvaluator(policy=NetGovernancePolicy())

    gov_trajectories = []
    blind_trajectories = []

    for rollout_idx in range(rollouts):
        for scenario in SCENARIOS:
            # 1. Blind condition rollout
            b_traj = blind_adapter.run(scenario, rollout_idx=rollout_idx)
            if b_traj.final_sql_raw:
                eval_res = oracle.evaluate_agent_sql(b_traj.final_sql_raw, scenario)
                b_traj.execution_success = eval_res["execution_success"]
                b_traj.contract_compliant = eval_res["contract_compliant"]
                b_traj.result_correct = eval_res["result_correct"]
            blind_trajectories.append(b_traj)

            # 2. Governed condition rollout
            g_traj = gov_adapter.run(scenario, rollout_idx=rollout_idx)
            if g_traj.final_sql_raw:
                eval_res = oracle.evaluate_agent_sql(g_traj.final_sql_raw, scenario)
                g_traj.execution_success = eval_res["execution_success"]
                g_traj.contract_compliant = eval_res["contract_compliant"]
                g_traj.result_correct = eval_res["result_correct"]
            gov_trajectories.append(g_traj)

    # Calculate scorecard
    scorecard = evaluator.compute_scorecard(blind_trajectories, gov_trajectories)
    scorecard["run_mode"] = "SYNTHETIC_SIMULATION" if is_synthetic else "LIVE_MODEL_EVALUATION"
    scorecard["provider"] = provider
    scorecard["model"] = model

    out_p = Path(output)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")

    # Export trajectories with privacy redaction and local artifact preservation
    all_trajs = blind_trajectories + gov_trajectories
    export_trajectories(all_trajs, trajectories_out, raw_artifacts_dir=artifacts_dir)

    console.print(f"[bold green]Benchmark live run complete:[/bold green] {rollouts} rollouts x {len(SCENARIOS)} scenarios.")
    console.print(f"Scorecard written to: {output}")
    console.print(f"Run Mode: [cyan]{scorecard['run_mode']}[/cyan]")
    console.print(f"Semantic Lift: [bold]{scorecard.get('semantic_lift', 0.0) * 100:.1f}%[/bold]")
@main.command("audit-provenance")
@click.option("--target-dir", type=click.Path(exists=True), default="benchmark_corpus", help="Target directory with schemas / contracts")
@click.option("--audit-citations", type=click.Path(exists=True), default=None, help="Optional LaTeX paper file to audit citations")
@click.option("--strict/--no-strict", default=True, help="Fail with non-zero exit code if any provenance claim fails verification")
def audit_provenance_cmd(target_dir, audit_citations, strict):
    """Mechanically audit external repository provenance claims against ground-truth upstream repos."""
    from semantic_reliability.evaluation.provenance_auditor import ProvenanceAuditor

    console.print(Panel(
        f"[bold cyan]Auditing External Provenance Claims in:[/bold cyan] {target_dir}\n"
        + (f"[bold cyan]Auditing LaTeX Citations in:[/bold cyan] {audit_citations}\n" if audit_citations else "")
        + "[dim]Verifying all claimed repositories, files, columns, and test symbols against upstream git sources...[/dim]",
        title="[bold green]Mechanical Provenance Verifier[/bold green]",
        border_style="cyan",
    ))

    results = ProvenanceAuditor.audit_directory(Path(target_dir))
    any_failed = False

    if not results:
        console.print("[yellow]No external provenance claims found in target directory.[/yellow]")
    else:
        table = Table(title="Provenance Mechanical Verification Audit", show_header=True, header_style="bold magenta")
        table.add_column("Source File", width=35)
        table.add_column("Claimed Repository", width=30)
        table.add_column("File Exists", width=12)
        table.add_column("Status", width=12)
        table.add_column("Reason / Detail", width=40)

        for r in results:
            status_str = "[bold green]VERIFIED[/bold green]" if r.passed else "[bold red]FAILED[/bold red]"
            if not r.passed:
                any_failed = True
            file_status = "✓ Yes" if r.file_exists else "✗ No"
            table.add_row(
                Path(r.claim.source_file).name,
                r.claim.repository.split("/")[-1],
                file_status,
                status_str,
                r.reason,
            )

        console.print(table)

    if audit_citations:
        bib_res = ProvenanceAuditor.audit_latex_bibliography(Path(audit_citations))
        bib_table = Table(title=f"LaTeX Bibliography Citation Audit ({audit_citations})", show_header=True, header_style="bold cyan")
        bib_table.add_column("Citation Key", width=25)
        bib_table.add_column("Status", width=15)
        bib_table.add_column("Details", width=45)

        for entry in bib_res["entry_details"]:
            status_str = "[bold green]VALID[/bold green]" if entry["valid"] else "[bold red]INVALID[/bold red]"
            detail = "Well-formed author and year" if entry["valid"] else "Missing standard author or publication year"
            bib_table.add_row(entry["key"], status_str, detail)

        for missing in bib_res["missing_declarations"]:
            bib_table.add_row(missing, "[bold red]UNDECLARED[/bold red]", "Cited in paper text but missing from thebibliography block")
            any_failed = True

        console.print(bib_table)

    if any_failed and strict:
        console.print("\n[bold red]❌ Provenance Audit Failed.[/bold red] Found unverified, non-existent, or fabricated claims.")
        sys.exit(1)
    elif not any_failed:
        console.print("\n[bold green]✓ All external provenance claims and citations mechanically verified.[/bold green]\n")


if __name__ == "__main__":
    main()









