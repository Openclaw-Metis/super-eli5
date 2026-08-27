"""super-eli5 回歸測試。

執行：
  python -m unittest discover -s tests -v

只用標準函式庫；不連網；所有寫入都在暫存目錄。
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_ROOT = REPO_ROOT / "skills" / "super-eli5"
SCRIPTS = SKILL_ROOT / "scripts"
FIXTURES = REPO_ROOT / "tests" / "fixtures"
EXAMPLES = SKILL_ROOT / "assets" / "examples"

sys.path.insert(0, str(SCRIPTS))

import render_html  # noqa: E402
import self_check  # noqa: E402
import validate_spec as vs  # noqa: E402
import verify_artifact as va  # noqa: E402


def minimal_concept_spec(language: str = "zh-TW") -> dict:
    return {
        "version": 1,
        "language": language,
        "mode": "concept",
        "title": "快取是什麼",
        "audience": "新進同事",
        "one_liner": "快取就是把常用的答案先抄一份放在手邊。",
        "analogy": {"text": "像把常打的電話號碼寫在便利貼貼在螢幕上。", "limits": "便利貼不會過期，快取會。"},
        "ladder": {"analogy": "常用答案先抄一份。", "truth": "快取是離使用者更近、但容量更小的儲存層，命中就不用回源。", "caveat": "快取可能過期；失效策略決定你看到多舊的資料。"},
        "scenes": [
            {
                "id": "s1",
                "title": "先問快取",
                "caption": "命中就直接回答。",
                "nodes": [
                    {"id": "n_ask", "label": "使用者提問", "status": "analogy", "note": "像問路。", "evidence": ["e_note"]},
                    {"id": "n_cache", "label": "快取", "status": "verified", "note": "命中直接回。", "evidence": ["e_doc"]},
                    {"id": "n_origin", "label": "原始資料庫", "status": "inferred", "note": "沒命中才去。", "evidence": []},
                ],
                "edges": [{"from": "n_ask", "to": "n_cache", "label": "先問"}, {"from": "n_cache", "to": "n_origin", "label": "沒命中"}],
            }
        ],
        "trace": [
            {"step": 1, "scene": "s1", "node": "n_ask", "text": "使用者提問。"},
            {"step": 2, "scene": "s1", "node": "n_cache", "text": "先看快取。"},
        ],
        "failure_lens": [{"id": "f_stale", "what_breaks": "快取沒有及時失效", "symptom": "看到舊價格", "status": "inferred", "evidence": []}],
        "teach_back": [{"question": "快取命中是什麼意思？", "answer": "要的答案剛好已經抄在手邊。"}],
        "glossary": [{"term": "命中", "plain": "快取裡剛好有你要的答案。"}],
        "evidence": [
            {
                "id": "e_doc",
                "status": "verified",
                "claim": "快取命中時不需要回源",
                "locator": "https://example.org/docs/cache",
                "quote": "A cache hit serves the response without contacting the origin.",
                "retrieved_at": "2026-08-25T10:00:00+08:00",
                "content_sha256": "0" * 64,
            },
            {"id": "e_note", "status": "analogy", "claim": "便利貼只是比喻", "note": "比喻用。"},
        ],
        "mode_data": {"misconceptions": [{"myth": "快取永遠是最新的。", "reality": "快取會過期，要看失效策略。"}]},
    }


def error_codes(result: vs.ValidationResult) -> set[str]:
    return {item.code for item in result.errors}


class CanonicalFormTests(unittest.TestCase):
    def test_hash_is_key_order_independent(self) -> None:
        spec = minimal_concept_spec()
        reordered = json.loads(json.dumps(spec, ensure_ascii=False, sort_keys=True))
        reordered = dict(reversed(list(reordered.items())))
        self.assertEqual(vs.spec_sha256(spec), vs.spec_sha256(reordered))
        self.assertNotIn("\n", vs.canonical_json(spec))

    def test_loader_rejects_non_standard_json_constants(self) -> None:
        with tempfile.TemporaryDirectory(prefix="super-eli5-json-") as tmp:
            path = Path(tmp) / "non-standard.json"
            for constant in ("NaN", "Infinity", "-Infinity"):
                path.write_text(f'{{"version": {constant}}}', encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "非標準 JSON 常數"):
                    vs.load_spec(path)


class ValidatorContractTests(unittest.TestCase):
    def test_minimal_concept_passes(self) -> None:
        result = vs.validate_spec(minimal_concept_spec())
        self.assertTrue(result.ok, result.as_dict())
        self.assertEqual(result.verification, {"e_doc": "structural"})

    def test_unknown_top_level_field_rejected(self) -> None:
        spec = minimal_concept_spec()
        spec["extra"] = 1
        self.assertIn("top_level_unknown_field", error_codes(vs.validate_spec(spec)))

    def test_boolean_cannot_impersonate_integer_fields(self) -> None:
        version = minimal_concept_spec()
        version["version"] = True
        self.assertIn("version_unsupported", error_codes(vs.validate_spec(version)))

        trace = minimal_concept_spec()
        trace["trace"][0]["step"] = True
        self.assertIn("trace_step_type", error_codes(vs.validate_spec(trace)))

    def test_duplicate_node_ids_across_scenes_rejected(self) -> None:
        spec = minimal_concept_spec()
        second = copy.deepcopy(spec["scenes"][0])
        second["id"] = "s2"
        spec["scenes"].append(second)
        self.assertIn("id_duplicate", error_codes(vs.validate_spec(spec)))

    def test_edge_to_unknown_node_and_self_loop_rejected(self) -> None:
        spec = minimal_concept_spec()
        spec["scenes"][0]["edges"].append({"from": "n_ask", "to": "n_missing"})
        spec["scenes"][0]["edges"].append({"from": "n_cache", "to": "n_cache"})
        codes = error_codes(vs.validate_spec(spec))
        self.assertIn("edge_ref_missing", codes)
        self.assertIn("edge_self_loop", codes)

    def test_structured_reference_values_fail_without_crashing(self) -> None:
        edge = minimal_concept_spec()
        edge["scenes"][0]["edges"][0]["from"] = {}
        self.assertIn("edge_ref_type", error_codes(vs.validate_spec(edge)))

        trace = minimal_concept_spec()
        trace["trace"][0]["node"] = []
        self.assertIn("trace_node_type", error_codes(vs.validate_spec(trace)))

    def test_unsafe_locators_rejected(self) -> None:
        for locator in ("javascript:alert(1)", "data:text/html,hi", "/etc/passwd", "C:\\secrets\\x.txt", "../outside.md", "~/notes.md", "ftp://host/file"):
            spec = minimal_concept_spec()
            spec["evidence"][0]["locator"] = locator
            self.assertIn("locator_invalid", error_codes(vs.validate_spec(spec)), locator)

    def test_verified_requires_quote_snapshot_identity_and_url_retrieved_at(self) -> None:
        spec = minimal_concept_spec()
        del spec["evidence"][0]["quote"]
        del spec["evidence"][0]["retrieved_at"]
        del spec["evidence"][0]["content_sha256"]
        codes = error_codes(vs.validate_spec(spec))
        self.assertIn("verified_quote_missing", codes)
        self.assertIn("verified_immutable_ref_missing", codes)
        self.assertIn("verified_url_retrieved_at_missing", codes)
        self.assertIn("verified_url_content_identity_missing", codes)

    def test_git_identity_requires_repo_and_full_commit_sha(self) -> None:
        spec = minimal_concept_spec()
        spec["evidence"][0]["commit_sha"] = "abcdef0"
        codes = error_codes(vs.validate_spec(spec))
        self.assertIn("commit_sha_invalid", codes)
        self.assertIn("git_identity_incomplete", codes)

        spec["evidence"][0]["commit_sha"] = "a" * 40
        spec["evidence"][0]["repo_url"] = "https://github.com/example/project"
        self.assertTrue(vs.validate_spec(spec).ok, vs.validate_spec(spec).as_dict())

    def test_verified_node_needs_verified_evidence(self) -> None:
        spec = minimal_concept_spec()
        spec["scenes"][0]["nodes"][1]["evidence"] = ["e_note"]
        self.assertIn("verified_without_verified_evidence", error_codes(vs.validate_spec(spec)))

    def test_all_analogy_spec_rejected(self) -> None:
        spec = minimal_concept_spec()
        for node in spec["scenes"][0]["nodes"]:
            node["status"] = "analogy"
            node["evidence"] = []
        self.assertIn("analogy_only", error_codes(vs.validate_spec(spec)))

    def test_inferred_requires_reasoning(self) -> None:
        spec = minimal_concept_spec()
        spec["evidence"].append({"id": "e_guess", "status": "inferred", "claim": "沒有理由的推論"})
        self.assertIn("inferred_reasoning_missing", error_codes(vs.validate_spec(spec)))

    def test_trace_sequence_and_scene_mismatch(self) -> None:
        spec = minimal_concept_spec()
        spec["trace"][1]["step"] = 5
        spec["trace"][0]["scene"] = "s_wrong"
        codes = error_codes(vs.validate_spec(spec))
        self.assertIn("trace_step_sequence", codes)
        self.assertIn("trace_scene_mismatch", codes)

    def test_failure_lens_cannot_be_analogy(self) -> None:
        spec = minimal_concept_spec()
        spec["failure_lens"][0]["status"] = "analogy"
        self.assertIn("status_analogy_forbidden", error_codes(vs.validate_spec(spec)))

    def test_text_limits_and_control_chars(self) -> None:
        spec = minimal_concept_spec()
        spec["one_liner"] = "太長" * 40
        spec["title"] = "有控制字元\x07"
        codes = error_codes(vs.validate_spec(spec))
        self.assertIn("text_too_long", codes)
        self.assertIn("text_control_char", codes)


class ModeContractTests(unittest.TestCase):
    def test_incident_chronology_rules(self) -> None:
        spec = vs.load_spec(EXAMPLES / "incident-dashboard-zero.zh-TW.json")
        broken = copy.deepcopy(spec)
        timeline = broken["mode_data"]["timeline"]
        timeline[1]["kind"], timeline[5]["kind"] = "recovery", "first_break"
        self.assertIn("timeline_recovery_before_break", error_codes(vs.validate_spec(broken)))
        out_of_order = copy.deepcopy(spec)
        out_of_order["mode_data"]["timeline"][2]["t"] = "2026-08-18T01:00:00+08:00"
        self.assertIn("timeline_out_of_order", error_codes(vs.validate_spec(out_of_order)))
        analogy_cause = copy.deepcopy(spec)
        analogy_cause["mode_data"]["root_cause"]["status"] = "analogy"
        self.assertIn("status_analogy_forbidden", error_codes(vs.validate_spec(analogy_cause)))

    def test_metric_definition_and_comparison_rules(self) -> None:
        spec = vs.load_spec(EXAMPLES / "metric-mau.zh-TW.json")
        unverified = copy.deepcopy(spec)
        unverified["mode_data"]["definition"]["status"] = "inferred"
        self.assertIn("definition_not_verified", error_codes(vs.validate_spec(unverified)))
        no_evidence = copy.deepcopy(spec)
        no_evidence["mode_data"]["comparison"]["evidence"] = []
        self.assertIn("comparison_evidence_missing", error_codes(vs.validate_spec(no_evidence)))
        empty_scope = copy.deepcopy(spec)
        empty_scope["mode_data"]["scope"] = {"grain": "", "time_window": "", "filters": ""}
        self.assertIn("scope_empty", error_codes(vs.validate_spec(empty_scope)))

    def test_module_requires_local_verified_evidence_and_non_analogy_entry(self) -> None:
        spec = vs.load_spec(FIXTURES / "module-daily-orders.zh-TW.json")
        spec["evidence"][0]["content_sha256"] = "0" * 64
        self.assertTrue(vs.validate_spec(spec).ok, vs.validate_spec(spec).as_dict())
        url_only = copy.deepcopy(spec)
        url_only["evidence"][0]["locator"] = "https://example.org/daily_orders.py"
        url_only["evidence"][0]["retrieved_at"] = "2026-08-25"
        self.assertIn("module_local_evidence_missing", error_codes(vs.validate_spec(url_only)))
        analogy_entry = copy.deepcopy(spec)
        analogy_entry["scenes"][0]["nodes"][0]["status"] = "analogy"
        analogy_entry["scenes"][0]["nodes"][0]["evidence"] = []
        self.assertIn("module_node_analogy", error_codes(vs.validate_spec(analogy_entry)))

        invalid_entry = copy.deepcopy(spec)
        invalid_entry["mode_data"]["entry"] = {}
        self.assertIn("module_node_type", error_codes(vs.validate_spec(invalid_entry)))

    def test_tradeoff_recommendation_rules(self) -> None:
        spec = vs.load_spec(FIXTURES / "tradeoff-batch-vs-stream.en.json")
        spec["evidence"][0]["content_sha256"] = "0" * 64
        self.assertTrue(vs.validate_spec(spec).ok, vs.validate_spec(spec).as_dict())
        bad_option = copy.deepcopy(spec)
        bad_option["mode_data"]["recommendation"]["option"] = "o_missing"
        self.assertIn("recommendation_option_missing", error_codes(vs.validate_spec(bad_option)))
        analogy_rec = copy.deepcopy(spec)
        analogy_rec["mode_data"]["recommendation"]["status"] = "analogy"
        self.assertIn("status_analogy_forbidden", error_codes(vs.validate_spec(analogy_rec)))
        one_option = copy.deepcopy(spec)
        one_option["mode_data"]["options"] = one_option["mode_data"]["options"][:1]
        self.assertIn("list_bounds", error_codes(vs.validate_spec(one_option)))

    def test_tradeoff_node_references_have_an_explicit_array_contract(self) -> None:
        spec = vs.load_spec(FIXTURES / "tradeoff-batch-vs-stream.en.json")
        spec["evidence"][0]["content_sha256"] = "0" * 64

        string_nodes = copy.deepcopy(spec)
        string_nodes["mode_data"]["options"][0]["nodes"] = "n_batch"
        self.assertIn("option_nodes_type", error_codes(vs.validate_spec(string_nodes)))

        structured_node = copy.deepcopy(spec)
        structured_node["mode_data"]["options"][0]["nodes"] = [{}]
        self.assertIn("option_node_type", error_codes(vs.validate_spec(structured_node)))

        structured_recommendation = copy.deepcopy(spec)
        structured_recommendation["mode_data"]["recommendation"]["option"] = {}
        self.assertIn("recommendation_option_type", error_codes(vs.validate_spec(structured_recommendation)))


class ProvenanceBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="super-eli5-test-")
        self.root = Path(self.tmp.name)
        for rel in ("pipeline/daily_orders.py", "docs/adr-0007-batch-vs-stream.md"):
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((FIXTURES / "sources" / rel).read_bytes())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_bind_sets_hash_and_quote_checked_then_detects_source_change(self) -> None:
        spec = vs.load_spec(FIXTURES / "module-daily-orders.zh-TW.json")
        result = vs.validate_spec(spec, source_root=self.root, check_quotes=True, bind=True)
        self.assertTrue(result.ok, result.as_dict())
        evidence = spec["evidence"][0]
        expected = hashlib.sha256((self.root / "pipeline/daily_orders.py").read_bytes()).hexdigest()
        self.assertEqual(evidence["content_sha256"], expected)
        self.assertEqual(evidence["verification"], "quote-checked")
        self.assertEqual(result.verification, {"e_py": "quote-checked"})

        (self.root / "pipeline/daily_orders.py").write_text("MIN_ROWS = 1\n", encoding="utf-8")
        stale = vs.validate_spec(spec, source_root=self.root, check_quotes=True)
        self.assertIn("content_sha256_mismatch", error_codes(stale))

    def test_quote_not_found_and_line_range_enforced(self) -> None:
        spec = vs.load_spec(FIXTURES / "module-daily-orders.zh-TW.json")
        spec["evidence"][0]["quote"] = "this text is not in the file"
        result = vs.validate_spec(spec, source_root=self.root, check_quotes=True, bind=True)
        self.assertIn("quote_not_found", error_codes(result))

        outside_range = vs.load_spec(FIXTURES / "module-daily-orders.zh-TW.json")
        outside_range["evidence"][0]["line_start"] = 1
        outside_range["evidence"][0]["line_end"] = 5
        result = vs.validate_spec(outside_range, source_root=self.root, check_quotes=True, bind=True)
        self.assertIn("quote_not_found", error_codes(result))

    def test_explicit_quote_check_or_bind_fails_when_source_is_missing(self) -> None:
        spec = vs.load_spec(FIXTURES / "module-daily-orders.zh-TW.json")
        spec["evidence"][0]["content_sha256"] = "0" * 64
        missing_root = self.root / "missing"
        missing_root.mkdir()

        checked = vs.validate_spec(copy.deepcopy(spec), source_root=missing_root, check_quotes=True)
        self.assertIn("source_not_found", error_codes(checked))

        bound = vs.validate_spec(copy.deepcopy(spec), source_root=missing_root, bind=True)
        self.assertIn("source_not_found", error_codes(bound))

    def test_locator_cannot_escape_source_root(self) -> None:
        spec = vs.load_spec(FIXTURES / "module-daily-orders.zh-TW.json")
        secret = self.root.parent / "outside-secret.txt"
        secret.write_text("if len(rows) < MIN_ROWS:\n", encoding="utf-8")
        try:
            inner = self.root / "pipeline" / "sub"
            inner.mkdir()
            spec["evidence"][0]["locator"] = "pipeline/sub/../../../outside-secret.txt"
            self.assertIn("locator_invalid", error_codes(vs.validate_spec(spec, source_root=inner)))
            direct = vs.load_spec(FIXTURES / "module-daily-orders.zh-TW.json")
            direct["evidence"][0]["content_sha256"] = "0" * 64
            self.assertIsNone(vs.resolve_local_source(inner, "../../../outside-secret.txt"))
        finally:
            secret.unlink()

    def test_claimed_level_above_confirmed_is_stale(self) -> None:
        spec = vs.load_spec(FIXTURES / "module-daily-orders.zh-TW.json")
        spec["evidence"][0]["content_sha256"] = hashlib.sha256((self.root / "pipeline/daily_orders.py").read_bytes()).hexdigest()
        spec["evidence"][0]["verification"] = "quote-checked"
        spec["evidence"][0]["quote"] = "not really in the file"
        result = vs.validate_spec(spec, source_root=self.root, check_quotes=True)
        self.assertIn("quote_not_found", error_codes(result))

    def test_bind_cli_is_no_clobber_unless_forced(self) -> None:
        out = self.root / "bound.json"
        out.write_text("{}", encoding="utf-8")
        argv = [str(FIXTURES / "module-daily-orders.zh-TW.json"), "--source-root", str(self.root), "--check-quotes", "--bind", "--out", str(out), "--json"]
        with _captured_stdout() as stdout:
            code = vs.main(argv)
        self.assertEqual(code, 1)
        self.assertIn("bind_write_failed", stdout.getvalue())
        with _captured_stdout() as stdout:
            code = vs.main(argv + ["--force"])
        self.assertEqual(code, 0, stdout.getvalue())
        bound = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(bound["evidence"][0]["verification"], "quote-checked")


class RenderAndVerifyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="super-eli5-render-")
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_bundled_examples_self_check(self) -> None:
        with _captured_stdout():
            self.assertEqual(self_check.main(["--json"]), 0)

    def test_render_is_deterministic_and_verifies(self) -> None:
        spec = minimal_concept_spec()
        first, second = render_html.render(spec), render_html.render(spec)
        self.assertEqual(first, second)
        report = va.verify_html(first, spec)
        self.assertEqual(report["status"], "PASS", report)
        self.assertTrue(report["reproduction"]["byte_identical"])
        self.assertTrue(report["pair"]["byte_identical"])
        self.assertNotIn("<script", first.lower())

    def test_renderer_ignores_self_declared_verification_level(self) -> None:
        spec = minimal_concept_spec()
        spec["evidence"][0]["content_sha256"] = "0" * 64
        spec["evidence"][0]["verification"] = "quote-checked"
        html_text = render_html.render(spec)
        self.assertIn('<td>結構</td>', html_text)
        self.assertEqual(va.verify_html(html_text)["status"], "PASS")

    def test_renderer_cli_displays_only_levels_checked_this_run(self) -> None:
        source_root = FIXTURES / "sources"
        spec = vs.load_spec(FIXTURES / "module-daily-orders.zh-TW.json")
        source = source_root / "pipeline" / "daily_orders.py"
        spec["evidence"][0]["content_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        spec["evidence"][0]["verification"] = "quote-checked"
        spec_path = self.root / "module.json"
        spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        out = self.root / "module.html"
        with _captured_stdout():
            code = render_html.main(
                [str(spec_path), str(out), "--workspace", str(self.root), "--source-root", str(source_root), "--check-quotes", "--json"]
            )
        self.assertEqual(code, 0)
        html_text = out.read_bytes().decode("utf-8")
        self.assertIn('<td>引述已核對</td>', html_text)
        self.assertEqual(va.verify_html(html_text)["status"], "PASS")

    def test_hostile_text_stays_inert(self) -> None:
        spec = minimal_concept_spec()
        hostile = '</pre><script>alert(1)</script><a href="https://evil.example">x</a>'
        spec["evidence"][0]["claim"] = hostile
        spec["scenes"][0]["nodes"][0]["label"] = "<img src=x onerror=alert(1)>"
        spec["title"] = "標題 <b>粗體</b> & 符號"
        self.assertTrue(vs.validate_spec(spec).ok)
        html_text = render_html.render(spec)
        report = va.verify_html(html_text, spec)
        self.assertEqual(report["status"], "PASS", report)
        self.assertIn("&lt;script&gt;", html_text)
        self.assertNotIn("<script>", html_text)
        self.assertNotIn('href="https://evil.example"', html_text)

    def test_tampering_is_detected(self) -> None:
        spec = minimal_concept_spec()
        html_text = render_html.render(spec)
        edited = html_text.replace("快取就是把常用的答案先抄一份放在手邊。", "快取永遠正確。", 1)
        self.assertNotEqual(edited, html_text)
        self.assertEqual(va.verify_html(edited, spec)["status"], "FAIL")
        standalone = va.verify_html(edited)
        self.assertEqual(standalone["status"], "FAIL")
        self.assertIn("embedded_render_mismatch", {item["code"] for item in standalone["findings"]})
        injected = html_text.replace("</main>", '<script>alert(1)</script></main>', 1)
        codes = {item["code"] for item in va.verify_html(injected)["findings"]}
        self.assertIn("script_tag", codes)
        restyled = html_text.replace("--accent:#0b5fa5", "--accent:#ff0000", 1)
        codes = {item["code"] for item in va.verify_html(restyled)["findings"]}
        self.assertTrue({"style_hash_mismatch", "csp_style_hash_mismatch", "style_not_trusted"} <= codes, codes)
        swapped = html_text.replace('<pre hidden id="super-eli5-spec">', '<pre hidden id="super-eli5-spec">{"version":1}', 1)
        codes = {item["code"] for item in va.verify_html(swapped)["findings"]}
        self.assertTrue(codes & {"embedded_spec_hash_mismatch", "embedded_spec_invalid_json"}, codes)
        linked = html_text.replace("</footer>", '<a href="https://evil.example/x">x</a></footer>', 1)
        codes = {item["code"] for item in va.verify_html(linked)["findings"]}
        self.assertIn("link_not_allowed", codes)

    def test_non_standard_embedded_json_is_reported_instead_of_crashing(self) -> None:
        html_text = render_html.render(minimal_concept_spec())
        malformed = html_text.replace('&quot;version&quot;:1', '&quot;version&quot;:NaN', 1)
        report = va.verify_html(malformed)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("embedded_spec_invalid_json", {item["code"] for item in report["findings"]})

    def test_all_languages_render(self) -> None:
        for language, marker in (("zh-TW", "一句話版"), ("zh-CN", "一句话版"), ("en", "One sentence")):
            spec = minimal_concept_spec(language)
            html_text = render_html.render(spec)
            self.assertIn(marker, html_text)
            self.assertEqual(va.verify_html(html_text, spec)["status"], "PASS")
        spec = vs.load_spec(FIXTURES / "tradeoff-batch-vs-stream.en.json")
        spec["evidence"][0]["content_sha256"] = "0" * 64
        html_text = render_html.render(spec)
        self.assertIn("Option comparison", html_text)
        self.assertEqual(va.verify_html(html_text, spec)["status"], "PASS")

    def test_cli_no_clobber_force_and_workspace_boundary(self) -> None:
        spec_path = self.root / "spec.json"
        spec_path.write_text(json.dumps(minimal_concept_spec(), ensure_ascii=False), encoding="utf-8")
        out = self.root / "out" / "explainer.html"
        argv = [str(spec_path), str(out), "--workspace", str(self.root), "--json"]
        with _captured_stdout():
            self.assertEqual(render_html.main(argv), 0)
        with _captured_stdout() as stdout:
            self.assertEqual(render_html.main(argv), 1)
        self.assertIn("write_refused", stdout.getvalue())
        with _captured_stdout():
            self.assertEqual(render_html.main(argv + ["--force"]), 0)
        outside = Path(tempfile.gettempdir()) / "super-eli5-escape.html"
        with _captured_stdout() as stdout:
            self.assertEqual(render_html.main([str(spec_path), str(outside), "--workspace", str(self.root)]), 1)
        self.assertFalse(outside.exists())
        self.assertIn("workspace", stdout.getvalue())

    @unittest.skipIf(os.name == "nt", "symlink 測試只在 POSIX 執行")
    def test_symlink_target_rejected(self) -> None:
        victim = self.root / "victim.html"
        victim.write_text("keep me", encoding="utf-8")
        link = self.root / "link.html"
        link.symlink_to(victim)
        with self.assertRaises(FileExistsError):
            render_html.write_text_atomic(link, "<html></html>", force=True, workspace=self.root)
        self.assertEqual(victim.read_text(encoding="utf-8"), "keep me")

    def test_invalid_spec_is_not_rendered(self) -> None:
        spec_path = self.root / "bad.json"
        bad = minimal_concept_spec()
        del bad["ladder"]
        spec_path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
        out = self.root / "bad.html"
        with _captured_stdout() as stdout:
            self.assertEqual(render_html.main([str(spec_path), str(out), "--workspace", str(self.root), "--json"]), 1)
        self.assertIn("spec_invalid", stdout.getvalue())
        self.assertFalse(out.exists())


class _captured_stdout:
    def __enter__(self):
        import io

        self._old = sys.stdout
        self.buffer = io.StringIO()
        sys.stdout = self.buffer
        return self.buffer

    def __exit__(self, *exc):
        sys.stdout = self._old
        return False


if __name__ == "__main__":
    unittest.main()
