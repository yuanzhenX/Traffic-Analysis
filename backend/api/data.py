from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.db import get_db
from backend.db.models import DetectionLog
from backend.core.data_calc import DataStorageManager, TrafficAnalyzer, HeatmapGenerator

"""
================================================================================
数据API路由模块 (api/data.py)
================================================================================
功能说明:
    本模块提供数据查询和统计相关的REST API接口。
    
    提供的接口:
    1. GET /api/traffic_stats - 获取交通统计数据
    2. GET /api/detection_logs - 获取检测日志
    3. GET /api/today_stats - 获取今日统计摘要
    4. GET /api/peak_hours - 获取高峰时段
    5. GET /api/trends - 获取交通趋势
    6. GET /api/ratio - 获取人车比例
    7. GET /api/heatmap - 获取热力图数据
    8. GET /api/dashboard - 获取仪表盘数据

作者: Nathan
创建日期: 2026-03-19
"""


# 创建路由
router = APIRouter(
    prefix="/api",
    tags=["data"],
    responses={404: {"description": "Not found"}}
)


# 辅助函数
def parse_time_range(
    start_time: Optional[str],
    end_time: Optional[str],
    default_start: Optional[datetime] = None
) -> tuple[datetime, datetime]:
    """
    解析时间范围参数
    
    参数:
        start_time: 开始时间字符串（ISO格式）
        end_time: 结束时间字符串（ISO格式）
        default_start: 默认开始时间，如果未提供则使用当前时间
    
    返回:
        (start, end) 元组
    """
    if start_time:
        start = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
    else:
        start = default_start if default_start else datetime.now()

    if end_time:
        end = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
    else:
        end = datetime.now()

    return start, end


# 数据模型
class TrafficStatsResponse(BaseModel):
    """交通统计响应模型"""
    time_slot: str
    person_count: int
    vehicle_count: int
    avg_speed: float
    density: float
    direction_stats: Dict[str, int]


class DashboardData(BaseModel):
    """仪表盘数据模型"""
    today_person: int
    today_vehicle: int
    avg_speed: float
    density: float
    peak_hour: Optional[str]
    hourly_data: List[Dict[str, Any]]


# API路由定义
@router.get("/traffic_stats")
async def get_traffic_stats(
    start_time: Optional[str] = Query(None, description="开始时间 (ISO格式)"),
    end_time: Optional[str] = Query(None, description="结束时间 (ISO格式)"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取交通统计数据
    
    功能:
        查询指定时间范围内的交通统计数据（每分钟一条记录）
    
    参数:
        start_time: 开始时间，ISO格式（如 2026-03-16T00:00:00）
        end_time: 结束时间，ISO格式
    
    返回:
        {
            "stats": [
                {
                    "time_slot": "2026-03-16T08:00:00",
                    "person_count": 45,
                    "vehicle_count": 23,
                    "avg_speed": 12.5,
                    "density": 0.35,
                    "direction_stats": {"east": 20, "west": 15, ...}
                }
            ],
            "total": 100
        }
    """
    try:
        # 解析时间参数
        default_start = datetime.now().replace(hour=0, minute=0, second=0)
        start, end = parse_time_range(start_time, end_time, default_start)

        # 查询数据
        storage = DataStorageManager(db)
        stats = storage.get_traffic_stats(start, end)

        # 转换为字典列表
        stats_data = [s.to_dict() for s in stats]

        return {
            "stats": stats_data,
            "total": len(stats_data),
            "start_time": start.isoformat(),
            "end_time": end.isoformat()
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"时间格式错误: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/detection_logs")
async def get_detection_logs(
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    object_type: Optional[str] = Query(None, description="目标类型过滤"),
    limit: int = Query(1000, description="返回记录数限制"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取检测日志
    
    功能:
        查询原始检测记录（每秒多次记录）
    
    参数:
        start_time: 开始时间
        end_time: 结束时间
        object_type: 目标类型过滤（person/car等）
        limit: 返回记录数上限
    
    返回:
        {"logs": [...], "total": 100}
    """
    try:
        # 解析时间
        default_start = datetime.now() - timedelta(hours=1)  # 默认最近1小时
        start, end = parse_time_range(start_time, end_time, default_start)

        # 查询数据
        storage = DataStorageManager(db)
        logs = storage.get_detection_logs(start, end, object_type)

        # 限制返回数量
        logs = logs[:limit]

        return {
            "logs": [log.to_dict() for log in logs],
            "total": len(logs)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/today_stats")
async def get_today_stats(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    获取今日统计摘要
    
    返回:
        {
            "total_person": 1200,
            "total_vehicle": 500,
            "avg_speed": 15.5,
            "avg_density": 0.35,
            "peak_hour": "08:00",
            "record_count": 24
        }
    """
    try:
        storage = DataStorageManager(db)
        stats = storage.get_today_stats()

        return stats

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/peak_hours")
async def get_peak_hours(
    top_n: int = Query(3, description="返回前N个高峰时段"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取交通高峰时段
    
    参数:
        top_n: 返回前N个高峰时段
    
    返回:
        {
            "peak_hours": [
                {"time": "08:00", "person_count": 100, "vehicle_count": 50, "total": 150}
            ]
        }
    """
    try:
        analyzer = TrafficAnalyzer(db)
        peaks = analyzer.find_peak_hours(top_n=top_n)

        return {"peak_hours": peaks}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@router.get("/trends")
async def get_trends(
    days: int = Query(7, description="分析最近几天的数据"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取交通趋势
    
    参数:
        days: 分析最近几天的数据
    
    返回:
        {
            "days_analyzed": 7,
            "daily_trends": [...],
            "total_records": 100
        }
    """
    try:
        analyzer = TrafficAnalyzer(db)
        trends = analyzer.analyze_trends(days=days)

        return trends

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@router.get("/ratio")
async def get_ratio(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    获取人车比例
    
    返回:
        {
            "person_count": 1200,
            "vehicle_count": 500,
            "person_percentage": 70.6,
            "vehicle_percentage": 29.4,
            "ratio": "1200:500"
        }
    """
    try:
        analyzer = TrafficAnalyzer(db)
        ratio = analyzer.get_person_vehicle_ratio()

        return ratio

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/heatmap")
async def get_heatmap(
    start_time: Optional[str] = Query(None, description="开始时间"),
    end_time: Optional[str] = Query(None, description="结束时间"),
    grid_size: int = Query(20, description="网格大小"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取热力图数据
    
    功能:
        根据目标位置数据生成热力图
    
    参数:
        start_time: 开始时间
        end_time: 结束时间
        grid_size: 网格大小（像素）
    
    返回:
        {
            "width": 960,
            "height": 540,
            "grid_size": 20,
            "data": [[0.1, 0.2, ...], ...],
            "max_value": 10.0
        }
    """
    try:
        # 解析时间
        default_start = datetime.now() - timedelta(hours=1)
        start, end = parse_time_range(start_time, end_time, default_start)

        # 查询位置数据
        logs = db.query(DetectionLog.x, DetectionLog.y).filter(
            DetectionLog.timestamp >= start,
            DetectionLog.timestamp <= end
        ).all()

        positions = [(log.x, log.y) for log in logs]

        # 生成热力图
        generator = HeatmapGenerator(
            width=960,
            height=540,
            grid_size=grid_size
        )
        heatmap = generator.generate(positions)

        return heatmap.to_dict()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成热力图失败: {str(e)}")


@router.get("/dashboard")
async def get_dashboard(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    获取仪表盘数据
    
    功能:
        聚合仪表盘所需的所有数据
    
    返回:
        {
            "today": {...},
            "hourly_data": [...],
            "peak_hours": [...],
            "ratio": {...}
        }
    """
    try:
        storage = DataStorageManager(db)
        analyzer = TrafficAnalyzer(db)

        # 今日统计
        today = storage.get_today_stats()

        # 今日每 30 分钟数据
        now = datetime.now()
        start_of_day = now.replace(hour=0, minute=0, second=0)
        hourly_stats = storage.get_traffic_stats(start_of_day, now)

        # 将每分钟数据转换为每 30 分钟数据
        half_hourly_data = []
        for stat in hourly_stats:
            half_hourly_data.append({
                "time": stat.time_slot.strftime("%H:%M"),
                "person": stat.person_count,
                "vehicle": stat.vehicle_count,
                "total": stat.person_count + stat.vehicle_count
            })

        # 高峰时段
        peaks = analyzer.find_peak_hours(top_n=3)

        # 人车比例
        ratio = analyzer.get_person_vehicle_ratio()

        return {
            "today": today,
            "hourly_data": half_hourly_data,
            "peak_hours": peaks,
            "ratio": ratio
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取仪表盘数据失败: {str(e)}")
