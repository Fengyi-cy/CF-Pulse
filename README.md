# CF-Pulse - 专为 CF 节点打造的极速测速、出口优选与网络体检工具

> **macOS & Android 双端原生专属支持 · Mac 原生自包含 App + 安卓 Termux 移动端深度调优 · 零磁盘残留 · 纯内存流转**

**告别看视频卡顿与网站报错（如 Error 1000）！**  
如果你在使用基于 Cloudflare (CF) 的代理节点（如 VLESS-Worker、Pages、EdgeTunnel 等），遇到过“测速慢 / 延迟高”、“部分网站打不开报错”、“IP 经常跳人机验证”等问题，**CF-Pulse** 就是专为你量身打造的一站式提速、防报错与网络体检全能工具。

无论是 Mac 电脑还是安卓手机，均采用独立原生路线，无需折腾繁琐环境，开箱即用。

---

## 🎯 核心功能：它到底能为你做什么？

1. ⚡ **测出最快入口（极速提速）**：多线程并发探测真实的 TCP 延迟、丢包率与 HTTP 下载带宽，测出在您当前网络环境下速度最快、延迟最低的 CDN 边缘节点，告别看视频缓冲转圈。
2. 🛡️ **挑选优质出口（告别报错）**：通过并发 TLS 探针秒级挑选高可用 ProxyIP 反代出口，彻底避免访问 Cloudflare 托管网站时触发的 `Error 1000: DNS points to prohibited IP` 死循环报错。
3. 🔍 **给节点做全面体检（排查故障）**：一键捕获节点真实双出站路径（非 CF 出口 vs CF 出口），深度评估 IP 纯净度、欺诈分与 Google、ChatGPT 等关键服务解锁能力。

---

## 📖 核心原理：让复杂的网络概念通俗易懂

很多朋友好奇：为什么用了 CF 节点还需要这个工具？下面这张拓扑图直观展示了你的网络请求是如何流转的：

```text
[您的手机/电脑]
      │
      │ (1) 入口链路：CDN 边缘优选 决定您到节点的延迟与带宽 (握手耗时/丢包率)
      ▼
[Cloudflare Anycast 边缘机房 (如 SJC/LAX/HKG)]
      │
      │ (2) 出口分流：双通道隔离架构
      ├─── 访问非 CF 网站 (Google / YouTube / GitHub) ──► 【Worker 原生出口 IP】
      │
      └─── 访问 CF 保护网站 (Discord / Notion / CF CDN) ─► 【ProxyIP 反代出口 IP】
                                                           (避免 Error 1000 回环)
```

### 1. ⚡ CDN 边缘节点优选（决定“入口连接速度”）
- **通俗解释**：Cloudflare 在全球有成百上千个 Anycast 边缘服务器。由于各省电信、联通、移动的骨干网路由不同，同一个节点在不同网络下的延迟和丢包差距极大。
- **核心作用**：自动从数万个 Cloudflare IP 网段中抽取候选节点，多线程并发探测真实的 **TCP 延迟、丢包率与 HTTP 下载带宽**，测出在您当前网络环境下速度最快、延迟最低的入口 IP。

### 2. 🛡️ ProxyIP 智能优选（决定“出口访问稳定性”）
- **通俗解释**：Cloudflare 为了防止网络死循环，禁止 Worker 节点直接回源访问托管在 Cloudflare 上的网站，否则会触发著名的 **`Error 1000: DNS points to prohibited IP`** 错误。因此，访问这类网站必须借道一个中继代理（即 ProxyIP 出口）。
- **核心作用**：通过 Python 原生并发 TLS 探针，秒级探测候选反代 IP 的连通性与握手延迟，并向官方 Trace 端点反解真实的**落地机房（Colo）与国家归属（Loc）**，挑选出延迟最低且未被墙的优质反代出口。

### 3. 🔍 节点双出站与 IP 质量深度体检（决定“节点健康与解锁能力”）
- **通俗解释**：一个配置良好的 CF 节点，访问不同网站走的是两条完全不同的出口路线。如果在单个页面不能同时测出两个出口，就无法知道节点分流是否正常。
- **核心作用**：
  - **双通道并发捕获**：单次测试即可同时呈现【Worker 原生出口 IP】与【ProxyIP 出站 IP】；
  - **分流拓扑诊断**：自动校验两端出口是否物理隔离，若相同则发出回环预警；
  - **IP 纯净度与欺诈评分**：基于风控模型评估出口 IP 的 0-100 欺诈值，辨别是机房数据中心（Hosting）还是原生住宅家宽（Residential），标注代理/爬虫风险标签；
  - **关键服务解锁矩阵**：并发探测 Google、ChatGPT / OpenAI、Google Gemini、YouTube、GitHub 及 Cloudflare 边缘的访问延迟与连通状态。

---

## 🛠️ 双端原生安装指南 (macOS & Android)

本项目为 **Mac 与 Android 双端原生定制**，采用物理隔离的双轨架构，您可以根据所使用的设备选择对应的部署方式：

---

### 🖥️ 路线 A：macOS 原生桌面部署

专为 Mac 系统优化，采用自包含 Application Bundle 架构，零外部依赖，与安卓路线完全物理隔离。

#### 1. 克隆代码与权限配置
打开 Mac 终端（Terminal），依次执行：
```bash
# 1. 克隆项目仓库到本地
git clone https://github.com/Fengyi-cy/CF-Pulse.git
cd CF-Pulse

# 2. 为可执行启动脚本与测速核心赋予权限
chmod +x "CF优选测速.app/Contents/MacOS/CF优选测速"
chmod +x "CF优选测速.app/Contents/Resources/CloudflareSpeedTest/CloudflareSpeedTest"
chmod +x "CF优选测速.app/Contents/Resources/CloudflareSpeedTest/cfst"

# 3. 解除 macOS Gatekeeper 安全隔离属性 (避免系统提示“文件已损坏”或“未受信任的开发者”)
xattr -cr "CF优选测速.app"
```

#### 2. 启动与使用
- **方式一（推荐，双击即用）**：
  直接在访达（Finder）中双击 **`CF优选测速.app`**（亦可拖入 `/Applications` 应用程序文件夹）。应用将在后台自动静默拉起服务，并自动为您唤起默认浏览器打开控制台：`http://127.0.0.1:8989`。
- **方式二（命令行启动）**：
  ```bash
  python3 CF优选测速.app/Contents/Resources/launcher/server.py
  # 随后在浏览器访问 http://127.0.0.1:8989
  ```

---

### 📱 路线 B：Android 移动端原生部署 (Termux 深度适配)

在移动端直接测速至关重要——手机连着蜂窝网络（5G/4G）或出门在外的 Wi-Fi，其网络路由与家中的宽带电脑截然不同。在手机本地直接测出的节点才是真正最匹配当前手机信号的。

本项目已在 **Redmi K80（高通骁龙 8 Gen 3，HyperOS 2 / Android 16）** 及主流安卓设备上完成真机深层适配与调优。

#### 1. 前置准备
在手机上安装 **Termux**（推荐使用来自 [GitHub Releases](https://github.com/termux/termux-app/releases) 或 F-Droid 的官方稳定版本）。

#### 2. 一键极速部署（Termux 终端）
打开 Termux，依次粘贴执行以下两行命令：
```bash
# 1. 更新环境并安装 git
pkg update -y && pkg install git -y

# 2. 克隆仓库并一键自动安装配置
git clone https://github.com/Fengyi-cy/CF-Pulse.git
cd CF-Pulse && bash install_android.sh
```

> **自动化安装亮点**：
> - 自动安装配置 Python 3 运行环境与 Linux ARM64 原生测速核心；
> - 自动向 Termux 注入 CA 根证书网络库；
> - 自动开通文件管理读写权限，并在手机根目录下创建专属可见文件夹 **`/sdcard/优选IP/`**；
> - 自动注册全局快捷命令 `cfst`，并预生成桌面小部件脚本；
> - 部署完成后**自动唤起手机默认浏览器**打开控制台！

#### 3. 手机端日常启动的三种方式
- **方式 1：手机桌面 PWA 独立应用（全屏无地址栏，原生体验 🌟）**
  - 在手机浏览器打开控制台后，点击浏览器菜单（`⋮` 或 `≡`）-> 选择 **【添加到主屏幕 / 安装应用】**；
  - 手机桌面即可生成独立的 **【CF优选测速】** 原生图标，点开即为无浏览器顶栏底栏的纯净独立 App 界面！
- **方式 2：Termux:Widget 桌面微件（点一下后台静默拉起 + 自动弹浏览器）**
  - 手机安装配套插件 `Termux:Widget`；
  - 桌面长按空白处 -> 点击【添加微件 / 小部件】 -> 找到 **Termux** -> 拖出微件并选择 **`CF优选测速`**；
  - 点一下桌面图标，后台全自动静默拉起服务并唤起浏览器，全程无需接触黑底命令行！
- **方式 3：Termux 命令行一键自愈**
  - 在 Termux 中直接输入 `cfst`，自动检测后台状态、自动后台唤醒、自动将访问地址写入手机系统剪贴板并弹出浏览器。

---

## 🗑️ 如何彻底卸载与清理

本项目遵循**纯净无残留**原则，不向系统深层目录写入隐蔽文件，随时可彻底移除：

### 🖥️ macOS 端卸载
1. 如服务正在运行，终端执行一条命令退出后台：
   ```bash
   pkill -f "launcher/server.py" 2>/dev/null || true
   ```
2. 直接将 **`CF优选测速.app`** 与克隆的 **`CF-Pulse`** 项目目录移入废纸篓清空即可，不留任何系统垃圾。

### 📱 Android 端卸载
打开 Termux，粘贴执行以下命令即可一键彻底清理所有程序组件、全局快捷命令与微件脚本：
```bash
# 1. 停止后台运行的探针服务
pkill -f "server.py" 2>/dev/null || true

# 2. 清除程序核心目录与全局 cfst 命令
rm -rf ~/cfst-pro "$PREFIX/bin/cfst" ~/.shortcuts/tasks/CF优选测速 ~/.shortcuts/CF优选测速

# 3. （可选）删除保存在手机存储中的测速导出记录
rm -rf /sdcard/优选IP/
```
若手机桌面上添加了 PWA 网页应用图标或桌面微件，长按图标选择「移除」或「卸载」即可。

---

## 🔬 底层适配机制 (供研究与二次开发参考)

> 本项目已在底层全自动化处理了双端环境兼容性，日常使用开箱即用。以下技术点仅供二次开发或网络拓扑研究者参考：

- **CA 根证书自动注入**：针对 Android Termux 环境下 Go 静态二进制无法读取系统 Keystore 的特性，启动时自动注入 `$PREFIX/etc/tls/cert.pem`，保障 TLS 握手与机房反解 100% 成功；
- **移动端探针网络容差**：探针超时自适应调优至 3.5s，并优化了高可用 Anycast IP 池，有效消除蜂窝移动网络的偶发抖动与丢包误判；
- **后台保活与墓碑兼容**：Android 端采用轻量无状态设计，建议将 Termux 省电策略设为「无限制」，配合系统白名单实现秒级唤醒；
- **安全存储架构分层**：遵循 Android `noexec` 存储隔离规范，执行引擎安全保存在 Termux 私有区，测速结果自动导出至可见公共存储。

---

## 📁 项目完整目录结构

```text
CF-Pulse/
├── CF优选测速.app/                          # 🖥️ macOS 原生应用程序包 (Darwin 路线)
│   └── Contents/
│       ├── Info.plist                     # macOS App 元数据声明
│       ├── MacOS/CF优选测速                # 可执行启动脚本（守护进程管理与浏览器联动）
│       └── Resources/
│           ├── CloudflareSpeedTest/       # macOS 原生测速核心 (XIU2) 与默认网段
│           │   ├── cfst                   # macOS 编译二进制
│           │   ├── ip.txt                 # IPv4 官方候选网段
│           │   └── ipv6.txt               # IPv6 官方候选网段
│           └── launcher/                  # 一体化轻量后端与响应式前端
│               ├── server.py              # Python 探针服务器 (0.0.0.0:8989)
│               └── index.html             # 三合一控制台 Web 交互界面
│
├── android/                               # 📱 Android 原生移植套件 (Linux ARM64 路线)
│   ├── cfst                               # Linux ARM64 静态链接测速引擎 (XIU2)
│   ├── server.py                          # 适配移动端环境的轻量后端探针
│   ├── index.html                         # 适配移动端视口与 PWA 规范的控制台前端
│   ├── start.sh                           # 智能启动器（剪贴板同步 + 浏览器唤起）
│   ├── install_android.sh                 # 手机端一键极速配置与全局指令注册脚本
│   ├── ip.txt                             # 移动端专用 IPv4 候选池
│   └── ipv6.txt                           # 移动端专用 IPv6 候选池
│
├── install_android.sh                     # 根目录快速部署入口
└── README.md                              # 权威架构交付与使用文档
```

---

## 🤝 致敬与鸣谢开源项目 (Credits & Acknowledgements)

本项目深度融合与借鉴了开源社区多位开发者的优秀成果，特此致谢：

1. **[XIU2/CloudflareSpeedTest](https://github.com/XIU2/CloudflareSpeedTest)**
   - **核心贡献**：提供了业界公认最高性能的 Cloudflare CDN 优选核心引擎与 Anycast 多线程测速算法。
   - **本项目应用**：内置其编译好的 macOS 及 Linux ARM64 静态核心，并深度封装为 Web 控制台驱动。
2. **[xgonce/Cloudflare_IP](https://github.com/xgonce/Cloudflare_IP)**
   - **核心贡献**：提供了持续维护的高质量活跃 Cloudflare 反代 ProxyIP 社区数据库。
   - **本项目应用**：作为 ProxyIP 智能优选模块的云端在线同步数据源。
3. **[Termux 项目组](https://github.com/termux/termux-app) 与 [Termux:Widget](https://github.com/termux/termux-widget)**
   - **核心贡献**：为 Android 平台带来了完整的 Linux 运行时环境与强大的桌面小部件交互能力，使移动端免 Root 独立运行成为现实。

---

## 🔒 开源协议与说明
本项目仅供个人网络质量诊断、链路优选与网络拓扑研究使用。开源代码采用 MIT 协议发布，欢迎提交 Issue 与 Pull Request 共同完善。
