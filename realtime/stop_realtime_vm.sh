#!/bin/bash
# 停止实时作业（Spark Streaming + 爬虫/producer）
for p in $(ps -ef | grep -E 'spark_streaming_job|MedHealthStreamingVisit|crawler\.py|producer\.py' | grep -v grep | awk '{print $2}'); do
  kill -9 $p 2>/dev/null && echo "killed $p"
done
sleep 2
ps -ef | grep -E 'spark_streaming_job|crawler\.py|producer\.py' | grep -v grep | wc -l
