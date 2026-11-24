# 技术调研与实施结论

结论：可以做成独立 Python 程序，再用同一份 Agent Skills 指令供 Trae 和 DeepSeek Harness 调用；不需要 Codex、OpenAI SDK、浏览器或常驻服务器。运行需要 Python 3.9+、markdown-it-py 和 Pillow。

## 证据与技术阻塞点

| 问题 | 核实结果与处理 |
|---|---|
| 账号能否通过官方 API 写草稿 | 已实测 stable_token、正文图、永久封面、draft/add、draft/get 全部通过，后台预览正常。历史实测不是对当前凭证及 IP 仍有效的保证。 |
| 本机是否被“服务器端调用”限制 | 这里指密钥在可信程序中、通过 HTTPS 调用，而非浏览器前端。此前 Mac 本机调用成功。 |
| 动态 IP、代理分流 | 无法保证家庭宽带公网出口不变。默认仅微信 API 直连，不修改系统代理；可显式选择系统代理。以微信 40164 中的 IP 为准，显示白名单页面；不自动修改安全设置。 |
| AppSecret 与 Agent 环境隔离 | 不依赖终端继承 .zshrc。支持环境变量、权限 600 的本地密钥文件、既有 ~/.config/wechat-workflow/env 的字面量读取；不执行该文件、不回显凭证。首次配置可在独立终端隐藏输入。相同系统用户下其他程序仍可读取其文件，不声称加密隔离。 |
| 图片格式与大小 | 官方正文上传接口只支持 JPG/PNG，必须小于 1 MB；生图可能输出 WebP 或数 MB PNG。用 Pillow 统一转 JPEG、压缩缩放，原图不改动，缓存转换结果。image 类型永久素材当前文档上限 10M；本工具封面也压至 1 MB 内。 |
| HTML 与排版 | Markdown 经 markdown-it-py 转换，再使用受限标签和行内样式；禁用原始 HTML，拒绝外链图片，图片替换为微信上传 URL。支持普通段落、标题、强调、列表、引用、分隔线、代码和本地插图；表格等超出基础语法范围的写法应在预览中调整。微信仍可能改写样式，手机最终验收不能取消。 |
| 正文字数与字段限制 | 官方标题 ≤32 字、作者 ≤16 字、摘要 ≤120 字；HTML 少于 20000 字符且小于 1 MB。运行时检查，并默认正文可见字符 ≤3000；不自动截断文章。 |
| 正文图片回读变化 | 真实实测 src 会变为 data-src，HTTP 会变 HTTPS，/0 会变 /640。按微信域名、资源路径和图片顺序核验，允许这些转换，不能只比较完整 URL。 |
| 封面裁切 | 提供 2.35:1、1:1 居中裁切坐标，图像本身不强制裁掉。人物偏置等美术判断仍需预览检查。 |
| 重复执行与中断 | 每篇有稳定 article_id，按账号+article_id 保存状态，记录上传缓存和草稿 media_id，文件锁防并发。已成功的不重传；输入变化时拒绝隐式覆盖，明确 --update 才修改已知草稿。状态丢失时不能声称绝对去重。 |
| HTTP 超时与不确定写入 | 微信新增草稿没有本工具可用的幂等键。写入前记录 pending；超时/异常保留 pending，重跑停止。可 read-only reconcile 扫描草稿，以字段和资源回读匹配唯一候选后接管。未找到不等于没创建，不能自动清除状态重建。素材上传超时可能留下无法识别的孤立素材；stop 并人工核查，不承诺 exactly-once。 |
| 人在后台修改同一草稿 | 更新前回读并和上次成功结果比较；发现人工改动停止，避免覆盖你设置和编辑。已发表/删除草稿不自动重建。 |
| 作者、留言和摘要 | 官方草稿接口支持 author、need_open_comment、only_fans_can_comment、digest；已加入独立个人偏好文件和留言回读检查，摘要不进入正文。 |
| Trae 技能安装 | 官方明确项目 .trae/skills、用户 ~/.trae-cn/skills；也支持启用 .agents/skills。安装脚本复制整个便携包，不能只复制 SKILL.md，不能带走 .venv 或密钥。 |
| DeepSeek Harness 技能安装 | 核实本机发行版随附文档：项目 .dsh/skills、.agents/skills、用户 ~/.dsh/skills、~/.agents/skills，默认根受当前 preset/provider 配置影响。只发现一层，不应深层嵌套。支持 /skill-name。本文核实格式和路径，未向 DSH 会话发送指令或实际验证其加载本新包。 |
| “无人值守” | 工具运行本身不调用模型。可供任何能读文件、运行命令且获用户许可的 Agent 使用。白名单扫码、凭证变更和最终发布仍由人完成。无 MCP 服务或 DSH 插件依赖。 |

## 官方来源

- 新增草稿：https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_add.html
- 上传正文图片：https://developers.weixin.qq.com/doc/subscription/api/material/permanent/api_uploadimage.html
- 上传永久素材：https://developers.weixin.qq.com/doc/subscription/api/material/permanent/api_addmaterial.html
- 更新草稿：https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_update.html
- stable_token：https://developers.weixin.qq.com/doc/subscription/api/base/api_getstableaccesstoken.html
- Trae Skills：https://docs.trae.cn/ide/skills
- Agent Skills：https://agentskills.io/specification

上述微信页面通过其 .md 官方版本重新获取核对；Trae 页面读取嵌入的正文内容。DSH 证据来自本机官方安装包内的随附文档：

- dsh/node_modules/@deepseek-ai/dsh/docs/subsystems/skills.zh.md
- dsh/node_modules/@deepseek-ai/dsh-skill-filesystem/README.zh.md
- dsh/node_modules/@deepseek-ai/dsh-client-ui-skill/README.zh.md

## 验证范围

交付时由 tests/test_importer.py 覆盖本地与模拟 HTTP 流程。模拟测试不冒充正式图文的实测，也不声称其他 Agent 已实际执行过此技能。
