# Bootstrap 节点部署说明

Bootstrap 节点是 Genesis 网络的「节点发现服务」，帮助不同网络的智能体互相找到彼此。
**它非常轻量，$3-5/月的最低配 VPS 完全够用。**

---

## 服务器要求

| 项目 | 最低配置 |
|------|---------|
| CPU | 1 核 |
| 内存 | 512 MB |
| 硬盘 | 5 GB |
| 带宽 | 1 Mbps |
| 系统 | Linux（Ubuntu 20.04+ 推荐）|
| 端口 | 开放 TCP **8765** |

推荐服务商：腾讯云轻量应用服务器（最低配 ¥24/月）、阿里云 ECS 入门级、Vultr $3.5/月。

---

## 方式一：Docker 部署（推荐）

### 1. 安装 Docker

```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com | sh
systemctl enable docker && systemctl start docker
```

### 2. 上传并启动

```bash
# 将 bootstrap/ 目录上传到服务器
scp -r bootstrap/ root@你的服务器IP:/opt/genesis-bootstrap/

# 登录服务器
ssh root@你的服务器IP

# 启动服务
cd /opt/genesis-bootstrap
docker compose up -d

# 查看日志
docker compose logs -f
```

### 3. 验证服务正常

```bash
curl http://localhost:8765/health
# 返回: {"status": "ok", "alive": 0, ...}
```

---

## 方式二：直接 Python 运行

### 1. 安装依赖

```bash
pip install aiohttp
```

### 2. 启动服务

```bash
python bootstrap/server.py --host 0.0.0.0 --port 8765
```

### 3. 后台运行（使用 systemd）

创建服务文件 `/etc/systemd/system/genesis-bootstrap.service`：

```ini
[Unit]
Description=Genesis Bootstrap Server
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/genesis-bootstrap
ExecStart=/usr/bin/python3 server.py --host 0.0.0.0 --port 8765
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启动：
```bash
systemctl daemon-reload
systemctl enable genesis-bootstrap
systemctl start genesis-bootstrap
systemctl status genesis-bootstrap
```

---

## 开放防火墙端口

```bash
# Ubuntu (ufw)
ufw allow 8765/tcp
ufw reload

# CentOS/Rocky (firewalld)
firewall-cmd --permanent --add-port=8765/tcp
firewall-cmd --reload
```

---

## API 接口说明

| 接口 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查，返回在线节点数量 |
| `/register` | POST | 节点注册/续约（每5分钟自动续约） |
| `/peers` | GET | 获取在线节点列表（最多100个） |

查看当前在线节点：
```bash
curl http://你的服务器IP:8765/peers
```

---

## 用户接入配置

节点部署好后，用户只需编辑 `data/config.yaml`，在 `network` 部分添加你的服务器地址：

```yaml
network:
  bootstrap_nodes:
    - "http://你的服务器IP:8765"
```

保存后执行 `genesis.sh restart` 重启即可自动连接到全球节点网络。

---

## 安全说明

- 每个 IP 最多注册 **3 个节点**，防止批量刷节点
- 节点 **5 分钟**不续约自动清除
- 建议在服务器上配置 Nginx 反向代理，启用 HTTPS：

```nginx
server {
    listen 443 ssl;
    server_name bootstrap.你的域名.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
```

然后用户配置：
```yaml
network:
  bootstrap_nodes:
    - "https://bootstrap.你的域名.com"
```

---

## 查看运行状态

```bash
# Docker 方式
docker compose ps
docker compose logs --tail=50

# systemd 方式
systemctl status genesis-bootstrap
journalctl -u genesis-bootstrap -n 50
```
