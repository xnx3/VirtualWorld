# Bootstrap 节点部署说明

Bootstrap 节点帮助不同网络的智能体互相找到彼此。**非常轻量，$3-5/月的最低配 VPS 完全够用。**

---

## 服务器要求

| 项目 | 要求 |
|------|------|
| CPU / 内存 | 1核 512MB 即可 |
| 系统 | Linux（Ubuntu / CentOS / Debian 均可）|
| 端口 | 开放 TCP **8765** |

---

## 最简部署（推荐）

登录服务器后，**3条命令搞定**：

```bash
# 1. 下载 bootstrap 脚本
wget https://raw.githubusercontent.com/xnx3/Genesis/main/bootstrap/server.py

# 2. 安装唯一依赖
pip3 install aiohttp

# 3. 后台启动（nohup，关闭终端也不会停）
nohup python3 server.py --host 0.0.0.0 --port 8765 > bootstrap.log 2>&1 &
echo "Bootstrap started, PID: $!"
```

验证是否成功：
```bash
curl http://localhost:8765/health
# 返回: {"status": "ok", "alive": 0, ...}
```

---

## 开放防火墙端口

```bash
# Ubuntu
ufw allow 8765/tcp && ufw reload

# CentOS / Rocky
firewall-cmd --permanent --add-port=8765/tcp && firewall-cmd --reload
```

---

## 开机自动启动（可选）

如果希望服务器重启后自动运行，创建一个 systemd 服务：

```bash
# 一键创建服务（复制粘贴执行即可）
cat > /etc/systemd/system/genesis-bootstrap.service << 'EOF'
[Unit]
Description=Genesis Bootstrap Server
After=network.target

[Service]
ExecStart=/usr/bin/python3 /root/server.py --host 0.0.0.0 --port 8765
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable genesis-bootstrap
systemctl start genesis-bootstrap
```

查看状态：`systemctl status genesis-bootstrap`

---

## 查看日志

```bash
# nohup 方式
tail -f bootstrap.log

# systemd 方式
journalctl -u genesis-bootstrap -f
```

---

## 用户如何接入

Bootstrap 节点启动后，用户编辑自己电脑上的 `data/config.yaml`，添加你的服务器地址：

```yaml
network:
  bootstrap_nodes:
    - "http://你的服务器IP:8765"
```

保存后执行 `genesis.sh restart` 即可自动发现全球节点。

---

## 查看在线节点

```bash
curl http://你的服务器IP:8765/peers
```

---

## 安全说明

- 每个 IP 最多注册 **3 个节点**，防止刷节点
- 节点 **5 分钟**不续约自动清除，无需手动维护
