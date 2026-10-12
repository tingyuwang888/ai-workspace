# 堡垒机部署步骤

- Chat ID: `mnqvnmlkehzp20it`
- 分类：堡垒机部署
- 起始日期：2026-04-09
- 会话文件数：1

---


## 会话 1/1 · `1d6a12e8`

### 🧑 用户 · 2026-04-09T02:48:16.591Z

总结一下通过堡垒机部署skill的部署步骤

<system-reminder>
User environment — Timezone: Asia/Shanghai (UTC+08:00). Locale: en-US. OS: darwin.
Note: If you need the current date or time, run `date` via Bash to get a fresh, accurate value. Do not assume a fixed time.
</system-reminder>
<system-reminder>
Available MCP servers:
- builtin_browser: Browser automation for web interaction. Core workflow: (1) Use list_tabs to get available tabs, (2) Use navigate to open URLs, (3) Use snapshot to read page content (lightweight, preferred) or screenshot for visual needs, (4) Use click/type/scroll/press_key to interact with elements via refs from snapshot. Also supports: hover, drag, select_option for forms, wait_for for delays, evaluate for JavaScript execution, and console_messages/network_requests for debugging.

Use qw_mcp_list to see all tools, qw_mcp_get to get tool schema (ALWAYS call this before qw_mcp_call to get correct arguments), qw_mcp_call to execute.

Available tools:
mcp__builtin_browser__list_tabs, mcp__builtin_browser__close_tab, mcp__builtin_browser__navigate, mcp__builtin_browser__snapshot, mcp__builtin_browser__screenshot, mcp__builtin_browser__click, mcp__builtin_browser__type, mcp__builtin_browser__hover, mcp__builtin_browser__drag, mcp__builtin_browser__select_option, mcp__builtin_browser__press_key, mcp__builtin_browser__scroll, mcp__builtin_browser__wait_for, mcp__builtin_browser__evaluate, mcp__builtin_browser__upload_file, mcp__builtin_browser__handle_dialog, mcp__builtin_browser__console_messages, mcp__builtin_browser__network_requests, mcp__builtin_browser__page_errors
</system-reminder>

### 🤖 助手 · 2026-04-09T02:48:16.601Z

Let我先搜索一下相关的skill文档，看看有没有关于通过堡垒机部署的具体步骤说明。

### 🤖 助手 · 2026-04-09T02:48:24.817Z

找到了相关的skill文档，让我读取关键文件来了解部署步骤。

### 🤖 助手 · 2026-04-09T02:48:29.514Z

根据 `jumpserver-tiance-deploy` skill 的文档，通过堡垒机部署天策决策中台的完整步骤如下：

---

**核心差异**：因为无法直接 SSH/SCP 到目标服务器，所有远程命令需通过 expect 脚本（macOS/Linux 用 `jrun.sh`）或 paramiko Python 脚本（Windows 用 `jconn.py`）自动化堡垒机交互式会话，文件传输则通过 FTP 中转或 SSH 公钥免密 SCP。

**推荐的三台服务器角色划分**：应用服务器（Nginx + 全部应用 + 前端资源）、数据服务器（MySQL + ES + ApexDB）、消息服务器（ZooKeeper + Kafka + Nacos）。

**整体部署流程分为 9 个阶段**：

**阶段 0：前置准备**。安装本地依赖（macOS 上 `brew install expect sshpass lftp`，Windows 上 `pip install paramiko`），验证 FTP 连通性，给 `jrun.sh` 等脚本加执行权限，然后逐台服务器执行 `jrun.sh <IP> "hostname && whoami"` 验证堡垒机连通性。

**阶段 1：上传交付物**。推荐 FTP 中转方式：先用 lftp 或 FileZilla 将本地 hera 交付物上传到 FTP 服务器的个人目录下（按 jdk/mysql/elasticsearch/apexdb/zookeeper/kafka/nacos/nginx/backend/static/sql/config 子目录组织），再通过 `jrun.sh` 在各目标服务器上执行 `wget` 从 FTP 下载到 `/data01/td/temp/` 目录。JDK 分发到全部三台，MySQL/ES/ApexDB/SQL 到数据服务器，ZK/Kafka/Nacos 到消息服务器，应用包/前端/Nginx 到应用服务器。

**阶段 2：系统初始化**。在所有服务器上创建 `/data01/td/infra`、`/data01/td/tiance`、`/data01/td/temp` 目录结构，调整内核参数（`fs.file-max`、`vm.max_map_count` 等）和 `limits.conf`，关闭防火墙，最后在每台服务器上安装 JDK 1.8 到 `/usr/local/`。

**阶段 3：中间件部署**。按依赖顺序逐个部署，数据服务器上：MySQL 5.7（解压、建 my.cnf、初始化、启动、创建 tongdun 用户）→ Elasticsearch 7.10（配置 `elasticsearch.yml`、用 tdops 用户启动）→ ApexDB（RPM 安装、写 `apexdb.conf` 配置 product-key 和 namespace、启动）。消息服务器上：ZooKeeper 3.4（解压、配置 zoo.cfg、启动）→ Kafka 2.12（配置 `server.properties` 指向 ZK、后台启动）→ Nacos（解压、先在数据服务器建 nacos 库并导入 schema、配置连 MySQL、单机模式启动）。Nacos 启动后需建 SSH 隧道到 18848 端口，通过浏览器访问 Nacos 控制台导入 `tiance-nacos.zip` 配置包。

**阶段 4：SQL 初始化**。建立 MySQL SSH 隧道（本地 13306 映射到数据服务器 3306），创建 tiance 数据库，然后按顺序执行 SQL 脚本：`init_i18n` → `init_common` → `init_bifrost` → `init_aflow` → `init_roster` → `init_salaxy` → `init_tiangong` → `init_tiangong_data`（用 `--force`）→ `init_holmes` → `init_tianzuo` → `init_spartan` → `init_spartan-merchant` → `init_tdscheduler` → `init_spartan-account` → `init_spartan-account_data`。执行后必须做 SQL 验证，检查 `system_config`、`bifrost_user`、`tiangong_template`、`salaxy_node_info` 等关键表的行数。此外还需初始化 ES 索引（执行 `init_elasticsearch_manual.sh`）。

**阶段 5：应用部署**。在应用服务器上先安装 Nginx（RPM 方式），然后按顺序部署并启动 Java 应用：bifrost(8501) → salaxy(8502) → tiangong-admin(8503) → tiangong-api(8504) → kratos-consumer(8506) → 场景应用（spartan/atreus 等按需）→ tdjob(8011) → holmes-web(8513) → holmes-python(9002) → tianzuo-server(8512)。每个应用需在对应目录放入 jar 包和 `bootstrap.properties` 配置（指向 Nacos 地址），通过 `nohup java -jar` 启动。

**阶段 6：前端资源部署**。解压静态文件 tar.gz 包，将 `*-resource` 目录（bifrost-resource、lightbox-resource、salaxy-resource 等）复制到 `/data01/td/tiance/static/`。

**阶段 7：SSH 隧道与访问**。建立 Nginx SSH 隧道（本地 8080 映射到应用服务器 80 端口），浏览器访问 `http://localhost:8080/user/login`，默认账号 `admin / Td@123456`。

**阶段 8：系统初始化**。登录后导入 license 和解决方案，配置 admin 超级权限，调用 `/noahApi/relationReference/reBuild?type=ALL` 接口初始化数据关系。

**阶段 9：数据完整性检查**。检查重复记录（bifrost_system_field、bifrost_field_group 等表去重）、验证 SystemVariableConfig 配置项存在、确认主维度表（bifrost_main_dimension）有数据。如有缺失则按文档补插入或通过 bifrost API 添加主维度。

---

**平台兼容性**方面，macOS/Linux 上使用 `jrun.sh`（基于 expect + sshpass），Windows 上自动切换为 `jconn.py`（基于 Python paramiko），两者 CLI 参数兼容（`<server_ip> "<command>" [wait_seconds]`），只需替换命令前缀即可。

如果需要我实际执行某个阶段的部署，或者需要更详细的某个步骤说明，随时告诉我。

### 🧑 用户 · 2026-04-09T02:50:17.224Z

<user-pasted-image file="/Users/td/.qoderwork/workspace/mnqvnmlkehzp20it/uploads/image_1775703016522_vo7v2ps.png" /> 什么时候导入nacos配置呢？

### 🤖 助手 · 2026-04-09T02:50:17.229Z

根据部署流程，**Nacos 配置导入的时机是在阶段 3（中间件部署）的 Nacos 启动完成之后、阶段 4（SQL 初始化）之前**。

具体来说，步骤是这样的：

1. 先在消息服务器上启动 Nacos（单机模式），确认 Nacos 服务正常运行
2. 建立 SSH 隧道将 Nacos 端口映射到本地：
   ```bash
   sshpass -p '${JUMPSERVER_PASS}' ssh -o StrictHostKeyChecking=no -p ${JUMPSERVER_PORT} \
       -L 18848:${MSG_SERVER_IP}:8848 \
       ${JUMPSERVER_USER}@${JUMPSERVER_HOST} -N -f
   ```
3. 浏览器访问 `http://localhost:18848/nacos`，用 nacos/nacos 登录
4. 在默认 public 命名空间下，**导入 `tiance-nacos.zip` 配置包**

从你的截图来看，你已经打开了 Nacos 控制台，并且正在查看某个配置项的详情（Data ID 是 `*.properties`，Group 是 `nacos2405_tdov`）。这说明配置已经存在或者你正在编辑配置。

**为什么必须在 SQL 初始化之前导入？** 因为后续启动的所有 Java 应用（bifrost、salaxy、tiangong 等）都依赖 Nacos 中的配置来连接 MySQL、Kafka、ES 等中间件。如果 Nacos 配置缺失，应用启动时会报连接错误或 placeholder 解析失败。

**导入后需要特别检查的一点**：如果 `tiance-nacos.zip` 是从其他环境导出的，里面的 IP 地址可能指向旧环境。导入后务必检查 `common.properties`、`common-tiance.properties`、`application-holmes-manager.properties` 等核心配置中的 MySQL、ES、Kafka、ZK 地址是否已替换为当前环境的实际 IP，否则应用启动后会连到错误的地址（troubleshooting 案例 13 就是这个问题）。
