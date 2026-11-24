# 作者、留言与摘要设置

## 个人文件

个人偏好默认放在程序根目录的 `personal-settings.json`，权限 600，和 AppID/AppSecret 文件分开。调用同一程序目录的 Agent 共用；不写入 SKILL.md、代码、测试或公开文章示例。

初次设置可复制仓库中的 `personal-settings.example.json` 到上述位置并填写。已有文件无需再次配置。使用其他账号时请为它指定独立的个人文件：

```bash
./wechat-draft --personal-settings "/private/path/personal-settings.json" prepare "/path/to/article"
./wechat-draft --personal-settings "/private/path/personal-settings.json" import "/path/to/article"
```

默认文件不存在时兼容旧版行为，不要求填写；显式指定的文件不存在、权限过宽或格式不正确则停止。个人文件只保存偏好，不放 AppSecret；prepare 读取偏好但不读取凭证、不访问微信。

| 字段 | 作用 |
| --- | --- |
| `author` | 默认作者，最多 16 字；文章 author 缺失或为空时自动使用。文章明确填写非空作者时优先使用文章值。 |
| `need_open_comment` | 1 开留言、0 关闭；需公众号有留言权限。 |
| `only_fans_can_comment` | 0 所有人可留言、1 仅粉丝；设为 1 时需同时开启留言。 |

文章显式指定的留言字段优先于个人默认值；开关使用 JSON 数字 0/1。未提供留言设置时不主动发送字段，保持旧版兼容。

不要让 Agent 将默认作者复制到每篇 article.json；程序直接读取个人文件。真实作者在实际导入请求及本机状态记录中出现是功能所需，状态和文章资料也不应加入公共技能包。

## 摘要只进入专用字段

摘要取自 `article.json` 的 `digest`，最多 120 字，发送到微信专用摘要字段，不自动插入正文。

如果 Markdown 开头已有与 digest 相同的独立摘要段落，导入前会在内存中去掉，原文件不改。支持普通段落、`导语：`/`摘要：` 标记、引用块、加粗文字，以及开篇插图后紧接的摘要。若开头明确标为导语/摘要但内容与 digest 不同，会停止要求核对，避免误删正文；其他形式应由 Agent 整理交接包时分离，不做全文替换。

本地预览将摘要和封面放在折叠的设置区域，明确标注不属于上传正文。导入结果回读核验摘要、正文、作者及已提交的留言字段；留言缺失或不符不报告全部通过。

## 接口依据

核对官方新增草稿、更新草稿及草稿详情接口：

| 需求 | 公开官方接口与处理 |
| --- | --- |
| 作者 | draft/add、draft/update 的 `author`，草稿详情可回读；个人文件提供默认值。 |
| 留言 | `need_open_comment`、`only_fans_can_comment`，草稿详情可回读；程序透传并核验，账号缺少留言权限时停止，不静默改成关闭。 |
| 专用摘要 | `digest`，与正文 `content` 分开；导入时去掉与 digest 相同的开头摘要段落。 |

## Git 与打包

真实个人文件放在仓库根目录；`.gitignore` 同时忽略仓库中的 personal-settings.json、personal-settings.*.json，公开占位示例例外。Git Notes 不会阻止提交，排除文件应使用 .gitignore；忽略规则也不会撤销已追踪文件。

安装函数使用发布文件白名单，只复制程序、文档及通用示例，不复制真实个人文件、凭证、状态或缓存。新安装副本如需共用原个人文件，须用 --personal-settings 指定其绝对路径。

## 官方来源

- [新增草稿](https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_add.html)
- [更新草稿](https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_update.html)
- [获取草稿详情](https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_getdraft.html)
- [公众号 API 总目录](https://developers.weixin.qq.com/doc/subscription/api/)

文档核对使用上述页面的官方 .md 版本；未调用真实账号写入验证。
