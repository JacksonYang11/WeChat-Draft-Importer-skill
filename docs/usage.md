# 使用说明

## 文章交接包

每篇文章一个文件夹，名字固定为 `wechat-draft-package`，包含 `article.json`、正文 Markdown 和 `images/`。字段、字数与图片路径规则见 [文章交接格式](../references/article-format.md)。

```bash
./wechat-draft init "/path/to/article/wechat-draft-package"   # 生成占位示例；目录已存在时不会覆盖
```

## 凭证配置

程序按以下顺序取凭证：环境变量 `WEIXIN_APPID` / `WEIXIN_APPSECRET` → 配置文件（`appid` 与 `secret_file`）→ 既有 `~/.config/wechat-workflow/env` 中的字面量。该 env 文件只按字面量读取，不执行 shell。

首次使用在本人终端执行：

```bash
./wechat-draft configure
```

输入过程隐藏，AppID 与密钥分别写入 `~/.config/wechat-draft-importer/config.json` 和同目录的 `appsecret.txt`，权限 600。已有配置时 `configure` 会拒绝覆盖（退出码 8），需要修改请直接编辑文件或另指定 `--config`。

配置一次后无需重复执行，也不要因为开启新会话、重启电脑、环境变量为空或安装 skill 而重新配置：同一系统用户的 Trae、Harness 和独立命令共用这两份文件。凭证位于项目目录之外，不随 Git 提交，也不随 skill 安装迁移；换设备或换系统用户时需要重新检查。

自定义配置示例（只放密钥路径，不放密钥）：

```json
{
  "appid": "wxYOURAPPIDHERE123",
  "secret_file": "/absolute/private/path/appsecret.txt",
  "network": "direct",
  "state_dir": "/absolute/private/path/wechat-import-state"
}
```

调用时 `./wechat-draft --config "/path/to/config.json" doctor`，全局参数必须放在子命令前。默认直连微信、不修改系统代理；确需系统代理时加 `--network system`。密钥只发送给微信官方 API，程序不打印 token、HTTP 原始异常或凭证内容。

## 日常命令

作者和留言默认值从程序根目录的 `personal-settings.json` 自动读取，个人姓名不写进通用 Skill。已保存的个人文件无需重填；字段及摘要去重规则见 [文章设置](article-settings.md)。自定义文件用 `--personal-settings "/private/path/personal-settings.json"`，放在子命令之前；默认文件不存在时保留旧版行为。prepare 也会读取这份偏好文件，但不读取 AppSecret。

| 命令 | 作用 | 访问微信 |
| --- | --- | --- |
| `prepare <目录>` | 校验字段、压缩图片、生成 `.wechat-import/preview.html` | 否 |
| `doctor` | 只读检测凭证、网络、白名单、草稿与素材读取 | 是 |
| `import <目录>` | 上传素材、新建草稿、回读核验 | 是 |
| `import <目录> --update` | 明确更新该 article_id 的已有草稿 | 是 |
| `status <目录>` | 查看本地状态，不读密钥 | 否 |
| `verify <目录>` | 回读已导入草稿并核对图片 | 是 |
| `reconcile <目录>` | 只读扫描草稿箱，接管唯一匹配稿 | 是 |
| `install-skill --target ...` | 复制技能包，详见 [Agent 安装](agent-install.md) | 否 |

`prepare` 与 `import` 均输出 JSON。`import` 成功后到公众号后台检查排版、封面并自行发布；程序没有发布、群发、删除或白名单修改接口。不用命令行时也可双击 `Start.command` 按菜单选择。

## 重复导入与状态

- 状态保存在 `~/.local/share/wechat-draft-importer/<appid>/<article_id>.json`，与文章目录位置无关；搬动文件夹不改变身份，多台电脑不共享状态。
- 相同内容重跑只核验，不重新创建；修改内容后必须 `import <目录> --update`。更新前会检查后台是否有人工编辑或设置变化，发现变化即停止。
- 修改个人作者/留言默认值或升级渲染版本也可能使内容指纹变化，仍须明确 --update；不得换 article_id 绕过。
- 更新范围是工具管理的单篇图文。在后台手动调整后，不建议再通过 API 更新。
- 超时后结果可能不确定：状态保留 `pending`，禁止盲目重试；可用 `reconcile` 只读核查并接管唯一匹配稿，扫描上限 1000 条。
- 未找到匹配不代表没创建，不会自动清空状态重建。不要删除状态文件来“解决”错误。
- `status` 查本地状态，`verify` 回读核验；图片校验兼容微信 URL 的尺寸转换和 `data-src`，排版仍需手机最终确认。

## 测试素材

`example-article/` 是仓库自带的测试素材，不是可直接发布的文章：正文是占位文字，`images/` 是纯色占位图，用于验证交接格式、图片处理和预览链路。

```bash
./wechat-draft prepare example-article
open example-article/.wechat-import/preview.html
```

`prepare` 完全本地运行，会按 `article.json` 校验标题、导语、字数与图片路径，生成压缩图和预览，不访问微信。需要验证完整链路时可执行 `./wechat-draft import example-article`，它会真实写入草稿箱，测试后请自行删除草稿。
