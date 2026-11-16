#!/usr/bin/env bash
# =============================================================================
# 04_install_hive.sh —— 安装与配置 Hive 3.1.3（对应《项目操作流程》步骤 5 后半）
# 功能：安装 Hive → 配置 MySQL 元数据库 → 放置 mysql-connector 驱动
#       → schematool -initSchema → 启动 metastore 与 hiveserver2
# 运行：以 root 执行   bash 04_install_hive.sh
# 前置：已执行 01、02、03（Hadoop 已启动）
# =============================================================================
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"

log_info "===== 1. 安装 Hive ${HIVE_VERSION} ====="
if [ -x "${HIVE_HOME}/bin/hive" ]; then
  log_info "Hive 已安装于 ${HIVE_HOME}，跳过解压"
else
  fetch_pkg "$URL_HIVE" "${PKG_DIR}/${HIVE_TARBALL}"
  install_tarball "${PKG_DIR}/${HIVE_TARBALL}" "$INSTALL_ROOT"
  # 官方包名为 apache-hive-3.1.3-bin，软链为 hive-3.1.3
  if [ ! -d "${HIVE_HOME}" ] && [ -d "${INSTALL_ROOT}/apache-hive-${HIVE_VERSION}-bin" ]; then
    ln -sfn "${INSTALL_ROOT}/apache-hive-${HIVE_VERSION}-bin" "${HIVE_HOME}"
  fi
fi

log_info "===== 2. 放置 MySQL JDBC 驱动 ====="
CONNECTOR_JAR="${HIVE_HOME}/lib/mysql-connector-j-${MYSQL_CONNECTOR_VERSION}.jar"
if [ ! -f "$CONNECTOR_JAR" ]; then
  fetch_pkg "$URL_MYSQL_CONNECTOR" "${PKG_DIR}/${MYSQL_CONNECTOR_TARBALL}"
  if [ -f "${PKG_DIR}/${MYSQL_CONNECTOR_TARBALL}" ]; then
    tar -zxf "${PKG_DIR}/${MYSQL_CONNECTOR_TARBALL}" -C "${PKG_DIR}"
    find "${PKG_DIR}" -name "mysql-connector-j-${MYSQL_CONNECTOR_VERSION}.jar" -exec cp -f {} "$CONNECTOR_JAR" \;
  fi
fi
if [ -f "$CONNECTOR_JAR" ]; then
  log_info "驱动就绪: $CONNECTOR_JAR"
else
  log_warn "未找到 mysql-connector jar，请手动拷贝到 ${HIVE_HOME}/lib/"
fi

log_info "===== 3. 解决 Hive 与 Hadoop 的 guava 版本冲突 ====="
# Hive 3.1.3 自带 guava-19.0，Hadoop 3.3.6 使用 guava-27.0-jre。
# 保留 Hadoop 版本（更新），删除 Hive 里的旧 guava。
if [ -f "${HADOOP_HOME}/share/hadoop/common/lib/guava-27.0-jre.jar" ]; then
  rm -f "${HIVE_HOME}/lib/guava-19.0.jar"
  cp -fn "${HADOOP_HOME}/share/hadoop/common/lib/guava-27.0-jre.jar" "${HIVE_HOME}/lib/" 2>/dev/null || true
  log_info "已用 Hadoop 的 guava-27.0-jre 替换 Hive 旧版"
fi

log_info "===== 4. 生成 hive-site.xml ====="
cat > "${HIVE_HOME}/conf/hive-site.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<?xml-stylesheet type="text/xsl" href="configuration.xsl"?>
<configuration>
    <!-- ===== 元数据库：MySQL ===== -->
    <property>
        <name>javax.jdo.option.ConnectionURL</name>
        <value>${MYSQL_JDBC_URL}</value>
        <description>Hive 元数据存储的 MySQL 连接串</description>
    </property>
    <property>
        <name>javax.jdo.option.ConnectionDriverName</name>
        <value>com.mysql.cj.jdbc.Driver</value>
    </property>
    <property>
        <name>javax.jdo.option.ConnectionUserName</name>
        <value>${HIVE_META_USER}</value>
    </property>
    <property>
        <name>javax.jdo.option.ConnectionPassword</name>
        <value>${HIVE_META_PWD}</value>
    </property>

    <!-- ===== 仓库位置（HDFS） ===== -->
    <property>
        <name>hive.metastore.warehouse.dir</name>
        <value>${HDFS_WAREHOUSE}</value>
    </property>
    <property>
        <name>hive.downloaded.resources.dir</name>
        <value>/tmp/hive/resources</value>
    </property>

    <!-- ===== 元数据校验 ===== -->
    <property>
        <name>hive.metastore.schema.verification</name>
        <value>false</value>
    </property>
    <property>
        <name>datanucleus.schema.autoCreateAll</name>
        <value>true</value>
    </property>

    <!-- ===== Metastore / HiveServer2 服务 ===== -->
    <property>
        <name>hive.metastore.uris</name>
        <value>thrift://${HOSTNAME_MASTER}:${PORT_HIVE_METASTORE}</value>
    </property>
    <property>
        <name>hive.server2.thrift.bind.host</name>
        <value>0.0.0.0</value>
    </property>
    <property>
        <name>hive.server2.thrift.port</name>
        <value>${PORT_HIVESERVER2}</value>
    </property>
    <property>
        <name>hive.server2.webui.port</name>
        <value>${PORT_HIVESERVER2_WEB}</value>
    </property>
    <property>
        <name>hive.server2.enable.doAs</name>
        <value>false</value>
    </property>
    <property>
        <name>hive.server2.active.passive.ha.enable</name>
        <value>true</value>
    </property>

    <!-- ===== 执行引擎（Spark/Tez 可选；默认 MR，Spark 集成见 06 脚本） ===== -->
    <property>
        <name>hive.execution.engine</name>
        <value>mr</value>
    </property>

    <!-- ===== 常见兼容项 ===== -->
    <property>
        <name>hive.server2.thrift.http.path</name>
        <value>cliservice</value>
    </property>
    <property>
        <name>hive.metastore.event.db.notification.api.auth</name>
        <value>false</value>
    </property>
    <property>
        <name>hive.stats.autogather</name>
        <value>false</value>
    </property>
    <property>
        <name>hive.support.concurrency</name>
        <value>true</value>
    </property>
</configuration>
EOF

# XML 转义：JDBC URL 中的 & 必须写成 &amp;，否则 schematool 解析 hive-site.xml 报错
sed -i 's/&/\&amp;/g' "${HIVE_HOME}/conf/hive-site.xml"

# hadoop 相关 classpath，便于 Hive 找 HDFS 依赖
cp -fn "${HADOOP_HOME}/etc/hadoop/core-site.xml" "${HIVE_HOME}/conf/" 2>/dev/null || true
cp -fn "${HADOOP_HOME}/etc/hadoop/hdfs-site.xml" "${HIVE_HOME}/conf/" 2>/dev/null || true

chown -R "${CLUSTER_USER}:${CLUSTER_GROUP}" "$HIVE_HOME"

log_info "===== 5. 初始化 Hive 元数据库 schematool ====="
if mysql -uroot -p"${MYSQL_ROOT_PWD}" -e "USE ${HIVE_META_DB}; SHOW TABLES;" 2>/dev/null | grep -q "TBLS"; then
  log_info "元数据库已初始化（存在 TBLS 表），跳过"
else
  su - "$CLUSTER_USER" -c "source /etc/profile.d/bigdata_env.sh; schematool -dbType mysql -initSchema" \
    && log_info "schematool 初始化成功" \
    || { log_error "schematool 初始化失败，检查 MySQL 连接串/驱动/guava"; exit 1; }
fi

log_info "===== 6. 启动 Metastore 与 HiveServer2 ====="
# 后台启动（Hive 自带脚本会 nohup）；日志见 /tmp/${CLUSTER_USER}/hive.log
su - "$CLUSTER_USER" -c "source /etc/profile.d/bigdata_env.sh; \
  nohup hive --service metastore >/tmp/hive-metastore.log 2>&1 &" || true
sleep 5
su - "$CLUSTER_USER" -c "source /etc/profile.d/bigdata_env.sh; \
  nohup hive --service hiveserver2 >/tmp/hive-hiveserver2.log 2>&1 &" || true
sleep 8

log_info "===== 7. 验证 ====="
if command -v ss >/dev/null 2>&1; then
  ss -lntp 2>/dev/null | grep -E ":${PORT_HIVE_METASTORE}|:${PORT_HIVESERVER2}" || log_warn "端口未监听，首次启动较慢请稍后重试"
fi
# 冒烟测试：建库建表
su - "$CLUSTER_USER" -c "source /etc/profile.d/bigdata_env.sh; \
  beeline -u 'jdbc:hive2://${HOSTNAME_MASTER}:${PORT_HIVESERVER2}' -n ${CLUSTER_USER} \
  -e 'CREATE DATABASE IF NOT EXISTS med_health; SHOW DATABASES;'" || log_warn "beeline 连接失败，请查看 /tmp/hive-hiveserver2.log"

cat <<EOF

============================================================
 04_install_hive.sh 执行完成
 Metastore   : thrift://${HOSTNAME_MASTER}:${PORT_HIVE_METASTORE}
 HiveServer2 : jdbc:hive2://${HOSTNAME_MASTER}:${PORT_HIVESERVER2}
 Web UI      : http://${IP_MASTER}:${PORT_HIVESERVER2_WEB}
 元数据库    : MySQL ${HIVE_META_DB}
 连接命令    : beeline -u "jdbc:hive2://${HOSTNAME_MASTER}:${PORT_HIVESERVER2}" -n ${CLUSTER_USER}
 下一步      : bash 05_install_zookeeper_kafka.sh
============================================================
EOF
