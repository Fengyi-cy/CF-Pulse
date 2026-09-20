#!/usr/bin/env python3
"""
CF-Pulse 本地 Web 启动器与专业控制面板
多线程原生 Web 服务器，支持 IPv4/IPv6、多端口切换、高低频探测、多格式复制导出
"""

import os
import sys
import json
import time
import signal
import random
import csv
import io
import ssl
import socket
import ipaddress
import subprocess
import threading
import tempfile
import urllib.request
import concurrent.futures
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = 8989
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_cfst_env():
    """动态探测 CloudflareSpeedTest 核心目录与执行路径，支持自包含与外部回退（兼容 macOS 与 Android）"""
    internal_dir = os.path.abspath(os.path.join(BASE_DIR, "..", "CloudflareSpeedTest"))
    candidates = [
        # 1. 当前脚本同级目录（适用于 Android Termux 模式，cfst 与 server.py 同目录）
        BASE_DIR,
        # 2. App 内置独立资源目录（适用于 macOS 模式）
        internal_dir,
        # 3. 外部候选目录
        os.path.join(BASE_DIR, "CloudflareSpeedTest"),
        os.path.expanduser("~/Desktop/CloudflareSpeedTest"),
        os.path.expanduser("~/CloudflareSpeedTest"),
        os.path.expanduser("~"),
    ]

    cfst_dir = None
    cfst_bin = None
    for d in candidates:
        if os.path.isdir(d):
            for bin_name in ["cfst", "CloudflareSpeedTest", "CloudflareST", "CloudflareST_linux_arm64"]:
                bp = os.path.join(d, bin_name)
                if os.path.isfile(bp) and os.access(bp, os.X_OK):
                    cfst_dir = d
                    cfst_bin = bp
                    break
        if cfst_dir and cfst_bin:
            break

    if not cfst_dir:
        cfst_dir = internal_dir
    if not cfst_bin:
        cfst_bin = os.path.join(cfst_dir, "CloudflareSpeedTest")

    # 寻找 ip.txt 与 ipv6.txt
    ip_txt = os.path.join(cfst_dir, "ip.txt")
    if not os.path.exists(ip_txt):
        for d in candidates:
            alt_ip = os.path.join(d, "ip.txt")
            if os.path.exists(alt_ip):
                ip_txt = alt_ip
                break

    ipv6_txt = os.path.join(cfst_dir, "ipv6.txt")
    if not os.path.exists(ipv6_txt):
        for d in candidates:
            alt_ipv6 = os.path.join(d, "ipv6.txt")
            if os.path.exists(alt_ipv6):
                ipv6_txt = alt_ipv6
                break

    return cfst_dir, cfst_bin, ip_txt, ipv6_txt

CFST_DIR, CFST_BIN, IP_TXT, IPV6_TXT = get_cfst_env()

TEMP_DIR = tempfile.gettempdir()
SAMPLED_IP_TXT = os.path.join(TEMP_DIR, "cfst_temp_sampled_ip.txt")
RESULT_CSV = os.path.join(TEMP_DIR, "cfst_temp_result.csv")

class TaskManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.process = None
        self.is_running = False
        self.logs = []
        self.results = []
        self.start_time = 0
        self.end_time = 0
        self.current_port = 443

    def add_log(self, text):
        with self.lock:
            self.logs.append(text)
            if len(self.logs) > 600:
                self.logs.pop(0)

    def get_status(self):
        with self.lock:
            return {
                "is_running": self.is_running,
                "start_time": self.start_time,
                "end_time": self.end_time,
                "log_count": len(self.logs),
                "result_count": len(self.results),
                "results": self.results,
                "port": self.current_port
            }

    def stop(self):
        with self.lock:
            if self.process and self.is_running:
                try:
                    self.process.terminate()
                    time.sleep(0.3)
                    if self.process.poll() is None:
                        self.process.kill()
                except Exception:
                    pass
                self.is_running = False
                self.end_time = time.time()
                self.add_log("\n[系统提示] 测速任务已被手动停止。")

    def run_test(self, params):
        with self.lock:
            if self.is_running:
                return False, "已有测速任务正在运行中"
            self.is_running = True
            self.logs = []
            self.results = []
            self.start_time = time.time()
            self.end_time = 0
            self.current_port = int(params.get("port", 443))

        thread = threading.Thread(target=self._worker, args=(params,))
        thread.daemon = True
        thread.start()
        return True, "测速任务已启动"

    def _worker(self, params):
        cfst_dir, cfst_bin, ip_txt, ipv6_txt = get_cfst_env()
        try:
            if not os.path.isfile(cfst_bin):
                self.add_log(f"\n[错误] 未找到测速核心程序: {cfst_bin}，请检查 CloudflareSpeedTest 是否已编译。")
                return

            ip_version = params.get("ip_version", "ipv4")
            sample_count = int(params.get("sample_count", 150))
            use_custom_file = False
            
            # 1. 抽样处理
            if sample_count > 0:
                proto_name = "IPv6" if ip_version == "ipv6" else "IPv4"
                self.add_log(f"[*] 协议栈: {proto_name} | 正在随机抽取 {sample_count} 个候选 IP 节点...")
                sampled_ips = self._sample_ips(sample_count, ip_version, ip_txt=ip_txt, ipv6_txt=ipv6_txt)
                with open(SAMPLED_IP_TXT, "w", encoding="utf-8") as f:
                    f.write("\n".join(sampled_ips))
                use_custom_file = True
                self.add_log(f"[✓] 抽取就绪，本轮将精准探测这 {len(sampled_ips)} 个节点。")
            else:
                self.add_log("[*] 模式：全量扫描模式 (将遍历全量网段库，耗时较长)...")

            # 2. 组装命令参数
            cmd = [cfst_bin]
            
            # 指定 IP 文件
            if use_custom_file:
                cmd.extend(["-f", SAMPLED_IP_TXT])
            else:
                if ip_version == "ipv6":
                    cmd.extend(["-f", ipv6_txt])
                else:
                    cmd.extend(["-f", ip_txt])

            # 临时输出结果文件 (读后即焚)
            cmd.extend(["-o", RESULT_CSV])

            # 端口
            port = int(params.get("port", 443))
            cmd.extend(["-tp", str(port)])
            self.add_log(f"[*] 测速端口: {port}")

            # 并发线程数
            threads = int(params.get("threads", 200))
            cmd.extend(["-n", str(threads)])

            # 单 IP Ping 探测次数
            ping_count = int(params.get("ping_count", 4))
            cmd.extend(["-t", str(ping_count)])

            # 地区匹配
            region = params.get("region", "SJC,LAX,SFO,SEA").strip()
            if region and region.upper() != "ALL":
                cmd.append("-httping")
                cmd.extend(["-cfcolo", region])
                self.add_log(f"[*] 机房过滤: HTTPing 匹配 [{region}]")
            else:
                if params.get("httping", False):
                    cmd.append("-httping")

            # 测速模式
            mode = params.get("mode", "latency_only")
            if mode == "latency_only":
                cmd.append("-dd")
                self.add_log("[*] 优选模式: 仅测延迟与丢包率 (极速跳过大文件下载)")
            else:
                download_time = int(params.get("download_time", 10))
                cmd.extend(["-dt", str(download_time)])
                
                min_speed = float(params.get("min_speed", 0))
                if min_speed > 0:
                    cmd.extend(["-sl", str(min_speed)])
                
                custom_url = params.get("custom_url", "").strip()
                if custom_url:
                    cmd.extend(["-url", custom_url])
                    self.add_log(f"[*] 自定义测速源: {custom_url}")
                
                self.add_log(f"[*] 优选模式: 全面优选 (测延迟 + 真实带宽下载，限时 {download_time}s)")

            # 输出/挑选节点数量
            limit = int(params.get("limit_count", 10))
            cmd.extend(["-p", str(limit)])
            if mode != "latency_only":
                cmd.extend(["-dn", str(limit)])

            # 延迟上限 (留空或 0 则不限制)
            max_delay = int(params.get("max_delay", 0))
            if max_delay > 0:
                cmd.extend(["-tl", str(max_delay)])
                self.add_log(f"[*] 延迟过滤上限: {max_delay} ms")
            
            max_loss = params.get("max_loss", "")
            if max_loss != "" and float(max_loss) < 1.0:
                cmd.extend(["-tlr", str(max_loss)])

            # 清理旧临时文件
            if os.path.exists(RESULT_CSV):
                try:
                    os.remove(RESULT_CSV)
                except Exception:
                    pass

            self.add_log(f"[*] 执行命令: {' '.join(cmd)}\n")

            # 启动子进程
            env = os.environ.copy()
            ca_candidates = [
                env.get("SSL_CERT_FILE", ""),
                os.path.join(os.environ.get("PREFIX", "/data/data/com.termux/files/usr"), "etc", "tls", "cert.pem"),
                "/data/data/com.termux/files/usr/etc/tls/cert.pem",
                "/etc/ssl/certs/ca-certificates.crt"
            ]
            for ca in ca_candidates:
                if ca and os.path.exists(ca):
                    env["SSL_CERT_FILE"] = ca
                    os.environ["SSL_CERT_FILE"] = ca
                    break

            self.process = subprocess.Popen(
                cmd,
                cwd=cfst_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env
            )

            for line in iter(self.process.stdout.readline, ''):
                cleaned = line.rstrip()
                if cleaned:
                    self.add_log(cleaned)

            self.process.wait()

            # 解析结果并严格截取前 limit 个
            if os.path.exists(RESULT_CSV):
                parsed = self._parse_csv(RESULT_CSV, limit=limit, port=port)
                with self.lock:
                    self.results = parsed
                self.add_log(f"\n[✓] 测速完成！已挑选出排名前 {len(parsed)} 个最佳节点（内存呈现，支持一键多格式复制）。")
                try:
                    os.remove(RESULT_CSV)
                except Exception:
                    pass
            else:
                self.add_log("\n[!] 测速结束，未发现满足全部设定条件的有效 IP（建议将延迟上限留空或放宽地区限制）。")

        except Exception as e:
            self.add_log(f"\n[错误] 运行异常: {str(e)}")
        finally:
            if os.path.exists(RESULT_CSV):
                try:
                    os.remove(RESULT_CSV)
                except Exception:
                    pass
            if os.path.exists(SAMPLED_IP_TXT):
                try:
                    os.remove(SAMPLED_IP_TXT)
                except Exception:
                    pass
            for f in ["result.csv", "sampled_ip.txt"]:
                fp = os.path.join(cfst_dir, f)
                if os.path.exists(fp):
                    try:
                        os.remove(fp)
                    except Exception:
                        pass
            with self.lock:
                self.is_running = False
                self.end_time = time.time()
                self.process = None

    def _sample_ips(self, count, ip_version="ipv4", ip_txt=None, ipv6_txt=None):
        if not ip_txt or not ipv6_txt:
            _, _, default_ip, default_ipv6 = get_cfst_env()
            ip_txt = ip_txt or default_ip
            ipv6_txt = ipv6_txt or default_ipv6

        if ip_version == "ipv6":
            source_file = ipv6_txt if (ipv6_txt and os.path.exists(ipv6_txt)) else None
            cidrs = []
            if source_file:
                with open(source_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            cidrs.append(line)
            if not cidrs:
                return ["2606:4700::"]
            ips = []
            for _ in range(count):
                c = random.choice(cidrs)
                try:
                    net = ipaddress.ip_network(c)
                    rnd = random.randint(1, 65535)
                    ips.append(str(net.network_address + rnd))
                except Exception:
                    ips.append(c.split("/")[0])
            return list(set(ips))[:count]
        else:
            cidrs = []
            if ip_txt and os.path.exists(ip_txt):
                with open(ip_txt, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            cidrs.append(line)
            else:
                cidrs = ["104.16.0.0/12", "172.64.0.0/13", "162.158.0.0/15"]

            all_subnets = []
            for c in cidrs:
                try:
                    net = ipaddress.ip_network(c)
                    if net.prefixlen <= 24:
                        all_subnets.extend(list(net.subnets(new_prefix=24)))
                    else:
                        all_subnets.append(net)
                except Exception:
                    pass

            if not all_subnets:
                return ["104.16.1.1"]

            sample_size = min(count, len(all_subnets))
            sampled_subnets = random.sample(all_subnets, sample_size)
            ips = []
            for s in sampled_subnets:
                host_ip = str(s.network_address + random.randint(1, 254))
                ips.append(host_ip)
            return ips

    def _parse_csv(self, csv_path, limit=0, port=443):
        results = []
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                for row in reader:
                    if len(row) >= 6:
                        ip_val = row[0].strip()
                        results.append({
                            "ip": ip_val,
                            "port": port,
                            "sent": row[1].strip(),
                            "received": row[2].strip(),
                            "loss": row[3].strip(),
                            "delay": row[4].strip(),
                            "speed": row[5].strip(),
                            "colo": row[6].strip() if len(row) > 6 else "N/A"
                        })
                        if limit > 0 and len(results) >= limit:
                            break
        except Exception as e:
            print(f"Error parsing CSV: {e}")
        return results

task_manager = TaskManager()

class ProxyIPTaskManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.is_running = False
        self.stop_requested = False
        self.logs = []
        self.results = []
        self.start_time = 0
        self.end_time = 0
        self.current_port = 443
        self.cached_sources = []
        self._init_builtin_sources()

    def _init_builtin_sources(self):
        # 预载入高质量优质备选池（覆盖各地区优质反代节点）
        self.cached_sources = [
            {"ip": "104.16.1.1", "port": 443, "colo": "LAX", "loc": "US"},
            {"ip": "104.24.94.139", "port": 443, "colo": "SJC", "loc": "US"},
            {"ip": "172.67.182.203", "port": 443, "colo": "LAX", "loc": "US"},
            {"ip": "104.21.60.2", "port": 443, "colo": "SJC", "loc": "US"},
            {"ip": "104.16.178.15", "port": 443, "colo": "LAX", "loc": "US"},
            {"ip": "172.67.75.148", "port": 443, "colo": "SIN", "loc": "SG"},
            {"ip": "104.20.73.11", "port": 443, "colo": "HKG", "loc": "HK"},
            {"ip": "104.26.12.18", "port": 443, "colo": "LHR", "loc": "GB"},
            {"ip": "172.67.195.122", "port": 443, "colo": "SJC", "loc": "US"},
            {"ip": "104.22.18.99", "port": 443, "colo": "LAX", "loc": "US"},
            {"ip": "172.67.158.4", "port": 443, "colo": "HKG", "loc": "HK"},
            {"ip": "188.114.97.7", "port": 443, "colo": "FRA", "loc": "DE"},
            {"ip": "158.51.123.177", "port": 443, "colo": "SEA", "loc": "US"},
            {"ip": "40.233.99.248", "port": 443, "colo": "YYZ", "loc": "CA"},
            {"ip": "172.93.32.237", "port": 443, "colo": "YVR", "loc": "CA"},
            {"ip": "40.233.110.251", "port": 443, "colo": "YYZ", "loc": "CA"},
            {"ip": "68.233.122.42", "port": 443, "colo": "EWR", "loc": "US"},
            {"ip": "70.79.240.221", "port": 443, "colo": "YVR", "loc": "CA"},
            {"ip": "167.160.190.137", "port": 443, "colo": "YYZ", "loc": "CA"},
            {"ip": "140.238.144.211", "port": 443, "colo": "YYZ", "loc": "CA"},
            {"ip": "147.182.156.112", "port": 443, "colo": "YYZ", "loc": "CA"}
        ]

    def add_log(self, text):
        with self.lock:
            self.logs.append(text)
            if len(self.logs) > 600:
                self.logs.pop(0)

    def get_status(self):
        with self.lock:
            return {
                "is_running": self.is_running,
                "start_time": self.start_time,
                "end_time": self.end_time,
                "log_count": len(self.logs),
                "result_count": len(self.results),
                "results": self.results,
                "port": self.current_port
            }

    def stop(self):
        with self.lock:
            if self.is_running:
                self.stop_requested = True
                self.add_log("\n[系统提示] 正在中止 ProxyIP 探测任务...")

    def fetch_sources(self):
        self.add_log("[*] 正在从云端反代数据库同步最新 ProxyIP 池...")
        sources = [
            "https://raw.githubusercontent.com/xgonce/Cloudflare_IP/main/result.csv"
        ]
        new_items = []
        for url in sources:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "CFST/2.0"})
                with urllib.request.urlopen(req, timeout=5) as res:
                    raw = res.read().decode("utf-8", errors="ignore")
                    if len(raw) > 100:
                        reader = csv.reader(io.StringIO(raw))
                        header = next(reader, None)
                        for r in reader:
                            if len(r) >= 3:
                                ip_val = r[0].strip()
                                port_val = int(r[2].strip()) if r[2].strip().isdigit() else 443
                                colo_val = r[5].strip() if len(r) > 5 else "N/A"
                                if ip_val:
                                    new_items.append({"ip": ip_val, "port": port_val, "colo": colo_val, "loc": r[4].strip() if len(r) > 4 else "N/A"})
                        if len(new_items) > 50:
                            break
            except Exception as e:
                self.add_log(f"[提示] 源请求跳过: {e}")
                continue

        with self.lock:
            if new_items:
                seen = set()
                merged = []
                for it in new_items + self.cached_sources:
                    key = f"{it['ip']}:{it.get('port', 443)}"
                    if key not in seen:
                        seen.add(key)
                        merged.append(it)
                self.cached_sources = merged
                cnt = len(self.cached_sources)
                msg = f"[✓] 成功获取并汇总 {cnt} 个可用候选 ProxyIP！"
            else:
                cnt = len(self.cached_sources)
                msg = f"[✓] 云端拉取暂未响应，使用内置高可用 ProxyIP 池 ({cnt} 个)。"

        self.add_log(msg)
        return self.cached_sources

    def run_test(self, params):
        with self.lock:
            if self.is_running:
                return False, "已有 ProxyIP 探测任务正在运行中"
            self.is_running = True
            self.stop_requested = False
            self.logs = []
            self.results = []
            self.start_time = time.time()
            self.end_time = 0
            self.current_port = int(params.get("port", 443))

        t = threading.Thread(target=self._worker, args=(params,))
        t.daemon = True
        t.start()
        return True, "ProxyIP 探测任务已启动"

    def _worker(self, params):
        try:
            target_port = int(params.get("port", 443))
            threads = int(params.get("threads", 35))
            sample_count = int(params.get("sample_count", 30))
            region = params.get("region", "ALL").strip()
            custom_sources = params.get("custom_sources", "").strip()
            limit_count = int(params.get("limit_count", 10))

            candidates = []
            if custom_sources:
                for line in custom_sources.splitlines():
                    item = line.strip()
                    if not item:
                        continue
                    if ":" in item:
                        parts = item.split(":")
                        candidates.append({"ip": parts[0].strip(), "port": int(parts[1].strip())})
                    else:
                        candidates.append({"ip": item, "port": target_port})
            else:
                if not self.cached_sources:
                    self.fetch_sources()
                port_candidates = [c for c in self.cached_sources if c.get("port", 443) == target_port]
                if not port_candidates:
                    port_candidates = [{"ip": c["ip"], "port": target_port} for c in self.cached_sources]
                random.shuffle(port_candidates)
                candidates = port_candidates[:sample_count]

            self.add_log(f"[*] 抽取目标: {len(candidates)} 个候选节点 | 并发: {threads} | 端口: {target_port} | 目标机房: {region}")
            self.add_log("[*] 开始执行 Cloudflare TLS 探针与握手测速...\n")

            valid_nodes = []
            tested_count = 0

            def probe(cand):
                if self.stop_requested:
                    return None
                ip = cand["ip"]
                port = cand.get("port", target_port)
                try:
                    t0 = time.time()
                    sock = socket.create_connection((ip, port), timeout=3.5)
                    sock.settimeout(3.5)
                    tcp_ms = round((time.time() - t0) * 1000, 1)

                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE

                    t1 = time.time()
                    ssock = ctx.wrap_socket(sock, server_hostname="speed.cloudflare.com")
                    ssock.settimeout(3.5)
                    tls_ms = round((time.time() - t1) * 1000, 1)

                    ssock.sendall(b"GET /cdn-cgi/trace HTTP/1.1\r\nHost: speed.cloudflare.com\r\nUser-Agent: CFST/2.0\r\nConnection: close\r\n\r\n")
                    resp = ssock.recv(2048).decode("utf-8", errors="ignore")
                    ssock.close()

                    colo = cand.get("colo", "N/A")
                    loc = cand.get("loc", "N/A")
                    for line in resp.splitlines():
                        if line.startswith("colo="):
                            colo = line.split("=")[1].strip()
                        elif line.startswith("loc="):
                            loc = line.split("=")[1].strip()

                    if "cloudflare" in resp.lower() or colo != "N/A":
                        return {
                            "ip": ip,
                            "port": port,
                            "colo": colo,
                            "loc": loc,
                            "tcp_delay": tcp_ms,
                            "tls_delay": tls_ms,
                            "total_delay": round(tcp_ms + tls_ms, 1),
                            "valid": True
                        }
                except Exception:
                    pass
                return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
                futures = [executor.submit(probe, c) for c in candidates]
                for fut in concurrent.futures.as_completed(futures):
                    if self.stop_requested:
                        break
                    tested_count += 1
                    res = fut.result()
                    if res:
                        if region != "ALL":
                            target_colos = [c.strip() for c in region.split(",") if c.strip()]
                            if res["colo"] not in target_colos:
                                continue
                        valid_nodes.append(res)
                        self.add_log(f"[✓] 发现有效反代: {res['ip']}:{res['port']} | 机房: {res['colo']} ({res['loc']}) | TCP: {res['tcp_delay']}ms | TLS: {res['tls_delay']}ms | 综合: {res['total_delay']}ms")

            if self.stop_requested:
                self.add_log("\n[系统提示] 探测任务已被手动停止。")
            else:
                valid_nodes.sort(key=lambda x: x["total_delay"])
                final_results = valid_nodes[:limit_count]
                with self.lock:
                    self.results = final_results
                self.add_log(f"\n[✓] 探测完毕！已从 {tested_count} 个候选节点中成功挑选出 {len(final_results)} 个最佳 ProxyIP。")

        except Exception as e:
            self.add_log(f"\n[错误] 运行异常: {str(e)}")
        finally:
            with self.lock:
                self.is_running = False
                self.end_time = time.time()

proxy_task_manager = ProxyIPTaskManager()

def get_ip_intel(ip_str):
    if not ip_str:
        return {"error": "Missing IP"}
    intel = {
        "ip": ip_str,
        "country": "未知",
        "country_code": "",
        "city": "未知",
        "region": "",
        "isp": "未知",
        "asn": "",
        "is_datacenter": False,
        "is_proxy": False,
        "is_vpn": False,
        "is_tor": False,
        "risk_score": 0,
        "risk_level": "极低风险",
        "risk_color": "emerald"
    }
    try:
        res = subprocess.run(["curl", "-s", "-m", "3", f"https://api.ipquery.io/{ip_str}"], capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip().startswith("{"):
            d = json.loads(res.stdout)
            loc = d.get("location", {})
            isp = d.get("isp", {})
            risk = d.get("risk", {})
            if loc.get("country"):
                intel["country"] = loc.get("country", "")
                intel["country_code"] = loc.get("country_code", "")
                intel["city"] = loc.get("city", "")
                intel["region"] = loc.get("state", "")
                intel["isp"] = isp.get("isp", "") or isp.get("org", "")
                intel["asn"] = isp.get("asn", "")
                intel["is_datacenter"] = risk.get("is_datacenter", False)
                intel["is_proxy"] = risk.get("is_proxy", False)
                intel["is_vpn"] = risk.get("is_vpn", False)
                intel["is_tor"] = risk.get("is_tor", False)
                intel["risk_score"] = risk.get("risk_score", 0)
    except Exception:
        pass

    if not intel["country"] or intel["country"] == "未知":
        try:
            res = subprocess.run(["curl", "-s", "-m", "3", f"http://ip-api.com/json/{ip_str}?fields=status,country,countryCode,regionName,city,isp,as,mobile,proxy,hosting"], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip().startswith("{"):
                d = json.loads(res.stdout)
                if d.get("status") == "success":
                    intel["country"] = d.get("country", "")
                    intel["country_code"] = d.get("countryCode", "")
                    intel["city"] = d.get("city", "")
                    intel["region"] = d.get("regionName", "")
                    intel["isp"] = d.get("isp", "")
                    intel["asn"] = d.get("as", "")
                    intel["is_datacenter"] = d.get("hosting", False)
                    intel["is_proxy"] = d.get("proxy", False)
                    if d.get("proxy"):
                        intel["risk_score"] = max(intel["risk_score"], 45)
                    if d.get("hosting"):
                        intel["risk_score"] = max(intel["risk_score"], 15)
        except Exception:
            pass

    score = intel["risk_score"]
    if score <= 15:
        intel["risk_level"] = "极低风险 (极度纯净)"
        intel["risk_color"] = "emerald"
    elif score <= 40:
        intel["risk_level"] = "低风险 (正常使用)"
        intel["risk_color"] = "teal"
    elif score <= 70:
        intel["risk_level"] = "中度风险 (机房/代理)"
        intel["risk_color"] = "amber"
    else:
        intel["risk_level"] = "高风险 (黑名单/爬虫)"
        intel["risk_color"] = "rose"

    return intel

class RequestHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path

        if path == "/" or path == "/index.html":
            self._serve_html()
        elif path == "/api/status":
            self._send_json(task_manager.get_status())
        elif path == "/api/logs":
            status = task_manager.get_status()
            self._send_json({"logs": task_manager.logs, "is_running": status["is_running"]})
        elif path == "/api/results":
            self._send_json(task_manager.results)
        elif path == "/api/proxyip/sources":
            self._send_json({"count": len(proxy_task_manager.cached_sources), "sources": proxy_task_manager.cached_sources[:50]})
        elif path == "/api/proxyip/status":
            self._send_json(proxy_task_manager.get_status())
        elif path == "/api/proxyip/logs":
            status = proxy_task_manager.get_status()
            self._send_json({"logs": proxy_task_manager.logs, "is_running": status["is_running"]})
        elif path == "/api/proxyip/results":
            self._send_json(proxy_task_manager.results)
        elif path == "/api/inspect/ip_info":
            q_ip = parse_qs(url.query).get('ip', [None])[0]
            self._send_json(get_ip_intel(q_ip))
        elif path == "/api/inspect/non_cf":
            # 辅助请求非 CF 接口
            try:
                res = subprocess.run(["curl", "-s", "-m", "3", "https://ipinfo.io/json"], capture_output=True, text=True)
                if res.returncode == 0 and res.stdout.strip().startswith("{"):
                    self._send_json(json.loads(res.stdout))
                else:
                    self._send_json({"error": "Failed to fetch non-cf ip"})
            except Exception as e:
                self._send_json({"error": str(e)})
        elif path == "/api/inspect/cf_trace":
            # 辅助请求 CF 接口
            try:
                res = subprocess.run(["curl", "-s", "-m", "3", "https://www.cloudflare.com/cdn-cgi/trace"], capture_output=True, text=True)
                lines = {}
                for line in res.stdout.splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        lines[k.strip()] = v.strip()
                self._send_json(lines)
            except Exception as e:
                self._send_json({"error": str(e)})
        elif path == "/manifest.json":
            self._serve_manifest()
        elif path == "/icon.svg":
            self._serve_icon()
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        url = urlparse(self.path)
        path = url.path
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else ""
        try:
            params = json.loads(body) if body else {}
        except Exception:
            params = {}

        if path == "/api/start":
            success, msg = task_manager.run_test(params)
            self._send_json({"success": success, "message": msg})
        elif path == "/api/stop":
            task_manager.stop()
            self._send_json({"success": True, "message": "已下发停止信号"})
        elif path == "/api/proxyip/fetch_sources":
            items = proxy_task_manager.fetch_sources()
            self._send_json({"success": True, "count": len(items), "message": f"成功拉取 {len(items)} 个候选 ProxyIP"})
        elif path == "/api/proxyip/start":
            success, msg = proxy_task_manager.run_test(params)
            self._send_json({"success": success, "message": msg})
        elif path == "/api/proxyip/stop":
            proxy_task_manager.stop()
            self._send_json({"success": True, "message": "已下发停止信号"})
        else:
            self.send_error(404, "Not Found")

    def _serve_html(self):
        html_file = os.path.join(BASE_DIR, "index.html")
        
        if os.path.exists(html_file):
            with open(html_file, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404, "index.html not found")

    def _serve_manifest(self):
        manifest = {
            "name": "CF-Pulse 节点优选与体检控制台",
            "short_name": "CF-Pulse",
            "start_url": "/",
            "display": "standalone",
            "background_color": "#0f172a",
            "theme_color": "#f59e0b",
            "icons": [
                {
                    "src": "/icon.svg",
                    "sizes": "192x192 512x512",
                    "type": "image/svg+xml"
                }
            ]
        }
        content = json.dumps(manifest, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header("Content-Type", "application/manifest+json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)

    def _serve_icon(self):
        svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#f59e0b"/>
      <stop offset="50%" stop-color="#ea580c"/>
      <stop offset="100%" stop-color="#d97706"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="120" fill="url(#g)"/>
  <text x="50%" y="54%" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" font-weight="900" font-size="240" fill="#ffffff" text-anchor="middle" dominant-baseline="middle">CF</text>
</svg>"""
        content = svg.encode('utf-8')
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, data):
        content = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        return

def run_server():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), RequestHandler)
    print(f"CF-Pulse WebUI (Threading) 已就绪: http://127.0.0.1:{PORT} (局域网支持: http://0.0.0.0:{PORT})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == "__main__":
    run_server()
