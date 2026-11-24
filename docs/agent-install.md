# 安装到 Agent

任何能读文件、执行命令的 Agent 都可以直接阅读本目录的 `SKILL.md` 并调用 `wechat-draft`，即使该 Agent 不支持技能发现也能执行。

需要被自动发现时，手动选择目标安装：

```bash
./wechat-draft install-skill --target trae
./wechat-draft install-skill --target harness
# 安装到指定项目（任选一个，不必全装）
./wechat-draft install-skill --target trae --project "/path/to/Articles"
./wechat-draft install-skill --target shared --project "/path/to/Articles"
```

| 目标 | 用户目录 | 项目目录 |
| --- | --- | --- |
| trae | `~/.trae-cn/skills/wechat-draft-importer` | `.trae/skills` |
| harness | `~/.dsh/skills/wechat-draft-importer` | `.dsh/skills` |
| shared | `~/.agents/skills/wechat-draft-importer` | `.agents/skills` |

程序、文档、测试和示例会整体复制；虚拟环境、状态和凭证不会复制，目标目录需单独运行 `setup.sh`。

真实 personal-settings.json 同样不会复制；各副本默认读取自身根目录的 personal-settings.json，共用原文件时使用 --personal-settings 指定绝对路径，无需把个人作者名或凭证写进 Skill。详情见 [文章设置](article-settings.md)。

注意事项：

- 目标目录已存在时不会覆盖，升级前需先手动删除旧目录。
- 不修改 Agent 配置，也不代为安装。Trae 项目需为可信项目；共享 `.agents` 可能需在 Trae 设置中开启。
- DeepSeek Harness 的加载取决于当前 preset 是否启用了文件系统 skills provider。
- 本仓库未在目标 Agent 中实测加载。

使用方式：Trae 可说“用 wechat-draft-importer 导入这个文件夹”；Harness 支持 `/wechat-draft-importer`。新安装后若菜单未刷新，重新打开会话或连接。
