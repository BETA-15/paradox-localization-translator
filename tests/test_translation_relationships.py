from __future__ import annotations

from pathlib import Path

import translator_core as core


def _entries(prefix: str, count: int, value_prefix: str = "Text"):
    return {f"{prefix}_{index:05d}": f"{value_prefix} {index}" for index in range(count)}


def _candidate_row(
    japanese: dict[str, str],
    *,
    english: dict[str, str] | None = None,
    chinese: dict[str, str] | None = None,
    base_english: dict[str, str] | None = None,
    base_chinese: dict[str, str] | None = None,
    name: str = "Candidate",
    path: str = "/candidate",
    manual_role: str = "auto",
):
    english = english or {}
    chinese = chinese or {}
    base_english = base_english or {}
    base_chinese = base_chinese or {}
    return {
        "path": path,
        "mod": name,
        "japanese": dict(japanese),
        "japanese_keys": set(japanese),
        "japanese_files": 1,
        "language_files": {
            "japanese": 1,
            "english": 1 if english else 0,
            "simp_chinese": 1 if chinese else 0,
        },
        "language_keys": {
            "japanese": set(japanese),
            "english": set(english),
            "simp_chinese": set(chinese),
        },
        "source_language_entries": {
            "english": dict(english),
            "simp_chinese": dict(chinese),
        },
        "base_game_keys": set(base_english) | set(base_chinese),
        "base_game_source_entries": {
            "english": dict(base_english),
            "simp_chinese": dict(base_chinese),
        },
        "profile": {
            "localization_ratio": 1.0,
            "non_localization_files": 0,
            "gameplay_files": 0,
            "other_files": 0,
            "gameplay_dirs": [],
        },
        "dependencies": [],
        "localization_folder_names": [],
        "manual_role": manual_role,
        "manual_source_paths": [],
    }


def test_ercf_ditn_vanilla_carryover_is_not_relationship_evidence():
    base = _entries("vanilla", 921, "Vanilla")
    source = {**base, **_entries("ercf", 3654, "ERCF")}
    candidate_japanese = {**{key: f"日本語 {index}" for index, key in enumerate(base)}, **_entries("ditn", 4947, "日本語")}
    candidate_english = {key: f"DITN changed {index}" for index, key in enumerate(candidate_japanese)}
    row = _candidate_row(
        candidate_japanese,
        english=candidate_english,
        base_english=base,
        name="Dynamic and Improved Title Name",
    )

    result = core._translation_mod_weight(
        "Eastern Roman Culture & Flavor",
        set(source),
        row,
        source_language_entries={"english": source, "simp_chinese": {}},
        source_path="/ercf",
    )

    assert result["raw_overlap_keys"] == 921
    assert result["vanilla_carryover_keys"] == 921
    assert result["effective_overlap_keys"] == 0
    assert result["classification"] == "rejected"


def test_large_partial_translation_passes_candidate_side_40_percent():
    source = _entries("source", 10_000)
    japanese = {key: f"訳 {index}" for index, key in enumerate(list(source)[:500])}
    row = _candidate_row(japanese)
    result = core._translation_mod_weight(
        "Large Source",
        set(source),
        row,
        source_language_entries={"english": source, "simp_chinese": {}},
        source_path="/large",
    )

    assert result["effective_overlap_keys"] == 500
    assert result["effective_source_rate"] == 0.05
    assert result["effective_candidate_rate"] == 1.0
    assert result["final_relation_gate"] is True
    assert result["classification"] == "auto"


def test_large_relation_requires_200_effective_keys():
    source = _entries("source", 500)
    row_199 = _candidate_row({key: "訳" for key in list(source)[:199]})
    row_200 = _candidate_row({key: "訳" for key in list(source)[:200]})
    args = {"english": source, "simp_chinese": {}}

    fail = core._translation_mod_weight("Source", set(source), row_199, source_language_entries=args)
    passed = core._translation_mod_weight("Source", set(source), row_200, source_language_entries=args)

    assert fail["effective_source_rate"] < 0.40
    assert fail["effective_count_pass"] is False
    assert fail["classification"] == "rejected"
    assert passed["effective_source_rate"] == 0.40
    assert passed["effective_count_pass"] is True
    assert passed["final_relation_gate"] is True


def test_small_source_keeps_20_percent_gate():
    source = _entries("small", 50)
    row = _candidate_row({key: "訳" for key in list(source)[:10]})
    result = core._translation_mod_weight(
        "Small Source",
        set(source),
        row,
        source_language_entries={"english": source, "simp_chinese": {}},
    )

    assert result["required_match_count"] == 10
    assert result["effective_source_rate"] == 0.20
    assert result["final_relation_gate"] is True


def test_candidate_source_text_mismatch_removes_shared_keys():
    source = _entries("shared", 100, "Source")
    japanese = {key: "訳" for key in source}
    candidate_english = {key: "Different text" for key in source}
    row = _candidate_row(japanese, english=candidate_english)

    evidence = core.translation_relation_evidence(
        {"english": source, "simp_chinese": {}},
        row,
    )

    assert evidence["preverified_overlap_keys"] == 100
    assert evidence["source_text_mismatch_keys"] == 100
    assert evidence["effective_overlap_keys"] == 0
    assert evidence["relation_gate"] is False


def test_self_localized_mod_is_not_external_translation_without_explicit_evidence():
    source = _entries("shared", 200)
    row = _candidate_row(
        {key: "訳" for key in source},
        english=source,
        name="Unrelated Self Localized Mod",
    )
    result = core._translation_mod_weight(
        "Source Mod",
        set(source),
        row,
        source_language_entries={"english": source, "simp_chinese": {}},
    )

    assert result["candidate_paired_source_rate"] == 1.0
    assert result["ordinary_gate"] is True
    assert result["translation_shape_gate"] is False
    assert result["classification"] == "rejected"


def test_candidate_role_boundaries_for_base_and_source_pairing():
    base_49 = _entries("base", 49)
    small = core.classify_translation_candidate_role(
        _candidate_row({key: "訳" for key in base_49}, base_english=base_49)
    )
    base_80 = _entries("base", 80)
    non_base_20 = _entries("mod", 20)
    strong = core.classify_translation_candidate_role(
        _candidate_row(
            {key: "訳" for key in {**base_80, **non_base_20}},
            base_english=base_80,
        )
    )
    base_70 = _entries("base", 70)
    non_base_30 = _entries("mod", 30)
    mixed = core.classify_translation_candidate_role(
        _candidate_row(
            {key: "訳" for key in {**base_70, **non_base_30}},
            base_english=base_70,
        )
    )

    assert small["candidate_base_classification"] == "small_base_candidate"
    assert strong["candidate_base_classification"] == "base_translation"
    assert strong["candidate_non_base_rate"] == 0.20
    assert mixed["candidate_base_classification"] == "large_override_candidate"


def test_base_translation_is_not_linked_by_folder_name_alone():
    base = _entries("base", 80)
    source = _entries("source", 20)
    japanese = {key: "訳" for key in {**base, **source}}
    row = _candidate_row(japanese, base_english=base, name="Base Japanese Improvement")
    row["localization_folder_names"] = ["Source Mod"]

    result = core._translation_mod_weight(
        "Source Mod",
        set(source),
        row,
        source_language_entries={"english": source, "simp_chinese": {}},
    )

    assert result["candidate_base_translation"] is True
    assert result["localization_folder_points"] > 0
    assert result["base_role_gate"] is False
    assert result["classification"] == "rejected"


def test_translation_shape_20_and_80_percent_boundaries():
    japanese = _entries("key", 100)
    keys = list(japanese)
    translation = core.classify_translation_candidate_role(
        _candidate_row(japanese, english={key: "Source" for key in keys[:20]})
    )
    independent = core.classify_translation_candidate_role(
        _candidate_row(japanese, english={key: "Source" for key in keys[:80]})
    )

    assert translation["candidate_localization_shape"] == "translation_only"
    assert independent["candidate_localization_shape"] == "self_localized"


def test_changed_base_source_text_remains_effective_for_japanese_only_patch():
    base = _entries("base", 10, "Vanilla")
    source = {key: f"Changed {index}" for index, key in enumerate(base)}
    row = _candidate_row({key: "訳" for key in base}, base_english=base)
    evidence = core.translation_relation_evidence(
        {"english": source, "simp_chinese": {}},
        row,
    )

    assert evidence["vanilla_carryover_keys"] == 0
    assert evidence["changed_base_overlap_keys"] == 10
    assert evidence["effective_overlap_keys"] == 10
    assert evidence["relation_gate"] is True


def _write_source_mod(root: Path, prefix: str, count: int):
    loc = root / "localization" / "english"
    loc.mkdir(parents=True)
    lines = ["l_english:"]
    lines.extend(f' {prefix}_{index:05d}:0 "Text {index}"' for index in range(count))
    (loc / f"{prefix}_l_english.yml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_multi_translation_union_gate_handles_five_mod_pack(tmp_path):
    source_roots = []
    japanese = {}
    for source_index in range(5):
        root = tmp_path / f"Source{source_index}"
        prefix = f"source{source_index}"
        _write_source_mod(root, prefix, 1_000)
        source_roots.append(root)
        japanese.update({f"{prefix}_{index:05d}": f"訳 {index}" for index in range(200)})
    candidate_path = tmp_path / "CombinedJapanese"
    row = _candidate_row(japanese, path=str(candidate_path), name="Combined Japanese")

    assigned = core.assign_translation_candidate_owners(source_roots, [row])[0]

    assert len(assigned["multi_translation_source_paths"]) == 5
    assert assigned["multi_translation_union_keys"] == 1_000
    assert assigned["multi_translation_union_coverage"] == 1.0
    first_source = source_roots[0]
    first_data = core._collect_mod_language_entries(first_source)
    result = core._translation_mod_weight(
        "Source0",
        set(first_data["source"]),
        assigned,
        source_language_entries={"english": first_data["english"], "simp_chinese": {}},
        source_path=str(first_source.resolve()),
    )
    assert result["effective_source_rate"] == 0.20
    assert result["effective_candidate_rate"] == 0.20
    assert result["ordinary_gate"] is False
    assert result["multi_translation_gate"] is True
    assert result["classification"] == "auto"


def test_multi_translation_contributor_requires_200_effective_keys(tmp_path):
    source_roots = []
    japanese = {}
    for source_index in range(2):
        root = tmp_path / f"Source{source_index}"
        prefix = f"source{source_index}"
        _write_source_mod(root, prefix, 1_000)
        source_roots.append(root)
        japanese.update({f"{prefix}_{index:05d}": f"訳 {index}" for index in range(199)})
    row = _candidate_row(japanese, path=str(tmp_path / "CombinedJapanese"), name="Combined Japanese")

    assigned = core.assign_translation_candidate_owners(source_roots, [row])[0]

    assert assigned.get("multi_translation_source_paths") == []


def _write_legacy_english_translation(root: Path, values, *, name="Legacy Japanese Translation", translation_tag=True):
    root.mkdir(parents=True, exist_ok=True)
    tags = 'tags={\n "Translation"\n}\n' if translation_tag else ""
    (root / "descriptor.mod").write_text(
        f'name="{name}"\n{tags}',
        encoding="utf-8",
    )
    loc = root / "localization" / "english"
    loc.mkdir(parents=True)
    lines = ["l_english:"]
    lines.extend(f' legacy_{index}:0 "{value}"' for index, value in enumerate(values))
    (loc / "legacy_l_english.yml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_legacy_japanese_in_l_english_is_reported_as_warning(tmp_path):
    root = tmp_path / "LegacyJapanese"
    _write_legacy_english_translation(root, ["これは古い日本語化です"] * 20)

    result = core.analyze_mod_translation_status(root)

    profile = result["translation_format_profile"]
    assert profile["legacy_english_japanese_layout"] is True
    assert profile["english_japanese_text_keys"] == 20
    assert result["status"] == "要確認（旧式日本語化）"
    assert len(result["translation_warnings"]) == 1


def test_chinese_text_is_not_mistaken_for_legacy_japanese(tmp_path):
    root = tmp_path / "ChineseTranslation"
    _write_legacy_english_translation(root, ["这是中文翻译文本"] * 20, name="Chinese Translation")

    profile = core.translation_localization_format_profile(root)

    assert profile["english_japanese_text_keys"] == 0
    assert profile["legacy_english_japanese_layout"] is False


def test_normal_english_mod_has_no_translation_warning(tmp_path):
    root = tmp_path / "NormalMod"
    _write_legacy_english_translation(
        root,
        ["Ordinary English text"] * 20,
        name="Normal Gameplay Mod",
        translation_tag=False,
    )

    result = core.analyze_mod_translation_status(root)

    assert result["translation_format_profile"]["translation_hint"] is False
    assert result["translation_warnings"] == []


def test_outdated_native_japanese_candidate_gets_unresolved_source_warning():
    profile = {
        "translation_hint": True,
        "legacy_english_japanese_layout": False,
    }

    warnings = core.translation_localization_warnings(
        profile,
        japanese_files=1,
        has_review_candidate=True,
        has_external_translation=False,
    )
    linked = core.translation_localization_warnings(
        profile,
        japanese_files=1,
        has_review_candidate=True,
        has_external_translation=True,
    )

    assert len(warnings) == 1
    assert "対応元Mod" in warnings[0]
    assert linked == []


def test_warning_status_is_restored_after_later_status_refinement():
    result = {
        "status": "翻訳なし",
        "message": "後段で再計算された状態です。",
        "translation_format_profile": {"legacy_english_japanese_layout": True},
        "translation_warnings": ["古い日本語化方式です。"],
    }

    core.apply_translation_warning_status(result)
    core.apply_translation_warning_status(result)

    assert result["status"] == "要確認（旧式日本語化）"
    assert result["message"].count("警告:") == 1
