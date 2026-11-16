#!/usr/bin/env bash
# =============================================================================
# 01_system_prepare.sh —— 集群操作系统准备（对应《项目操作流程》步骤 3~4 前半）
# 功能：主机名 / hosts / 关闭防火墙与 SELinux / 时间同步 / 创建 hadoop 用户
#       / SSH 免密登录 / 目录规划
# 运行：以 root 执行   bash 01_system_prepare.sh
# 幂等：重复执行不会破坏已配置项
# =============================================================================
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/env.sh"

log_info "===== 步骤 1/7 配置主机名与 hosts ====="
CUR_HOST="$(hostname)"
if [ "$CUR_HOST" != "$HOSTNAME_MASTER" ] && [ "$CUR_HOST" != "$HOSTNAME_SLAVE1" ] && [ "$CUR_HOST" != "$HOSTNAME_SLAVE2" ]; then
  log_info "设置主机名为 $HOSTNAME_MASTER"
  hostnamectl set-hostname "$HOSTNAME_MASTER"
else
  log_info "主机名已为 $CUR_HOST，跳过"
fi

# hosts：写入集群映射（存在则不重复追加）
build_hosts_entry() {
  local ip="$1" name="$2"
  if ! grep -qE "^[0-9.]+[[:space:]]+${name}([[:space:]]|$)" /etc/hosts; then
    echo "${ip}    ${name}" >> /etc/hosts
    log_info "追加 hosts: ${ip} ${name}"
  fi
}
build_hosts_entry "$IP_MASTER" "$HOSTNAME_MASTER"
# 三节点扩展：取消下面两行注释即可
# build_hosts_entry "$IP_SLAVE1" "$HOSTNAME_SLAVE1"
# build_hosts_entry "$IP_SLAVE2" "$HOSTNAME_SLAVE2"

log_info "===== 步骤 2/7 关闭防火墙 ====="
# CentOS 7+
if systemctl list-unit-files 2>/dev/null | grep -q firewalld; then
  systemctl stop firewalld 2>/dev/null || true
  systemctl disable firewalld 2>/dev/null || true
  log_info "firewalld 已停止并禁用"
fi
# CentOS 6（旧版）兼容
if command -v service >/dev/null 2>&1 && [ -f /etc/init.d/iptables ]; then
  service iptables stop 2>/dev/null || true
  chkconfig iptables off 2>/dev/null || true
fi

log_info "===== 步骤 3/7 关闭 SELinux ====="
setenforce 0 2>/dev/null || true
if [ -f /etc/selinux/config ]; then
  sed -i 's/^SELINUX=.*/SELINUX=disabled/' /etc/selinux/config
  log_info "SELinux 已设为 disabled（重启后永久生效）"
fi

log_info "===== 步骤 4/7 配置时间同步（chrony） ====="
if ! command -v chronyd >/dev/null 2>&1; then
  yum install -y chrony || log_warn "chrony 安装失败，请检查 yum 源"
fi
# 单机：直接与本机硬件时钟同步；多节点：指向同一 NTP 服务器
cat > /etc/chrony.conf <<'EOF'
# 使用国内阿里云 NTP 服务器（集群各节点保持一致）
server ntp.aliyun.com iburst
server ntp1.aliyun.com iburst
driftfile /var/lib/chrony/drift
makestep 1.0 3
rtcsync
logdir /var/log/chrony
EOF
systemctl enable chronyd 2>/dev/null || true
systemctl restart chronyd 2>/dev/null || true
chronyc sources -v 2>/dev/null | head -n 8 || log_warn "chronyc 暂不可用（容器/无网络环境常见）"

log_info "===== 步骤 5/7 创建 hadoop 用户与用户组 ====="
if ! id "$CLUSTER_USER" >/dev/null 2>&1; then
  groupadd "$CLUSTER_GROUP" 2>/dev/null || true
  useradd -m -g "$CLUSTER_GROUP" "$CLUSTER_USER"
  log_info "用户 $CLUSTER_USER 已创建"
else
  log_info "用户 $CLUSTER_USER 已存在，跳过"
fi
# 赋予 sudo 权限（免密）
echo "${CLUSTER_USER} ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/${CLUSTER_USER}"
chmod 440 "/etc/sudoers.d/${CLUSTER_USER}"
# 设置初始密码（教学环境，建议首次登录后修改）
echo "${CLUSTER_USER}:${CLUSTER_USER}123" | chpasswd || true

log_info "===== 步骤 6/7 配置 SSH 免密登录 ====="
SSH_DIR="${CLUSTER_USER_HOME}/.ssh"
mkdir -p "$SSH_DIR"
# 以 hadoop 用户生成密钥
if [ ! -f "${SSH_DIR}/id_rsa" ]; then
  su - "$CLUSTER_USER" -c "ssh-keygen -t rsa -b 4096 -N '' -f ~/.ssh/id_rsa" >/dev/null
  log_info "已生成 SSH 密钥对"
else
  log_info "SSH 密钥已存在，跳过生成"
fi
AUTH_KEYS="${SSH_DIR}/authorized_keys"
touch "$AUTH_KEYS"
if ! grep -qF "$(cat "${SSH_DIR}/id_rsa.pub")" "$AUTH_KEYS" 2>/dev/null; then
  cat "${SSH_DIR}/id_rsa.pub" >> "$AUTH_KEYS"
  log_info "已把公钥写入 authorized_keys"
fi
chown -R "${CLUSTER_USER}:${CLUSTER_GROUP}" "$SSH_DIR"
chmod 700 "$SSH_DIR"
chmod 600 "$AUTH_KEYS"
# 追加本机映射，方便三节点批量分发公钥
if ! grep -q "${HOSTNAME_MASTER}" "${SSH_DIR}/config" 2>/dev/null; then
  cat >> "${SSH_DIR}/config" <<EOF
Host ${HOSTNAME_MASTER}
    HostName ${IP_MASTER}
    User ${CLUSTER_USER}
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
EOF
  chown "${CLUSTER_USER}:${CLUSTER_GROUP}" "${SSH_DIR}/config"
  chmod 600 "${SSH_DIR}/config"
fi
# 自测免密（首次会写入 known_hosts）
su - "$CLUSTER_USER" -c "ssh-keyscan -H ${MY_HOSTNAME} >> ~/.ssh/known_hosts 2>/dev/null" || true
su - "$CLUSTER_USER" -c "ssh -o StrictHostKeyChecking=no -o BatchMode=yes ${MY_HOSTNAME} 'echo SSH_OK'" \
  && log_info "SSH 免密登录自测通过" \
  || log_warn "SSH 免密自测未通过，请检查 sshd 配置（PermitRootLogin/密码认证）"

log_info "===== 步骤 7/7 目录规划 ====="
# 组件统一装到 INSTALL_ROOT/PKG_DIR，数据放 DATA_ROOT
mkdir -p "$INSTALL_ROOT" "$PKG_DIR"
# HDFS / YARN 数据目录
mkdir -p "${DATA_ROOT}/hdfs/name" "${DATA_ROOT}/hdfs/data" "${DATA_ROOT}/hdfs/edits"
mkdir -p "${DATA_ROOT}/yarn/local" "${DATA_ROOT}/yarn/log"
mkdir -p "${DATA_ROOT}/journalnode"       # 三节点 HA 用
mkdir -p "${DATA_ROOT}/zookeeper"
mkdir -p "${DATA_ROOT}/kafka-logs"
chown -R "${CLUSTER_USER}:${CLUSTER_GROUP}" "$INSTALL_ROOT" "$PKG_DIR" "$DATA_ROOT"
chmod -R 755 "$DATA_ROOT"
log_info "目录规划完成：INSTALL_ROOT=$INSTALL_ROOT  DATA_ROOT=$DATA_ROOT"

cat <<EOF

============================================================
 01_system_prepare.sh 执行完成
 主机名   : $(hostname)
 集群节点 : ${CLUSTER_NODES}
 防火墙   : 已关闭
 SELinux  : disabled
 时间同步 : chronyd（阿里云 NTP）
 用户     : ${CLUSTER_USER}（已配置免密）
 目录     : ${INSTALL_ROOT} / ${PKG_DIR} / ${DATA_ROOT}
 下一步   : bash 02_install_jdk_mysql.sh
============================================================
EOF
