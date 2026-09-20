#!/bin/sh
# ==============================================================================
# CloudflareSpeedTest Pro - Android (Termux) 智能极速启动脚本
# 功能：后台自启服务、自动复制访问网址到安卓系统剪贴板、自动唤起手机默认浏览器
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT=8989
URL="http://127.0.0.1:$PORT"

# 1. 确保 Termux CA 证书可用 (解决部分 Android 设备上 Go 报证书未知错误的问题)
if [ -n "$PREFIX" ] && [ -f "$PREFIX/etc/tls/cert.pem" ]; then
    export SSL_CERT_FILE="$PREFIX/etc/tls/cert.pem"
fi

# 2. 赋予核心程序与脚本执行权限
chmod +x "$SCRIPT_DIR/cfst" 2>/dev/null
chmod +x "$SCRIPT_DIR/server.py" 2>/dev/null

# 3. 检查服务是否已在运行
IS_RUNNING=0
if command -v lsof >/dev/null 2>&1; then
    if lsof -i :$PORT >/dev/null 2>&1; then
        IS_RUNNING=1
    fi
elif command -v netstat >/dev/null 2>&1; then
    if netstat -tuln 2>/dev/null | grep -q ":$PORT "; then
        IS_RUNNING=1
    fi
fi

if [ $IS_RUNNING -eq 0 ]; then
    echo "[*] 正在启动 Cloudflare 节点优选后台服务..."
    cd "$SCRIPT_DIR" && nohup python3 "$SCRIPT_DIR/server.py" > /dev/null 2>&1 &
    
    # 等待服务就绪（最多 2 秒）
    for i in 1 2 3 4 5 6 7 8 9 10; do
        if curl -s -f -m 1 "$URL/api/status" >/dev/null 2>&1; then
            break
        fi
        sleep 0.2
    done
fi

# 4. 自动将访问网址复制到安卓系统剪贴板
COPIED=0
if command -v termux-clipboard-set >/dev/null 2>&1; then
    termux-clipboard-set "$URL" 2>/dev/null && COPIED=1
fi

# 5. 自动唤起手机浏览器打开控制台
OPENED=0
if command -v termux-open-url >/dev/null 2>&1; then
    termux-open-url "$URL" 2>/dev/null && OPENED=1
elif command -v am >/dev/null 2>&1; then
    am start -a android.intent.action.VIEW -d "$URL" >/dev/null 2>&1 && OPENED=1
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" 2>/dev/null && OPENED=1
fi

# 6. 友好终端控制台反馈
clear 2>/dev/null || true
echo "========================================================"
echo "    🚀 Cloudflare 节点优选控制台 (Android Pro) 就绪    "
echo "========================================================"
echo " [✓] 本地后台服务 : 正常运行中 (端口: $PORT)"
echo " [✓] 手机访问网址 : $URL"
if [ $COPIED -eq 1 ]; then
    echo " [📋] 剪贴板状态   : 网址已自动写入手机系统剪贴板！"
else
    echo " [💡] 温馨提示     : 可直接在任意手机浏览器打开该网址"
fi
if [ $OPENED -eq 1 ]; then
    echo " [🌐] 浏览器联动   : 已自动为您唤起手机默认浏览器！"
fi
echo "========================================================"
echo " 📱 手机桌面快捷方式支持："
echo "  1. 浏览器内点击「添加到主屏幕」即可生成独立无地址栏全屏 APP！"
echo "  2. 桌面长按添加 Termux 微件选择「CF优选测速」，一键后台静默直达！"
echo "========================================================"
echo " 提示：按 Ctrl+C 可退出当前终端，后台测速服务不受影响。"
echo " 再次启动只需在 Termux 中运行: cfst"
echo "========================================================"

