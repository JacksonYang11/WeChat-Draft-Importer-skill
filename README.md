# WeChat Draft Importer

一个用于把已定稿的 Markdown、导语、封面和插图导入微信公众号草稿箱的skill。核心是一个本地 Python 程序，不调用模型、不依赖浏览器或云服务器，也可以作为 Trae / DeepSeek Harness 的 skill 使用。

## 能做什么

- 本地校验文章交接包，生成压缩图片和 HTML 预览，不访问微信
- 上传正文图片与封面，新建或更新草稿，回读核验后返回 media\_id
- 相同内容重复执行不重复建稿；中断或超时保留状态，可只读核查后恢复
- 不做写作、生图、原创声明、发布、群发、删除和白名单修改

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
- 公众号 AppID / AppSecret；
- 需要在微信公众号后台白名单写入当前访问的设备ip（动态ip变化后需要及时更新）

# 快速开始

```bash
cd "/path/to/wechat-draft-importer"
sh setup.sh                        # 首次运行：创建 .venv 并安装依赖
./wechat-draft configure           # 首次运行：隐藏输入并保存凭证
./wechat-draft doctor              # 检测凭证与网络
./wechat-draft prepare "/path/to/article-folder"
./wechat-draft import "/path/to/article-folder"
```

`prepare` 完全本地运行，在文章目录下输出 `.wechat-import/preview.html` 和压缩图片；`import` 成功后到公众号后台完成原创、赞赏、合集和发布。文章文件夹结构见 [文章交接格式](references/article-format.md)。没有现成文章时可用 `./wechat-draft init "/path/to/new-folder"` 生成示例；不用命令行也可双击 `Start.command` 按菜单操作。

## 文档

- [使用说明](docs/usage.md)：凭证配置、日常命令、状态与恢复、测试素材
- [故障排查](docs/troubleshooting.md)：动态 IP、退出码与常见错误
- [Agent 安装](docs/agent-install.md)：装到 Trae / DeepSeek Harness
- [技术调研与官方来源](references/feasibility.md)

## 测试

```bash
.venv/bin/python -m unittest discover -s tests -v
```
