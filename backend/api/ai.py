import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool  # 线程池
from typing import Optional, Dict, Any
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.db import get_db
from backend.core.ai_interact import AIAnalysisService, QuickAnalysisHandler

"""
================================================================================
AI API路由模块 (api/ai.py)
================================================================================
功能说明:
    本模块提供AI分析相关的REST API接口。
    
    提供的接口:
    1. POST /api/ai_analysis - AI交通分析（自由问答）
    2. POST /api/ai_quick_analysis - 快捷分析（高峰期/趋势/比例）
    3. GET /api/ai_analysis_types - 获取可用的分析类型

作者: Nathan
创建日期: 2026-03-18
"""

# 创建路由router
router = APIRouter(
    prefix="/api",
    tags=["ai"],
    responses={404: {"description": "Not found"}}
)


# 前端传给AI的问题请求格式
class AIAnalysisRequest(BaseModel):
    """AI分析请求模型"""
    question: str  # 用户问题


# 前端传给AI的快捷分析请求格式
class AIQuickAnalysisRequest(BaseModel):
    """AI快捷分析请求模型"""
    analysis_type: str  # "peak", "trend", "ratio"


# AI返回给前端的数据格式模板
class AIAnalysisResponse(BaseModel):
    """AI分析响应模型"""
    success: bool  # 是否成功
    answer: str  # AI返回的内容
    raw_data: Optional[Dict[str, Any]] = None  # 原始数据
    error: Optional[str] = None  # 错误信息
    """
    前端操作：
    if (success) 看 answer
        else 看 error
    """


# 处理AI分析请求接口方法
@router.post("/ai_analysis", response_model=AIAnalysisResponse)  # path是请求地址，response_model是响应数据模型
async def ai_analysis(  # 使用异步函数，在等待AI结果的这段时间内不阻塞CPU，而是去执行其他任务
        request: AIAnalysisRequest,  # 需要传入从前端发送的此格式数据
        db: Session = Depends(get_db)  # 传入时自动连接数据库
) -> AIAnalysisResponse:  # 返回此格式的回答
    try:
        # 把数据库对象交给AI服务，创建了一个AI服务对象
        ai_service = AIAnalysisService(db)

        # 将传入的问题交给AI服务对象的分析函数进行分析，并返回结果
        result = await asyncio.wait_for(
            run_in_threadpool(ai_service.analyze, request.question),  # await run_in_threadpool相当于在后台开一个线程去执行该函数
            timeout=10  # 防止AI分析过久，10秒没结果就报错
        )

        # 将结果转换为AIAnalysisResponse格式并返回
        return AIAnalysisResponse(
            success=result.success,
            answer=result.answer,
            raw_data=result.raw_data,
            error=result.error
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI分析失败: {str(e)}")


# 处理AI快捷分析请求接口方法
@router.post("/ai_quick_analysis", response_model=AIAnalysisResponse)
async def ai_quick_analysis(
        request: AIQuickAnalysisRequest,
        db: Session = Depends(get_db)
) -> AIAnalysisResponse:
    try:
        # 创建AI分析服务
        ai_service = AIAnalysisService(db)

        # 创建快捷分析处理器
        handler = QuickAnalysisHandler(ai_service)

        # 执行分析
        result = await run_in_threadpool(
            handler.handle,
            request.analysis_type
        )

        return AIAnalysisResponse(
            success=result.success,
            answer=result.answer,
            raw_data=result.raw_data,
            error=result.error
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"快捷分析失败: {str(e)}")


# 获取可用的分析类型
# 将可用快捷类型的控制权从前端转到后端，这样如果需要增加快捷类型就不用修改前端代码，而是修改后端代码，然后前端从后端获取
@router.get("/ai_analysis_types")
async def get_analysis_types(db: Session = Depends(get_db)) -> Dict[str, Any]:
    try:
        # 创建临时的AI服务和处理器
        ai_service = AIAnalysisService(db)
        handler = QuickAnalysisHandler(ai_service)

        # 获取分析类型列表
        types = handler.get_available_analyses()

        return {"types": types}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取分析类型失败: {str(e)}")
