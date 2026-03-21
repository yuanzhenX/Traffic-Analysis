import json
import requests
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from sqlalchemy.orm import Session
from backend.config import APIConfig
from backend.core.data_calc import TrafficAnalyzer, DataStorageManager
import time

"""
================================================================================
AI交互模块 (core/ai_interact.py)
================================================================================
功能说明:
    本模块负责与大语言模型（智谱AI）进行交互，实现自然语言交通分析功能。
    
    主要功能:
    1. 调用智谱AI API进行自然语言理解和生成
    2. 根据用户问题查询数据库获取相关统计数据
    3. 构造Prompt模板，将统计数据提供给AI进行分析
    4. 处理AI返回的分析结果并格式化输出
    5. 支持预设的分析场景（高峰期分析、趋势分析、人车比例分析）

交互流程:
    用户提问 → 查询数据库 → 整理数据 → 构造Prompt → 调用AI → 返回结果

作者: Nathan
创建日期: 2026-03-19
"""


# AI响应数据类
@dataclass  # 用于自动生成初始化函数
class AIResponse:
    success: bool  # 是否成功
    answer: str  # AI的回答内容
    raw_data: Optional[Dict[str, Any]] = None  # 原始统计数据（用于展示）
    error: Optional[str] = None  # 错误信息（如果失败）

    # 转换为字典格式
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "answer": self.answer,
            "raw_data": self.raw_data,
            "error": self.error
        }


# 智谱AI客户端
class ZhipuAIClient:
    # 初始化方法，在创建对象时自动执行
    def __init__(self):
        # 从配置中读取API密钥和接口地址
        self.api_key = APIConfig.ZHIPU_API_KEY
        self.api_url = APIConfig.ZHIPU_API_URL
        self.timeout = APIConfig.REQUEST_TIMEOUT
        self.max_retries = APIConfig.MAX_RETRIES  # 最大重试次数

        # 验证API密钥
        if not self.api_key:
            raise ValueError("API密钥未配置，请在.env文件中设置ZHIPU_API_KEY")
        print("[AI客户端] 已初始化")

    # 输入问题，返回AI的回答
    def chat(
            self,
            prompt: str,  # 用户问题
            model: str = "glm-4",  # 模型名称，默认为glm-4
            temperature: float = 0.7,  # 温度参数，控制创造性（0-1）
            max_tokens: int = 2000  # 最大生成token数
    ) -> str:  # AI的回复内容

        # 构造请求头
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        # 构造请求体
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个专业的交通数据分析助手，擅长分析校园主干道的交通流量数据。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        # 重试机制
        for attempt in range(self.max_retries):
            try:
                # 向AI服务器发送HTTP请求
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout
                )

                # 检查是否响应成功
                response.raise_for_status()
                # 解析响应
                result = response.json()
                # 提取AI的回答
                if "choices" in result and len(result["choices"]) > 0:
                    message = result["choices"][0].get("message", {})
                    content = message.get("content", "")
                    return content.strip()
                else:
                    raise Exception(f"AI响应格式异常: {result}")

            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1:  # 如果还没到最大次数，进行重试
                    print(f"[AI客户端] 请求失败，正在重试 ({attempt + 1}/{self.max_retries}): {e}")
                    time.sleep(1)
                else:
                    raise Exception(f"AI API调用失败: {e}")

        return "抱歉，AI服务暂时不可用，请稍后重试。"


# Prompt构造器，实现根据用户问题和统计数据构造AI提示词
class PromptBuilder:
    # 系统角色设定
    SYSTEM_ROLE = """
        你是一位专业的校园交通数据分析师，专门负责分析校园主干道的交通流量数据。
        
        你的职责:
        1. 分析人流和车流的时空分布特征
        2. 识别交通高峰期和低谷期
        3. 提供交通管理优化建议
        4. 用通俗易懂的语言解释数据洞察
        
        注意事项:
        - 回答要简洁明了，避免过于技术化
        - 提供具体的数据支撑你的结论
        - 如果数据不足，如实说明
        - 使用中文回答
    """

    @staticmethod   # 不需要创建对象即可直接使用该方法
    def build_traffic_analysis_prompt(question: str, stats_data: Dict[str, Any]) -> str:  # 用户问题、统计数据 -> 构造好的Prompt

        prompt = f"""{PromptBuilder.SYSTEM_ROLE}
        
            以下是校园主干道的交通统计数据:
            {json.dumps(stats_data, ensure_ascii=False, indent=2)}
            用户问题: {question}

            请基于以上数据进行分析并回答用户的问题。回答要求:
            1. 直接回答问题，不要绕弯子
            2. 引用具体数据支撑你的观点
            3. 如果数据不足，说明还需要哪些数据
            4. 可以适当提供建议或预测
            
            请给出你的分析:
        """
        return prompt

    # 构造高峰期分析Prompt
    @staticmethod
    def build_peak_analysis_prompt(peak_data: List[Dict[str, Any]]) -> str:

        prompt = f"""{PromptBuilder.SYSTEM_ROLE}

            以下是今日交通高峰时段数据:
            {json.dumps(peak_data, ensure_ascii=False, indent=2)}

            请分析:
            1. 哪个时段是交通最高峰？为什么？
            2. 高峰期的人车比例如何？
            3. 有什么管理建议？
            
            请给出你的分析:
        """

        return prompt

    # 构造趋势分析Prompt
    @staticmethod
    def build_trend_analysis_prompt(trend_data: Dict[str, Any]) -> str:

        prompt = f"""{PromptBuilder.SYSTEM_ROLE}

            以下是近期交通趋势数据:
            {json.dumps(trend_data, ensure_ascii=False, indent=2)}

            请分析:
            1. 人流和车流的变化趋势如何？
            2. 是否有明显的规律（如工作日vs周末）？
            3. 对未来交通情况的预测和建议
            
            请给出你的分析:
        """

        return prompt

    # 构造人车比例分析Prompt
    @staticmethod
    def build_ratio_analysis_prompt(ratio_data: Dict[str, Any]) -> str:

        prompt = f"""{PromptBuilder.SYSTEM_ROLE}

            以下是今日人车比例数据:
            {json.dumps(ratio_data, ensure_ascii=False, indent=2)}

            请分析:
            1. 行人和车辆的比例是否合理？
            2. 这种比例反映了什么交通特征？
            3. 对校园交通管理有什么建议？
            
            请给出你的分析:
        """

        return prompt


# 整合数据查询、Prompt构造和AI调用，提供完整的分析功能
class AIAnalysisService:

    def __init__(self, db_session: Session):
        self.db = db_session

        # 初始化AI客户端
        try:
            self.ai_client = ZhipuAIClient()
        except ValueError as e:
            print(f"[AI服务] 警告: {e}")
            self.ai_client = None

        # 初始化数据分析器
        self.analyzer = TrafficAnalyzer(db_session)
        self.storage = DataStorageManager(db_session)
        print("[AI服务] AI分析服务已初始化")

    def analyze(self, question: str) -> AIResponse:
        # 检查AI客户端是否可用
        if self.ai_client is None:
            return AIResponse(success=False, answer="AI服务未配置，无法进行分析。", error="API密钥未配置")

        try:
            # 获取相关统计数据
            stats_data = self._gather_data_for_question(question)
            # 构造Prompt
            prompt = PromptBuilder.build_traffic_analysis_prompt(question, stats_data)
            # 调用AI
            answer = self.ai_client.chat(prompt)
            return AIResponse(success=True, answer=answer, raw_data=stats_data)

        except Exception as e:
            print(f"[AI服务] 分析失败: {e}")
            return AIResponse(success=False, answer="分析过程中出现错误，请稍后重试。", error=str(e))

    def analyze_peak_hours(self) -> AIResponse:
        if self.ai_client is None:
            return AIResponse(success=False, answer="AI服务未配置", error="API密钥未配置")

        try:
            # 获取高峰数据
            peak_data = self.analyzer.find_peak_hours(top_n=5)
            if not peak_data:
                return AIResponse(
                    success=True,
                    answer="目前还没有足够的交通数据来分析高峰期。请等待系统收集更多数据后再进行分析。",
                    raw_data={}
                )
            # 构造Prompt
            prompt = PromptBuilder.build_peak_analysis_prompt(peak_data)
            # 调用AI
            answer = self.ai_client.chat(prompt)
            return AIResponse(
                success=True,
                answer=answer,
                raw_data={"peak_hours": peak_data}
            )

        except Exception as e:
            return AIResponse(success=False, answer="高峰期分析失败", error=str(e))

    def analyze_trends(self) -> AIResponse:

        if self.ai_client is None:
            return AIResponse(success=False, answer="AI服务未配置", error="API密钥未配置")

        try:
            # 获取趋势数据
            trend_data = self.analyzer.analyze_trends(days=7)

            if "error" in trend_data:
                return AIResponse(
                    success=True,
                    answer="目前还没有足够的交通数据来分析趋势。请等待系统收集更多数据后再进行分析。",
                    raw_data={}
                )

            # 构造Prompt
            prompt = PromptBuilder.build_trend_analysis_prompt(trend_data)
            # 调用AI
            answer = self.ai_client.chat(prompt)
            return AIResponse(success=True, answer=answer, raw_data=trend_data)

        except Exception as e:
            return AIResponse(success=False, answer="趋势分析失败", error=str(e))

    def analyze_ratio(self) -> AIResponse:

        if self.ai_client is None:
            return AIResponse(success=False, answer="AI服务未配置", error="API密钥未配置")

        try:
            # 获取人车比例数据
            ratio_data = self.analyzer.get_person_vehicle_ratio()

            if ratio_data["person_count"] == 0 and ratio_data["vehicle_count"] == 0:
                return AIResponse(
                    success=True,
                    answer="目前还没有交通数据来分析人车比例。请等待系统收集数据后再进行分析。",
                    raw_data={}
                )

            # 构造Prompt
            prompt = PromptBuilder.build_ratio_analysis_prompt(ratio_data)
            # 调用AI
            answer = self.ai_client.chat(prompt)
            return AIResponse(success=True, answer=answer, raw_data=ratio_data)

        except Exception as e:
            return AIResponse(success=False, answer="人车比例分析失败", error=str(e))

    # 根据问题类型收集相关数据
    def _gather_data_for_question(self, question: str) -> Dict[str, Any]:

        data = {}

        # 无论问什么都会默认返回今天的统计数据
        today_stats = self.storage.get_today_stats()
        data["today"] = today_stats

        # 预处理：统一小写
        question_lower = question.lower()

        # 高峰期相关
        if any(kw in question_lower for kw in ["高峰", "peak", " busiest"]):
            data["peak_hours"] = self.analyzer.find_peak_hours(top_n=3)
        # 趋势相关
        if any(kw in question_lower for kw in ["趋势", "trend", "变化", "change"]):
            data["trends"] = self.analyzer.analyze_trends(days=7)
        # 比例相关
        if any(kw in question_lower for kw in ["比例", "ratio", "占比", "percentage"]):
            data["ratio"] = self.analyzer.get_person_vehicle_ratio()
        # 方向相关
        if any(kw in question_lower for kw in ["方向", "direction", "东", "西", "南", "北"]):
            # 获取方向统计数据
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=1)
            stats = self.storage.get_traffic_stats(start_time, end_time)
            if stats:
                data["direction_summary"] = {
                    "east": sum(s.east_count for s in stats),
                    "west": sum(s.west_count for s in stats),
                    "south": sum(s.south_count for s in stats),
                    "north": sum(s.north_count for s in stats)
                }
        # 速度相关
        if any(kw in question_lower for kw in ["速度", "speed", "快", "慢", "拥堵"]):
            data["speed_info"] = {
                "avg_speed_today": today_stats.get("avg_speed", 0),
                "note": "像素速度，单位: pixel/s"
            }

        return data


# 快捷分析按钮处理器
class QuickAnalysisHandler:

    # 分析类型映射
    ANALYSIS_TYPES = {
        "peak": {
            "name": "高峰期分析",
            "description": "分析今日交通高峰时段"
        },
        "trend": {
            "name": "趋势分析",
            "description": "分析近期交通变化趋势"
        },
        "ratio": {
            "name": "人车比例分析",
            "description": "分析行人与车辆的比例关系"
        }
    }

    def __init__(self, ai_service: AIAnalysisService):
        self.ai_service = ai_service

    # 处理快捷分析请求
    def handle(self, analysis_type: str) -> AIResponse:

        if analysis_type not in self.ANALYSIS_TYPES:
            return AIResponse(success=False, answer=f"未知的分析类型: {analysis_type}", error="Invalid analysis type")

        # 根据类型调用相应的分析方法
        if analysis_type == "peak":
            return self.ai_service.analyze_peak_hours()
        elif analysis_type == "trend":
            return self.ai_service.analyze_trends()
        elif analysis_type == "ratio":
            return self.ai_service.analyze_ratio()

        return AIResponse(success=False, answer="分析处理失败", error="Unknown error")

    # 获取可用的分析类型列表
    def get_available_analyses(self) -> List[Dict[str, str]]:
        return [
            {"type": key, **value}
            for key, value in self.ANALYSIS_TYPES.items()
        ]
