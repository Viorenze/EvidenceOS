#!/usr/bin/env python3
"""EvidenceOS E2E Automated Test Suite Runner.

Executes all 5 tiers of the EvidenceOS E2E test suite:
- Tier 1: Feature Coverage (25 tests)
- Tier 2: Boundary & Corner Cases (25 tests)
- Tier 3: Cross-Feature Combinations (6 tests)
- Tier 4: Real-World Application Scenarios (4 tests)
- Tier 5: White-Box Adversarial Stress Testing (42 tests)

Provides unified execution, timing metrics, formatted ANSI reporting, and exit code.
Usage:
    python tests/e2e/test_runner.py
    uv run python tests/e2e/test_runner.py
"""

import os
import sys
import time
from pathlib import Path
import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Enforce deterministic testing configurations
os.environ.setdefault("EMBEDDING_PROVIDER", "fake")
os.environ.setdefault("LLM_PROVIDER", "fake")
os.environ["DATABASE_URL"] = "postgresql+psycopg://evidence:evidence@127.0.0.1:5432/evidenceos"

TIERS = [
    {
        "id": "Tier 1",
        "name": "Feature Coverage",
        "file": "tests/e2e/test_tier1_feature_coverage.py",
        "description": "Upload, list, delete, SSE streaming, citation reconciliation & chunk modal",
    },
    {
        "id": "Tier 2",
        "name": "Boundary & Corner Cases",
        "file": "tests/e2e/test_tier2_boundary_corner.py",
        "description": "0-byte files, bad extensions, 404s, empty/whitespace queries, refusals, code shielding, subscript immunity",
    },
    {
        "id": "Tier 3",
        "name": "Cross-Feature Combinations",
        "file": "tests/e2e/test_tier3_pairwise_combinations.py",
        "description": "Pairwise interactions, full lifecycle cascade, multi-doc disambiguation, concurrent streams",
    },
    {
        "id": "Tier 4",
        "name": "Real-World Application Scenarios",
        "file": "tests/e2e/test_tier4_real_world_scenarios.py",
        "description": "End-to-end interview demonstration walkthrough, multi-format corpus, high-stress resilience",
    },
    {
        "id": "Tier 5",
        "name": "White-Box Adversarial Stress Testing",
        "file": "tests/e2e/test_tier5_adversarial.py",
        "description": "Rapid abort/submit lifecycle, polling resilience, deletion edge cases, StyleX CSS layers & adversarial SSE",
    },
]


class TierResultTracker:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def pytest_runtest_logreport(self, report):
        if report.when == "call":
            if report.passed:
                self.passed += 1
            elif report.failed:
                self.failed += 1
            elif report.skipped:
                self.skipped += 1


def main():
    print("=" * 80)
    print(" EvidenceOS Web Frontend Refactor — 5-Tier E2E Test Suite Runner")
    print(f" Working Directory: {PROJECT_ROOT}")
    print(" Environment: EMBEDDING_PROVIDER=fake | LLM_PROVIDER=fake")
    print("=" * 80)

    overall_start = time.perf_counter()
    tier_summaries = []
    total_passed = 0
    total_failed = 0

    for tier in TIERS:
        tier_file = PROJECT_ROOT / tier["file"]
        if not tier_file.exists():
            print(f"[!] Warning: Test file not found: {tier_file}")
            continue

        print(f"\n>>> Running {tier['id']}: {tier['name']}...")
        print(f"    Scope: {tier['description']}")

        tracker = TierResultTracker()
        tier_start = time.perf_counter()

        ret_code = pytest.main(
            [str(tier_file), "-q", "--tb=short"],
            plugins=[tracker],
        )

        tier_duration = time.perf_counter() - tier_start
        total_tests = tracker.passed + tracker.failed + tracker.skipped
        passed = (ret_code == 0 and tracker.failed == 0)

        status_str = "\033[92mPASS\033[0m" if passed else "\033[91mFAIL\033[0m"
        print(f"    Result: {status_str} | {tracker.passed}/{total_tests} passed in {tier_duration:.2f}s")

        tier_summaries.append({
            "tier": tier["id"],
            "name": tier["name"],
            "passed": tracker.passed,
            "failed": tracker.failed,
            "total": total_tests,
            "duration": tier_duration,
            "status": "PASS" if passed else "FAIL",
        })

        total_passed += tracker.passed
        total_failed += tracker.failed

    overall_duration = time.perf_counter() - overall_start

    # Final Summary Table
    print("\n" + "=" * 80)
    print(" E2E TEST EXECUTION SUMMARY")
    print("=" * 80)
    print(f"{'Tier':<10} {'Name':<35} {'Passed':<8} {'Failed':<8} {'Total':<8} {'Time':<8} {'Status':<6}")
    print("-" * 80)

    for s in tier_summaries:
        status_colored = f"\033[92m{s['status']}\033[0m" if s['status'] == "PASS" else f"\033[91m{s['status']}\033[0m"
        print(
            f"{s['tier']:<10} {s['name']:<35} {s['passed']:<8} {s['failed']:<8} "
            f"{s['total']:<8} {s['duration']:<7.2f}s {status_colored:<6}"
        )

    print("-" * 80)
    all_passed = (total_failed == 0 and total_passed > 0)
    total_status = "\033[92mALL TESTS PASSED (100%)\033[0m" if all_passed else "\033[91mTEST SUITE FAILED\033[0m"
    print(f"Total Tests: {total_passed + total_failed} | Passed: {total_passed} | Failed: {total_failed} | Time: {overall_duration:.2f}s")
    print(f"Final Status: {total_status}")
    print("=" * 80)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
