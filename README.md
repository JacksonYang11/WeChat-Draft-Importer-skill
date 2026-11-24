# WeChat Draft Importer

独立运行的微信公众号草稿导入工具。核心程序不调用模型，不依赖 Codex、浏览器自动化或云服务器；也可作为 Trae / DeepSeek Harness 的 skill 调用。

## 首次运行

在 macOS/Linux 终端执行（Python 3.9+）：

```bash
cd "/path/to/wechat-draft-importer"
sh setup.sh
./wechat-draft doctor
```

setup.sh 创建本目录 .venv 并从 PyPI 安装 Pillow、markdown-it-py，仅首次需要联网下载依赖。启动程序支持任意工作目录，路径中有空格也可。不必激活虚拟环境。不支持直接双击 Windows 批处理；现版本以 macOS/Linux 验证。

已有 `WEIXIN_APPID` / `WEIXIN_APPSECRET` 环境变量时直接使用；也支持既有 `~/.config/wechat-workflow/env`，程序只读字面量，不执行 shell。凭证文件权限须为 600。若没有配置，在**本人终端**执行：

```bash
./wechat-draft configure
```

这会隐藏输入密钥，保存至 `~/.config/wechat-draft-importer/appsecret.txt`（权限 600），配置保存至同目录 config.json。不修改公众号密钥，不复制此前临时文件，不依赖任何 Agent 持有的临时状态。相同系统账号仍能访问本地密钥文件。

**如果本机已完成凭证配置，后续可直接运行，无需重复执行 configure 或设置环境变量。** 同一系统用户启动的 Trae、Harness 和独立程序共用配置；重启电脑、更换会话或复制安装 skill 均无需重复填写。环境变量为空不影响本地文件读取。只有凭证失效、文件丢失或更换设备/系统用户时，才需要检查并补充对应配置。

本机真实使用的配置位于 `~/.config/wechat-draft-importer/config.json`（保存 AppID 和密钥路径），AppSecret 位于 `~/.config/wechat-draft-importer/appsecret.txt`。`~` 表示当前系统用户的主目录。这两个文件均在当前项目目录之外，不随 Git 提交，无需在本项目的 `.gitignore` 中添加外部路径。换设备后需检查目标设备的配置，不要假定凭证随仓库迁移。

自定义配置示例（配置内只放密钥路径，不放密钥）：

```json
{
  "appid": "wxYOURAPPIDHERE123",
  "secret_file": "/absolute/private/path/appsecret.txt",
  "network": "direct",
  "state_dir": "/absolute/private/path/wechat-import-state"
}
```

调用时：`./wechat-draft --config "/path/to/config.json" doctor`。全局参数必须放在子命令前。默认独立直连微信，不改变系统代理；确需系统代理时显式 `--network system`。密钥只发给微信官方 API，不打印 token、HTTP 原始异常或凭证内容。

## 日常使用

先让 Trae 整理 [文章交接包](references/article-format.md)，然后：

```bash
./wechat-draft prepare "/path/to/article-folder"
./wechat-draft doctor
./wechat-draft import "/path/to/article-folder"
```

`prepare` 完全本地运行，不需密钥，输出文章目录中的 `.wechat-import/preview.html` 和压缩图片。`import` 会上传素材、新建草稿、回读核验，成功后你去公众号后台完成原创、赞赏、合集和发布。程序没有发布、群发、删除或白名单修改接口。

也可以双击 **Start.command**，按终端菜单完成检测、预览或导入。不是常驻服务，执行结束即可关闭；批量自动处理可由其他 Agent 或 shell 调用，不要求 Codex 开启。

生成示例（只在本地创建，无微信写入）：

```bash
./wechat-draft init "/path/to/new-example-folder"
```

## 测试素材

`example-article/` 是仓库自带的测试素材，不是可直接发布的文章：正文是占位文字，`images/` 里是纯色占位图，只用于验证交接格式、图片处理和预览链路。

```bash
./wechat-draft prepare example-article
open example-article/.wechat-import/preview.html
```

`prepare` 完全本地运行，会按 `article.json` 校验标题、导语、字数与图片路径，生成压缩图和预览，不访问微信。需要验证完整链路时可执行 `./wechat-draft import example-article`，它会真实写入草稿箱，测试后请自行删除草稿。

## 重复导入与恢复

- 同一账号和 article\_id 的结果保存在 `~/.local/share/wechat-draft-importer/<appid>/<article_id>.json`，与 Codex/Trae 目录无关；搬动文章文件夹不改变身份。多台电脑不共享状态，不保证跨设备去重。
- 相同内容重跑只核验，不重新创建；修改内容后必须明确 `import "/article" --update`。更新前检查后台是否有人工编辑或设置变化，发现变化停止。
- 更新范围是工具管理的单篇图文。在后台做原创/赞赏/合集等操作后，建议不要再通过 API 更新；这些设置不属于工具保证保留的范围。
- 超时后的写入结果可能不确定，状态会保留 pending，禁止盲目重复。草稿新增/修改用 `reconcile "/article"` 只读扫描并接管唯一匹配稿；扫描上限 1000 条。
- 未找到不代表没创建，不会自动清空状态重建。素材上传超时或状态文件丢失需要人工核查，不能承诺服务器端 exactly-once。不要删除状态来“解决”错误。
- `status "/article"` 查看本地状态；`verify "/article"` 回读已导入稿。正文图片校验兼容微信 URL 尺寸转换和 data-src，核对数量与顺序。排版仍需手机最终检查。

## 动态 IP

若 doctor/import 返回退出码 4，JSON 会给出微信实际识别的 `observed_ip` 和 `settings_url`。你打开页面修改白名单、完成管理员扫码后，重跑即可。程序不自动扩大访问权限，不使用公共 IP 网站猜测微信出口。

白名单已包含出口时不需要每天修改。换宽带、热点或代理可能改变出口；这个平台限制无法靠 skill 消除。

## 交给其他 Agent

可以直接让任何能读文件和运行命令的 Agent 阅读本目录 SKILL.md，并调用 wechat-draft；即使该 Agent 不支持技能发现也能执行。

需要自动发现时，手动选择目标安装：

```bash
./wechat-draft install-skill --target trae
./wechat-draft install-skill --target harness
# 或安装到指定项目（任选一个，不必全装）
./wechat-draft install-skill --target trae --project "/path/to/Articles"
./wechat-draft install-skill --target shared --project "/path/to/Articles"
```

复制位置分别是 `~/.trae-cn/skills/wechat-draft-importer`、`~/.dsh/skills/wechat-draft-importer`；指定项目时分别为 `.trae/skills`、`.dsh/skills` 或共享 `.agents/skills`。整个包均会复制，虚拟环境和凭证不会复制；目标目录需独立运行 setup.sh。不覆盖已有技能，不修改 Agent 配置。Trae 项目需可信；共享 .agents 支持可能需在 Trae 设置中开启。DSH 的加载还取决于当前 preset 是否启用了文件系统 skills provider。

Trae 可说“用 wechat-draft-importer 导入这个文件夹”；Harness 支持 `/wechat-draft-importer`。新安装后若菜单未刷新，重新打开会话/连接。交付前未自动安装到这些应用、未发送测试消息。

## 退出码 / Agent 处理

| 退出码 | 意义                 | 下一步                       |
| --- | ------------------ | ------------------------- |
| 0   | 本命令成功；doctor 仅验证读取 | 检查 JSON status，不混淆只读与已导入  |
| 2   | 输入、依赖或格式错误         | 修正文稿/图片，或运行 setup.sh      |
| 3   | 凭证缺失或权限不正确         | 本人终端配置，不在聊天粘贴密钥           |
| 4   | IP 白名单不符           | 按 observed\_ip 手动更新并扫码    |
| 5   | 网络/HTTP/响应异常       | 查看 pending，禁止盲目重传         |
| 6   | 微信业务拒绝             | 按 wechat\_code 核对权限/配额/密钥 |
| 7   | 同篇正在被其他进程处理        | 等该进程完成                    |
| 8   | 更新冲突、后台有改动或文件已存在   | 人工判断，禁止隐式覆盖               |
| 9   | 上次写入结果不确定          | reconcile 或人工核查           |
| 10  | 草稿存在但回读核验失败        | 查看 checks，不声称成功           |

验证：`.venv/bin/python -m unittest discover -s tests -v`。

[技术调研与官方来源](references/feasibility.md)
