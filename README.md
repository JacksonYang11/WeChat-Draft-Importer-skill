# WeChat Draft Importer

一个用于把已定稿的 Markdown、导语、封面和插图导入微信公众号草稿箱的skill。核心是一个本地 Python 程序，不调用模型、不依赖浏览器或云服务器，也可以作为 Trae / DeepSeek Harness 的 skill 使用。

## 能做什么

- 本地校验文章交接包，生成压缩图片和 HTML 预览，不访问微信
- 上传正文图片与封面，新建或更新草稿，回读核验后返回 media\_id
- 自动读取独立个人文件中的默认作者和留言设置；摘要只进入专用字段，去掉对应的开头摘要段落
- 相同内容重复执行不重复建稿；中断或超时保留状态，可只读核查后恢复
- 不做写作、生图、发布、群发、删除和白名单修改

## 前置条件

- macOS / Linux（Windows 未验证）
- Python 3.9+
- 已定稿的文章资料，按固定文件夹格式准备：

  ```text
  文章文件夹/
    article.json   # 文章ID、标题、导语、正文路径、封面路径
    article.md     # 定稿正文，插图位置直接写在 Markdown 里
    images/        # 封面与插图（PNG / JPEG / WebP）
  ```

  字段限制与写法见 [文章交接格式](references/article-format.md)，也可用 `./wechat-draft init` 生成模板。

公众号侧需完成以下配置，在 [微信开发者平台](https://developers.weixin.qq.com/platform/) 选择对应账号操作：

| 项目 | 要求 |
| --- | --- |
| 账号与管理权限 | 个人主体完成管理员实名；非个人主体启用密钥时可能要求主体认证，以后台提示为准。登录者需为管理员或已绑定的开发者。 |
| AppID / AppSecret | 在“基础信息 → 开发密钥”启用并保存 AppSecret，供本机程序获取调用凭证。 |
| API IP 白名单 | 添加程序调用微信时的实际公网出口 IP；家庭宽带或热点出口变化后需更新，以工具返回的 IP 为准。 |
| 接口权限与额度 | 在“接口管理 → 接口权限与额度”确认可获取调用凭证、上传正文图片和永久素材、新增／更新／获取草稿，且额度充足。 |
| 留言权限（可选） | 通过 API 开启留言时，账号本身须具备留言功能权限。 |

个人公众号也可使用草稿导入，以实际接口权限为准。仅导入草稿无需启用“消息推送／服务器配置”，也无需配置回调 URL、Token、EncodingAESKey 或 JS 安全域名；本机联网即可，不需要云服务器。配置入口见 [官方说明](https://developers.weixin.qq.com/doc/subscription/guide/dev/migration.html)。

## 快速开始

```bash
cd "/path/to/wechat-draft-importer"
sh setup.sh                        # 首次运行：创建 .venv 并安装依赖
./wechat-draft configure           # 首次运行：隐藏输入并保存凭证
./wechat-draft doctor              # 检测凭证与网络
./wechat-draft prepare "/path/to/article-folder"
./wechat-draft import "/path/to/article-folder"
```

`prepare` 完全本地运行，在文章目录下输出 `.wechat-import/preview.html` 和压缩图片；`import` 成功后到公众号后台检查排版、封面并自行发布。文章文件夹结构见 [文章交接格式](references/article-format.md)。没有现成文章时可用 `./wechat-draft init "/path/to/new-folder"` 生成示例；不用命令行也可双击 `Start.command` 按菜单操作。

## 文档

- [使用说明](docs/usage.md)：凭证配置、日常命令、状态与恢复、测试素材
- [故障排查](docs/troubleshooting.md)：动态 IP、退出码与常见错误
- [Agent 安装](docs/agent-install.md)：装到 Trae / DeepSeek Harness
- [文章设置与接口边界](docs/article-settings.md)：个人偏好、作者、留言和摘要
- [技术调研与官方来源](references/feasibility.md)

## 测试

```bash
.venv/bin/python -m unittest discover -s tests -v
```
