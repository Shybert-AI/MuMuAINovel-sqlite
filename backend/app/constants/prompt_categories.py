"""提示词工坊分类常量"""

PROMPT_CATEGORIES = {
    "general": "通用",
    "fantasy": "玄幻/仙侠",
    "martial": "武侠",
    "romance": "言情",
    "scifi": "科幻",
    "horror": "悬疑/惊悚",
    "history": "历史",
    "urban": "都市",
    "game": "游戏/电竞",
    "other": "其他",
}

CATEGORY_LIST = [
    {"id": k, "name": v} for k, v in PROMPT_CATEGORIES.items()
]

# 热门标签（建议）
POPULAR_TAGS = [
    "玄幻", "仙侠", "修真", "升级流", "热血",
    "武侠", "古风", "言情", "甜宠", "虐恋",
    "科幻", "星际", "末日", "悬疑", "推理",
    "惊悚", "历史", "架空", "都市", "职场",
    "游戏", "电竞", "二次元", "轻小说", "系统流",
    "无敌流", "慢热", "日常", "治愈"
]