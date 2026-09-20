#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# CloudflareSpeedTest Pro - Android Termux 一键极速部署脚本
# ==============================================================================

set -e

echo "========================================================"
echo "    🚀 正在为您部署 CloudflareSpeedTest Pro 安卓端...    "
echo "========================================================"

# 1. 更新并安装基础依赖 (Python 与 CA 证书)
echo "[1/4] 正在配置 Android Python 与网络根证书环境..."
pkg update -y
pkg install -y python ca-certificates curl termux-tools termux-api 2>/dev/null || pkg install -y python ca-certificates curl

# 2. 写入证书环境变量避免 Go 握手异常
if [ -n "$PREFIX" ]; then
    grep -q "SSL_CERT_FILE" ~/.profile 2>/dev/null || echo 'export SSL_CERT_FILE=$PREFIX/etc/tls/cert.pem' >> ~/.profile
    export SSL_CERT_FILE="$PREFIX/etc/tls/cert.pem"
fi

# 3. 部署程序目录
TARGET_DIR="$HOME/cfst-pro"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ "$SCRIPT_DIR" != "$TARGET_DIR" ]; then
    echo "[2/4] 正在同步程序文件到 $TARGET_DIR ..."
    mkdir -p "$TARGET_DIR"
    if [ -d "$SCRIPT_DIR/android" ]; then
        cp -rf "$SCRIPT_DIR/android/"* "$TARGET_DIR/"
    else
        cp -rf "$SCRIPT_DIR/"* "$TARGET_DIR/"
    fi
fi

# 4. 赋予执行权限
chmod +x "$TARGET_DIR/cfst" "$TARGET_DIR/server.py" "$TARGET_DIR/start.sh" 2>/dev/null || true

# 5. 创建全局快捷命令 cfst (在 Termux 任意位置输入 cfst 即可启动)
if [ -n "$PREFIX" ] && [ -d "$PREFIX/bin" ]; then
    echo "[3/5] 正在创建全局命令 cfst ..."
    cat << 'EOF' > "$PREFIX/bin/cfst"
#!/bin/sh
exec "$HOME/cfst-pro/start.sh" "$@"
EOF
    chmod +x "$PREFIX/bin/cfst"
fi

# 6. 配置桌面快捷方式 (Termux:Widget 静默后台启动支持)
echo "[4/5] 正在配置桌面一键快捷启动支持..."
mkdir -p "$HOME/.shortcuts/tasks" "$HOME/.shortcuts" 2>/dev/null || true
cat << 'EOF' > "$HOME/.shortcuts/tasks/CF优选测速"
#!/data/data/com.termux/files/usr/bin/bash
$HOME/cfst-pro/start.sh >/dev/null 2>&1
EOF
chmod +x "$HOME/.shortcuts/tasks/CF优选测速" 2>/dev/null || true

cat << 'EOF' > "$HOME/.shortcuts/CF优选测速"
#!/data/data/com.termux/files/usr/bin/bash
exec $HOME/cfst-pro/start.sh
EOF
chmod +x "$HOME/.shortcuts/CF优选测速" 2>/dev/null || true

echo "[5/5] 部署成功！正在为您自动启动服务并唤起浏览器..."
echo ""
exec "$TARGET_DIR/start.sh"

