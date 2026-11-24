---
name: wechat-draft-importer
description: 将已定稿的 Markdown、导语、封面和插图导入微信公众号草稿箱，支持本机 API 检测、图片压缩、断点恢复和回读核验。适用于 Trae、DeepSeek Harness 等能执行本地命令的 Agent；不负责写作、生图、原创声明或发布。
---

# 微信公众号草稿导入

核心是本目录的独立命令行程序，不需要 Codex 或任何模型 API。以本 skill 实际目录为 `TOOL_DIR`，文章文件夹为 `ARTICLE_DIR`；命令中的路径应正确引用，不能把用户文本拼成 shell 代码。

首次使用先执行 `sh "$TOOL_DIR/setup.sh"`，以后运行 `"$TOOL_DIR/wechat-draft" ...`。离线部署须预装 requirements.txt 中的依赖。

## 复用本机凭证

如果本机已完成凭证配置，后续直接调用程序，无需重复配置。程序默认读取当前系统用户下的：

- `~/.config/wechat-draft-importer/config.json`：AppID 和密钥路径。
- `~/.config/wechat-draft-importer/appsecret.txt`：AppSecret（实际路径以配置为准）。

本机真实使用的凭证正保存在上述两个路径；`~` 表示当前系统用户的主目录。配置与密钥均在当前项目目录之外，不随 Git 提交，无需在本项目的 `.gitignore` 中添加外部路径。其他设备须先检查自己的实际配置，不能假定已配置。

这些文件与 skill 安装位置无关；同一系统用户的 Trae、Harness 或独立命令共用，不需要复制到文章或 skill 目录。换设备或系统用户时先由 `doctor` 检查是否已有配置，不能假定凭证随 skill 迁移。

不要因为开启了新会话、从桌面启动 Agent、环境变量为空或首次使用某个 Agent，就让用户重新输入 AppID/AppSecret、运行 configure 或配置环境变量。直接执行 `doctor`，让程序读取已保存的配置；不要 cat、打印或把密钥正文读入对话。程序仍支持用户主动设置的环境变量覆盖本地配置，排查时仅检查变量是否存在，不输出值。

## 输入与执行

1. 读取用户明确指定的定稿及图片；已有文章目录先读 `article.json`。没有交接包时按 [文章格式](references/article-format.md) 整理到独立目录，保留原文、不自行重写，不从最近目录猜文章或封面。
2. `prepare "$ARTICLE_DIR"` 仅在本地产生压缩图片和预览，检查返回的图片数量、字数和路径。`prepare` 不访问微信也不需要密钥。
3. 用户已要求导入此篇到自己的公众号时，执行 `doctor`，通过后执行 `import "$ARTICLE_DIR"`。不需要为同一项已授权导入重复征求确认。命令默认微信直连，不能擅自切换代理。
4. 成功结果须 `ok=true` 且核验项全部通过。返回标题、media_id、预览和状态路径。用户继续在后台声明原创、设置赞赏/合集、检查封面并发布。

程序输出为 JSON；日志不得包含 AppSecret、token、凭证文件正文或完整 HTTP 异常。退出码及恢复方式见 [使用说明](README.md)。

## 必须正确处理的状态

- 退出码 4 / `ip_whitelist`：显示 `observed_ip` 和 `settings_url`，等用户更新白名单及本人扫码；之后重跑。不要把查询网站的代理 IP 当作微信 IP，不自动扩大白名单。
- 退出码 3：先依据错误检查默认配置是否存在、密钥文件是否存在且非空、权限是否为 600、是否传错 --config。检查只返回存在性、权限等状态，不显示凭证值。已有配置不重新运行 configure；权限或路径问题先修复原文件。确实缺失、内容错误或用户已更换凭证时，才提示本人在本地补充或修正相应文件，不要求两项全部重填、不在聊天索取密钥、不重置凭证。支持既有 `~/.config/wechat-workflow/env`，不依赖 Agent 加载 shell 配置。
- `unchanged`：同一内容已导入并核验，无需创建新草稿。用户明确要求替换旧稿时才使用 `import --update`。发现后台人工改动则停止。
- 退出码 9 / `pending_write`：不能清除状态、改变 article_id 或循环重跑来绕过。草稿写入可用 `reconcile "$ARTICLE_DIR"` 只读核查并接管唯一匹配稿；上传素材结果不确定时停止并说明需人工核查。
- 检测失败、草稿已发表/删除、回读不一致时不得报告成功，不自动新建替代稿。用户若刻意要新稿，再创建新的交接包及 article_id。

## 交付与可移植性

技能须保留整个文件夹；只复制 SKILL.md 会丢失程序。用户自行调用命令可完全不启动 Agent。
安装到 Trae/DSH 的方法见 README；调研与已知限制见 [技术调研](references/feasibility.md)。安装脚本只复制程序，不复制虚拟环境、状态或凭证。未实际验证目标 Agent 已加载技能时，不声称完成了跨 Agent 联调。
