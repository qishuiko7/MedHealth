#!/usr/bin/env bash
# =============================================================================
# 03_install_hadoop.sh —— 安装与配置 Hadoop 3.3.6（对应《项目操作流程》步骤 5 前半）
# 功能：解压安装 → 配置 5 个核心文件 → 格式化 NameNode → 启动 HDFS/YARN
# 运行：以 root 执行   bash 03_install_hadoop.sh
# 前置：已执行 01、02
# 说明：默认单节点伪分布式（dfs.replication=1）；三节点扩展见 file 末尾注释
# =============================================================================
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"

HADOOP_CONF_DIR="${HADOOP_HOME}/etc/hadoop"

log_info "===== 1. 安装 Hadoop ${HADOOP_VERSION} ====="
if [ -x "${HADOOP_HOME}/bin/hdfs" ]; then
  log_info "Hadoop 已安装于 ${HADOOP_HOME}，跳过解压"
else
  fetch_pkg "$URL_HADOOP" "${PKG_DIR}/${HADOOP_TARBALL}"
  install_tarball "${PKG_DIR}/${HADOOP_TARBALL}" "$INSTALL_ROOT"
fi
chown -R "${CLUSTER_USER}:${CLUSTER_GROUP}" "$HADOOP_HOME"

log_info "===== 2. 配置 Hadoop 核心文件 ====="

# ---------- 2.1 hadoop-env.sh ----------
# 显式指定 JAVA_HOME，避免 Hadoop 找不到 Java
cat > "${HADOOP_CONF_DIR}/hadoop-env.sh" <<EOF
# ===== 由 03_install_hadoop.sh 生成 =====
export JAVA_HOME=${JAVA_HOME}
export HADOOP_HOME=${HADOOP_HOME}
export HADOOP_CONF_DIR=${HADOOP_HOME}/etc/hadoop
# 以 hadoop 用户运行，避免 root 启动告警
export HDFS_NAMENODE_USER=${CLUSTER_USER}
export HDFS_DATANODE_USER=${CLUSTER_USER}
export HDFS_SECONDARYNAMENODE_USER=${CLUSTER_USER}
export YARN_RESOURCEMANAGER_USER=${CLUSTER_USER}
export YARN_NODEMANAGER_USER=${CLUSTER_USER}
# JVM 参数（教学环境内存较小时避免 OOM）
export HDFS_NAMENODE_OPTS="-Dhadoop.security.logger=INFO,RFAS -Xmx1024m"
export HDFS_DATANODE_OPTS="-Dhadoop.security.logger=ERROR,RFAS -Xmx1024m"
EOF

# ---------- 2.2 core-site.xml ----------
cat > "${HADOOP_CONF_DIR}/core-site.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<?xml-stylesheet type="text/xsl" href="configuration.xsl"?>
<configuration>
    <!-- HDFS 默认文件系统地址（NameNode RPC 端口 8020） -->
    <property>
        <name>fs.defaultFS</name>
        <value>hdfs://${HOSTNAME_MASTER}:${PORT_NAMENODE_RPC}</value>
    </property>
    <!-- Hadoop 临时目录（HDFS/YARN 中间数据） -->
    <property>
        <name>hadoop.tmp.dir</name>
        <value>${DATA_ROOT}/hadoop/tmp</value>
    </property>
    <!-- 允许通过代理访问的用户（HiveServer2 / Spark 提交作业需要） -->
    <property>
        <name>hadoop.proxyuser.${CLUSTER_USER}.hosts</name>
        <value>*</value>
    </property>
    <property>
        <name>hadoop.proxyuser.${CLUSTER_USER}.groups</name>
        <value>*</value>
    </property>
    <!-- 关闭权限检查（教学环境简化；生产不建议） -->
    <property>
        <name>hadoop.http.staticuser.user</name>
        <value>${CLUSTER_USER}</value>
    </property>
</configuration>
EOF

# ---------- 2.3 hdfs-site.xml ----------
cat > "${HADOOP_CONF_DIR}/hdfs-site.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<?xml-stylesheet type="text/xsl" href="configuration.xsl"?>
<configuration>
    <!-- 单节点副本数=1；三节点集群改为 3 -->
    <property>
        <name>dfs.replication</name>
        <value>1</value>
    </property>
    <!-- NameNode 元数据目录 -->
    <property>
        <name>dfs.namenode.name.dir</name>
        <value>file://${DATA_ROOT}/hdfs/name</value>
    </property>
    <!-- DataNode 数据块目录 -->
    <property>
        <name>dfs.datanode.data.dir</name>
        <value>file://${DATA_ROOT}/hdfs/data</value>
    </property>
    <!-- SecondaryNameNode HTTP 端口 -->
    <property>
        <name>dfs.namenode.secondary.http-address</name>
        <value>${HOSTNAME_MASTER}:${PORT_SECONDARYNN_WEB}</value>
    </property>
    <!-- NameNode Web UI 端口（Hadoop 3.x 为 9870） -->
    <property>
        <name>dfs.namenode.http-address</name>
        <value>0.0.0.0:${PORT_NAMENODE_WEB}</value>
    </property>
    <!-- 关闭 HDFS 权限检查（教学环境；生产请开启） -->
    <property>
        <name>dfs.permissions.enabled</name>
        <value>false</value>
    </property>
    <!-- 关闭 DataNode 磁盘空间均衡检查，避免单机伪分布式误报 -->
    <property>
        <name>dfs.datanode.du.reserved</name>
        <value>104857600</value>
    </property>
</configuration>
EOF

# ---------- 2.4 mapred-site.xml ----------
cat > "${HADOOP_CONF_DIR}/mapred-site.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<?xml-stylesheet type="text/xsl" href="configuration.xsl"?>
<configuration>
    <!-- MapReduce 运行在 YARN 之上 -->
    <property>
        <name>mapreduce.framework.name</name>
        <value>yarn</value>
    </property>
    <!-- JobHistory Server 地址 -->
    <property>
        <name>mapreduce.jobhistory.address</name>
        <value>${HOSTNAME_MASTER}:10020</value>
    </property>
    <property>
        <name>mapreduce.jobhistory.webapp.address</name>
        <value>${HOSTNAME_MASTER}:${PORT_JOBHISTORY}</value>
    </property>
    <!-- YARN 容器内的 classpath（伪分布式必须） -->
    <property>
        <name>mapreduce.application.classpath</name>
        <value>\$HADOOP_MAPRED_HOME/share/hadoop/mapreduce/*:\$HADOOP_MAPRED_HOME/share/hadoop/mapreduce/lib/*</value>
    </property>
</configuration>
EOF

# ---------- 2.5 yarn-site.xml ----------
cat > "${HADOOP_CONF_DIR}/yarn-site.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<?xml-stylesheet type="text/xsl" href="configuration.xsl"?>
<configuration>
    <!-- ResourceManager 所在主机 -->
    <property>
        <name>yarn.resourcemanager.hostname</name>
        <value>${HOSTNAME_MASTER}</value>
    </property>
    <!-- NodeManager 的 Shuffle 服务（MapReduce 必需） -->
    <property>
        <name>yarn.nodemanager.aux-services</name>
        <value>mapreduce_shuffle</value>
    </property>
    <property>
        <name>yarn.nodemanager.aux-services.mapreduce_shuffle.class</name>
        <value>org.apache.hadoop.mapred.ShuffleHandler</value>
    </property>
    <!-- 允许从容器环境继承的变量（伪分布式关键） -->
    <property>
        <name>yarn.nodemanager.env-whitelist</name>
        <value>JAVA_HOME,HADOOP_COMMON_HOME,HADOOP_HDFS_HOME,HADOOP_CONF_DIR,CLASSPATH_PREPEND_DISTCACHE,HADOOP_YARN_HOME,HADOOP_MAPRED_HOME</value>
    </property>
    <!-- 关闭虚拟内存检查，避免容器因内存不足被 kill -->
    <property>
        <name>yarn.nodemanager.vmem-check-enabled</name>
        <value>false</value>
    </property>
    <!-- 允许物理内存超配，避免 Spark 提交即失败 -->
    <property>
        <name>yarn.nodemanager.pmem-check-enabled</name>
        <value>false</value>
    </property>
    <!-- 日志聚合 -->
    <property>
        <name>yarn.log-aggregation-enable</name>
        <value>true</value>
    </property>
    <property>
        <name>yarn.nodemanager.local-dirs</name>
        <value>${DATA_ROOT}/yarn/local</value>
    </property>
    <property>
        <name>yarn.nodemanager.log-dirs</name>
        <value>${DATA_ROOT}/yarn/log</value>
    </property>
    <!-- ResourceManager Web UI -->
    <property>
        <name>yarn.resourcemanager.webapp.address</name>
        <value>${HOSTNAME_MASTER}:${PORT_RM_WEB}</value>
    </property>
</configuration>
EOF

# ---------- 2.6 workers（Hadoop 3.x 用 workers，2.x 为 slaves） ----------
cp -f "${HADOOP_CONF_DIR}/workers" "${HADOOP_CONF_DIR}/slaves" 2>/dev/null || true
cat > "${HADOOP_CONF_DIR}/workers" <<EOF
${HOSTNAME_MASTER}
# 三节点扩展：追加下面两行
# ${HOSTNAME_SLAVE1}
# ${HOSTNAME_SLAVE2}
EOF
cp -f "${HADOOP_CONF_DIR}/workers" "${HADOOP_CONF_DIR}/slaves"

mkdir -p "${DATA_ROOT}/hadoop/tmp"
chown -R "${CLUSTER_USER}:${CLUSTER_GROUP}" "$HADOOP_HOME" "${DATA_ROOT}/hadoop"

log_info "===== 3. 格式化 HDFS（幂等：已格式化则跳过） ====="
if [ -f "${DATA_ROOT}/hdfs/name/current/VERSION" ]; then
  log_warn "NameNode 已格式化，跳过（如需重格式化请先停止集群并清空 ${DATA_ROOT}/hdfs/name）"
else
  su - "$CLUSTER_USER" -c "source /etc/profile.d/bigdata_env.sh; hdfs namenode -format -force -nonInteractive" \
    && log_info "HDFS 格式化成功" \
    || { log_error "HDFS 格式化失败，请检查 JAVA_HOME 与配置"; exit 1; }
fi

log_info "===== 4. 启动 HDFS 与 YARN ====="
su - "$CLUSTER_USER" -c "source /etc/profile.d/bigdata_env.sh; start-dfs.sh"
sleep 3
su - "$CLUSTER_USER" -c "source /etc/profile.d/bigdata_env.sh; start-yarn.sh"
sleep 3
# JobHistory Server（可选，用于查看历史作业）
su - "$CLUSTER_USER" -c "source /etc/profile.d/bigdata_env.sh; mapred --daemon start historyserver" || true

log_info "===== 5. 创建数仓所需 HDFS 目录 ====="
su - "$CLUSTER_USER" -c "source /etc/profile.d/bigdata_env.sh; \
  hdfs dfs -mkdir -p ${HDFS_ODS} ${HDFS_DWD} ${HDFS_DWS} ${HDFS_ADS}; \
  hdfs dfs -mkdir -p /user/${CLUSTER_USER}; \
  hdfs dfs -chmod -R 777 /origin_data /warehouse /user/${CLUSTER_USER}; \
  hdfs dfs -mkdir -p /tmp/hive; hdfs dfs -chmod -R 777 /tmp/hive" || log_warn "目录创建异常，请手动执行"

log_info "===== 6. 启动结果 ====="
su - "$CLUSTER_USER" -c "source /etc/profile.d/bigdata_env.sh; jps" || true

cat <<EOF

============================================================
 03_install_hadoop.sh 执行完成
 HDFS Web UI : http://${IP_MASTER}:${PORT_NAMENODE_WEB}
 YARN Web UI : http://${IP_MASTER}:${PORT_RM_WEB}
 JobHistory  : http://${IP_MASTER}:${PORT_JOBHISTORY}
 数仓目录    : ${HDFS_ODS} / ${HDFS_DWD} / ${HDFS_DWS} / ${HDFS_ADS}
 下一步      : bash 04_install_hive.sh
============================================================

【三节点扩展提示】
 1) 修改 env.sh 的 CLUSTER_NODES 与 /etc/hosts；
 2) hdfs-site.xml 中 dfs.replication 改为 3；
 3) workers 文件填入 hadoop02/hadoop03；
 4) 用 ssh-copy-id 分发公钥：for h in hadoop02 hadoop03; do ssh-copy-id \$h; done
 5) 每台节点重复执行本脚本（格式化仅在 hadoop01 执行一次）。
EOF
