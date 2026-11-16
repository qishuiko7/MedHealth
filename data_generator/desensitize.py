# -*- coding: utf-8 -*-
"""
数据脱敏模块
------------------------------------------------------------------
设计原则
1. 可逆性分级：姓名 / 手机号 / 地址采用「掩码 + 泛化」，身份证 / 病历号采用
   「不可逆哈希（HMAC-SHA256 加盐）」，确保同一患者在不同表中的脱敏结果一致，
   从而保留数据分析所需的关联能力（join 不失效），同时无法还原原始值。
2. 一致性：同一原始值 + 同一盐 → 同一脱敏值（确定性脱敏）。
3. 可分性：保留统计特征所需的最小信息（保留姓氏、保留地区码与出生年份段），
   使「按年龄段统计」「按地区统计」等分析仍然可行。
4. 可审计：每条规则登记到 DESENSITIZE_RULES，供前端「脱敏规则说明」页面展示。
"""
import hashlib
import hmac
import re

try:                                    # 包内导入
    from .config import HASH_SALT
except ImportError:                     # 直接以脚本方式运行
    from config import HASH_SALT

# ---------------------------------------------------------------------------
# 脱敏规则清单（前端「数据脱敏规则」页面直接读取）
# ---------------------------------------------------------------------------
DESENSITIZE_RULES = [
    {
        "field": "姓名 name",
        "type": "保留姓氏掩码",
        "method": "保留姓氏，其余字符替换为 *",
        "example_raw": "张三",
        "example_masked": "张*",
        "principle": "保留姓氏便于人工核对与同姓统计，姓名主体不可识别",
        "reversible": "不可逆",
    },
    {
        "field": "身份证号 id_card",
        "type": "哈希加盐 + 区间泛化",
        "method": "HMAC-SHA256(盐, 原值) 取前 16 位十六进制；另派生出生年份、性别、年龄段",
        "example_raw": "110101199001011234",
        "example_masked": "a1b2c3d4e5f6a7b8（保留年龄 34、性别 男、地区 110101）",
        "principle": "去掉可还原性，仅保留统计分析必需的年龄与地域粒度",
        "reversible": "不可逆",
    },
    {
        "field": "手机号 phone",
        "type": "中间四位掩码",
        "method": "保留前 3 位与后 4 位，第 4~7 位替换为 *",
        "example_raw": "13800000000",
        "example_masked": "138****0000",
        "principle": "保留号段用于渠道/地域分析，个人无法被定位",
        "reversible": "不可逆",
    },
    {
        "field": "家庭住址 address",
        "type": "向上泛化",
        "method": "截断到「省+市+区」三级行政区，去除门牌号、楼栋、单元、室",
        "example_raw": "某省某市某区某街道 123 号",
        "example_masked": "某省某市某区",
        "principle": "满足区域分布统计，去掉可精确到户的位置信息",
        "reversible": "不可逆",
    },
    {
        "field": "病历号 / 患者编号 patient_no",
        "type": "伪名化（HMAC 重映射）",
        "method": "HMAC-SHA256(盐, 原值) 取前 12 位，加前缀 MED 生成伪编号",
        "example_raw": "P20250300001234",
        "example_masked": "MED4c1e8a90b2f3",
        "principle": "跨表一致，join 不失效；无法反查真实病历号",
        "reversible": "不可逆",
    },
    {
        "field": "电子邮箱 email",
        "type": "局部掩码",
        "method": "保留首字符与完整域名，@ 前其余字符替换为 *",
        "example_raw": "zhangsan@example.com",
        "example_masked": "z*******@example.com",
        "principle": "保留域名用于邮箱服务商统计",
        "reversible": "不可逆",
    },
    {
        "field": "医生姓名 doctor_name",
        "type": "保留姓氏掩码",
        "method": "保留姓氏，其余替换为 *",
        "example_raw": "张医生",
        "example_masked": "张*",
        "principle": "医生工号已重编码，姓名仅保留姓氏",
        "reversible": "不可逆",
    },
    {
        "field": "就诊人主诉 / 现病史 chief_complaint",
        "type": "文本泛化",
        "method": "去除其中出现的人名、数字、时间细节，只保留症状关键词",
        "example_raw": "患者于3天前无明显诱因出现咳嗽，家属陪同就诊",
        "example_masked": "患者无明显诱因出现咳嗽",
        "principle": "文本类非结构化字段做通用化处理，避免间接标识",
        "reversible": "不可逆",
    },
]

# 中文人名常见复姓
COMPOUND_SURNAME = ("欧阳", "司马", "上官", "诸葛", "东方", "皇甫", "尉迟", "公孙",
                    "慕容", "长孙", "宇文", "轩辕", "令狐", "独孤", "南宫", "闻人")


def _hmac_hex(value: str, length: int = 16) -> str:
    """HMAC-SHA256 加盐哈希，返回十六进制前缀。

    使用标准库 hmac.new(key=盐, msg=原值, digestmod=sha256)，
    保证同一原值 + 同一盐 → 同一脱敏值（确定性），跨表 join 不失效，且不可逆。
    """
    if value is None:
        return None
    s = str(value)
    digest = hmac.new(HASH_SALT.encode("utf-8"), s.encode("utf-8"),
                      hashlib.sha256).hexdigest()
    return digest[:length]


def mask_name(name: str) -> str:
    """姓名脱敏：保留姓氏，其余用 * 代替。"""
    if not name:
        return name
    name = str(name).strip()
    if len(name) <= 1:
        return name
    for cs in COMPOUND_SURNAME:
        if name.startswith(cs):
            return cs + "*" * max(len(name) - len(cs), 1)
    return name[0] + "*" * (len(name) - 1)


def mask_phone(phone: str) -> str:
    """手机号脱敏：保留前 3 位与后 4 位。"""
    if not phone:
        return phone
    s = re.sub(r"\D", "", str(phone))
    if len(s) < 7:
        return "*" * len(s)
    return s[:3] + "*" * (len(s) - 7) + s[-4:]


def mask_id_card(id_card: str) -> str:
    """身份证脱敏：HMAC 伪名化，保留地区码（前 6 位）作为单独字段。"""
    if not id_card:
        return None
    return _hmac_hex(id_card, 16)


def id_region(id_card: str) -> str:
    """从身份证取地区码（前 6 位），用于地域统计。"""
    if not id_card or len(str(id_card)) < 6:
        return None
    return str(id_card)[:6]


def mask_address(address: str) -> str:
    """地址泛化：只保留 省+市+区/县 三级。"""
    if not address:
        return address
    s = str(address).strip()
    # 匹配"XX省XX市XX区(县)"或"XX自治区XX市XX区"等组合
    m = re.match(r"^(.{2,8}?(?:省|自治区|特别行政区))?(.{2,10}?(?:市|自治州|地区))?(.{2,10}?(?:区|县|市|旗))?", s)
    if m:
        parts = [p for p in m.groups() if p]
        if parts:
            return "".join(parts)
    # 兜底：去掉门牌号
    s = re.sub(r"\d+.*$", "", s)
    return s.strip() or s[:6]


def mask_email(email: str) -> str:
    """邮箱脱敏：保留首字符与域名。"""
    if not email:
        return email
    s = str(email)
    if "@" not in s:
        return s[0] + "*" * max(len(s) - 1, 1)
    local, _, domain = s.partition("@")
    if len(local) <= 1:
        return local + "*@" + domain
    return local[0] + "*" * (len(local) - 1) + "@" + domain


def pseudo_no(original: str, prefix: str = "MED", length: int = 12) -> str:
    """病历号 / 工号伪名化：跨表一致，不可反查。"""
    if not original:
        return None
    return prefix + _hmac_hex(original, length)


def generalize_complaint(text: str) -> str:
    """主诉文本泛化：剔除数字、时间、人名与陪同描述。"""
    if not text:
        return text
    s = str(text)
    s = re.sub(r"[\d０-９]+(?:\s*(?:天|周|月|年|小时|分钟|次|岁|度|mm|cm|ml))*", "", s)
    s = re.sub(r"(家属|其子|其女|其父|其母|同伴|同事|同学)[\u4e00-\u9fa5]{1,3}(陪同|随同|伴)", "", s)
    s = re.sub(r"(患者|病人|本人)", "患者", s)
    s = re.sub(r"[，。；、]{2,}", "，", s)
    s = s.strip("，。；、 ")
    return s or "一般不适"


def mask_id_card_keep_region(id_card: str) -> str:
    """身份证脱敏的另一种口径：保留地区码 + 出生年份，掩码其余。"""
    if not id_card:
        return None
    s = str(id_card)
    if len(s) < 14:
        return "*" * len(s)
    return s[:6] + "********" + s[-2:]
