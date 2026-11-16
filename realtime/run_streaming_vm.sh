#!/bin/bash
# VM 端启动 Spark Structured Streaming 实时作业
# 对应《项目操作流程》第 15 步：爬虫 → Kafka → Spark Streaming 实时处理
export JAVA_HOME=/opt/module/jdk1.8.0_381
export PATH=$JAVA_HOME/bin:$PATH
export SPARK_HOME=/opt/module/spark-3.5.1-bin-hadoop3
export HADOOP_CONF_DIR=/opt/module/hadoop-3.3.6/etc/hadoop

LOG=/data/realtime/streaming.log
CK=/tmp/ck/med_health_v2
: > $LOG

nohup $SPARK_HOME/bin/spark-submit \
  --master local[2] \
  --name MedHealthStreamingVisit \
  --jars /opt/software/mysql-connector-j-8.0.33.jar \
  /data/realtime/spark_streaming_job.py \
  --ck-root $CK --ck-clean \
  >> $LOG 2>&1 < /dev/null &

echo "started pid=$!"
