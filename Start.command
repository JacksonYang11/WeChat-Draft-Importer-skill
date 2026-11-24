#!/bin/bash
set -eu
TOOL_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ ! -x "$TOOL_DIR/.venv/bin/python" ]; then
    "$TOOL_DIR/setup.sh"
fi
echo '公众号草稿导入：1 检测连接  2 本地预览  3 导入草稿  4 首次配置  5 创建示例'
read -r -p '请选择 [1-5]：' TASK_CHOICE
TASK_COMMAND=''
case "$TASK_CHOICE" in
    1) TASK_COMMAND=doctor ;;
    2) TASK_COMMAND=prepare ;;
    3) TASK_COMMAND=import ;;
    4) TASK_COMMAND=configure ;;
    5) TASK_COMMAND=init ;;
    *) echo '无效选择'; exit 2 ;;
esac
TASK_STATUS=0
case "$TASK_COMMAND" in
    prepare|import|init)
        read -r -p '输入文章文件夹绝对路径（直接粘贴路径，不加引号）：' TASK_FOLDER
        "$TOOL_DIR/wechat-draft" "$TASK_COMMAND" "$TASK_FOLDER" || TASK_STATUS=$?
        ;;
    *) "$TOOL_DIR/wechat-draft" "$TASK_COMMAND" || TASK_STATUS=$? ;;
esac
echo "退出码：$TASK_STATUS"
read -r -p '按回车关闭窗口。' TASK_CLOSE
exit "$TASK_STATUS"
