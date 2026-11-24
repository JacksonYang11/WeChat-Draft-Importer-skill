"""Behavioral checks with isolated files and a fake WeChat account. No live writes."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import wechat_draft as w
from PIL import Image


class FakeWeChat:
    appid = "wx1234567890abcdef"

    def __init__(self):
        self.remote, self.calls = {}, []
        self.fail, self.reject = None, None

    def get(self, media_id):
        self.calls.append("get")
        if media_id not in self.remote:
            raise w.ApiFailure("not found", "wechat_api", 6, wechat_code=40007)
        article = copy.deepcopy(self.remote[media_id])
        article["content"] = article["content"].replace('src="http:', 'data-src="https:').replace('/0?from=', '/640?from=')
        article["url"] = "https://mp.weixin.qq.com/s?tempkey=" + str(len(self.calls))
        return {"news_item": [article]}

    def call(self, path, payload=None, image=None, query=None):
        self.calls.append(path)
        if self.reject == path:
            self.reject = None
            raise w.ApiFailure("explicit rejection", "wechat_api", 6, wechat_code=45009)
        if path.endswith("uploadimg"):
            if self.fail == "upload":
                self.fail = None
                raise w.Failure("network timeout", "network", 5)
            return {"url": "http://mmbiz.qpic.cn/sz_mmbiz_jpg/" + w.digest(image) + "/0?from=appmsg"}
        if path.endswith("add_material"):
            return {"media_id": "cover-" + w.digest(image)}
        if path.endswith("draft/add"):
            media_id = "draft-" + str(len(self.remote) + 1)
            self.remote[media_id] = copy.deepcopy(payload["articles"][0])
            if self.fail == "add":
                self.fail = None
                raise w.Failure("timeout after server committed", "network", 5)
            return {"media_id": media_id}
        if path.endswith("draft/update"):
            self.remote[payload["media_id"]] = copy.deepcopy(payload["articles"])
            if self.fail == "update":
                self.fail = None
                raise w.Failure("timeout after server committed", "network", 5)
            return {"errcode": 0}
        if path.endswith("draft/batchget"):
            return {"total_count": len(self.remote), "item": [
                {"media_id": key, "content": {"news_item": [value]}} for key, value in self.remote.items()]}
        raise AssertionError(path)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wechat-import-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / "文章 空格"
        w.initialize(self.folder)
        self.config = {"state_dir": str(self.root / "state")}
        self.client = FakeWeChat()

    def bundle(self):
        return w.load_bundle(self.folder)

    def saved(self):
        return w.read_json(w.state_path(self.config, self.client.appid, self.bundle()))

    def change(self):
        with (self.folder / "article.md").open("a") as f:
            f.write("\n修改后的一段内容。\n")

    def test_full_import_readback_normalization_and_no_duplicate(self):
        first = w.import_bundle(self.client, self.config, self.bundle())
        second = w.import_bundle(self.client, self.config, self.bundle())
        self.assertTrue(first["ok"])
        self.assertTrue(all(first["checks"].values()))
        self.assertEqual(second["status"], "unchanged")
        self.assertEqual(self.client.calls.count("/cgi-bin/draft/add"), 1)
        self.assertEqual(self.client.calls.count("/cgi-bin/media/uploadimg"), 1)
        self.assertEqual(len(self.client.remote), 1)

    def test_explicit_update_uses_original_id_and_cached_images(self):
        first = w.import_bundle(self.client, self.config, self.bundle())
        self.change()
        with self.assertRaises(w.Failure) as error:
            w.import_bundle(self.client, self.config, self.bundle())
        self.assertEqual(error.exception.result["status"], "update_required")
        second = w.import_bundle(self.client, self.config, self.bundle(), update=True)
        self.assertTrue(second["ok"])
        self.assertEqual(first["media_id"], second["media_id"])
        self.assertEqual(self.client.calls.count("/cgi-bin/media/uploadimg"), 1)

    def test_failed_update_does_not_mark_new_revision_committed(self):
        w.import_bundle(self.client, self.config, self.bundle())
        old = self.saved()["fingerprint"]
        self.change()
        self.client.reject = "/cgi-bin/draft/update"
        with self.assertRaises(w.ApiFailure):
            w.import_bundle(self.client, self.config, self.bundle(), update=True)
        state = self.saved()
        self.assertEqual(state["fingerprint"], old)
        self.assertNotIn("pending", state)
        self.assertNotIn("intended", state)
        self.assertTrue(w.import_bundle(self.client, self.config, self.bundle(), update=True)["ok"])

    def test_manual_backend_text_and_settings_not_overwritten(self):
        first = w.import_bundle(self.client, self.config, self.bundle())
        self.client.remote[first["media_id"]]["need_open_comment"] = 1
        self.change()
        with self.assertRaises(w.Failure) as error:
            w.import_bundle(self.client, self.config, self.bundle(), update=True)
        self.assertEqual(error.exception.result["status"], "remote_changed")
        self.assertNotIn("/cgi-bin/draft/update", self.client.calls)

    def test_verify_does_not_silently_accept_backend_settings_changes(self):
        first = w.import_bundle(self.client, self.config, self.bundle())
        state = self.saved()
        baseline = state["remote_signature"]
        self.client.remote[first["media_id"]]["need_open_comment"] = 1
        self.assertFalse(w.verify(self.client, state))
        self.assertEqual(state["remote_signature"], baseline)
        self.assertFalse(state["checks"]["backend_unchanged"])

    def test_manual_backend_layout_not_overwritten(self):
        first = w.import_bundle(self.client, self.config, self.bundle())
        article = self.client.remote[first["media_id"]]
        article["content"] = article["content"].replace("font-size:16px", "font-size:20px")
        self.change()
        with self.assertRaises(w.Failure) as error:
            w.import_bundle(self.client, self.config, self.bundle(), update=True)
        self.assertEqual(error.exception.result["status"], "remote_changed")
        self.assertNotIn("/cgi-bin/draft/update", self.client.calls)

    def test_generic_wechat_system_error_does_not_clear_pending(self):
        original = self.client.call
        def fail_system(path, *args, **kwargs):
            if path.endswith("draft/add"):
                raise w.ApiFailure("system busy", "wechat_api", 6, wechat_code=-1)
            return original(path, *args, **kwargs)
        self.client.call = fail_system
        with self.assertRaises(w.ApiFailure):
            w.import_bundle(self.client, self.config, self.bundle())
        self.assertEqual(self.saved()["pending"]["operation"], "draft_add")

    def test_ambiguous_creation_reconciles_without_resubmission(self):
        self.client.fail = "add"
        with self.assertRaises(w.Failure):
            w.import_bundle(self.client, self.config, self.bundle())
        self.assertEqual(self.saved()["pending"]["operation"], "draft_add")
        with self.assertRaises(w.Failure):
            w.import_bundle(self.client, self.config, self.bundle())
        recovered = w.reconcile(self.client, self.config, self.bundle())
        self.assertTrue(recovered["ok"])
        self.assertNotIn("pending", self.saved())
        self.assertEqual(self.client.calls.count("/cgi-bin/draft/add"), 1)

    def test_ambiguous_update_reconciles_intended_revision(self):
        w.import_bundle(self.client, self.config, self.bundle())
        self.change()
        self.client.fail = "update"
        with self.assertRaises(w.Failure):
            w.import_bundle(self.client, self.config, self.bundle(), update=True)
        self.assertTrue(w.reconcile(self.client, self.config, self.bundle())["ok"])
        self.assertEqual(self.saved()["fingerprint"], self.bundle()["fingerprint"])

    def test_missing_ambiguous_draft_keeps_pending(self):
        self.client.fail = "add"
        with self.assertRaises(w.Failure):
            w.import_bundle(self.client, self.config, self.bundle())
        self.client.remote.clear()
        with self.assertRaises(w.Failure):
            w.reconcile(self.client, self.config, self.bundle())
        self.assertIn("pending", self.saved())

    def test_upload_timeout_is_not_blindly_retried(self):
        self.client.fail = "upload"
        with self.assertRaises(w.Failure):
            w.import_bundle(self.client, self.config, self.bundle())
        with self.assertRaises(w.Failure):
            w.import_bundle(self.client, self.config, self.bundle())
        self.assertEqual(self.client.calls.count("/cgi-bin/media/uploadimg"), 1)

    def test_deleted_draft_not_recreated(self):
        w.import_bundle(self.client, self.config, self.bundle())
        self.client.remote.clear()
        with self.assertRaises(w.ApiFailure):
            w.import_bundle(self.client, self.config, self.bundle())
        self.assertEqual(self.client.calls.count("/cgi-bin/draft/add"), 1)

    def test_moving_article_does_not_change_identity(self):
        w.import_bundle(self.client, self.config, self.bundle())
        destination = self.root / "moved"
        shutil.move(str(self.folder), destination)
        self.folder = destination
        self.assertEqual(w.import_bundle(self.client, self.config, self.bundle())["status"], "unchanged")

    def test_wrong_image_or_wrong_order_fails_verification(self):
        second = self.folder / "images/second.png"
        Image.new("RGB", (100, 100), "red").save(second)
        with (self.folder / "article.md").open("a") as f:
            f.write("\n![second](images/second.png)\n")
        result = w.import_bundle(self.client, self.config, self.bundle())
        state = self.saved()
        article = self.client.remote[result["media_id"]]
        urls = []
        for value in state["uploads"].values():
            if "url" in value:
                urls.append(value["url"])
        article["content"] = article["content"].replace(urls[0], "PLACEHOLDER").replace(urls[1], urls[0]).replace("PLACEHOLDER", urls[1])
        self.assertFalse(w.verify(self.client, state))
        self.assertFalse(state["checks"]["images"])

    def test_concurrent_processes_block_same_article(self):
        path = self.root / "lock"
        with w.lock(path):
            with self.assertRaises(w.Failure) as error:
                with w.lock(path):
                    pass
        self.assertEqual(error.exception.result["status"], "locked")

    def test_offline_preview_and_invalid_external_image(self):
        preview = w.preview(self.bundle())
        content = Path(preview["preview"]).read_text()
        self.assertIn('src="image_1.jpg"', content)
        self.assertNotIn("wxasset:", content)
        with (self.folder / "article.md").open("a") as f:
            f.write("\n![external](https://example.com/private.png)\n")
        with self.assertRaises(w.Failure):
            self.bundle()
        self.assertFalse(self.client.calls)

    def test_oversized_text_stops_before_network(self):
        (self.folder / "article.md").write_text("字" * 3001)
        with self.assertRaises(w.Failure):
            self.bundle()
        self.assertFalse(self.client.calls)

    def test_webp_and_large_noisy_image_compressed_without_modifying_source(self):
        path = self.root / "large.webp"
        Image.effect_noise((2400, 1600), 100).convert("RGB").save(path, "WEBP", lossless=True)
        before = path.read_bytes()
        prepared = w.prepare_image(path)
        self.assertLess(len(prepared["bytes"]), 1_000_000)
        self.assertEqual(before, path.read_bytes())
        with Image.open(io.BytesIO(prepared["bytes"])) as converted:
            self.assertEqual(converted.format, "JPEG")
            self.assertLessEqual(max(converted.size), 1920)

    def test_duplicate_inline_reference_uploaded_once_but_checked_twice(self):
        with (self.folder / "article.md").open("a") as f:
            f.write("\n![again](images/illustration.jpg)\n")
        bundle = self.bundle()
        self.assertEqual(len(bundle["images"]), 1)
        self.assertEqual(len(bundle["order"]), 2)
        self.assertTrue(w.import_bundle(self.client, self.config, bundle)["ok"])
        self.assertEqual(self.client.calls.count("/cgi-bin/media/uploadimg"), 1)


class CredentialAndTransportTests(unittest.TestCase):
    def test_literal_env_is_not_shell_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "env"
            file.write_text('export WEIXIN_APPSECRET="$(touch dangerous)"\n')
            file.chmod(0o600)
            with self.assertRaises(w.Failure):
                w.env_file(file)
            file.write_text('WEIXIN_APPID=wx1234567890abcdef\nWEIXIN_APPSECRET="private-value"\n')
            self.assertEqual(w.env_file(file)["WEIXIN_APPSECRET"], "private-value")
            file.chmod(0o644)
            with self.assertRaises(w.Failure):
                w.env_file(file)

    def test_wechat_whitelist_error_only_exposes_validated_ip(self):
        client = w.WeChat("wx1234567890abcdef", "SECRET")
        body = {"errcode": 40164, "errmsg": "invalid ip 192.0.2.1, not in whitelist secret=SECRET"}
        with patch.object(client.opener, "open", return_value=io.BytesIO(json.dumps(body).encode())):
            with self.assertRaises(w.ApiFailure) as error:
                client.login()
        result = error.exception.result
        self.assertEqual(result["observed_ip"], "192.0.2.1")
        self.assertNotIn("SECRET", json.dumps(result))

    def test_http_error_never_leaks_token_url(self):
        client = w.WeChat("wx1234567890abcdef", "SECRET")
        client.token = "PRIVATE_TOKEN"
        failure = urllib.error.HTTPError("https://api.weixin.qq.com/?access_token=PRIVATE_TOKEN", 500, "error", {}, None)
        with patch.object(client.opener, "open", side_effect=failure):
            with self.assertRaises(w.Failure) as error:
                client.call("/cgi-bin/draft/count")
        self.assertNotIn("PRIVATE_TOKEN", json.dumps(error.exception.result))

    def test_publish_and_delete_are_not_executable(self):
        client = w.WeChat("wx1234567890abcdef", "SECRET")
        with patch.object(client.opener, "open") as network:
            for path in ("/cgi-bin/freepublish/submit", "/cgi-bin/draft/delete"):
                with self.assertRaises(w.Failure):
                    client.call(path)
            network.assert_not_called()

    def test_program_runs_from_other_directory_with_spaces_without_codex(self):
        with tempfile.TemporaryDirectory(prefix="portable importer ") as temp:
            bundle = Path(temp) / "article"
            program = w.ROOT / "scripts/wechat_draft.py"
            for command in (["init", str(bundle)], ["prepare", str(bundle)]):
                process = subprocess.run([sys.executable, str(program)] + command, cwd=temp,
                                         env={"PATH": os.environ["PATH"]}, capture_output=True, text=True)
                self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
                self.assertTrue(json.loads(process.stdout)["ok"])

    def test_skill_copy_is_self_contained_and_excludes_virtualenv(self):
        with tempfile.TemporaryDirectory(prefix="skill-copy-test-") as temp:
            value = w.install_skill("harness", Path(temp))
            target = Path(value["skill"])
            self.assertTrue((target / "SKILL.md").is_file())
            self.assertTrue((target / "scripts/wechat_draft.py").is_file())
            self.assertFalse((target / ".venv").exists())
            process = subprocess.run([sys.executable, str(target / "scripts/wechat_draft.py"), "--version"],
                                     cwd=temp, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0)
            self.assertEqual(process.stdout.strip(), w.VERSION)

    def test_skill_copy_does_not_copy_unrelated_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            root.mkdir()
            (root / "SKILL.md").write_text("skill")
            (root / "appsecret.txt").write_text("do-not-copy")
            (root / "private-account.json").write_text("do-not-copy")
            with patch.object(w, "ROOT", root):
                value = w.install_skill("trae", Path(temp) / "project")
            target = Path(value["skill"])
            self.assertTrue((target / "SKILL.md").exists())
            self.assertFalse((target / "appsecret.txt").exists())
            self.assertFalse((target / "private-account.json").exists())

    def test_offline_preview_does_not_read_account_config(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "article"
            w.initialize(folder)
            bad_config = Path(temp) / "broken-config.json"
            bad_config.write_text("not JSON")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(w.main(["--config", str(bad_config), "prepare", str(folder)]), 0)

    def test_state_path_rejects_traversal(self):
        with self.assertRaises(w.Failure):
            w.state_path({"state_dir": "/tmp"}, "wx1234567890abcdef", {"manifest": {"article_id": "../../other"}})


if __name__ == "__main__":
    unittest.main()
