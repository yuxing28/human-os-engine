"""
Human-OS Engine - L4 执行工具层：转换规则

基于 08-转换规则模块.md 的内容。
实现禁用词汇替换和内部术语过滤。

这是输出前的最后一步：将内部思考转换为对外表达。
"""

# 从统一常量导入，保持向后兼容
import re

from utils.constants import (
    PRIORITY_1_REPLACEMENTS,
    PRIORITY_2_REPLACEMENTS,
    PRIORITY_3_REPLACEMENTS,
    PRIORITY_4_REPLACEMENTS,
    INTERNAL_TERMS,
)


VISIBLE_PACKAGING_MARKERS = [
    "知识参考",
    "案例参考",
    "环境建议",
    "表达模式",
    "优先参考",
]


def replace_forbidden_words(text: str) -> str:
    """
    替换禁用词汇

    按优先级顺序处理：
    1. 第一优先级（必须为0次）
    2. 第二优先级
    3. 第三优先级
    4. 第四优先级（套路词）
    """
    result = text

    # 合并所有替换规则（第一优先级优先）
    all_replacements = {
        **PRIORITY_4_REPLACEMENTS,
        **PRIORITY_3_REPLACEMENTS,
        **PRIORITY_2_REPLACEMENTS,
        **PRIORITY_1_REPLACEMENTS,
    }

    for forbidden, alternatives in all_replacements.items():
        if forbidden in result:
            # 选择第一个替代词
            replacement = alternatives[0]
            result = result.replace(forbidden, replacement)

    return result


def check_internal_terms(text: str) -> list[str]:
    """
    检查内部术语泄露

    Returns:
        list[str]: 发现的内部术语列表
    """
    found = []
    for term in INTERNAL_TERMS:
        if term in text:
            found.append(term)
    return found


def remove_internal_terms(text: str) -> str:
    """
    移除内部术语（框架泄露防护）

    如果发现内部术语，用"我换个方式说"重新表述
    """
    found = check_internal_terms(text)

    if found:
        # 有内部术语泄露，需要重写
        # 简单处理：删除这些术语
        result = text
        for term in found:
            result = result.replace(term, "")
        return result.strip()

    return text


def strip_visible_packaging(text: str) -> str:
    """
    去掉会让用户看到“系统包装痕迹”的外露标签。

    目标：
    - 不展示“知识参考/案例参考/环境建议/表达模式”这类内部包装
    - 尽量保留真正的人话内容
    """
    result = text

    # 先删掉整段包装提示
    line_patterns = [
        r"(?im)^\s*知识参考.*$",
        r"(?im)^\s*案例参考.*$",
        r"(?im)^\s*\[环境建议\].*$",
        r"(?im)^\s*环境建议[:：].*$",
    ]
    for pattern in line_patterns:
        result = re.sub(pattern, "", result)

    # 再处理嵌在一句话里的标签
    inline_patterns = [
        r"表达模式[:：][^。！？\n]*[。！？]?",
        r"知识参考《[^》]+》[:：]?[^。！？\n]*[。！？]?",
        r"案例参考《[^》]+》[:：]?[^。！？\n]*[。！？]?",
        r"\[环境建议\][^\n]*",
    ]
    for pattern in inline_patterns:
        result = re.sub(pattern, "", result)

    # 清掉多余空行和空格
    result = re.sub(r"\n\s*\n+", "\n\n", result)
    result = re.sub(r"[ \t]{2,}", " ", result)
    return result.strip()


def convert_to_output(text: str) -> tuple[str, bool]:
    """
    将内部文本转换为对外输出

    Args:
        text: 内部生成的文本

    Returns:
        tuple[str, bool]: (转换后的文本, 是否通过检查)
    """
    # 1. 替换禁用词汇
    converted = replace_forbidden_words(text)

    # 1.5 去掉会直接暴露内部包装的标签
    converted = strip_visible_packaging(converted)

    # 2. 检查内部术语
    internal_found = check_internal_terms(converted)
    if internal_found:
        converted = remove_internal_terms(converted)

    # 3. 检查第一优先级词汇是否仍存在
    for forbidden in PRIORITY_1_REPLACEMENTS:
        if forbidden in converted:
            # 仍然存在，返回失败标记
            return converted, False

    return converted, True


# ===== 测试入口 =====

if __name__ == "__main__":
    test_cases = [
        "利用用户的贪婪心理，制造恐惧来推动决策",
        "这个钩子很有效，害怕失去的感觉会让人行动",
        "我理解你的感受，天呐这确实很难",
        "根据五层结构，第一层是共情",
    ]

    print("--- 禁用词汇替换测试 ---")
    for text in test_cases:
        converted, passed = convert_to_output(text)
        print(f"\n原文: {text}")
        print(f"转换: {converted}")
        print(f"通过: {passed}")
