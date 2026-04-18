"""Integration / smoke tests for the full build pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import build

if TYPE_CHECKING:
    from pathlib import Path


class TestFullBuild:
    """Run the real build pipeline against repo data."""

    @pytest.fixture()
    def output_dir(self, tmp_path: Path) -> Path:
        return tmp_path / "dist"

    def test_build_produces_html_and_xlsx(
        self,
        output_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
        build.build(output_dir=output_dir)

        html = output_dir / "variables_browser.html"
        xlsx = output_dir / "variables_browser.xlsx"

        assert html.exists()
        assert xlsx.exists()

    def test_html_is_non_trivial(
        self,
        output_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
        build.build(output_dir=output_dir)

        html = output_dir / "variables_browser.html"
        content = html.read_text(encoding="utf-8")

        # Sanity: non-trivial size.
        assert len(content) > 100_000

        # Contains expected structural elements.
        assert "<!DOCTYPE html>" in content or "<html" in content
        assert "Build date:" in content
        assert "2023-11-14" in content  # from SOURCE_DATE_EPOCH

    def test_xlsx_is_non_trivial(
        self,
        output_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
        build.build(output_dir=output_dir)

        xlsx = output_dir / "variables_browser.xlsx"
        assert xlsx.stat().st_size > 10_000

        # XLSX files are ZIP archives — first bytes are PK.
        header = xlsx.read_bytes()[:4]
        assert header == b"PK\x03\x04"

    def test_static_files_copied(
        self,
        output_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
        build.build(output_dir=output_dir)

        static_files = list(build.STATIC_DIR.iterdir())
        for src in static_files:
            dest = output_dir / src.name
            assert dest.exists(), f"Static file {src.name} not copied"

    def test_idempotent_html(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")

        dir1 = tmp_path / "run1"
        dir2 = tmp_path / "run2"

        build.build(output_dir=dir1)
        build.build(output_dir=dir2)

        html1 = (dir1 / "variables_browser.html").read_text(
            encoding="utf-8",
        )
        html2 = (dir2 / "variables_browser.html").read_text(
            encoding="utf-8",
        )
        assert html1 == html2

    def test_html_contains_all_datasets(
        self,
        output_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
        build.build(output_dir=output_dir)

        html = (output_dir / "variables_browser.html").read_text(
            encoding="utf-8",
        )

        # Each data file should produce a section in the output.
        discovered = build._discover_datasets()
        for dataset_id in discovered:
            assert dataset_id in html or dataset_id.replace(
                "_", " ",
            ) in html, (
                f"Dataset '{dataset_id}' not found in HTML output"
            )
