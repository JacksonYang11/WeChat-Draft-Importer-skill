---
name: wechat-draft-importer
description: 将已定稿的 Markdown、导语、封面和插图导入微信公众号草稿箱，支持本机 API 检测、图片压缩、断点恢复和回读核验。适用于 Trae、DeepSeek Harness 等能执行本地命令的 Agent；不负责写作、生图或发布。
---

# 微信公众号草稿导入

核心是本目录的独立命令行程序，不需要 Codex 或任何模型 API。以本 skill 实际目录为 `TOOL_DIR`，文章文件夹为 `ARTICLE_DIR`；命令中的路径应正确引用，不能把用户文本拼成 shell 代码。

首次使用先执行 `sh "$TOOL_DIR/setup.sh"`，以后运行 `"$TOOL_DIR/wechat-draft" ...`。离线部署须预装 requirements.txt 中的依赖。

## 复用本机凭证

程序默认读取 `~/.config/wechat-draft-importer/config.json` 和同目录的 `appsecret.txt`（`~` 指当前系统用户）。这两份文件在项目目录之外，与 skill 安装位置无关，不随 Git 提交或安装迁移。

只要 `doctor` 能通过就直接使用：不要因为新会话、环境变量为空或首次使用某个 Agent，就让用户重新输入 AppID/AppSecret、运行 configure 或配置环境变量。不要 cat、打印或把密钥正文读入对话，排查时只检查存在性与权限。换设备或系统用户时先运行 `doctor` 检查已有配置。凭证读取顺序与自定义配置见 [使用说明](docs/usage.md#凭证配置)。

## 个人偏好与设置范围

作者、留言默认值保存在本 Skill 根目录的 `personal-settings.json`（权限 600），由程序自动读取。不要在 Skill、代码、通用示例或文章交接文件中硬编码个人默认作者；文章 author 可省略或留空以继承个人设置。不必因新会话或安装副本而重填。自定义位置用全局参数 `--personal-settings`；字段规则、Git 排除及接口依据见 [文章设置](docs/article-settings.md)。


导语只放 article.json 的 digest，不能同时写进正文。整理交接包时将独立的导语/摘要段落移出正文，保留原稿；程序会去掉与 digest 完全对应的开头摘要，遇到标记摘要与 digest 不符时停止核对，不自行重写。预览中的折叠设置区域不是上传正文。

## 输入与执行

1. 读取用户明确指定的定稿及图片；已有文章目录先读 `article.json`。没有交接包时按 [文章格式](references/article-format.md) 整理到文章所在目录下的 `wechat-draft-package/`，保留原文、不自行重写，不从最近目录猜文章或封面。交接包目录固定叫 `wechat-draft-package`，不要另起名字（如 wechat-handoff、wechat-draft）；已存在同名目录时直接复用。
2. `prepare "$ARTICLE_DIR"` 仅在本地产生压缩图片和预览，检查返回的图片数量、字数和路径。`prepare` 不访问微信也不需要密钥。
3. 用户已要求导入此篇到自己的公众号时，执行 `doctor`，通过后执行 `import "$ARTICLE_DIR"`。不需要为同一项已授权导入重复征求确认。命令默认微信直连，不能擅自切换代理。
4. 成功结果须 `ok=true` 且核验项全部通过。返回标题、media_id、预览和状态路径。用户在后台检查排版和封面后自行发布。

程序输出为 JSON；日志不得包含 AppSecret、token、凭证文件正文或完整 HTTP 异常。退出码及恢复方式见 [故障排查](docs/troubleshooting.md)。

## 必须正确处理的状态

- 退出码 4 / `ip_whitelist`：显示 `observed_ip` 和 `settings_url`，等用户更新白名单及本人扫码；之后重跑。不要把查询网站的代理 IP 当作微信 IP，不自动扩大白名单。
- 退出码 3：先依据错误检查默认配置是否存在、密钥文件是否存在且非空、权限是否为 600、是否传错 --config。检查只返回存在性、权限等状态，不显示凭证值。已有配置不重新运行 configure；权限或路径问题先修复原文件。确实缺失、内容错误或用户已更换凭证时，才提示本人在本地补充或修正相应文件，不要求两项全部重填、不在聊天索取密钥、不重置凭证。支持既有 `~/.config/wechat-workflow/env`，不依赖 Agent 加载 shell 配置。
- `unchanged`：同一内容已导入并核验，无需创建新草稿。用户明确要求替换旧稿时才使用 `import --update`。发现后台人工改动则停止。
- 退出码 9 / `pending_write`：不能清除状态、改变 article_id 或循环重跑来绕过。草稿写入可用 `reconcile "$ARTICLE_DIR"` 只读核查并接管唯一匹配稿；上传素材结果不确定时停止并说明需人工核查。
- 检测失败、草稿已发表/删除、回读不一致时不得报告成功，不自动新建替代稿。用户若刻意要新稿，再创建新的交接包及 article_id。

## 交付与可移植性

技能须保留整个文件夹；只复制 SKILL.md 会丢失程序。用户自行调用命令可完全不启动 Agent。
安装到 Trae/DSH 的方法见 [Agent 安装](docs/agent-install.md)；已知限制见 [技术调研](references/feasibility.md)。安装脚本只复制程序，不复制虚拟环境、状态或凭证。未实际验证目标 Agent 已加载技能时，不声称完成了跨 Agent 联调。
