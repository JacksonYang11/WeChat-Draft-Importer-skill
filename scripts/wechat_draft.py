#!/usr/bin/env python3
"""Independent WeChat draft importer. Python 3.9+, no model or browser runtime."""
import argparse
import contextlib
import datetime
import fcntl
import getpass
import hashlib
import html
from html.parser import HTMLParser
import io
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid

VERSION = "1.1.0"
API = "https://api.weixin.qq.com"
ROOT = Path(__file__).resolve().parent.parent
CONFIG = Path.home() / ".config/wechat-draft-importer/config.json"
PERSONAL = ROOT / "personal-settings.json"
DATA = Path.home() / ".local/share/wechat-draft-importer"
MAX_IMAGE = 950_000  # Stay below the documented <1 MB limit, including rounding differences.
STYLES = {
    "section": "font-size:16px;line-height:1.8;color:#333;word-wrap:break-word;",
    "p": "margin:0 0 18px;line-height:1.8;",
    "h1": "font-size:23px;font-weight:bold;margin:28px 0 18px;",
    "h2": "font-size:21px;font-weight:bold;margin:28px 0 16px;",
    "h3": "font-size:18px;font-weight:bold;margin:24px 0 14px;",
    "h4": "font-size:17px;font-weight:bold;margin:20px 0 12px;",
    "blockquote": "border-left:3px solid #aaa;padding:0 14px;color:#666;margin:18px 0;",
    "ul": "padding-left:26px;margin:0 0 18px;", "ol": "padding-left:26px;margin:0 0 18px;",
    "li": "margin:0 0 8px;", "img": "width:100%;height:auto;display:block;margin:16px auto;",
    "pre": "white-space:pre-wrap;background:#f5f5f5;padding:12px;font-size:14px;",
    "code": "font-family:monospace;", "strong": "font-weight:bold;",
    "em": "font-style:italic;", "hr": "border:0;border-top:1px solid #ddd;margin:24px 0;",
    "a": "color:#576b95;", "br": "",
}
VOID = {"img", "hr", "br"}


class Failure(Exception):
    def __init__(self, message, status="error", exit_code=1, **details):
        super().__init__(message)
        self.result = {"ok": False, "status": status, "message": message, **details}
        self.exit_code = exit_code


class ApiFailure(Failure):
    pass


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2), flush=True)


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data, private=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=".write-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, 0o600 if private else 0o644)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def save_json(path, value):
    atomic(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Failure("无法读取 JSON 文件：" + str(path), "invalid_input", 2)


def private_read(path):
    path = Path(path).expanduser()
    if os.name == "posix" and path.stat().st_mode & 0o077:
        raise Failure("密钥文件权限过宽，请先执行 chmod 600：" + str(path), "credentials", 3)
    return path.read_text(encoding="utf-8").strip()


def env_file(path):
    """Read literal assignments, never source/eval a user's shell file."""
    result = {}
    for line in private_read(path).splitlines():
        match = re.fullmatch(r"\s*(?:export\s+)?(WEIXIN_APPID|WEIXIN_APPSECRET)\s*=\s*(.*?)\s*", line)
        if not match:
            continue
        value = match[2]
        if value[:1] in ("'", '"'):
            if len(value) < 2 or value[-1] != value[0]:
                raise Failure("凭证文件中有不完整的引号", "credentials", 3)
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        if any(ch in value for ch in ("$", "`", "\n", "\r")):
            raise Failure("凭证文件须使用字面量，不能包含 shell 展开表达式", "credentials", 3)
        result[match[1]] = value
    return result


def settings(args):
    config = read_json(args.config) if args.config.is_file() else {}
    if not isinstance(config, dict):
        raise Failure("配置文件须为 JSON 对象", "invalid_input", 2)
    config.setdefault("network", "direct")
    config.setdefault("state_dir", str(DATA))
    if args.network:
        config["network"] = args.network
    if config["network"] not in ("direct", "system"):
        raise Failure("network 只能设置为 direct 或 system", "invalid_input", 2)
    # An existing user-owned config is supported without moving or printing secrets.
    old = Path.home() / ".config/wechat-workflow/env"
    if not any(config.get(key) for key in ("secret_file", "env_file")) and old.is_file():
        config["env_file"] = str(old)
    return config


def credentials(config):
    need_file = not os.environ.get("WEIXIN_APPID") or not os.environ.get("WEIXIN_APPSECRET")
    literal = env_file(Path(config["env_file"]).expanduser()) if need_file and config.get("env_file") else {}
    appid = os.environ.get("WEIXIN_APPID") or config.get("appid") or literal.get("WEIXIN_APPID")
    secret = os.environ.get("WEIXIN_APPSECRET")
    if not secret and config.get("secret_file"):
        secret = private_read(config["secret_file"])
    secret = secret or literal.get("WEIXIN_APPSECRET")
    if not appid or not secret:
        raise Failure("缺少公众号凭证，请在独立终端运行 configure，或配置环境变量/本地密钥文件。", "credentials", 3)
    if not re.fullmatch(r"wx[a-zA-Z0-9]{16}", appid):
        raise Failure("AppID 格式不正确", "credentials", 3)
    return appid, secret


def personal_settings(path=None):
    """Read publishing preferences without reading credentials or contacting WeChat."""
    explicit = path is not None
    path = Path(path).expanduser() if explicit else PERSONAL
    if not path.exists() and not explicit:
        return {}
    if not path.is_file():
        raise Failure("个人设置文件不存在：" + str(path), "invalid_input", 2)
    if path.stat().st_mode & 0o077:
        raise Failure("个人设置文件权限须为 600：" + str(path), "invalid_input", 2)
    value = read_json(path)
    allowed = {"author", "need_open_comment", "only_fans_can_comment", "backend_settings"}
    if not isinstance(value, dict) or set(value) - allowed:
        raise Failure("个人设置格式错误或含不支持的字段，见 personal-settings.example.json", "invalid_input", 2)
    if "author" in value and (not isinstance(value["author"], str) or len(value["author"]) > 16):
        raise Failure("个人设置 author 须为不超过 16 字的字符串", "invalid_input", 2)
    for key in ("need_open_comment", "only_fans_can_comment"):
        if key in value and (type(value[key]) is not int or value[key] not in (0, 1)):
            raise Failure("个人设置 " + key + " 须为数字 0 或 1", "invalid_input", 2)
    backend = value.get("backend_settings", {})
    if not isinstance(backend, dict) or set(backend) - {"original", "reward", "creation_source"}:
        raise Failure("backend_settings 含不支持的字段", "invalid_input", 2)
    for key in ("original", "reward"):
        if key in backend and type(backend[key]) is not bool:
            raise Failure("backend_settings 的开关须为 true 或 false", "invalid_input", 2)
    if "creation_source" in backend and (not isinstance(backend["creation_source"], str)
                                           or len(backend["creation_source"]) > 120):
        raise Failure("creation_source 须为不超过 120 字的字符串", "invalid_input", 2)
    return value


def manual_settings(profile):
    # These are preferences, not documented API fields and never part of an API payload.
    return [{"setting": key, "requested": value, "status": "manual_required"}
            for key, value in profile.get("backend_settings", {}).items()
            if key != "creation_source" or value]


class WeChat:
    """No automatic HTTP retries, redirects, or secret-bearing raw errors."""
    def __init__(self, appid, secret, network="direct"):
        self.appid, self.secret, self.token = appid, secret, None
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None
        handlers = [NoRedirect()]
        if network == "direct":
            handlers.append(urllib.request.ProxyHandler({}))
        self.opener = urllib.request.build_opener(*handlers)

    def call(self, path, payload=None, image=None, query=None):
        # Keep the executable's API surface restricted to draft preparation/readback.
        allowed = {"/cgi-bin/stable_token", "/cgi-bin/draft/count", "/cgi-bin/draft/batchget",
                   "/cgi-bin/draft/get", "/cgi-bin/draft/add", "/cgi-bin/draft/update",
                   "/cgi-bin/material/get_materialcount", "/cgi-bin/media/uploadimg",
                   "/cgi-bin/material/add_material"}
        if path not in allowed:
            raise Failure("此程序不支持该接口")
        params = dict(query or {})
        if self.token and path != "/cgi-bin/stable_token":
            params["access_token"] = self.token
        url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
        data, headers = None, {}
        if image is not None:
            boundary = "wx" + uuid.uuid4().hex
            mime = "image/png" if image.startswith(b"\x89PNG") else "image/jpeg"
            ext = "png" if mime == "image/png" else "jpg"
            data = (f'--{boundary}\r\nContent-Disposition: form-data; name="media"; filename="image.{ext}"\r\n'
                    f'Content-Type: {mime}\r\n\r\n').encode() + image + f"\r\n--{boundary}--\r\n".encode()
            headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
        elif payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode()
            headers["Content-Type"] = "application/json; charset=utf-8"
        try:
            with self.opener.open(urllib.request.Request(url, data=data, headers=headers), timeout=45) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            raise Failure("微信 HTTP 请求失败，未自动重试", "network", 5, http_status=error.code)
        except (OSError, ValueError, urllib.error.URLError):
            raise Failure("微信连接中断或响应无效，未自动重试；若正在写入，请先核查状态。", "network", 5)
        if not isinstance(result, dict):
            raise Failure("微信响应格式异常", "network", 5)
        code = result.get("errcode", 0)
        if code:
            details = {"wechat_code": code}
            if code == 40164:
                match = re.search(r"invalid ip\s+([^\s,]+)", result.get("errmsg", ""), re.I)
                if match:
                    try:
                        details["observed_ip"] = str(ipaddress.ip_address(match[1]))
                    except ValueError:
                        pass
                details["settings_url"] = f"https://developers.weixin.qq.com/console/product/mp/{self.appid}?tab1=basicInfo"
                raise ApiFailure("调用出口 IP 不在白名单；请在开发者平台更新，必要时由管理员扫码。", "ip_whitelist", 4, **details)
            hints = {40125: "密钥无效，请核对当前账号的 AppSecret。", 48001: "账号缺少此接口权限。",
                     45009: "今日接口额度已用尽。", 40001: "凭证无效或失效。", 42001: "凭证过期。",
                     89503: "微信要求管理员确认本次调用。", 40007: "素材或草稿 ID 无效，可能已删除或发表。",
                     88000: "公众号缺少留言功能权限；不会自动关闭留言后重试。"}
            raise ApiFailure(hints.get(code, "微信拒绝请求，请按错误码核对官方文档。"), "wechat_api", 6, **details)
        return result

    def login(self):
        result = self.call("/cgi-bin/stable_token", {"grant_type": "client_credential", "appid": self.appid,
                          "secret": self.secret, "force_refresh": False})
        self.token = result["access_token"]
        self.secret = None

    def get(self, media_id):
        return self.call("/cgi-bin/draft/get", {"media_id": media_id})


def dependencies():
    try:
        from markdown_it import MarkdownIt
        from PIL import Image, ImageOps
        return MarkdownIt, Image, ImageOps
    except ImportError:
        raise Failure("缺少运行依赖，请先运行 setup.sh。", "dependencies", 2)


def prepare_image(path):
    _, Image, ImageOps = dependencies()
    try:
        with Image.open(path) as source:
            if getattr(source, "is_animated", False):
                raise Failure("不支持动画图片，请先选定静态帧：" + str(path), "invalid_input", 2)
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGBA")
            background = Image.new("RGB", image.size, "white")
            background.paste(image, mask=image.getchannel("A"))
    except Failure:
        raise
    except Exception:
        raise Failure("图片损坏、格式不受支持或尺寸过大：" + str(path), "invalid_input", 2)
    original_size = background.size
    background.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
    for scale in range(9):
        for quality in (90, 82, 74, 65, 55):
            buffer = io.BytesIO()
            background.save(buffer, "JPEG", quality=quality, optimize=True)
            data = buffer.getvalue()
            if len(data) < MAX_IMAGE:
                return {"bytes": data, "hash": digest(data), "size": background.size,
                        "original_size": original_size, "source": str(path)}
        background.thumbnail((max(1, int(background.width * .8)), max(1, int(background.height * .8))), Image.Resampling.LANCZOS)
    raise Failure("无法将图片压缩到接口限制内：" + str(path), "invalid_input", 2)


class Content(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.images, self.output = [], [], []

    def handle_starttag(self, tag, attrs):
        if tag not in STYLES:
            raise Failure("排版中包含不支持的标签：" + tag, "invalid_input", 2)
        attrs = dict(attrs)
        safe = {"style": STYLES[tag]} if STYLES[tag] else {}
        if tag == "img":
            src = attrs.get("src") or attrs.get("data-src", "")
            self.images.append(src)
            safe.update(src=src, alt=attrs.get("alt", ""))
        if tag == "a":
            href = attrs.get("href", "")
            if urllib.parse.urlsplit(href).scheme in ("http", "https"):
                safe["href"] = href
        if tag == "ol" and attrs.get("start", "").isdigit():
            safe["start"] = attrs["start"]
        self.output.append("<" + tag + "".join(f' {k}="{html.escape(v, quote=True)}"' for k, v in safe.items()) + ">")

    def handle_endtag(self, tag):
        if tag not in VOID:
            self.output.append("</" + tag + ">")

    def handle_data(self, data):
        self.text.append(data)
        self.output.append(html.escape(data))


def visible(content):
    # Readback may contain extra wrappers inserted by WeChat: collect text/images only.
    class Reader(HTMLParser):
        def __init__(self):
            super().__init__()
            self.text, self.images = [], []

        def handle_data(self, data):
            self.text.append(data)

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "img":
                self.images.append(attrs.get("data-src") or attrs.get("src", ""))
    reader = Reader()
    reader.feed(content)
    return re.sub(r"\s+", "", "".join(reader.text)), [image_identity(url) for url in reader.images]


def image_identity(url):
    parsed = urllib.parse.urlsplit(url)
    parent, _, size = parsed.path.rpartition("/")
    return (parsed.hostname, parent if size.isdigit() else parsed.path)


def signature(article):
    text, images = visible(article.get("content", ""))
    value = {key: article.get(key, "") for key in ("title", "author", "digest", "thumb_media_id")}
    value.update(text=text, images=images)
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True).encode())


def remote_revision(article):
    """Also detect backend settings changes; temporary preview/CDN URLs are volatile."""
    class Layout(HTMLParser):
        def __init__(self):
            super().__init__()
            self.events = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "img":
                source = attrs.pop("data-src", None) or attrs.get("src", "")
                attrs.pop("src", None)
                attrs["image_resource"] = image_identity(source)
            self.events.append(("start", tag, sorted(attrs.items())))

        def handle_endtag(self, tag):
            self.events.append(("end", tag))

        def handle_data(self, data):
            self.events.append(("text", data))

    layout = Layout()
    layout.feed(article.get("content", ""))
    metadata = {key: value for key, value in article.items() if key not in ("content", "url", "thumb_url")}
    return digest(json.dumps({"content": signature(article), "layout": layout.events, "metadata": metadata},
                             ensure_ascii=False, sort_keys=True).encode())


def remove_digest_tokens(tokens, summary):
    """Remove only a matching standalone opening summary, keeping leading pictures."""
    removed, index = 0, 0
    normal = lambda text: re.sub(r"\s+", "", text)
    while index < len(tokens):
        quoted = tokens[index].type == "blockquote_open"
        start = index + int(quoted)
        if (start + 2 >= len(tokens) or tokens[start].type != "paragraph_open"
                or tokens[start + 1].type != "inline" or tokens[start + 2].type != "paragraph_close"):
            break
        end = start + 3
        if quoted:
            if end >= len(tokens) or tokens[end].type != "blockquote_close":
                break
            end += 1
        children = tokens[start + 1].children or []
        if any(child.type == "image" for child in children):
            if not quoted and all(child.type in ("image", "softbreak", "hardbreak")
                                  or (child.type == "text" and not child.content.strip()) for child in children):
                index = end
                continue
            break
        text = "".join(child.content for child in children if child.type in ("text", "code_inline"))
        # CommonMark may treat **摘要：**紧接中文 as literal punctuation.
        label = re.match(r"^\s*(?:\*\*|__)?(?:导语|摘要)\s*[：:]\s*(?:\*\*|__)?\s*", text)
        content = text[label.end():] if label else text
        if normal(content) == normal(summary):
            del tokens[index:end]
            removed += 1
        elif label:
            raise Failure("正文开头的导语与 digest 不一致；请把最终导语填入 digest，正文仅保留文章内容。", "invalid_input", 2)
        else:
            break
    return removed


def load_bundle(folder, profile=None):
    profile = profile or {}
    MarkdownIt, _, _ = dependencies()
    folder = Path(folder).expanduser().resolve()
    manifest = read_json(folder / "article.json")
    if not isinstance(manifest, dict):
        raise Failure("article.json 须为对象", "invalid_input", 2)
    # Empty legacy author fields inherit the local preference; explicit nonempty author wins.
    if not manifest.get("author") and profile.get("author"):
        manifest["author"] = profile["author"]
    for field in ("need_open_comment", "only_fans_can_comment"):
        if field not in manifest and field in profile:
            manifest[field] = profile[field]
        if field in manifest and (type(manifest[field]) is not int or manifest[field] not in (0, 1)):
            raise Failure(field + " 须为数字 0 或 1", "invalid_input", 2)
    if manifest.get("only_fans_can_comment") == 1 and manifest.get("need_open_comment") != 1:
        raise Failure("仅粉丝留言需同时设置 need_open_comment=1", "invalid_input", 2)
    for field in ("article_id", "title", "digest", "content", "cover"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            raise Failure("缺少有效字段：" + field, "invalid_input", 2)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", manifest["article_id"]):
        raise Failure("article_id 须为 1–96 位英文、数字、下划线或连字符", "invalid_input", 2)
    for field, limit in (("title", 32), ("author", 16), ("digest", 120)):
        if not isinstance(manifest.get(field, ""), str) or len(manifest.get(field, "")) > limit:
            raise Failure(f"{field} 超过 {limit} 字或格式错误", "invalid_input", 2)
    limit = manifest.get("max_chars", 3000)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 15000:
        raise Failure("max_chars 须为 1–15000 的整数", "invalid_input", 2)

    def local_path(value):
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            raise Failure("图片/文件须使用本地路径，不接受外链、file URL 或查询参数：" + value, "invalid_input", 2)
        path = Path(urllib.parse.unquote(value)).expanduser()
        path = path.resolve() if path.is_absolute() else (folder / path).resolve()
        if not path.is_file():
            raise Failure("文件不存在：" + str(path), "invalid_input", 2)
        return path

    content_path = local_path(manifest["content"])
    if content_path.suffix.lower() != ".md":
        raise Failure("正文请使用 UTF-8 Markdown（.md）", "invalid_input", 2)
    markdown = content_path.read_text(encoding="utf-8-sig")
    # A single title is carried in article.json; avoid duplicating it in the body.
    if re.match(r"\A\s*#\s+" + re.escape(manifest["title"]) + r"\s*(?:\n|$)", markdown):
        markdown = re.sub(r"\A\s*#\s+[^\n]*(?:\n|$)", "", markdown, count=1)
    renderer = MarkdownIt("commonmark", {"html": False, "breaks": True})
    tokens = renderer.parse(markdown)
    summary_removed = remove_digest_tokens(tokens, manifest["digest"])
    images, by_path, order = {}, {}, []

    def visit(items):
        for token in items:
            if token.type == "image":
                path = local_path(token.attrGet("src"))
                if path not in by_path:
                    key = "image_" + str(len(by_path) + 1)
                    by_path[path] = key
                    images[key] = prepare_image(path)
                key = by_path[path]
                order.append(key)
                token.attrSet("src", "wxasset:" + key)
            if token.children:
                visit(token.children)
    visit(tokens)
    cleaned = Content()
    cleaned.feed(renderer.renderer.render(tokens, renderer.options, {}))
    body = '<section style="' + STYLES["section"] + '">' + "".join(cleaned.output) + "</section>"
    text, _ = visible(body)
    if not text:
        raise Failure("正文为空", "invalid_input", 2)
    if len(text) > limit:
        raise Failure(f"正文可见非空白字符 {len(text)}，超过 {limit}，请先修改定稿", "invalid_input", 2)
    cover = prepare_image(local_path(manifest["cover"]))
    # Leave headroom for long WeChat CDN URLs replacing short placeholders.
    check_content(body.replace("wxasset:", "https://mmbiz.qpic.cn/"), reserve=len(order) * 600)
    fingerprint = digest(json.dumps({"manifest": manifest, "body": body, "cover": cover["hash"],
                                    "images": {key: value["hash"] for key, value in images.items()},
                                    "renderer": VERSION}, ensure_ascii=False, sort_keys=True).encode())
    return {"folder": folder, "manifest": manifest, "body": body, "images": images, "order": order,
            "cover": cover, "fingerprint": fingerprint, "char_count": len(text),
            "summary_paragraphs_removed": summary_removed, "manual_settings": manual_settings(profile)}


def check_content(content, reserve=0):
    if len(content) + reserve >= 20000 or len(content.encode()) + reserve >= 1_000_000:
        raise Failure("排版后的 HTML 超过微信限制，请减少格式或拆分文章", "invalid_input", 2)


def preview(bundle):
    output = bundle["folder"] / ".wechat-import"
    body = bundle["body"]
    sizes = []
    for key, asset in bundle["images"].items():
        name = key + ".jpg"
        atomic(output / name, asset["bytes"])
        body = body.replace("wxasset:" + key + '"', name + '"')
        sizes.append({"name": key, "bytes": len(asset["bytes"]), "size": asset["size"]})
    atomic(output / "cover.jpg", bundle["cover"]["bytes"])
    manifest = bundle["manifest"]
    document = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src \'self\' file:; style-src \'unsafe-inline\'">'
                '<title>公众号导入预览</title><body style="max-width:677px;margin:32px auto;padding:0 20px">'
                '<p>本地排版预览；微信可能改写样式，发布前请在公众号后台检查。</p><h1>' + html.escape(manifest["title"]) +
                '</h1><details><summary>摘要与封面设置（不属于上传正文）</summary><p>摘要：' +
                html.escape(manifest["digest"]) + '</p><p>封面原图（后台按比例裁切）：</p>'
                '<img src="cover.jpg" style="max-width:100%"></details><hr>' + body + '</body></html>')
    atomic(output / "preview.html", document.encode())
    return {"ok": True, "status": "prepared", "article_id": manifest["article_id"], "title": manifest["title"],
            "characters": bundle["char_count"], "inline_images": len(bundle["order"]), "images": sizes,
            "preview": str(output / "preview.html"), "fingerprint": bundle["fingerprint"],
            "summary_paragraphs_removed": bundle.get("summary_paragraphs_removed", 0),
            "manual_settings": bundle.get("manual_settings", [])}


@contextlib.contextmanager
def lock(path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Failure("同一篇文章正在由另一个进程处理", "locked", 7)
        yield
    finally:
        os.close(fd)


def state_path(config, appid, bundle):
    article_id = bundle["manifest"].get("article_id", "")
    if not isinstance(article_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", article_id):
        raise Failure("无效的 article_id", "invalid_input", 2)
    if not re.fullmatch(r"wx[a-zA-Z0-9]{16}", appid):
        raise Failure("无效的 AppID", "invalid_input", 2)
    return Path(config["state_dir"]).expanduser() / appid / (article_id + ".json")


def get_article(client, media_id):
    news = client.get(media_id).get("news_item", [])
    if len(news) != 1:
        raise Failure("此工具只管理单篇图文，目标草稿不是单篇结构", "conflict", 8)
    return news[0]


def verify(client, state):
    saved = get_article(client, state["media_id"])
    expected = state["expected"]
    checks = {field: saved.get(field, "") == expected.get(field, "")
              for field in ("title", "author", "digest", "thumb_media_id")}
    for field in ("need_open_comment", "only_fans_can_comment"):
        if field in expected:
            checks[field] = type(saved.get(field)) is int and saved[field] == expected[field]
    expected_text, expected_images = visible(expected["content"])
    actual_text, actual_images = visible(saved.get("content", ""))
    checks.update(text=actual_text == expected_text, images=actual_images == expected_images)
    if state.get("remote_signature"):
        checks["backend_unchanged"] = remote_revision(saved) == state["remote_signature"]
    state["checks"], state["verified"] = checks, all(checks.values())
    if state["verified"]:
        state["remote_signature"] = remote_revision(saved)
    state["checked_at"] = stamp()
    return state["verified"]


def crop_info(size):
    width, height = size
    crops = []
    for name, ratio in (("2.35_1", 2.35), ("1_1", 1)):
        if width / height > ratio:
            dx = (1 - ratio * height / width) / 2
            coords = (dx, 0, 1 - dx, 1)
        else:
            dy = (1 - width / ratio / height) / 2
            coords = (0, dy, 1, 1 - dy)
        crops.append(dict(ratio=name, **{key: f"{value:.8f}" for key, value in zip(("x1", "y1", "x2", "y2"), coords)}))
    return {"crop_percent_list": crops}


def import_bundle(client, config, bundle, update=False):
    path = state_path(config, client.appid, bundle)
    with lock(path.with_suffix(".lock")):
        state = read_json(path) if path.exists() else {"article_id": bundle["manifest"]["article_id"],
                  "appid": client.appid, "uploads": {}, "created_at": stamp()}
        if state.get("pending"):
            raise Failure("上次写入结果不确定，禁止重复提交；请先运行 reconcile 或核查素材。", "pending_write", 9,
                          pending=state["pending"], state_file=str(path))
        if state.get("appid") != client.appid:
            raise Failure("状态属于其他公众号", "conflict", 8)
        media_id = state.get("media_id")
        changed = state.get("fingerprint") != bundle["fingerprint"]
        if media_id:
            saved = get_article(client, media_id)
            if state.get("remote_signature") and remote_revision(saved) != state["remote_signature"]:
                raise Failure("后台草稿已有人工修改，停止覆盖；请核对后另行处理", "remote_changed", 8, media_id=media_id)
            if changed and not update:
                raise Failure("文章已导入且内容有变化；明确使用 import --update 才更新原草稿。", "update_required", 8,
                              media_id=media_id)
            if not changed:
                ok = verify(client, state)
                state["manual_settings"] = bundle.get("manual_settings", [])
                save_json(path, state)
                return result(state, path, "unchanged" if ok else "verification_failed")

        def write(operation, callback, required=()):
            state["pending"] = {"operation": operation, "at": stamp()}
            save_json(path, state)
            try:
                response = callback()
            except ApiFailure as error:
                # An explicit WeChat rejection did not complete the operation; transport errors remain ambiguous.
                rejected = {40001, 40002, 40005, 40007, 40009, 40013, 40125, 40164, 42001, 45009, 48001, 88000}
                if error.result.get("wechat_code") in rejected:
                    state.pop("pending", None)
                    state.pop("intended", None)
                    save_json(path, state)
                raise
            if any(key not in response for key in required):
                raise Failure("写入响应缺少必要字段，结果不确定；请核查后恢复", "pending_write", 9)
            return response

        def upload(asset, kind):
            key = kind + ":" + asset["hash"]
            if key in state["uploads"]:
                return state["uploads"][key]
            endpoint = "/cgi-bin/media/uploadimg" if kind == "inline" else "/cgi-bin/material/add_material"
            required = "url" if kind == "inline" else "media_id"
            response = write("upload:" + key, lambda: client.call(endpoint, image=asset["bytes"],
                             query={"type": "image"} if kind == "cover" else None), (required,))
            state["uploads"][key] = {required: response[required]}
            state.pop("pending", None)
            save_json(path, state)
            return state["uploads"][key]

        body = bundle["body"]
        for key, asset in bundle["images"].items():
            url = upload(asset, "inline")["url"]
            parsed = urllib.parse.urlsplit(url)
            if parsed.scheme not in ("http", "https") or not parsed.hostname or not parsed.hostname.endswith(".qpic.cn"):
                raise Failure("微信返回了非预期的图片域名", "wechat_api", 6)
            body = body.replace("wxasset:" + key + '"', html.escape(url, quote=True) + '"')
        check_content(body)
        cover = upload(bundle["cover"], "cover")["media_id"]
        manifest = bundle["manifest"]
        article = {"article_type": "news", "title": manifest["title"], "author": manifest.get("author", ""),
                   "digest": manifest["digest"], "content": body, "thumb_media_id": cover,
                   "cover_info": crop_info(bundle["cover"]["size"])}
        for field in ("need_open_comment", "only_fans_can_comment"):
            if field in manifest:
                article[field] = manifest[field]
        # Persist intended content before the network call, so reconcile can compare an ambiguous result.
        state["intended"] = {"expected": article, "fingerprint": bundle["fingerprint"], "title": manifest["title"],
                             "manual_settings": bundle.get("manual_settings", [])}
        if media_id:
            write("draft_update", lambda: client.call("/cgi-bin/draft/update", {"media_id": media_id, "index": 0, "articles": article}))
        else:
            response = write("draft_add", lambda: client.call("/cgi-bin/draft/add", {"articles": [article]}), ("media_id",))
            state["media_id"] = response["media_id"]
        state.update(state.pop("intended"))
        state.pop("pending", None)
        state.pop("remote_signature", None)
        save_json(path, state)
        verify(client, state)
        save_json(path, state)
        return result(state, path, "imported" if state["verified"] else "verification_failed")


def result(state, path, status):
    return {"ok": bool(state.get("verified")), "status": status, "title": state.get("title"),
            "media_id": state.get("media_id"), "checks": state.get("checks"), "state_file": str(path),
            "manual_settings": state.get("manual_settings", []),
            "message": "草稿已保存并核验，请到公众号后台完成原创等设置和最终发布。" if state.get("verified") else "草稿核验未通过，请查看检查项。"}


def reconcile(client, config, bundle):
    path = state_path(config, client.appid, bundle)
    with lock(path.with_suffix(".lock")):
        state = read_json(path)
        operation = state.get("pending", {}).get("operation")
        if operation not in ("draft_add", "draft_update"):
            raise Failure("没有待核查的草稿写入；素材上传不确定时须人工核查，程序不会盲目重传。", "pending_write", 9)
        intended = state.get("intended")
        if not intended:
            raise Failure("缺少待写入内容记录，须人工核查", "pending_write", 9)
        if operation == "draft_update":
            candidates = [state["media_id"]]
        else:
            candidates = []
            offset = 0
            # Bounded read-only scan. A no-match result is never permission to retry creation.
            while offset < 1000:
                page = client.call("/cgi-bin/draft/batchget", {"offset": offset, "count": 20, "no_content": 0})
                items = page.get("item", [])
                for item in items:
                    news = item.get("content", {}).get("news_item", [])
                    if (len(news) == 1 and signature(news[0]) == signature(intended["expected"])
                            and all(type(news[0].get(field)) is int and news[0][field] == intended["expected"][field]
                                    for field in ("need_open_comment", "only_fans_can_comment")
                                    if field in intended["expected"])):
                        candidates.append(item["media_id"])
                offset += len(items)
                if not items or offset >= page.get("total_count", 0):
                    break
        if len(candidates) != 1:
            raise Failure("未找到唯一匹配草稿，保持暂停；不要清空状态后重新创建。", "pending_write", 9,
                          candidates=candidates, scanned_at_most=1000)
        state["media_id"] = candidates[0]
        state.update(intended)
        state.pop("remote_signature", None)
        if not verify(client, state):
            raise Failure("候选草稿回读不一致，保持暂停", "pending_write", 9)
        state.pop("intended", None)
        state.pop("pending", None)
        save_json(path, state)
        return result(state, path, "reconciled")


def configure(args):
    if not sys.stdin.isatty():
        raise Failure("configure 需要本人在独立终端交互输入；Agent 请使用 doctor 检查已有配置。", "credentials", 3)
    if args.config.exists():
        raise Failure("已有配置，避免隐式覆盖；请直接编辑配置或指定新的 --config 路径。", "conflict", 8)
    appid = input("公众号 AppID：").strip()
    if not re.fullmatch(r"wx[a-zA-Z0-9]{16}", appid):
        raise Failure("AppID 格式不正确", "invalid_input", 2)
    secret = getpass.getpass("AppSecret（隐藏输入，只保存本机）：").strip()
    if not secret:
        raise Failure("密钥为空", "credentials", 3)
    secret_path = args.config.parent / "appsecret.txt"
    if secret_path.exists():
        raise Failure("本地密钥文件已存在，不自动覆盖", "conflict", 8)
    atomic(secret_path, secret.encode())
    save_json(args.config, {"appid": appid, "secret_file": str(secret_path.resolve()), "network": "direct", "state_dir": str(DATA)})
    return {"ok": True, "status": "configured", "config": str(args.config), "message": "配置完成，密钥未显示；文件权限为 600。"}


def initialize(folder):
    _, Image, _ = dependencies()
    folder = Path(folder).expanduser().resolve()
    if folder.exists():
        raise Failure("示例目录已存在，不覆盖：" + str(folder), "conflict", 8)
    folder.mkdir(parents=True)
    (folder / "images").mkdir()
    Image.new("RGB", (1200, 675), (73, 103, 130)).save(folder / "images/illustration.jpg")
    Image.new("RGB", (1410, 600), (90, 75, 55)).save(folder / "images/cover.jpg")
    save_json(folder / "article.json", {"article_id": str(uuid.uuid4()), "title": "公众号草稿导入示例",
              "author": "", "digest": "用于验证文稿、封面和插图交接的示例。", "content": "article.md",
              "cover": "images/cover.jpg", "max_chars": 3000})
    atomic(folder / "article.md", "这是一份示例正文，请替换为已确认的文章。\n\n## 小标题\n\n图片紧跟对应段落。\n\n![第一张插图](images/illustration.jpg)\n\n图片后的正文。\n".encode())
    return {"ok": True, "status": "initialized", "bundle": str(folder)}


def install_skill(target, project=None):
    roots = {"trae": Path.home() / ".trae-cn/skills", "harness": Path.home() / ".dsh/skills",
             "shared": Path.home() / ".agents/skills"}
    if project:
        roots = {"trae": project / ".trae/skills", "harness": project / ".dsh/skills", "shared": project / ".agents/skills"}
    dest = roots[target] / "wechat-draft-importer"
    if dest.exists():
        raise Failure("目标 skill 已存在，未覆盖：" + str(dest), "conflict", 8)
    # Copy a release allowlist, never arbitrary files later placed beside the tool.
    files = (
        "SKILL.md", "README.md", "LICENSE", "requirements.txt", "setup.sh", "wechat-draft", "Start.command", ".gitignore",
        "personal-settings.example.json", "docs/article-settings.md",
        "scripts/wechat_draft.py", "tests/test_importer.py", "references/article-format.md",
        "references/feasibility.md", "docs/usage.md", "docs/troubleshooting.md", "docs/agent-install.md",
        "example-article/article.json",
        "example-article/article.md", "example-article/images/cover.jpg", "example-article/images/illustration.jpg",
    )
    dest.mkdir(parents=True)
    for name in files:
        source = ROOT / name
        if source.is_file():
            output = dest / name
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, output)
    return {"ok": True, "status": "installed", "skill": str(dest),
            "message": "已复制完整便携包，请在目标 Agent 中加载 skill；首次使用需运行该目录 setup.sh。"}


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--version", action="version", version=VERSION)
    p.add_argument("--config", type=Path, default=CONFIG)
    p.add_argument("--personal-settings", type=Path, help="个人偏好 JSON 路径；默认读取程序根目录 personal-settings.json，不读取密钥")
    p.add_argument("--network", choices=("direct", "system"), help="微信连接默认直连；system 显式使用系统代理")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("configure", help="本人在终端隐藏输入并保存凭证")
    sub.add_parser("doctor", help="只读检测凭证、网络、白名单、草稿与素材读取")
    init = sub.add_parser("init", help="生成文章交接示例")
    init.add_argument("folder")
    for cmd in ("prepare", "import", "status", "verify", "reconcile"):
        child = sub.add_parser(cmd)
        child.add_argument("folder", help="包含 article.json 的文章目录")
        if cmd == "import":
            child.add_argument("--update", action="store_true", help="明确更新此 article_id 以前导入的草稿")
    install = sub.add_parser("install-skill")
    install.add_argument("--target", choices=("trae", "harness", "shared"), required=True)
    install.add_argument("--project", type=Path, help="安装至指定项目；省略为用户目录")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == "configure":
        value = configure(args)
    elif args.command == "init":
        value = initialize(args.folder)
    elif args.command == "install-skill":
        value = install_skill(args.target, args.project)
    else:
        config = {} if args.command == "prepare" else settings(args)
        profile = personal_settings(args.personal_settings) if args.command in ("prepare", "import") else {}
        if args.command == "prepare":
            value = preview(load_bundle(args.folder, profile))
        else:
            # status does not read secrets or contact WeChat.
            if args.command == "status":
                manifest = read_json(Path(args.folder).expanduser() / "article.json")
                appid = os.environ.get("WEIXIN_APPID") or config.get("appid")
                if not appid and config.get("env_file"):
                    appid = env_file(config["env_file"]).get("WEIXIN_APPID")
                if not appid:
                    raise Failure("未配置 AppID", "credentials", 3)
                bundle = {"manifest": manifest}
                path = state_path(config, appid, bundle)
                state = read_json(path)
                value = {"ok": True, "status": "local_status", "state_file": str(path), "state": state}
            else:
                bundle = load_bundle(args.folder, profile) if hasattr(args, "folder") else None
                appid, secret = credentials(config)
                client = WeChat(appid, secret, config["network"])
                client.login()
                if args.command == "doctor":
                    drafts = client.call("/cgi-bin/draft/count")
                    materials = client.call("/cgi-bin/material/get_materialcount")
                    value = {"ok": True, "status": "ready", "appid": appid, "network": config["network"],
                             "draft_count": drafts.get("total_count"), "image_count": materials.get("image_count"),
                             "message": "凭证和读取接口正常；不等于本次已验证上传和新增草稿。"}
                elif args.command == "import":
                    local_preview = preview(bundle)
                    value = import_bundle(client, config, bundle, args.update)
                    value["preview"] = local_preview["preview"]
                elif args.command == "reconcile":
                    value = reconcile(client, config, bundle)
                else:
                    path = state_path(config, appid, bundle)
                    with lock(path.with_suffix(".lock")):
                        state = read_json(path)
                        if state.get("pending"):
                            raise Failure("请先 reconcile 处理未确定的写入", "pending_write", 9)
                        verify(client, state)
                        save_json(path, state)
                        value = result(state, path, "verified" if state["verified"] else "verification_failed")
    emit(value)
    return 0 if value.get("ok") else 10


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Failure as error:
        emit(error.result)
        sys.exit(error.exit_code)
    except KeyboardInterrupt:
        emit({"ok": False, "status": "interrupted", "message": "已中断；重跑会检查写入状态。"})
        sys.exit(130)
    except Exception as error:
        # Never print tracebacks or urllib error strings containing credential-bearing URLs.
        emit({"ok": False, "status": "unexpected", "error_type": type(error).__name__,
              "message": "程序停止；未输出可能包含凭证的异常详情。请先检查本地状态。"})
        sys.exit(1)
