# Trae → 导入工具的交接格式

每篇文章一个独立文件夹：

```text
my-history-article/
  article.json
  article.md
  images/
    cover.png
    opening.png
    illustration-01.webp
```

article.json（UTF-8 JSON，不是 shell 文件）：

```json
{
  "article_id": "history-20261117-001",
  "title": "你的最终标题",
  "author": "",
  "digest": "已经确认的简洁导语。",
  "content": "article.md",
  "cover": "images/cover.png",
  "max_chars": 3000
}
```

`article_id` 是文章稳定身份，英文/数字/连字符/下划线，最多 96 字符；同一篇后续修改仍用原 ID。另起新 ID 表示另一篇，会产生新草稿。不能为“修复报错”随意修改 ID。`init` 命令会生成 UUID。

`title` ≤32 字、`author` ≤16 字、`digest` ≤120 字。导语作为摘要填写，不自动插入正文；如需正文引言，请在 article.md 明确写好。正文默认限制为 3000 个可见非空白字符（包含标点和英文字母），比口语“中文字数”更保守，超限会停止，不截断。格式化 HTML 另受微信 20000 字符/1 MB 限制。

正文示例：

```markdown
开篇正文。

![开篇场景](images/opening.png)

## 第一个小标题

对应段落内容。

![此段对应的插图](images/illustration-01.webp)

图片之后的段落。
```

插图位置直接写入 Markdown，避免“第几段后”随修改漂移。支持本地绝对路径（含 `~/`）和相对文章文件夹的路径；可以直接引用生图输出目录，不要求搬动原图。路径含空格时用 Markdown 的 `![描述](<images/my image.png>)` 写法。路径不能含查询参数或 #；有这些字符时应 URL 编码。

不要放图片外链、`file://`、Base64、原始 HTML 图片标签或 JS。正文按基础 CommonMark 处理：段落、标题、列表、引用、强调、链接、代码、分隔线、图片；不承诺 Word、HTML 模板和复杂表格的无损导入。正文首行若是与 title 一致的一级标题，会去掉重复标题。

封面与插图可由 Pillow 支持的静态格式读入，包括 PNG/JPEG/WebP；程序生成无 EXIF 的 JPEG，透明区域铺白，长边最多 1920，压至 950000 字节内，原图不变。封面提交 2.35:1 和 1:1 居中裁切坐标，偏置构图请在后台微调。

可直接把以下要求交给 Trae 的写作/生图 Agent：

> 定稿和全部图片验收后，按 wechat-draft-importer/references/article-format.md 创建文章交接文件夹。保留最终正文，把每张已生成的本地插图路径写进对应位置的 Markdown 图片标记；生成 article.json，填写稳定 article_id、标题、导语、作者、正文路径和封面路径。不要执行生图，不要把 API 密钥写进交接包。交接完成后先运行 prepare 检查。
