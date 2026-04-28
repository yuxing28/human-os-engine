"""
Human-OS Engine 3.0 — 通用画像工厂 (Universal Persona Factory)

设计原则：
1. 配置驱动：每个场景独立配置，不硬编码
2. 场景无关：工厂不知道具体有哪些场景
3. 无限扩展：新增场景只需添加配置文件，无需改代码
4. 统一接口：所有场景使用相同的 generate() 方法

配置文件位置：config/personas/{scene_id}.json
"""

import os
import json
import random
from typing import List, Dict, Optional
from openai import OpenAI
from simulation.customer_agent import Persona
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))


# ===== 场景画像配置 =====
# 新增场景只需在此添加配置，或创建 config/personas/{scene_id}.json

SCENE_PERSONA_CONFIGS = {
    "sales": {
        "description": "B2B 软件采购客户",
        "industries": ["电商", "金融", "制造", "医疗", "教育", "SaaS", "物流"],
        "roles": ["CTO", "采购总监", "业务负责人", "老板", "运维主管"],
        "personalities": [
            "极度理性，只看数据，讨厌销售话术",
            "急躁，喜欢直奔主题，没耐心听废话",
            "多疑，总觉得销售在忽悠，需要第三方证明",
            "随和但没主见，容易被引导但也容易反悔",
            "傲慢，觉得自己很懂行，喜欢挑战销售",
            "保守，怕担责，倾向于选择大品牌或维持现状"
        ],
        "pains_by_industry": {
            "电商": ["大促期间系统崩溃", "并发能力不足", "数据不同步"],
            "金融": ["数据安全性", "合规审计", "高可用性"],
            "制造": ["设备联网率低", "数据孤岛", "运维成本高"],
            "医疗": ["系统稳定性", "数据隐私", "操作复杂"],
            "教育": ["高并发访问", "互动体验差", "数据丢失"],
            "SaaS": ["客户流失率高", "定制化难", "集成复杂"],
            "物流": ["实时追踪延迟", "路径规划差", "系统卡顿"]
        },
        "triggers_by_role": {
            "CTO": ["架构", "扩展性", "API", "SLA", "技术栈"],
            "采购": ["性价比", "售后", "账期", "折扣", "竞品对比"],
            "老板": ["ROI", "降本增效", "市场份额", "风险"],
            "运维": ["稳定性", "监控", "故障恢复", "自动化"]
        },
        "dealbreakers": ["画大饼", "催促下单", "没有案例", "数据造假", "态度傲慢", "不回复消息"],
        "product_template": "{industry}解决方案",
        "output_fields": {
            "name": "姓名（如'张总'、'李经理'）",
            "age": "年龄 (30-55)",
            "hidden_agenda": "隐藏意图（嘴上不说但心里在意的）",
            "budget_range": "预算范围（如'50-80 万'）",
            "trigger_words": "3-5 个能让他感兴趣的词",
            "dealbreakers": "2-3 个绝对不能忍受的行为",
            "current_stage": "当前局面阶段（如'试探观察'、'有限松动'、'扰动后重估'）",
            "current_pressure": "此刻最现实的外部压力（如预算、时间窗口、内部阻力）",
            "relationship_position": "他和对方现在的关系位置（如'礼貌疏离'、'谨慎松动'）",
            "current_blocker": "此刻最卡住推进的一点"
        }
    },
    "management": {
        "description": "企业员工或管理者",
        "industries": ["互联网", "金融", "制造", "零售", "教育"],
        "roles": ["基层员工", "团队主管", "部门经理", "HR", "项目经理"],
        "personalities": [
            "责任心强但容易 burnout",
            "能力强但不善表达",
            "表面服从内心抗拒",
            "积极主动但缺乏方向",
            "经验丰富但抗拒变革",
            "新人，紧张但渴望成长"
        ],
        "pains_by_industry": {
            "互联网": ["加班严重", "内卷", "35 岁危机"],
            "金融": ["合规压力", "KPI 过高", "跨部门推诿"],
            "制造": ["流程僵化", "沟通效率低", "人才流失"],
            "零售": ["人员流动大", "培训成本高", "排班混乱"],
            "教育": ["考核不合理", "资源不足", "家长压力"]
        },
        "triggers_by_role": {
            "基层员工": ["成长空间", "工作生活平衡", "认可"],
            "主管": ["团队效率", "向上管理", "资源分配"],
            "经理": ["绩效考核", "跨部门协同", "战略落地"],
            "HR": ["招聘难", "留存率", "企业文化"],
            "项目经理": ["进度失控", "需求变更", "风险管控"]
        },
        "dealbreakers": ["空洞说教", "不切实际的建议", "忽视个人感受", "一刀切管理"],
        "product_template": "管理咨询",
        "output_fields": {
            "name": "姓名",
            "age": "年龄 (22-50)",
            "hidden_agenda": "隐藏担忧（不敢对领导说的）",
            "budget_range": "不适用，填'N/A'",
            "trigger_words": "3-5 个能引起共鸣的词",
            "dealbreakers": "2-3 个最反感的沟通方式",
            "current_stage": "当前局面阶段（如'先稳住'、'试探观察'、'继续推进'）",
            "current_pressure": "此刻最大的现实压力来源",
            "relationship_position": "他和对方当前的关系位置",
            "current_blocker": "此刻最卡住他的一件事"
        }
    },
    "negotiation": {
        "description": "商务谈判对手",
        "industries": ["科技", "房地产", "制造业", "金融", "零售"],
        "roles": ["采购代表", "销售总监", "法务", "CEO", "合伙人"],
        "personalities": [
            "竞争型，零和思维，寸步不让",
            "合作型，寻求双赢，愿意让步",
            "回避型，不愿面对冲突，拖延决策",
            "妥协型，容易让步但事后后悔",
            "权力型，看重面子和地位",
            "分析型，只看数据，不讲感情"
        ],
        "pains_by_industry": {
            "科技": ["技术锁定", "知识产权", "交付周期"],
            "房地产": ["资金链", "政策风险", "土地成本"],
            "制造业": ["原材料涨价", "供应链断裂", "人工成本"],
            "金融": ["利率波动", "监管变化", "信用风险"],
            "零售": ["渠道冲突", "库存积压", "利润率"]
        },
        "triggers_by_role": {
            "采购": ["成本优化", "长期合作", "风险分担"],
            "销售": ["市场份额", "客户关系", "利润空间"],
            "法务": ["合规", "责任界定", "退出机制"],
            "CEO": ["战略协同", "品牌价值", "长期收益"],
            "合伙人": ["利益分配", "决策权", "退出路径"]
        },
        "dealbreakers": ["出尔反尔", "隐瞒关键信息", "人身攻击", "最后通牒威胁"],
        "product_template": "商业合作",
        "output_fields": {
            "name": "姓名",
            "age": "年龄 (30-60)",
            "hidden_agenda": "隐藏底线（最低可接受条件）",
            "budget_range": "预算或报价范围",
            "trigger_words": "3-5 个谈判中在意的关键词",
            "dealbreakers": "2-3 个会导致谈判破裂的行为",
            "current_stage": "当前谈判阶段（如'初始防御'、'继续对齐'、'往收口走'）",
            "current_pressure": "此刻最现实的压力来源",
            "relationship_position": "双方当前关系位置（如'互相试探'、'有限松动'）",
            "current_blocker": "谈判现在最卡的一点"
        }
    },
    "emotion": {
        "description": "有情感困扰的普通人",
        "industries": ["职场", "家庭", "亲密关系", "社交", "个人成长"],
        "roles": ["伴侣", "父母", "子女", "朋友", "同事", "独居者"],
        "personalities": [
            "焦虑型依恋，极度需要验证，害怕被抛弃",
            "回避型依恋，压力下关闭情感通道",
            "愤怒型，被伤害后爆发，难以冷静",
            "愧疚型，过度自责，愧疚瘫痪",
            "疲惫型，资源耗尽，认知枯竭",
            "绝望型，失去希望，被动消极"
        ],
        "pains_by_industry": {
            "职场": ["被霸凌", "被孤立", "职业枯竭", "不公平对待"],
            "家庭": ["婆媳矛盾", "亲子冲突", "经济控制", "冷暴力"],
            "亲密关系": ["背叛", "沟通障碍", "信任破裂", "情感忽视"],
            "社交": ["被排挤", "网络霸凌", "社交恐惧", "虚假友谊"],
            "个人成长": ["自我怀疑", "目标迷失", "比较焦虑", "拖延症"]
        },
        "triggers_by_role": {
            "伴侣": ["被理解", "安全感", "共同未来", "尊重"],
            "父母": ["被认可", "孩子好", "家庭和睦", "健康"],
            "子女": ["独立自主", "被理解", "个人空间", "公平"],
            "朋友": ["信任", "陪伴", "共同兴趣", "边界感"],
            "同事": ["公平", "尊重", "协作", "职业发展"],
            "独居者": ["连接感", "自我价值", "安全感", "意义"]
        },
        "dealbreakers": ["空洞安慰", "道德绑架", "强迫原谅", "人身攻击", "过度验证错误信念"],
        "product_template": "情感支持",
        "output_fields": {
            "name": "姓名",
            "age": "年龄 (18-65)",
            "hidden_agenda": "内心最深处的恐惧或渴望",
            "budget_range": "不适用，填'N/A'",
            "trigger_words": "3-5 个能触动情感的词或短语",
            "dealbreakers": "2-3 个最反感的回应方式",
            "current_stage": "当前情绪阶段（如'情绪外溢'、'试探是否被理解'、'慢慢松下来'）",
            "current_pressure": "此刻让他最喘不过气的现实压力",
            "relationship_position": "他和对方现在的关系感受",
            "current_blocker": "此刻最难跨过去的一道坎"
        }
    }
}


class UniversalPersonaFactory:
    """
    通用画像工厂 — 支持任意场景，配置驱动，无限扩展
    
    新增场景只需：
    1. 在 SCENE_PERSONA_CONFIGS 中添加配置
    2. 或创建 config/personas/{scene_id}.json
    """

    def __init__(self, config_dir: str = None):
        self.config_dir = config_dir or os.path.join(
            os.path.dirname(__file__), '..', 'config', 'personas'
        )
        self._configs = dict(SCENE_PERSONA_CONFIGS)
        self._load_external_configs()
        self._init_llm_client()

    def _load_external_configs(self):
        """从 config/personas/ 加载外部配置文件"""
        if not os.path.exists(self.config_dir):
            return
        
        for filename in os.listdir(self.config_dir):
            if filename.endswith('.json'):
                scene_id = filename[:-5]
                filepath = os.path.join(self.config_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        self._configs[scene_id] = json.load(f)
                except Exception as e:
                    print(f"⚠️ 加载画像配置失败 {filename}: {e}")

    def _init_llm_client(self):
        """初始化 LLM 客户端"""
        api_key = os.getenv("DEEPSEEK_API_KEY")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        
        if not api_key:
            nvidia_keys = os.getenv("NVIDIA_API_KEYS", "").split(",")
            if nvidia_keys:
                api_key = nvidia_keys[0]
                base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
                self.model = "deepseek-ai/deepseek-v3.1"
        
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def get_available_scenes(self) -> List[str]:
        """获取所有可用的场景 ID"""
        return list(self._configs.keys())

    def generate(self, scene_id: str, seed: Dict = None) -> Optional[Persona]:
        """
        生成指定场景的用户画像
        
        Args:
            scene_id: 场景 ID（如 "sales", "emotion"）
            seed: 可选的种子参数，用于控制随机性
        
        Returns:
            Persona 对象，如果场景不存在则返回 None
        """
        config = self._configs.get(scene_id)
        if not config:
            print(f"⚠️ 场景 '{scene_id}' 无画像配置，可用场景: {list(self._configs.keys())}")
            return None
        
        # 从配置中提取变量
        industries = config.get("industries", ["通用"])
        roles = config.get("roles", ["用户"])
        personalities = config.get("personalities", ["普通"])
        pains_by_industry = config.get("pains_by_industry", {})
        triggers_by_role = config.get("triggers_by_role", {})
        dealbreakers = config.get("dealbreakers", ["不尊重"])
        product_template = config.get("product_template", "服务")
        output_fields = config.get("output_fields", {})
        
        # 生成种子
        if not seed:
            seed = {
                "industry": random.choice(industries),
                "role": random.choice(roles),
                "personality": random.choice(personalities)
            }
        
        industry = seed.get("industry", random.choice(industries))
        role = seed.get("role", random.choice(roles))
        personality = seed.get("personality", random.choice(personalities))
        
        # 获取痛点
        pains = pains_by_industry.get(industry, ["一般困扰"])
        pain = random.choice(pains) if pains else "一般困扰"
        
        # 获取触发词
        role_triggers = triggers_by_role.get(role, ["通用"])
        
        # 构建 LLM Prompt
        fields_desc = "\n".join(f"  - {k}: {v}" for k, v in output_fields.items())
        
        prompt = f"""
请基于以下信息，生成一个真实、立体的用户画像。

【场景】{config.get("description", "通用对话")}
【行业/领域】{industry}
【角色】{role}
【性格】{personality}
【核心痛点】{pain}

【额外要求】
这不是只做一张人物名片。请把这个人放到“正在发生的局面”里去想：
- 他现在大概处在什么阶段
- 最现实的压力是什么
- 和对方现在是什么关系位置
- 推进最卡在哪里

【输出要求】
请输出一个 JSON 对象，包含以下字段：
{fields_desc}

只输出 JSON，不要其他文字。确保 JSON 格式正确。
"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                response_format={"type": "json_object"}
            )
            data = json.loads(response.choices[0].message.content)
            
            # 合并触发词
            final_triggers = list(set(
                data.get("trigger_words", []) + role_triggers
            ))[:5]
            
            return Persona(
                name=data.get("name", "用户"),
                role=role,
                age=data.get("age", 30),
                personality=personality,
                hidden_agenda=data.get("hidden_agenda", "无"),
                budget_range=data.get("budget_range", "N/A"),
                pain_points=[pain],
                trigger_words=final_triggers,
                dealbreakers=data.get("dealbreakers", dealbreakers[:2]),
                product=product_template.format(industry=industry),
                current_stage=data.get("current_stage", "试探观察"),
                current_pressure=data.get("current_pressure", pain),
                relationship_position=data.get("relationship_position", "礼貌疏离"),
                current_blocker=data.get("current_blocker", pain),
            )
        except Exception as e:
            print(f"⚠️ 画像生成失败，使用默认模板：{e}")
            return Persona(
                name="测试用户", role=role, age=30, personality=personality,
                hidden_agenda="无", budget_range="N/A",
                pain_points=[pain],
                trigger_words=role_triggers[:3] if role_triggers else ["通用"],
                dealbreakers=dealbreakers[:2],
                product=product_template.format(industry=industry),
                current_stage="试探观察",
                current_pressure=pain,
                relationship_position="礼貌疏离",
                current_blocker=pain,
            )

    def generate_batch(self, scene_id: str, count: int) -> List[Persona]:
        """批量生成指定场景的画像"""
        return [self.generate(scene_id) for _ in range(count)]


# 向后兼容：保留旧接口
PersonaFactory = UniversalPersonaFactory
