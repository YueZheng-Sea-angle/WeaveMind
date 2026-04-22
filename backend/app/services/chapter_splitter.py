"""
章节切割服务

切割策略（按优先级依次尝试，首个检测到 ≥2 章的策略生效）：
  1. Markdown H1 标题          # 标题
  2. Markdown H1-H2 标题       # / ## 标题
  3. 中文章节标题              第X章/节/回/篇/卷/部（汉字数字或阿拉伯数字）
  4. 英文章节标题              Chapter/Part/Section + 数字/罗马字
  5. 纯数字编号                1.  2.  3.
  6. 汉字序号                  一、二、三、
  7. LLM fallback              让模型识别分隔模式并返回正则
  8. 全文单章兜底
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Regex 策略定义（(name, pattern) 顺序即优先级）─────────────────────────────
_STRATEGIES: list[tuple[str, re.Pattern]] = [
    (
        "markdown_h1",
        re.compile(r"^# .+$", re.MULTILINE),
    ),
    (
        "markdown_h1h2",
        re.compile(r"^#{1,2} .+$", re.MULTILINE),
    ),
    (
        "zh_chapter",
        re.compile(
            r"^第[零一二三四五六七八九十百千万〇0-9]+[章节回篇卷部][^\n]*$",
            re.MULTILINE,
        ),
    ),
    (
        "en_chapter",
        re.compile(
            r"^(Chapter|CHAPTER|Part|PART|Section|SECTION)\s+[IVXivx\d]+[^\n]*$",
            re.MULTILINE,
        ),
    ),
    (
        "numeric_dot",
        re.compile(r"^\d{1,3}\.\s*\S[^\n]*$", re.MULTILINE),
    ),
    (
        "zh_ordinal",
        re.compile(
            r"^[一二三四五六七八九十百千]+[、]\s*\S[^\n]*$",
            re.MULTILINE,
        ),
    ),
]


# ── 核心拆分逻辑 ──────────────────────────────────────────────────────────────

def _split_by_pattern(text: str, pattern: re.Pattern) -> list[dict]:
    """
    按给定 pattern 匹配到的所有标题行将文本切分为章节。
    返回 {"title": str, "text": str} 列表；匹配数 < 2 时返回空列表。
    """
    matches = list(pattern.finditer(text))
    if len(matches) < 2:
        return []

    chapters: list[dict] = []
    for i, match in enumerate(matches):
        title = match.group(0).strip()
        content_start = match.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[content_start:content_end].strip()
        chapters.append(
            {
                "title": title,
                "text": body if body else title,
            }
        )
    return chapters


def _regex_split(text: str) -> Optional[list[dict]]:
    """尝试所有正则策略，返回首个产生 ≥2 章的结果；全部失败返回 None。"""
    for name, pattern in _STRATEGIES:
        result = _split_by_pattern(text, pattern)
        if len(result) >= 2:
            logger.info("章节切割策略 '%s' 成功，检测到 %d 章", name, len(result))
            return result
    return None


async def _llm_split(text: str) -> Optional[list[dict]]:
    """
    LLM fallback：发送文本前 4000 字给模型，让其识别章节标题的正则模式，
    再用该模式对全文进行切割。
    需要 OPENAI_API_KEY 已配置；失败时返回 None 而非抛出异常。
    """
    from app.core.config import settings

    if not settings.OPENAI_API_KEY:
        logger.warning("LLM fallback 不可用：未配置 OPENAI_API_KEY")
        return None

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
        )

        sample = text[:4000]
        prompt = (
            "你是一个小说章节识别助手。请分析以下文本片段，识别章节标题的正则表达式模式。\n\n"
            f"文本样本（前4000字符）：\n```\n{sample}\n```\n\n"
            "请：\n"
            "1. 识别章节标题的格式（如「第X章」「Chapter X」等）\n"
            "2. 返回一个 Python 正则表达式字符串（用于 re.compile + re.MULTILINE），"
            "能匹配所有章节标题行\n"
            "3. 只返回正则表达式字符串本身，不要任何解释，不要代码块标记\n\n"
            "如果无法识别章节分隔结构，只返回：NONE"
        )

        response = await client.chat.completions.create(
            model=settings.DEFAULT_PROCESSING_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0,
        )

        pattern_str = response.choices[0].message.content.strip()

        if not pattern_str or pattern_str.upper() == "NONE":
            logger.info("LLM 判断该文本无章节分隔结构")
            return None

        try:
            pattern = re.compile(pattern_str, re.MULTILINE)
        except re.error as exc:
            logger.warning("LLM 返回的正则无效 '%s': %s", pattern_str, exc)
            return None

        result = _split_by_pattern(text, pattern)
        if len(result) >= 2:
            logger.info(
                "LLM fallback 成功，检测到 %d 章（模式：%s）",
                len(result),
                pattern_str,
            )
            return result

        logger.warning("LLM 生成的正则未匹配到足够章节（< 2），模式：%s", pattern_str)
        return None

    except Exception as exc:
        logger.error("LLM fallback 异常：%s", exc, exc_info=True)
        return None


# ── 公开接口 ──────────────────────────────────────────────────────────────────

async def split_chapters(text: str) -> list[dict]:
    """
    将小说全文切割为章节列表。

    每项格式：
        {
            "title": str,   # 章节标题（原始标题行）
            "text":  str,   # 章节正文（不含标题行）
        }

    切割优先级：
        1. 正则策略（6 种常见格式，见模块顶部注释）
        2. LLM fallback（需配置 OPENAI_API_KEY）
        3. 全文作为单一章节（兜底）
    """
    text = text.strip()
    if not text:
        return []

    # 1. 正则策略
    result = _regex_split(text)
    if result:
        return result

    # 2. LLM fallback
    logger.info("所有正则策略均未命中，尝试 LLM fallback")
    result = await _llm_split(text)
    if result:
        return result

    # 3. 全文单章兜底
    logger.warning("章节切割失败，全文作为单章处理（长度：%d 字符）", len(text))
    return [{"title": "全文", "text": text}]
