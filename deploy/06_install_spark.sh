#!/usr/bin/env bash
# =============================================================================
# 06_install_spark.sh —— 安装与配置 Spark 3.5.1（对应《项目操作流程》步骤 6 后半）
# 功能：安装 Spark → spark-env.sh / spark-defaults.conf → 与 Hive 集成
#       → 集成 Kafka 的 jar → 启动 Master/Worker/HistoryServer
# 运行：以 root 执行   bash 06_install_spark.sh
# 前置：已执行 01~05（Hadoop、Hive、ZK、Kafka 已就绪）
# =============================================================================
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"

log_info "===== 1. 安装 Spark ${SPARK_VERSION} (${SPARK_HADOOP_TAG}) ====="
if [ -x "${SPARK_HOME}/bin/spark-submit" ]; then
  log_info "Spark 已安装于 ${SPARK_HOME}，跳过解压"
else
  fetch_pkg "$URL_SPARK" "${PKG_DIR}/${SPARK_TARBALL}"
  install_tarball "${PKG_DIR}/${SPARK_TARBALL}" "$INSTALL_ROOT"
fi
chown -R "${CLUSTER_USER}:${CLUSTER_GROUP}" "$SPARK_HOME"

log_info "===== 2. 配置 spark-env.sh ====="
cat > "${SPARK_HOME}/conf/spark-env.sh" <<EOF
# ===== 由 06_install_spark.sh 生成 =====
export JAVA_HOME=${JAVA_HOME}
export HADOOP_HOME=${HADOOP_HOME}
export HADOOP_CONF_DIR=${HADOOP_HOME}/etc/hadoop
export SPARK_HOME=${SPARK_HOME}
# Hive 集成所需
export HIVE_HOME=${HIVE_HOME}
export SPARK_DIST_CLASSPATH=\$(hadoop classpath)

# ===== Master / Worker 配置 =====
export SPARK_MASTER_HOST=${HOSTNAME_MASTER}
export SPARK_MASTER_PORT=${PORT_SPARK_MASTER}
export SPARK_MASTER_WEBUI_PORT=${PORT_SPARK_MASTER_WEB}
# Worker 可用核心与内存（按虚拟机实际内存调整：4G->2core/2g，8G->4core/4g）
export SPARK_WORKER_CORES=2
export SPARK_WORKER_MEMORY=2g
export SPARK_WORKER_WEBUI_PORT=${PORT_SPARK_WORKER_WEB}
export SPARK_WORKER_INSTANCES=1

# ===== History Server =====
export SPARK_HISTORY_OPTS="-Dspark.history.ui.port=${PORT_SPARK_HISTORY} \
  -Dspark.history.fs.logDirectory=hdfs://${HOSTNAME_MASTER}:${PORT_NAMENODE_RPC}/spark-history \
  -Dspark.history.retainedApplications=50"

# ===== Master 高可用（三节点时启用，依赖 ZooKeeper） =====
# export SPARK_DAEMON_JAVA_OPTS="-Dspark.deploy.recoveryMode=ZOOKEEPER \
#   -Dspark.deploy.zookeeper.url=${HOSTNAME_MASTER}:${PORT_ZK_CLIENT},${HOSTNAME_SLAVE1}:${PORT_ZK_CLIENT},${HOSTNAME_SLAVE2}:${PORT_ZK_CLIENT} \
#   -Dspark.deploy.zookeeper.dir=/spark"
EOF

log_info "===== 3. 配置 spark-defaults.conf ====="
cat > "${SPARK_HOME}/conf/spark-defaults.conf" <<EOF
# ===== 由 06_install_spark.sh 生成 =====
spark.master                     spark://${HOSTNAME_MASTER}:${PORT_SPARK_MASTER}
spark.eventLog.enabled           true
spark.eventLog.dir               hdfs://${HOSTNAME_MASTER}:${PORT_NAMENODE_RPC}/spark-history
spark.history.fs.logDirectory    hdfs://${HOSTNAME_MASTER}:${PORT_NAMENODE_RPC}/spark-history
spark.history.ui.port            ${PORT_SPARK_HISTORY}

# ===== 与 Hive 集成（直接读取 Hive 元数据仓库） =====
spark.sql.catalogImplementation  hive
spark.sql.warehouse.dir          ${HDFS_WAREHOUSE}
spark.sql.shuffle.partitions     8
spark.serializer                 org.apache.spark.serializer.KryoSerializer
spark.sql.adaptive.enabled       true

# ===== 本地/集群切换（Windows 单机跑 local[*]，见《项目运行手册》） =====
# spark.master                   local[*]
EOF

# 与 Hive 集成：软链 hive-site.xml
ln -sfn "${HIVE_HOME}/conf/hive-site.xml" "${SPARK_HOME}/conf/hive-site.xml"
log_info "已软链 hive-site.xml 到 Spark conf（Spark SQL 访问 Hive 元数据）"

# ===== Hadoop / YARN 相关类库软链，避免 ClassNotFound =====
# Spark on YARN 需要控制 Hadoop 客户端 jar 版本，on-HDFS 直读无需额外处理。

# ===== workers 文件 =====
cat > "${SPARK_HOME}/conf/workers" <<EOF
${HOSTNAME_MASTER}
# 三节点扩展：追加下面两行
# ${HOSTNAME_SLAVE1}
# ${HOSTNAME_SLAVE2}
EOF

log_info "===== 4. 集成 Kafka 依赖 jar ====="
# Spark 3.5.1 与 Kafka 对接需要以下 jar（与 Scala 2.12 匹配）：
#   spark-sql-kafka-0-10_2.12 / spark-streaming-kafka-0-10_2.12
#   kafka-clients / commons-pool2 / spark-token-provider-kafka-0-10
# 方式A（推荐，联网）：提交作业时用 --packages 自动拉取，无需预置
#   --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1
# 方式B（离线本脚本）：把 jar 放进 $SPARK_HOME/jars
JARS_DIR="${SPARK_HOME}/jars"
MVN_BASE="https://repo1.maven.org/maven2"
declare -a KAFKA_JARS=(
  "org/apache/spark/spark-sql-kafka-0-10_2.12/3.5.1/spark-sql-kafka-0-10_2.12-3.5.1.jar"
  "org/apache/spark/spark-token-provider-kafka-0-10_2.12/3.5.1/spark-token-provider-kafka-0-10_2.12-3.5.1.jar"
  "org/apache/kafka/kafka-clients/3.4.1/kafka-clients-3.4.1.jar"
  "org/apache/commons/commons-pool2/2.11.1/commons-pool2-2.11.1.jar"
)
if [ "${SKIP_KAFKA_JARS:-0}" = "1" ]; then
  log_warn "已设置 SKIP_KAFKA_JARS=1，跳过 Kafka jar 下载（改用 --packages）"
else
  for rel in "${KAFKA_JARS[@]}"; do
    jar_name="$(basename "$rel")"
    if [ -s "${JARS_DIR}/${jar_name}" ]; then
      log_info "已存在: ${jar_name}"
    else
      fetch_pkg "${MVN_BASE}/${rel}" "${PKG_DIR}/jars/${jar_name}" && \
        cp -f "${PKG_DIR}/jars/${jar_name}" "${JARS_DIR}/" || \
        log_warn "下载失败: ${jar_name}，可改用 --packages 方式"
    fi
  done
fi
chown -R "${CLUSTER_USER}:${CLUSTER_GROUP}" "$SPARK_HOME"

log_info "===== 5. 创建 Spark 事件日志目录 ====="
su - "$CLUSTER_USER" -c "source /etc/profile.d/bigdata_env.sh; \
  hdfs dfs -mkdir -p /spark-history && hdfs dfs -chmod -R 777 /spark-history" || log_warn "HDFS 未就绪时请稍后手动创建"

log_info "===== 6. 启动 Spark 集群与 History Server ====="
su - "$CLUSTER_USER" -c "source /etc/profile.d/bigdata_env.sh; ${SPARK_HOME}/sbin/start-master.sh"
sleep 3
su - "$CLUSTER_USER" -c "source /etc/profile.d/bigdata_env.sh; ${SPARK_HOME}/sbin/start-worker.sh spark://${HOSTNAME_MASTER}:${PORT_SPARK_MASTER}"
sleep 3
su - "$CLUSTER_USER" -c "source /etc/profile.d/bigdata_env.sh; ${SPARK_HOME}/sbin/start-history-server.sh" || true
sleep 2

log_info "===== 7. 冒烟测试 ====="
su - "$CLUSTER_USER" -c "source /etc/profile.d/bigdata_env.sh; \
  spark-shell --master local[2] --conf spark.ui.enabled=false <<'SPARKSHELL'
val df = spark.range(1, 11).toDF(\"id\")
df.createOrReplaceTempView(\"t\")
val cnt = spark.sql(\"select count(*) as c from t\").collect()(0).getLong(0)
println(s\"SPARK_SMOKE_OK count=\$cnt\")
System.exit(0)
SPARKSHELL" || log_warn "spark-shell 冒烟失败，请检查 spark-env.sh 与 Java 版本"

cat <<EOF

============================================================
 06_install_spark.sh 执行完成
 Spark Master : spark://${HOSTNAME_MASTER}:${PORT_SPARK_MASTER}
 Master UI    : http://${IP_MASTER}:${PORT_SPARK_MASTER_WEB}
 Worker UI    : http://${IP_MASTER}:${PORT_SPARK_WORKER_WEB}
 History UI   : http://${IP_MASTER}:${PORT_SPARK_HISTORY}
 与 Hive 集成 : conf/hive-site.xml 软链（spark.sql.catalogImplementation=hive）
 下一步       : bash 07_verify_all.sh
============================================================

【Spark 提交作业示例】
 # 本地模式
 spark-submit --master local[*] /path/to/job.py
 # 集群模式（on Spark Standalone）
 spark-submit --master spark://hadoop01:7077 \
   --executor-memory 1g --total-executor-cores 2 /path/to/job.py
 # on YARN
 spark-submit --master yarn --deploy-mode client /path/to/job.py
 # 集成 Kafka（联网自动拉包）
 spark-submit --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1 job.py
EOF
