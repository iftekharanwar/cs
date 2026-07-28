#!/usr/bin/env python3
"""
Tests for cs, run with: python3 test_cs.py

These cover the parsing of Claude Code's on-disk files, which is the part most
likely to break: the formats are internal to Claude Code and can change without
notice. Each test builds a fake ~/.claude tree, so nothing here depends on the
machine it runs on or on real session data.
"""

import json, os, shutil, sys, tempfile, time, unittest
from pathlib import Path

CS = Path(__file__).resolve().parent / "bin" / "cs"


def load_cs(home):
    """Import bin/cs with HOME pointed at a throwaway directory."""
    for mod in ("cs",):
        sys.modules.pop(mod, None)
    os.environ["HOME"] = str(home)
    # bin/cs has no .py suffix, so the loader has to be named explicitly.
    import importlib.util
    from importlib.machinery import SourceFileLoader
    spec = importlib.util.spec_from_loader("cs", SourceFileLoader("cs", str(CS)))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Fixture:
    """A minimal ~/.claude tree: a history file plus matching transcripts."""

    def __init__(self):
        self.home = Path(tempfile.mkdtemp())
        self.claude = self.home / ".claude"
        (self.claude / "projects").mkdir(parents=True)
        self.hist = self.claude / "history.jsonl"
        self.hist.touch()

    def prompt(self, sid, text, project="/work/app", ts=None):
        rec = {
            "sessionId": sid,
            "display": text,
            "project": project,
            "timestamp": ts if ts is not None else int(time.time() * 1000),
        }
        with self.hist.open("a") as f:
            f.write(json.dumps(rec) + "\n")

    def transcript(self, sid, title=None, turns=(), slug="-work-app"):
        d = self.claude / "projects" / slug
        d.mkdir(parents=True, exist_ok=True)
        lines = []
        for role, text in turns:
            lines.append(json.dumps({
                "type": role,
                "message": {"content": [{"type": "text", "text": text}]},
            }))
        if title:
            lines.append(json.dumps({"type": "ai-title", "aiTitle": title}))
        (d / f"{sid}.jsonl").write_text("\n".join(lines) + "\n")

    def close(self):
        shutil.rmtree(self.home, ignore_errors=True)


class ParsingTests(unittest.TestCase):
    def setUp(self):
        self.real_home = os.environ.get("HOME")
        self.fx = Fixture()

    def tearDown(self):
        self.fx.close()
        if self.real_home:
            os.environ["HOME"] = self.real_home

    def test_reads_history_records(self):
        self.fx.prompt("aaa11111", "first prompt")
        self.fx.prompt("aaa11111", "second prompt")
        cs = load_cs(self.fx.home)
        self.assertEqual(len(cs.load_history()), 2)

    def test_skips_malformed_lines(self):
        self.fx.prompt("aaa11111", "good line")
        with self.fx.hist.open("a") as f:
            f.write("this is not json\n")
            f.write(json.dumps({"display": "no session id"}) + "\n")
        cs = load_cs(self.fx.home)
        self.assertEqual(len(cs.load_history()), 1)

    def test_groups_prompts_into_one_session(self):
        for i in range(4):
            self.fx.prompt("bbb22222", f"prompt {i}")
        cs = load_cs(self.fx.home)
        entries = cs.group_sessions(cs.load_history())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["n"], 4)

    def test_title_comes_from_transcript(self):
        self.fx.prompt("ccc33333", "add pagination")
        self.fx.transcript("ccc33333", title="Add pagination to search")
        cs = load_cs(self.fx.home)
        self.assertEqual(cs.ai_title("ccc33333"), "Add pagination to search")

    def test_last_title_wins_when_repeated(self):
        # ai-title lines repeat and drift as a session is resumed; the most
        # recent one is the accurate description.
        self.fx.prompt("ddd44444", "hello")
        d = self.fx.claude / "projects" / "-work-app"
        d.mkdir(parents=True, exist_ok=True)
        (d / "ddd44444.jsonl").write_text(
            json.dumps({"type": "ai-title", "aiTitle": "Early guess"}) + "\n" +
            json.dumps({"type": "ai-title", "aiTitle": "Final title"}) + "\n")
        cs = load_cs(self.fx.home)
        self.assertEqual(cs.ai_title("ddd44444"), "Final title")

    def test_subagent_transcripts_are_not_sessions(self):
        # Nested directories hold subagent transcripts. Treating them as
        # resumable sessions would offer conversations that cannot be resumed.
        self.fx.prompt("eee55555", "parent session")
        self.fx.transcript("eee55555", title="Parent")
        nested = self.fx.claude / "projects" / "-work-app" / "subagents"
        nested.mkdir(parents=True, exist_ok=True)
        (nested / "fff66666.jsonl").write_text(
            json.dumps({"type": "ai-title", "aiTitle": "Subagent"}) + "\n")
        cs = load_cs(self.fx.home)
        index = cs.build_index()
        self.assertIn("eee55555", index)
        self.assertNotIn("fff66666", index)

    def test_reads_conversation_turns(self):
        self.fx.prompt("ggg77777", "question")
        self.fx.transcript("ggg77777", title="T", turns=[
            ("user", "how do I retry a failed job"),
            ("assistant", "use exponential backoff"),
        ])
        cs = load_cs(self.fx.home)
        f = cs.find_session_file("ggg77777")
        roles = [r for r, _ in cs.iter_messages(f)]
        self.assertEqual(roles, ["user", "assistant"])

    def test_sidechain_turns_are_skipped(self):
        self.fx.prompt("hhh88888", "question")
        d = self.fx.claude / "projects" / "-work-app"
        d.mkdir(parents=True, exist_ok=True)
        (d / "hhh88888.jsonl").write_text("\n".join([
            json.dumps({"type": "user", "isSidechain": True,
                        "message": {"content": [{"type": "text",
                                                 "text": "subagent chatter"}]}}),
            json.dumps({"type": "user",
                        "message": {"content": [{"type": "text",
                                                 "text": "real question"}]}}),
        ]) + "\n")
        cs = load_cs(self.fx.home)
        texts = [t for _, t in cs.iter_messages(cs.find_session_file("hhh88888"))]
        self.assertEqual(texts, ["real question"])


class SearchRangeTests(unittest.TestCase):
    """The 7-day window applies to browsing only. Anything naming a target
    searches all of history, or old work reports as missing."""

    def setUp(self):
        self.real_home = os.environ.get("HOME")
        self.fx = Fixture()
        old = int((time.time() - 60 * 86400) * 1000)
        self.fx.prompt("old00001", "kafka consumer lag", ts=old)
        self.fx.prompt("new00002", "recent work")

    def tearDown(self):
        self.fx.close()
        if self.real_home:
            os.environ["HOME"] = self.real_home

    def run_cs(self, *args):
        import subprocess
        env = dict(os.environ, HOME=str(self.fx.home))
        return subprocess.run([sys.executable, str(CS), *args],
                              capture_output=True, text=True, env=env).stdout

    def test_bare_listing_shows_recent_only(self):
        out = self.run_cs()
        self.assertIn("new00002"[:8], out)
        self.assertNotIn("old00001"[:8], out)

    def test_query_searches_all_time(self):
        out = self.run_cs("kafka")
        self.assertIn("old00001"[:8], out)

    def test_project_filter_searches_all_time(self):
        out = self.run_cs("-p", "app")
        self.assertIn("old00001"[:8], out)

    def test_view_finds_old_session_by_id(self):
        out = self.run_cs("-v", "old00001")
        self.assertNotIn("no session matching", out)

    def test_explicit_days_still_narrows_a_search(self):
        out = self.run_cs("-d", "3", "kafka")
        self.assertNotIn("old00001"[:8], out)


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.real_home = os.environ.get("HOME")
        self.fx = Fixture()

    def tearDown(self):
        self.fx.close()
        if self.real_home:
            os.environ["HOME"] = self.real_home

    def run_doctor(self):
        import subprocess
        env = dict(os.environ, HOME=str(self.fx.home))
        r = subprocess.run([sys.executable, str(CS), "--doctor"],
                           capture_output=True, text=True, env=env)
        return r.returncode, r.stdout

    def test_passes_on_a_healthy_tree(self):
        self.fx.prompt("iii99999", "a prompt")
        self.fx.transcript("iii99999", title="A title", turns=[
            ("user", "question"), ("assistant", "answer")])
        code, out = self.run_doctor()
        self.assertEqual(code, 0)
        self.assertIn("Formats match", out)

    def test_fails_when_a_required_field_disappears(self):
        # Simulates Claude Code renaming a field this tool depends on.
        with self.fx.hist.open("a") as f:
            f.write(json.dumps({"sessionId": "jjj00000", "project": "/work/app",
                                "timestamp": int(time.time() * 1000)}) + "\n")
        code, out = self.run_doctor()
        self.assertEqual(code, 1)
        self.assertIn("display", out)

    def test_fails_when_history_is_missing(self):
        self.fx.hist.unlink()
        code, out = self.run_doctor()
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
