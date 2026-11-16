#!/usr/bin/env bash
# =============================================================================
# 05_install_zookeeper_kafka.sh —— 安装与配置 ZooKeeper 3.8.4 + Kafka 3.6.1
# （对应《项目操作流程》步骤 6 前半）
# 功能：ZooKeeper 单节点(可扩三节点) → Kafka 单 Broker(可扩) → 启动并验证
# 运行：以 root 执行   bash 05_install_zookeeper_kafka.sh
# 前置：已执行 01、02
# =============================================================================
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"

# =============================================================================
# 第一部分：ZooKeeper
# =============================================================================
log_info "===== 1. 安装 ZooKeeper ${ZOOKEEPER_VERSION} ====="
if [ -x "${ZOOKEEPER_HOME}/bin/zkServer.sh" ]; then
  log_info "ZooKeeper 已安装，跳过解压"
else
  fetch_pkg "$URL_ZOOKEEPER" "${PKG_DIR}/${ZOOKEEPER_TARBALL}"
  install_tarball "${PKG_DIR}/${ZOOKEEPER_TARBALL}" "$INSTALL_ROOT"
  # 官方包名 apache-zookeeper-3.8.4-bin，软链为 zookeeper-3.8.4
  if [ ! -d "${ZOOKEEPER_HOME}" ] && [ -d "${INSTALL_ROOT}/apache-zookeeper-${ZOOKEEPER_VERSION}-bin" ]; then
    ln -sfn "${INSTALL_ROOT}/apache-zookeeper-${ZOOKEEPER_VERSION}-bin" "${ZOOKEEPER_HOME}"
  fi
fi

log_info "===== 2. 配置 zoo.cfg ====="
mkdir -p "${DATA_ROOT}/zookeeper"
cat > "${ZOOKEEPER_HOME}/conf/zoo.cfg" <<EOF
# ===== 由 05_install_zookeeper_kafka.sh 生成 =====
tickTime=2000
initLimit=10
syncLimit=5
# 数据快照目录
dataDir=${DATA_ROOT}/zookeeper
# 事务日志目录
dataLogDir=${DATA_ROOT}/zookeeper/log
# 客户端连接端口
clientPort=${PORT_ZK_CLIENT}
maxClientCnxns=60
# 关闭 AdminServer（3.5+ 默认开启 8080，会与 Spark Master 冲突）
admin.enableServer=false

# ===== 集群节点（单节点只保留 server.1；三节点放开后两行） =====
server.1=${HOSTNAME_MASTER}:${PORT_ZK_FOLLOWER}:${PORT_ZK_ELECTION}
# server.2=${HOSTNAME_SLAVE1}:${PORT_ZK_FOLLOWER}:${PORT_ZK_ELECTION}
# server.3=${HOSTNAME_SLAVE2}:${PORT_ZK_FOLLOWER}:${PORT_ZK_ELECTION}
EOF

# myid 文件（与 server.N 的 N 对应）
echo "1" > "${DATA_ROOT}/zookeeper/myid"
mkdir -p "${DATA_ROOT}/zookeeper/log"
chown -R "${CLUSTER_USER}:${CLUSTER_GROUP}" "${ZOOKEEPER_HOME}" "${DATA_ROOT}/zookeeper"

# 环境变量（zkEnv.sh 会自动读 ZOOBINDIR；如需指定 JAVA_HOME 可写入）
if ! grep -q "JAVA_HOME" "${ZOOKEEPER_HOME}/conf/zookeeper-env.sh" 2>/dev/null; then
  echo "export JAVA_HOME=${JAVA_HOME}" > "${ZOOKEEPER_HOME}/conf/zookeeper-env.sh"
fi

log_info "===== 3. 启动 ZooKeeper ====="
su - "$CLUSTER_USER" -c "source /etc/profile.d/bigdata_env.sh; zkServer.sh start"
sleep 3
su - "$CLUSTER_USER" -c "source /etc/profile.d/bigdata_env.sh; zkServer.sh status" || log_warn "ZooKeeper 状态查询失败"

# =============================================================================
# 第二部分：Kafka
# =============================================================================
log_info "===== 4. 安装 Kafka ${KAFKA_VERSION}（scala ${KAFKA_SCALA_VERSION}） ====="
if [ -x "${KAFKA_HOME}/bin/kafka-server-start.sh" ]; then
  log_info "Kafka 已安装，跳过解压"
else
  fetch_pkg "$URL_KAFKA" "${PKG_DIR}/${KAFKA_TARBALL}"
  install_tarball "${PKG_DIR}/${KAFKA_TARBALL}" "$INSTALL_ROOT"
fi
mkdir -p "${DATA_ROOT}/kafka-logs"

log_info "===== 5. 配置 server.properties ====="
cat > "${KAFKA_HOME}/config/server.properties" <<EOF
# ===== 由 05_install_zookeeper_kafka.sh 生成 =====
broker.id=0
# 监听地址（内网）：0.0.0.0 使 Windows 端也可访问
listeners=PLAINTEXT://0.0.0.0:${PORT_KAFKA}
# 对外通告地址（关键：Windows PySpark/Flask 生产者需按此地址连接）
advertised.listeners=PLAINTEXT://${HOSTNAME_MASTER}:${PORT_KAFKA}
num.network.threads=3
num.io.threads=8
socket.send.buffer.bytes=102400
socket.receive.buffer.bytes=102400
socket.request.max.bytes=104857600
# 日志数据目录
log.dirs=${DATA_ROOT}/kafka-logs
num.partitions=3
num.recovery.threads.per.data.dir=1
# 单机开发：副本因子设为 1（三节点可改 2/3）
offsets.topic.replication.factor=1
transaction.state.log.replication.factor=1
transaction.state.log.min.isr=1
log.retention.hours=168
log.segment.bytes=1073741824
log.retention.check.interval.ms=300000
# 连接 ZooKeeper（Kafka 3.6 仍支持 ZK 模式）
zookeeper.connect=${HOSTNAME_MASTER}:${PORT_ZK_CLIENT}
zookeeper.connection.timeout.ms=18000
group.initial.rebalance.delay.ms=0
# 关闭自动创建主题（按需；教学环境建议保留 false 并显式建topic）
auto.create.topics.enable=true
EOF

# Kafka 运行使用 JDK（Kafka 3.6 支持 Java 8+）
cat > "${KAFKA_HOME}/config/kafka-env.sh" <<EOF
export JAVA_HOME=${JAVA_HOME}
EOF
chown -R "${CLUSTER_USER}:${CLUSTER_GROUP}" "${KAFKA_HOME}" "${DATA_ROOT}/kafka-logs"

log_info "===== 6. 启动 Kafka ====="
su - "$CLUSTER_USER" -c "source /etc/profile.d/bigdata_env.sh; \
  nohup kafka-server-start.sh -daemon ${KAFKA_HOME}/config/server.properties >/tmp/kafka-start.log 2>&1 &"
sleep 8

log_info "===== 7. 创建实时主题 ====="
for t in "${KAFKA_TOPIC_REGISTRATION}" "${KAFKA_TOPIC_VISIT}" "${KAFKA_TOPIC_PRESCRIPTION}"; do
  su - "$CLUSTER_USER" -c "source /etc/profile.d/bigdata_env.sh; \
    kafka-topics.sh --bootstrap-server ${KAFKA_BOOTSTRAP} --create --if-not-exists \
    --topic $t --partitions 3 --replication-factor 1" \
    && log_info "主题就绪: $t" || log_warn "主题创建失败: $t"
done

log_info "===== 8. 验证 Kafka 主题列表 ====="
su - "$CLUSTER_USER" -c "source /etc/profile.d/bigdata_env.sh; \
  kafka-topics.sh --bootstrap-server ${KAFKA_BOOTSTRAP} --list" || log_warn "Kafka 未就绪，请查看 /tmp/kafka-start.log"

cat <<EOF

============================================================
 05_install_zookeeper_kafka.sh 执行完成
 ZooKeeper : ${HOSTNAME_MASTER}:${PORT_ZK_CLIENT}（dataDir=${DATA_ROOT}/zookeeper）
 Kafka     : ${KAFKA_BOOTSTRAP}（broker.id=0，log.dirs=${DATA_ROOT}/kafka-logs）
 主题       : ${KAFKA_TOPIC_REGISTRATION} / ${KAFKA_TOPIC_VISIT} / ${KAFKA_TOPIC_PRESCRIPTION}
 下一步     : bash 06_install_spark.sh
============================================================

【三节点扩展提示】
 1) zoo.cfg 放开 server.2/server.3，各节点 ${DATA_ROOT}/zookeeper/myid 分别写 1/2/3；
 2) Kafka 每台 broker.id 唯一（0/1/2），log.dirs 各节点独立目录；
 3) zookeeper.connect 写全部ZK节点：hadoop01:2181,hadoop02:2181,hadoop03:2181。
EOF
