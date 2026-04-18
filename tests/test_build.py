"""Tests for pure / near-pure helper functions in build.py."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

import build

if TYPE_CHECKING:
    from pathlib import Path

    _VarMap = dict[str, dict[str, object]]


# ── _sha256_file ─────────────────────────────────────────────────────


class TestSha256File:
    def test_known_digest(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("hello\n", encoding="utf-8")
        # sha256("hello\n") is well-known.
        expected = (
            "5891b5b522d5df086d0ff0b110fbd9d2"
            "1bb4fc7163af34d08286a2e846f6be03"
        )
        assert build._sha256_file(f) == expected

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty"
        f.write_bytes(b"")
        # sha256 of empty input.
        expected = (
            "e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855"
        )
        assert build._sha256_file(f) == expected

    def test_binary_file(self, tmp_path: Path) -> None:
        f = tmp_path / "bin"
        f.write_bytes(bytes(range(256)))
        digest = build._sha256_file(f)
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)


# ── _md_to_html ──────────────────────────────────────────────────────


class TestMdToHtml:
    def test_empty_string(self) -> None:
        assert build._md_to_html("") == ""

    def test_none_returns_empty(self) -> None:
        # The function guards with ``if not text``.
        assert build._md_to_html("") == ""

    def test_basic_paragraph(self) -> None:
        result = build._md_to_html("Hello world")
        assert "<p>" in result
        assert "Hello world" in result

    def test_bold(self) -> None:
        result = build._md_to_html("**bold**")
        assert "<strong>bold</strong>" in result

    def test_preserve_newlines(self) -> None:
        result = build._md_to_html(
            "line1\nline2",
            preserve_newlines=True,
        )
        assert "<br" in result

    def test_no_preserve_newlines(self) -> None:
        result = build._md_to_html(
            "line1\nline2",
            preserve_newlines=False,
        )
        # Without nl2br, a single newline should NOT produce <br>.
        assert "<br" not in result


# ── _notes_preview_and_flag ──────────────────────────────────────────


class TestNotesPreviewAndFlag:
    def test_none_input(self) -> None:
        preview, shortened = build._notes_preview_and_flag(None)
        assert preview == ""
        assert shortened is False

    def test_empty_string(self) -> None:
        preview, shortened = build._notes_preview_and_flag("")
        assert preview == ""
        assert shortened is False

    def test_short_text(self) -> None:
        preview, shortened = build._notes_preview_and_flag("Short.")
        assert preview == "Short."
        assert shortened is False

    def test_long_text_truncated(self) -> None:
        long_text = "word " * 50  # 250 chars
        preview, shortened = build._notes_preview_and_flag(long_text)
        assert shortened is True
        assert preview.endswith("\u2026")
        assert len(preview) <= 125  # 120 + ellipsis

    def test_double_newline_uses_first_paragraph(self) -> None:
        text = "First paragraph.\n\nSecond paragraph."
        preview, shortened = build._notes_preview_and_flag(text)
        assert "First paragraph" in preview
        assert "Second" not in preview
        assert shortened is True

    def test_whitespace_collapsed(self) -> None:
        text = "  lots   of   spaces  "
        preview, _shortened = build._notes_preview_and_flag(text)
        assert "  " not in preview


# ── _normalize_var ───────────────────────────────────────────────────


class TestNormalizeVar:
    def test_minimal_input(self) -> None:
        result = build._normalize_var({"name": "age"})
        assert result["name"] == "age"
        assert result["label"] == "age"  # falls back to name
        assert result["type"] == ""
        assert result["categories"] == []
        assert result["tags"] == []
        assert result["is_group"] is False

    def test_label_from_labels_field(self) -> None:
        result = build._normalize_var({
            "name": "bp",
            "labels": "Blood Pressure",
        })
        assert result["label"] == "Blood Pressure"

    def test_type_from_coltypes(self) -> None:
        result = build._normalize_var({
            "name": "x",
            "coltypes": "numeric",
        })
        assert result["type"] == "numeric"

    def test_type_from_dtype(self) -> None:
        result = build._normalize_var({
            "name": "x",
            "dtype": "character",
        })
        assert result["type"] == "character"

    def test_categories_string_to_list(self) -> None:
        result = build._normalize_var({
            "name": "x",
            "categories": "lab",
        })
        assert result["categories"] == ["lab"]

    def test_categories_list_passthrough(self) -> None:
        result = build._normalize_var({
            "name": "x",
            "categories": ["a", "b"],
        })
        assert result["categories"] == ["a", "b"]

    def test_tags_string_to_list(self) -> None:
        result = build._normalize_var({
            "name": "x",
            "tags": "important",
        })
        assert result["tags"] == ["important"]

    def test_name_fallback_to_colname_silver(self) -> None:
        result = build._normalize_var({
            "colname_silver": "bmi",
        })
        assert result["name"] == "bmi"

    def test_original_not_mutated(self) -> None:
        original = {"name": "test"}
        build._normalize_var(original)
        assert "label" not in original


# ── _sanitize_sheet_name ─────────────────────────────────────────────


class TestSanitizeSheetName:
    def test_clean_name(self) -> None:
        assert build._sanitize_sheet_name("Cancer") == "Cancer"

    def test_forbidden_chars_removed(self) -> None:
        assert build._sanitize_sheet_name("A[B]C:D*E") == "ABCDE"

    def test_max_31_chars(self) -> None:
        long_name = "A" * 50
        assert len(build._sanitize_sheet_name(long_name)) == 31

    def test_empty_returns_sheet(self) -> None:
        assert build._sanitize_sheet_name("") == "Sheet"

    def test_only_forbidden_chars(self) -> None:
        assert build._sanitize_sheet_name("[]:*?/\\") == "Sheet"

    def test_backslash_removed(self) -> None:
        assert build._sanitize_sheet_name("a\\b") == "ab"


# ── _get_build_date ──────────────────────────────────────────────────


class TestGetBuildDate:
    def test_source_date_epoch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
        result = build._get_build_date()
        assert result == "2023-11-14T22:13:20+00:00"

    def test_invalid_epoch_ignored(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "not_a_number")
        result = build._get_build_date()
        # Should fall through to wall clock.
        assert "T" in result  # still ISO format

    def test_no_epoch_returns_iso(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
        result = build._get_build_date()
        assert "T" in result
        assert len(result) >= 19  # YYYY-MM-DDTHH:MM:SS

    def test_input_files_mtime(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
        f = tmp_path / "data.yaml"
        f.write_text("x: 1\n")
        os.utime(f, (1_600_000_000, 1_600_000_000))
        result = build._get_build_date(input_files=[f])
        assert "2020-09-13" in result


# ── _compile_ignore_patterns ──────────────────────────────────────────


class TestCompileIgnorePatterns:
    def test_none_input(self) -> None:
        assert build._compile_ignore_patterns(None) == []

    def test_empty_list(self) -> None:
        assert build._compile_ignore_patterns([]) == []

    def test_valid_regex(self) -> None:
        patterns = build._compile_ignore_patterns([r"^tmp_"])
        assert len(patterns) == 1
        assert patterns[0].search("tmp_foo")
        assert not patterns[0].search("bar_tmp")

    def test_glob_fallback(self) -> None:
        # A glob like *.bak is not valid regex (unescaped *).
        patterns = build._compile_ignore_patterns(["*.bak"])
        assert len(patterns) == 1
        assert patterns[0].search("file.bak")
        assert not patterns[0].search("file.txt")

    def test_empty_strings_skipped(self) -> None:
        patterns = build._compile_ignore_patterns(["", "  ", "^ok"])
        assert len(patterns) == 1


# ── _extract_var_map_from_codebook ───────────────────────────────────


class TestExtractVarMapFromCodebook:
    def test_none_input(self) -> None:
        assert build._extract_var_map_from_codebook(None) == {}

    def test_empty_dict(self) -> None:
        assert build._extract_var_map_from_codebook({}) == {}

    def test_variables_list(self) -> None:
        data = {
            "variables": [
                {"name": "age", "label": "Age"},
                {"name": "bmi", "label": "BMI"},
            ],
        }
        result = build._extract_var_map_from_codebook(data)
        assert set(result.keys()) == {"age", "bmi"}

    def test_variables_dict(self) -> None:
        data = {
            "variables": {
                "age": {"label": "Age"},
                "bmi": {"label": "BMI"},
            },
        }
        result = build._extract_var_map_from_codebook(data)
        assert set(result.keys()) == {"age", "bmi"}

    def test_var_map_key(self) -> None:
        data = {
            "var_map": {
                "age": {"label": "Age"},
            },
        }
        result = build._extract_var_map_from_codebook(data)
        assert "age" in result

    def test_flat_mapping(self) -> None:
        data = {
            "age": {"label": "Age"},
            "bmi": {"label": "BMI"},
        }
        result = build._extract_var_map_from_codebook(data)
        assert set(result.keys()) == {"age", "bmi"}

    def test_variables_list_skips_nameless(self) -> None:
        data = {
            "variables": [
                {"name": "age"},
                {"label": "no name here"},
            ],
        }
        result = build._extract_var_map_from_codebook(data)
        assert list(result.keys()) == ["age"]


# ── _apply_ignore ────────────────────────────────────────────────────


class TestApplyIgnore:
    @pytest.fixture()
    def sample_vars(self) -> _VarMap:
        return {
            "age": build._normalize_var({
                "name": "age",
                "tags": ["keep"],
                "categories": ["demo"],
            }),
            "tmp_x": build._normalize_var({
                "name": "tmp_x",
                "tags": ["scratch"],
                "categories": ["temp"],
            }),
            "bmi": build._normalize_var({
                "name": "bmi",
                "tags": [],
                "categories": ["demo"],
            }),
        }

    def test_no_filters(self, sample_vars: _VarMap) -> None:
        result = build._apply_ignore(sample_vars, [], [])
        assert len(result) == 3

    def test_ignore_by_name(self, sample_vars: _VarMap) -> None:
        result = build._apply_ignore(
            sample_vars, ["tmp_x"], [],
        )
        assert "tmp_x" not in result
        assert len(result) == 2

    def test_ignore_by_pattern(self, sample_vars: _VarMap) -> None:
        patterns = build._compile_ignore_patterns([r"^tmp_"])
        result = build._apply_ignore(
            sample_vars, [], patterns,
        )
        assert "tmp_x" not in result

    def test_ignore_by_tag(self, sample_vars: _VarMap) -> None:
        result = build._apply_ignore(
            sample_vars,
            [],
            [],
            ignore_tags=["scratch"],
        )
        assert "tmp_x" not in result
        assert "age" in result

    def test_ignore_by_category(self, sample_vars: _VarMap) -> None:
        result = build._apply_ignore(
            sample_vars,
            [],
            [],
            ignore_categories=["temp"],
        )
        assert "tmp_x" not in result
        assert "bmi" in result

    def test_multiple_filters_combine(
        self,
        sample_vars: _VarMap,
    ) -> None:
        result = build._apply_ignore(
            sample_vars,
            ["age"],
            [],
            ignore_tags=["scratch"],
        )
        assert list(result.keys()) == ["bmi"]
