#!/usr/bin/env bash
# =============================================================================
# env.sh —— 医疗健康数据平台与疾病统计分析 集群统一环境变量
# 《大数据平台架构与应用开发课程设计》
# -----------------------------------------------------------------------------
# 用法：在所有部署脚本开头执行  source "$(dirname "$0")/env.sh"
# 说明：本文件只定义变量，不做任何安装动作，可被 01~07 脚本反复 source。
#       默认按【单节点伪分布式】编写，扩展为 hadoop01/02/03 三节点见文末注释。
# =============================================================================

# -----------------------------------------------------------------------------
# 0. 安装介质与目录规划
# -----------------------------------------------------------------------------
# 统一安装根目录（所有组件解压到 $INSTALL_ROOT 下，再软链到 /opt/module）
export INSTALL_ROOT="${INSTALL_ROOT:-/opt/module}"
# 安装包 / 离线 tar.gz 存放目录（网络不通时手工拷贝 tar.gz 到此处）
export PKG_DIR="${PKG_DIR:-/opt/software}"
# 数据目录（HDFS、YARN、MySQL 等）
export DATA_ROOT="${DATA_ROOT:-/data}"
# 部署用户名与用户组（Hadoop 生态禁止用 root 启动守护进程）
export CLUSTER_USER="${CLUSTER_USER:-hadoop}"
export CLUSTER_GROUP="${CLUSTER_GROUP:-hadoop}"
export CLUSTER_USER_HOME="${CLUSTER_USER_HOME:-/home/hadoop}"

# -----------------------------------------------------------------------------
# 1. 软件版本号（集中管理，改这里即可整包升级）
# -----------------------------------------------------------------------------
export JDK_VERSION="1.8.0_381"
export HADOOP_VERSION="3.3.6"
export HIVE_VERSION="3.1.3"
export ZOOKEEPER_VERSION="3.8.4"
export KAFKA_VERSION="3.6.1"
export KAFKA_SCALA_VERSION="2.12"
export SPARK_VERSION="3.5.1"
export SPARK_HADOOP_TAG="hadoop3"
export MYSQL_CONNECTOR_VERSION="8.0.33"
export ZK_VERSION="${ZOOKEEPER_VERSION}"

# -----------------------------------------------------------------------------
# 2. 各组件安装后路径（供 PATH / _HOME 使用）
# -----------------------------------------------------------------------------
export JAVA_HOME="${INSTALL_ROOT}/jdk${JDK_VERSION}"
export HADOOP_HOME="${INSTALL_ROOT}/hadoop-${HADOOP_VERSION}"
export HIVE_HOME="${INSTALL_ROOT}/hive-${HIVE_VERSION}"
export ZOOKEEPER_HOME="${INSTALL_ROOT}/zookeeper-${ZOOKEEPER_VERSION}"
export KAFKA_HOME="${INSTALL_ROOT}/kafka_${KAFKA_SCALA_VERSION}-${KAFKA_VERSION}"
export SPARK_HOME="${INSTALL_ROOT}/spark-${SPARK_VERSION}-bin-${SPARK_HADOOP_TAG}"
export HCAT_HOME="${HIVE_HOME}/hcatalog"

# -----------------------------------------------------------------------------
# 3. 集群主机名与 IP（单节点默认 hadoop01；三节点扩展见文末）
# -----------------------------------------------------------------------------
export HOSTNAME_MASTER="${HOSTNAME_MASTER:-hadoop01}"
export HOSTNAME_SLAVE1="${HOSTNAME_SLAVE1:-hadoop02}"
export HOSTNAME_SLAVE2="${HOSTNAME_SLAVE2:-hadoop03}"
export IP_MASTER="${IP_MASTER:-192.168.10.101}"
export IP_SLAVE1="${IP_SLAVE1:-192.168.10.102}"
export IP_SLAVE2="${IP_SLAVE2:-192.168.10.103}"
# 集群节点列表（单节点填 hadoop01 即可；三节点追加 hadoop02 hadoop03）
export CLUSTER_NODES="${CLUSTER_NODES:-hadoop01}"
# 集群名称（HDFS/YARN 逻辑名，默认 mycluster）
export CLUSTER_NAME="${CLUSTER_NAME:-mycluster}"
# Hadoop 服务的当前主机名（脚本内默认取本机 hostname）
export MY_HOSTNAME="$(hostname 2>/dev/null || echo hadoop01)"

# -----------------------------------------------------------------------------
# 4. 端口分配（与《集群部署文档》端口表保持一致）
# -----------------------------------------------------------------------------
# HDFS
export PORT_NAMENODE_RPC="8020"
export PORT_NAMENODE_WEB="9870"
export PORT_SECONDARYNN_WEB="9868"
export PORT_DATANODE="9866"
export PORT_JOURNALNODE="8485"        # 三节点 HA 时使用（单节点不使用）
export PORT_JOBHISTORY="19888"
# YARN
export PORT_RM_WEB="8088"
export PORT_RM_RPC="8032"
export PORT_NODEMANAGER_WEB="8042"
# Hive
export PORT_HIVE_METASTORE="9083"
export PORT_HIVESERVER2="10000"
export PORT_HIVESERVER2_WEB="10002"
# MySQL
export PORT_MYSQL="3306"
# ZooKeeper / Kafka
export PORT_ZK_CLIENT="2181"
export PORT_ZK_FOLLOWER="2888"
export PORT_ZK_ELECTION="3888"
export PORT_KAFKA="9092"
# Spark
export PORT_SPARK_MASTER="7077"
export PORT_SPARK_MASTER_WEB="8080"
export PORT_SPARK_WORKER_WEB="8081"
export PORT_SPARK_HISTORY="18080"
# 应用层
export PORT_FLASK="5000"

# -----------------------------------------------------------------------------
# 5. 数据库（Hive 元数据库 & 业务库）
# -----------------------------------------------------------------------------
export HIVE_META_DB="hive_meta"                 # Hive Metastore 元数据 schema
export HIVE_META_USER="hive"                    # Hive 元数据库账号
export HIVE_META_PWD="${HIVE_META_PWD:-change-me-hive}"   # 建议部署前用环境变量覆盖
export MYSQL_ROOT_PWD="${MYSQL_ROOT_PWD:-change-me-root}"
export BIZ_DB="med_health"                      # 业务库（与主工程 config.py 一致）
export BIZ_USER="med"
export BIZ_PWD="${BIZ_PWD:-change-me-biz}"

# MySQL JDBC 连接串（Hive 元数据库）
export MYSQL_JDBC_URL="jdbc:mysql://${HOSTNAME_MASTER}:${PORT_MYSQL}/${HIVE_META_DB}?useSSL=false&useUnicode=true&characterEncoding=UTF-8&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true"

# -----------------------------------------------------------------------------
# 6. Kafka / 数仓相关
# -----------------------------------------------------------------------------
export KAFKA_BOOTSTRAP="${HOSTNAME_MASTER}:${PORT_KAFKA}"
# 实时主题（与主工程 code/data_generator/config.py 保持一致）
export KAFKA_TOPIC_REGISTRATION="med_registration"
export KAFKA_TOPIC_VISIT="med_visit"
export KAFKA_TOPIC_PRESCRIPTION="med_prescription"
# HDFS 数仓根路径
export HDFS_WAREHOUSE="/user/hive/warehouse"
export HDFS_ODS="/origin_data/med_health/ods"
export HDFS_DWD="/warehouse/med_health/dwd"
export HDFS_DWS="/warehouse/med_health/dws"
export HDFS_ADS="/warehouse/med_health/ads"

# -----------------------------------------------------------------------------
# 7. 下载地址（官方稳定源；网络不通时改用 PKG_DIR 下同名 tar.gz）
# -----------------------------------------------------------------------------
export JDK_TARBALL="jdk-8u381-linux-x64.tar.gz"
export HADOOP_TARBALL="hadoop-${HADOOP_VERSION}.tar.gz"
export HIVE_TARBALL="apache-hive-${HIVE_VERSION}-bin.tar.gz"
export ZOOKEEPER_TARBALL="apache-zookeeper-${ZOOKEEPER_VERSION}-bin.tar.gz"
export KAFKA_TARBALL="kafka_${KAFKA_SCALA_VERSION}-${KAFKA_VERSION}.tgz"
export SPARK_TARBALL="spark-${SPARK_VERSION}-bin-${SPARK_HADOOP_TAG}.tgz"
export MYSQL_CONNECTOR_TARBALL="mysql-connector-j-${MYSQL_CONNECTOR_VERSION}.tar.gz"

# 镜像地址（如访问缓慢可换成国内镜像）
export URL_HADOOP="https://archive.apache.org/dist/hadoop/common/hadoop-${HADOOP_VERSION}/${HADOOP_TARBALL}"
export URL_HIVE="https://archive.apache.org/dist/hive/hive-${HIVE_VERSION}/${HIVE_TARBALL}"
export URL_ZOOKEEPER="https://archive.apache.org/dist/zookeeper/zookeeper-${ZOOKEEPER_VERSION}/${ZOOKEEPER_TARBALL}"
export URL_KAFKA="https://archive.apache.org/dist/kafka/${KAFKA_VERSION}/${KAFKA_TARBALL}"
export URL_SPARK="https://archive.apache.org/dist/spark/spark-${SPARK_VERSION}/${SPARK_TARBALL}"
export URL_MYSQL_CONNECTOR="https://repo1.maven.org/maven2/com/mysql/mysql-connector-j/${MYSQL_CONNECTOR_VERSION}/${MYSQL_CONNECTOR_TARBALL}"
# JDK 需登录 Oracle 账号，建议离线准备（放入 $PKG_DIR）
export URL_JDK="https://download.oracle.com/otn-pub/java/jdk/8u381-b09/8c876547113c4e4aab3c868e9e0ec572/jdk-8u381-linux-x64.tar.gz"

# -----------------------------------------------------------------------------
# 8. PATH 与运行时环境
# -----------------------------------------------------------------------------
export PATH="${JAVA_HOME}/bin:${HADOOP_HOME}/bin:${HADOOP_HOME}/sbin:${HIVE_HOME}/bin:${ZOOKEEPER_HOME}/bin:${KAFKA_HOME}/bin:${SPARK_HOME}/bin:${SPARK_HOME}/sbin:${PATH}"

export HADOOP_CONF_DIR="${HADOOP_HOME}/etc/hadoop"
export YARN_CONF_DIR="${HADOOP_HOME}/etc/hadoop"
export HIVE_CONF_DIR="${HIVE_HOME}/conf"
export LD_LIBRARY_PATH="${HADOOP_HOME}/lib/native:${LD_LIBRARY_PATH}"
export HADOOP_CLASSPATH="$(hadoop classpath 2>/dev/null):${HIVE_HOME}/lib/*"
export SPARK_DIST_CLASSPATH="$(hadoop classpath 2>/dev/null)"

# -----------------------------------------------------------------------------
# 9. 通用工具函数（供其它脚本调用）
# -----------------------------------------------------------------------------
# 彩色日志
log_info()  { echo -e "\033[32m[INFO ] $(date '+%F %T') $*\033[0m"; }
log_warn()  { echo -e "\033[33m[WARN ] $(date '+%F %T') $*\033[0m"; }
log_error() { echo -e "\033[31m[ERROR] $(date '+%F %T') $*\033[0m"; }

# 断言命令存在
require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { log_error "缺少命令: $1，请先安装"; exit 1; }
}

# 幂等下载：优先使用本地 $PKG_DIR 下 tar 包，否则 wget 下载
# 用法：fetch_pkg "$URL" "$PKG_DIR/$TARBALL"
fetch_pkg() {
  local url="$1" dest="$2"
  mkdir -p "$(dirname "$dest")"
  if [ -s "$dest" ]; then
    log_info "已存在安装包，跳过下载: $dest"
    return 0
  fi
  log_info "下载: $url"
  if command -v wget >/dev/null 2>&1; then
    wget -c -O "$dest" "$url"
  elif command -v curl >/dev/null 2>&1; then
    curl -fL -C - -o "$dest" "$url"
  else
    log_error "系统无 wget/curl，请将 $dest 离线拷贝到目标机"
    return 1
  fi
}

# 幂等解压到 INSTALL_ROOT 并软链常用名字
# 用法：install_tarball "$PKG_DIR/xxx.tar.gz" "$INSTALL_ROOT"
install_tarball() {
  local tarball="$1" target_dir="$2" name
  mkdir -p "$target_dir"
  name="$(basename "$tarball")"
  log_info "解压 $name 到 $target_dir"
  tar -zxf "$tarball" -C "$target_dir"
}

# 以 hadoop 用户执行命令（脚本以 root 运行时使用）
as_cluster_user() {
  su - "${CLUSTER_USER}" -c "$*"
}

log_info "env.sh 已加载：HADOOP_HOME=${HADOOP_HOME}  SPARK_HOME=${SPARK_HOME}"

# =============================================================================
# 【扩展为 3 节点集群】说明
# -----------------------------------------------------------------------------
# 1) 修改上面 CLUSTER_NODES：
#      export CLUSTER_NODES="hadoop01 hadoop02 hadoop03"
#    并在 /etc/hosts 中补齐三台机器 IP 映射。
# 2) HDFS 三副本：hdfs-site.xml 中 dfs.replication=3，并去掉单节点 dfs.replication=1。
# 3) 在 hdfs-site.xml、yarn-site.xml 中把 slaves 文件替换为 workers，
#    workers 内容 = CLUSTER_NODES 列表。
# 4) 若需 NameNode HA：启用 dfs.nameservices=mycluster、
#    dfs.ha.namenodes.mycluster=nn1,nn2、JournalNode（8485）、ZKFC，并依赖 ZooKeeper 选主。
# 5) Spark 三节点：spark-env.sh 中 SPARK_MASTER_HOST=hadoop01，
#    workers 文件填入 hadoop02/hadoop03；Hive Metastore 仍部署在 hadoop01。
# =============================================================================
