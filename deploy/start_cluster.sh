#!/bin/bash
# =============================================================================
# start_cluster.sh —— 医疗健康数据平台 集群一键启动脚本（以 hadoop 用户执行）
# -----------------------------------------------------------------------------
# 用途：按正确顺序启动整套大数据集群：
#   HDFS → YARN → ZooKeeper → Kafka → Hive(Metastore/HiveServer2) → Spark
# 依赖：MySQL（Hive 元数据库）需先启动（已配置 systemd 开机自启）
# 用法：su - hadoop -c "/bin/bash /opt/module/start_cluster.sh"
#       （本脚本也会被 /etc/rc.d/rc.local 在开机时自动调用）
#
# 【重要】本脚本对「拷贝/克隆虚拟机后首次开机」做了专门加固：
#   拷贝出来的虚拟机里，上一次运行的 PID 文件（ZooKeeper 等）会被一起打包带走，
#   冷启动时 zkServer.sh 会误判「已在运行」而跳过启动，导致 Kafka/Hive/Spark 连锁失败。
#   因此下面每次启动前都会：① 清理陈旧 PID 文件；② 清理残留的临时数据；③ 反复确认端口就绪。
# =============================================================================
source /etc/profile.d/bigdata_env.sh

ZK_PID_FILE="$ZOOKEEPER_HOME/bin/zookeeper_server.pid"
ZK_DATA_PID="/data/zookeeper/zookeeper_server.pid"

wait_port() {   # wait_port <port> <秒数>
  local port=$1 limit=${2:-60} i=0
  while [ $i -lt "$limit" ]; do
    if (echo >/dev/tcp/127.0.0.1/$port) >/dev/null 2>&1; then return 0; fi
    sleep 2; i=$((i+2))
  done
  return 1
}

echo "[$(date '+%F %T')] === 开始启动大数据集群 ==="

# ---------- 0/6 清理陈旧状态（关键！解决拷贝虚拟机冷启动失败） ----------
echo "[$(date '+%T')] 0/6 清理上一次遗留的 PID 文件与残留进程 ..."
for pf in "$ZK_PID_FILE" "$ZK_DATA_PID" \
          "$KAFKA_HOME/kafka-logs/.lock" \
          "$HADOOP_HOME/logs/hadoop-hadoop-namenode.pid"; do
  [ -f "$pf" ] && rm -f "$pf" && echo "  已删除陈旧文件: $pf"
done
# 如果确实有残留的 ZK 进程，先礼貌停掉
pkill -f 'org.apache.zookeeper.server.quorum.QuorumPeerMain' >/dev/null 2>&1 && sleep 3

echo "[$(date '+%T')] 1/6 启动 HDFS（NameNode + DataNode + SecondaryNameNode）..."
$HADOOP_HOME/sbin/start-dfs.sh

echo "[$(date '+%T')] 2/6 启动 YARN（ResourceManager + NodeManager）..."
$HADOOP_HOME/sbin/start-yarn.sh

echo "[$(date '+%T')] 3/6 启动 ZooKeeper ..."
$ZOOKEEPER_HOME/bin/zkServer.sh start
# 确认 2181 真的在监听，否则重试一次（应对首次启动偶发失败）
if ! wait_port 2181 30; then
  echo "  [$(date '+%T')] ZooKeeper 首次未就绪，删除 PID 后重启一次 ..."
  rm -f "$ZK_PID_FILE" "$ZK_DATA_PID"
  $ZOOKEEPER_HOME/bin/zkServer.sh start
  wait_port 2181 30 || echo "  [警告] ZooKeeper 2181 端口仍未监听，请检查 /data/zookeeper"
fi
echo "  [$(date '+%T')] ZooKeeper 状态: $($ZOOKEEPER_HOME/bin/zkServer.sh status 2>&1 | tail -1)"

echo "[$(date '+%T')] 4/6 启动 Kafka ..."
# 清理残留的 broker 注册节点（防止上次异常关机导致 NodeExists 启动失败）
for i in $(seq 1 20); do
  $ZOOKEEPER_HOME/bin/zkCli.sh -server hadoop01:2181 rmr /brokers/ids >/dev/null 2>&1
  if $ZOOKEEPER_HOME/bin/zkCli.sh -server hadoop01:2181 ls /brokers/ids 2>/dev/null | grep -q "\[\]"; then
    echo "  [$(date '+%T')] ZooKeeper 就绪，broker 节点已清理"
    break
  fi
  sleep 3
done
nohup $KAFKA_HOME/bin/kafka-server-start.sh $KAFKA_HOME/config/server.properties >/tmp/kafka.log 2>&1 &
wait_port 9092 60 && echo "  [$(date '+%T')] Kafka 9092 就绪" || echo "  [警告] Kafka 9092 未就绪，见 /tmp/kafka.log"

echo "[$(date '+%T')] 5/6 启动 Hive Metastore + HiveServer2 ..."
nohup $HIVE_HOME/bin/hive --service metastore >/tmp/metastore.log 2>&1 &
wait_port 9083 60 && echo "  [$(date '+%T')] Metastore 9083 就绪" || echo "  [警告] Metastore 9083 未就绪，见 /tmp/metastore.log"
nohup $HIVE_HOME/bin/hive --service hiveserver2 >/tmp/hiveserver2.log 2>&1 &
wait_port 10000 90 && echo "  [$(date '+%T')] HiveServer2 10000 就绪" || echo "  [警告] HiveServer2 10000 未就绪，见 /tmp/hiveserver2.log"

echo "[$(date '+%T')] 6/6 启动 Spark Master + Worker ..."
$SPARK_HOME/sbin/start-master.sh
$SPARK_HOME/sbin/start-workers.sh
wait_port 8080 30 && echo "  [$(date '+%T')] Spark Master 8080 就绪" || echo "  [警告] Spark 8080 未就绪"

echo "[$(date '+%T')] === 集群启动完成，可执行 07_verify_all.sh 验证 ==="
