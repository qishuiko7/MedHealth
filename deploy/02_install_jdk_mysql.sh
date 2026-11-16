#!/usr/bin/env bash
# =============================================================================
# 02_install_jdk_mysql.sh —— 安装 JDK 8 与 MySQL（对应《项目操作流程》步骤 4）
# 功能：1) 解压安装 JDK 8 并配置 JAVA_HOME / PATH
#       2) 安装并初始化 MySQL，创建 Hive 元数据库与业务库
# 运行：以 root 执行   bash 02_install_jdk_mysql.sh
# 前置：已执行 01_system_prepare.sh
# 说明：JDK 安装包需离线准备（Oracle 需登录），放入 $PKG_DIR；MySQL 走 yum 源
# =============================================================================
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"

# =============================================================================
# 第一部分：安装 JDK 8
# =============================================================================
log_info "===== 1. 安装 JDK ${JDK_VERSION} ====="
if [ -x "${JAVA_HOME}/bin/java" ]; then
  log_info "JDK 已安装于 ${JAVA_HOME}，跳过解压"
else
  if [ -s "${PKG_DIR}/${JDK_TARBALL}" ]; then
    log_info "使用离线安装包 ${PKG_DIR}/${JDK_TARBALL}"
  else
    log_warn "未找到 ${PKG_DIR}/${JDK_TARBALL}"
    log_warn "请从 Oracle 官网下载 jdk-8u381-linux-x64.tar.gz 后放入 ${PKG_DIR}/"
    log_warn "（官网下载需登录账号，无法脚本直连；也可使用 OpenJDK：yum install -y java-1.8.0-openjdk-devel）"
    exit 1
  fi
  install_tarball "${PKG_DIR}/${JDK_TARBALL}" "$INSTALL_ROOT"
  # 官方 tar 解压后目录名一般为 jdk1.8.0_381，若非此名则软链/改名
  if [ ! -d "${JAVA_HOME}" ]; then
    REAL_JDK_DIR="$(ls -d "${INSTALL_ROOT}"/jdk* 2>/dev/null | head -n1 || true)"
    [ -n "$REAL_JDK_DIR" ] && ln -sfn "$REAL_JDK_DIR" "$JAVA_HOME"
  fi
fi

# 写入全局环境变量（对所有用户生效）
cat > /etc/profile.d/bigdata_env.sh <<EOF
# ===== 大数据平台全局环境变量（由 02_install_jdk_mysql.sh 生成）=====
export JAVA_HOME=${JAVA_HOME}
export HADOOP_HOME=${HADOOP_HOME}
export HIVE_HOME=${HIVE_HOME}
export ZOOKEEPER_HOME=${ZOOKEEPER_HOME}
export KAFKA_HOME=${KAFKA_HOME}
export SPARK_HOME=${SPARK_HOME}
export PATH=\$JAVA_HOME/bin:\$HADOOP_HOME/bin:\$HADOOP_HOME/sbin:\$HIVE_HOME/bin:\$ZOOKEEPER_HOME/bin:\$KAFKA_HOME/bin:\$SPARK_HOME/bin:\$SPARK_HOME/sbin:\$PATH
export HADOOP_CONF_DIR=\$HADOOP_HOME/etc/hadoop
export HIVE_CONF_DIR=\$HIVE_HOME/conf
export LD_LIBRARY_PATH=\$HADOOP_HOME/lib/native:\$LD_LIBRARY_PATH
EOF
chmod 644 /etc/profile.d/bigdata_env.sh
chown -R "${CLUSTER_USER}:${CLUSTER_GROUP}" "$JAVA_HOME" 2>/dev/null || true

# 为避免已安装 JDK 时的 yum java 冲突，安装 java-1.8.0-openjdk-devel（提供 javac 依赖）
# 若已有官方 JDK 且 javac 可用，则跳过
if [ ! -x "${JAVA_HOME}/bin/javac" ]; then
  log_warn "${JAVA_HOME}/bin/javac 不存在，尝试 yum 安装 OpenJDK 作为补充"
  yum install -y java-1.8.0-openjdk-devel || log_warn "OpenJDK 安装失败"
fi

export JAVA_HOME PATH
java -version 2>&1 | head -n 3 || log_warn "java 命令暂不可用，请重新登录 shell 使环境变量生效"

# =============================================================================
# 第二部分：安装 MySQL
# =============================================================================
log_info "===== 2. 安装 MySQL ${PORT_MYSQL} ====="
if command -v mysqld >/dev/null 2>&1; then
  log_info "MySQL 服务端已存在，跳过程序安装"
else
  OS_MAJOR="$(rpm -E %{rhel} 2>/dev/null || echo 7)"
  log_info "检测到 RHEL/CentOS 主版本: ${OS_MAJOR}"
  # 方案 A：官方 MySQL 8.0 yum 源
  if yum install -y "https://dev.mysql.com/get/mysql80-community-release-el${OS_MAJOR}-1.noarch.rpm" 2>/dev/null \
     && yum install -y mysql-community-server mysql-community-client; then
    log_info "已通过官方源安装 MySQL 8.0 Community"
  else
    # 方案 B：系统自带 mysql-server（CentOS 8/9）或 mariadb（CentOS 7）
    log_warn "官方 MySQL 源不可用，改用系统自带源"
    yum install -y mysql-server 2>/dev/null || yum install -y mariadb-server mariadb || {
      log_error "MySQL 安装失败，请检查 yum 源或离线 rpm 包"; exit 1;
    }
  fi
fi

# 兼容 mariadb 与 mysql 的服务名
SVC_NAME="mysqld"
systemctl list-unit-files 2>/dev/null | grep -q "^mariadb.service" && SVC_NAME="mariadb"

# 初始化数据目录（MySQL 8 首次启动会自动初始化，此处兼容旧版）
if [ ! -d /var/lib/mysql/mysql ]; then
  if [ "$SVC_NAME" = "mariadb" ]; then
    mysql_install_db --user=mysql >/dev/null 2>&1 || true
  else
    mysqld --initialize-insecure --user=mysql >/dev/null 2>&1 || true
  fi
fi

systemctl enable "$SVC_NAME" 2>/dev/null || true
systemctl start  "$SVC_NAME"
sleep 3

# 获取初始密码（MySQL 8 官方源安装会生成随机临时密码）
if [ -s /var/log/mysqld.log ]; then
  TMP_PWD="$(grep 'temporary password' /var/log/mysqld.log 2>/dev/null | tail -n1 | awk '{print $NF}')"
fi
TMP_PWD="${TMP_PWD:-}"

# 统一改写后的 root 密码
log_info "配置 MySQL root 密码与业务库"
if [ -n "$TMP_PWD" ]; then
  mysql -uroot -p"$TMP_PWD" --connect-expired-password <<SQL || log_warn "使用临时密码登录失败，尝试空密码"
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '${MYSQL_ROOT_PWD}';
FLUSH PRIVILEGES;
SQL
fi
# 空密码登录（mariadb / initialize-insecure）
mysql -uroot <<SQL 2>/dev/null || mysql -uroot -p"${MYSQL_ROOT_PWD}" <<SQL
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '${MYSQL_ROOT_PWD}';
FLUSH PRIVILEGES;
SQL

# 允许远程连接（Windows 端 PyMySQL / Sqoop / Flask 需要连 Linux MySQL）
mysql -uroot -p"${MYSQL_ROOT_PWD}" <<SQL
-- 允许 root 远程登录（教学环境；生产改为专用账号）
CREATE USER IF NOT EXISTS 'root'@'%' IDENTIFIED WITH mysql_native_password BY '${MYSQL_ROOT_PWD}';
GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION;
FLUSH PRIVILEGES;

-- Hive 元数据库
CREATE DATABASE IF NOT EXISTS ${HIVE_META_DB} DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
CREATE USER IF NOT EXISTS '${HIVE_META_USER}'@'%' IDENTIFIED WITH mysql_native_password BY '${HIVE_META_PWD}';
GRANT ALL PRIVILEGES ON ${HIVE_META_DB}.* TO '${HIVE_META_USER}'@'%';
FLUSH PRIVILEGES;

-- 业务库（离线/实时结果落地，与主工程 config.py 的 med_health 保持一致）
CREATE DATABASE IF NOT EXISTS ${BIZ_DB} DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
CREATE USER IF NOT EXISTS '${BIZ_USER}'@'%' IDENTIFIED WITH mysql_native_password BY '${BIZ_PWD}';
GRANT ALL PRIVILEGES ON ${BIZ_DB}.* TO '${BIZ_USER}'@'%';
FLUSH PRIVILEGES;
SQL

# 放开远程访问：修改 bind-address
MYCNF="/etc/my.cnf"
[ -d /etc/my.cnf.d ] && [ ! -f "$MYCNF" ] && MYCNF="/etc/my.cnf.d/server.cnf"
if [ -f "$MYCNF" ]; then
  if grep -qE '^[[:space:]]*bind-address' "$MYCNF"; then
    sed -i 's/^[[:space:]]*bind-address.*/bind-address = 0.0.0.0/' "$MYCNF"
  else
    # 写入 [mysqld] 段
    if grep -q '^\[mysqld\]' "$MYCNF"; then
      sed -i '/^\[mysqld\]/a bind-address = 0.0.0.0\ndefault_authentication_plugin = mysql_native_password\ncharacter-set-server = utf8mb4\ncollation-server = utf8mb4_general_ci\ndefault-time-zone = "+08:00"' "$MYCNF"
    fi
  fi
  systemctl restart "$SVC_NAME" || true
  log_info "已放开 MySQL 远程访问（bind-address=0.0.0.0）"
fi

# 验证连接
mysql -uroot -p"${MYSQL_ROOT_PWD}" -e "SHOW DATABASES;" \
  && log_info "MySQL 安装与初始化完成" \
  || log_error "MySQL 连接验证失败，请检查密码与服务状态"

cat <<EOF

============================================================
 02_install_jdk_mysql.sh 执行完成
 JDK      : ${JAVA_HOME}  (java -version 查看)
 MySQL    : 端口 ${PORT_MYSQL}，root 密码 ${MYSQL_ROOT_PWD}
 Hive 元库: ${HIVE_META_DB}（账号 ${HIVE_META_USER}/${HIVE_META_PWD}）
 业务库   : ${BIZ_DB}（账号 ${BIZ_USER}/${BIZ_PWD}）
 下一步   : bash 03_install_hadoop.sh
============================================================
EOF
