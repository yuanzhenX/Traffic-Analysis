import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
from dataclasses import dataclass, field
from sqlalchemy.orm import Session
from sqlalchemy import and_, select
from backend.config import VideoConfig
from backend.db.models import DetectionLog, TrafficStat


"""
================================================================================
数据计算与统计模块 (core/data_calc.py)
================================================================================
功能说明:
    本模块负责交通数据的计算、统计和聚合。
    
    主要功能:
    1. 实时数据统计（当前帧的人车数量、平均速度、密度）
    2. 历史数据聚合（每分钟生成统计记录）
    3. 热力图数据生成
    4. 数据库存储和查询
    5. 跨线计数（可选功能）

数据流:
    检测数据 → 实时统计 → 数据库存储 → 历史查询 → 聚合分析

作者: Nathan
创建日期: 2026-03-19
"""


# 实时统计数据类
@dataclass
class RealtimeStats:
    timestamp: datetime  # 统计时间戳
    person_count: int = 0  # 当前行人数量
    vehicle_count: int = 0  # 当前车辆数量
    total_count: int = 0  # 总目标数量
    avg_speed: float = 0.0  # 平均像素速度
    density: float = 0.0  # 交通密度
    direction_counts: Dict[str, int] = field(default_factory=dict)  # 各方向流量统计

    # 转换为字典格式
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "person_count": self.person_count,
            "vehicle_count": self.vehicle_count,
            "total_count": self.total_count,
            "avg_speed": round(self.avg_speed, 2),
            "density": round(self.density, 4),
            "direction_counts": self.direction_counts
        }


# 热力图数据类
@dataclass
class HeatmapData:
    width: int  # 热力图宽度
    height: int  # 热力图高度
    grid_size: int  # 网格大小
    data: List[List[float]]  # 热力值矩阵
    max_value: float  # 最大值（用于归一化）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "grid_size": self.grid_size,
            "data": self.data,
            "max_value": self.max_value
        }


# 实时统计计算器
class RealtimeStatsCalculator:

    def __init__(self, roi_area: Optional[float] = None):  # roi_area: ROI区域面积（像素平方），用于计算密度，如果为None，则使用全画面面积
        if roi_area is None:
            self.roi_area = VideoConfig.FRAME_WIDTH * VideoConfig.FRAME_HEIGHT  # 默认使用全画面面积
        else:
            self.roi_area = roi_area

    # 计算实时统计数据
    def calculate(self, detections: List[Dict[str, Any]]) -> RealtimeStats:  # detections为检测结果列表，每个元素为字典

        timestamp = datetime.now()

        # 统计人车数量
        person_count = sum(1 for d in detections if d.get("class_name") == "person")
        vehicle_count = len(detections) - person_count

        # 计算平均速度
        if detections:
            speeds = [d.get("speed", 0) for d in detections]
            avg_speed = sum(speeds) / len(speeds)
        else:
            avg_speed = 0.0

        # 计算密度（目标数/ROI面积）
        total_count = len(detections)
        density = total_count / self.roi_area if self.roi_area > 0 else 0.0

        # 统计各方向流量
        direction_counts = defaultdict(int)
        for d in detections:
            direction = d.get("direction", "Unknown")
            if direction != "Unknown":
                direction_counts[direction] += 1

        return RealtimeStats(
            timestamp=timestamp,
            person_count=person_count,
            vehicle_count=vehicle_count,
            total_count=total_count,
            avg_speed=avg_speed,
            density=density,
            direction_counts=dict(direction_counts)
        )

    # 更新ROI区域面积
    def update_roi_area(self, roi_points: List[Tuple[int, int]]) -> None:

        # 如果ROI点不足3个，使用全画面
        if len(roi_points) < 3:
            self.roi_area = VideoConfig.FRAME_WIDTH * VideoConfig.FRAME_HEIGHT
            return

        # 使用鞋带公式计算多边形面积
        n = len(roi_points)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += roi_points[i][0] * roi_points[j][1]
            area -= roi_points[j][0] * roi_points[i][1]

        self.roi_area = abs(area) / 2.0
        print(f"[统计计算器] ROI面积已更新: {self.roi_area:.0f} 像素²")


# 数据存储管理器，负责管理所有“检测数据”和“统计数据”
class DataStorageManager:

    def __init__(self, db_session: Session):
        self.db = db_session
        self._last_aggregate_time: Optional[datetime] = None  # 上一次统计的时间
        self._aggregate_interval = 1800  # 每 30 分钟统计一次（1800 秒）

    # 将检测结果存进数据库
    def save_detections(self, detections: List[Dict[str, Any]], timestamp: Optional[datetime] = None) -> None:

        if timestamp is None:
            timestamp = datetime.now()

        # 批量创建空白检测记录
        detection_logs = []
        for det in detections:
            log = DetectionLog(
                track_id=det.get("track_id", 0),
                object_type=det.get("class_name", "unknown"),
                timestamp=timestamp,
                x=det.get("center", [0, 0])[0],
                y=det.get("center", [0, 0])[1],
                pixel_speed=det.get("speed", 0.0),
                direction=det.get("direction", "Unknown"),
                confidence=det.get("confidence", 0.0),
                bbox_x1=det.get("bbox", [0, 0, 0, 0])[0],
                bbox_y1=det.get("bbox", [0, 0, 0, 0])[1],
                bbox_x2=det.get("bbox", [0, 0, 0, 0])[2],
                bbox_y2=det.get("bbox", [0, 0, 0, 0])[3]
            )
            detection_logs.append(log)

        # 批量插入记录
        if detection_logs:
            self.db.bulk_save_objects(detection_logs)
            self.db.commit()

    # 每分钟做一次统计
    def aggregate_minute_stats(self, force: bool = False) -> Optional[TrafficStat]:  # force: 是否强制聚合，忽略时间间隔

        current_time = datetime.now()

        # 检查是否到了聚合时间
        if not force and self._last_aggregate_time is not None:
            elapsed = (current_time - self._last_aggregate_time).total_seconds()
            if elapsed < self._aggregate_interval:
                return None

        # 计算本分钟的时间范围
        # 取整到 30 分钟间隔（每小时的 00 分和 30 分）
        minute = 30 if current_time.minute >= 30 else 0
        time_slot = current_time.replace(minute=minute, second=0, microsecond=0)
        start_time = time_slot - timedelta(minutes=30)
        end_time = time_slot

        # 查询该时间段的检测数据
        logs = self.db.query(DetectionLog).filter(
            and_(
                DetectionLog.timestamp >= start_time,
                DetectionLog.timestamp < end_time
            )
        ).all()

        if not logs:
            return None

        # 统计人车数量
        person_count = sum(1 for log in logs if log.object_type == "person")
        vehicle_count = len(logs) - person_count

        # 计算平均速度
        speeds = [log.pixel_speed for log in logs if log.pixel_speed > 0]
        avg_speed = sum(speeds) / len(speeds) if speeds else 0.0

        # 计算密度（使用最新的检测数据）
        latest_logs = [log for log in logs if log.timestamp >= end_time - timedelta(seconds=5)]
        density = len(latest_logs) / (VideoConfig.FRAME_WIDTH * VideoConfig.FRAME_HEIGHT) if latest_logs else 0.0

        # 统计方向
        direction_counts = defaultdict(int)
        for log in logs:
            if log.direction != "Unknown":
                direction_counts[log.direction] += 1

        # 创建统计记录
        stat = TrafficStat(
            time_slot=time_slot,
            person_count=person_count,
            vehicle_count=vehicle_count,
            avg_speed=avg_speed,
            density=density,
            east_count=direction_counts.get("East", 0),
            west_count=direction_counts.get("West", 0),
            south_count=direction_counts.get("South", 0),
            north_count=direction_counts.get("North", 0)
        )

        # 保存到数据库
        self.db.add(stat)
        self.db.commit()

        self._last_aggregate_time = current_time

        print(f"[数据存储] 30 分钟统计已生成：{time_slot}, 行人:{person_count}, 车辆:{vehicle_count}")

        return stat

    # 查询某段时间的统计数据
    def get_traffic_stats(self, start_time: datetime, end_time: datetime) -> List[TrafficStat]:
        stmt = select(TrafficStat).where(
            TrafficStat.time_slot >= start_time,
            TrafficStat.time_slot <= end_time
        )
        stats = self.db.execute(stmt).scalars().all()

        return stats

    # 查询原始检测数据，可过滤目标类型
    def get_detection_logs(self,start_time: datetime,end_time: datetime,object_type: Optional[str] = None) -> List[DetectionLog]:
        query = self.db.query(DetectionLog).filter(
            and_(
                DetectionLog.timestamp >= start_time,
                DetectionLog.timestamp <= end_time
            )
        )

        if object_type:
            query = query.filter(DetectionLog.object_type == object_type)

        return query.order_by(DetectionLog.timestamp.asc()).all()

    # 获取今日统计数据
    def get_today_stats(self) -> Dict[str, Any]:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)

        stats = self.get_traffic_stats(today, tomorrow)

        if not stats:
            return {
                "total_person": 0,
                "total_vehicle": 0,
                "avg_speed": 0.0,
                "avg_density": 0.0,
                "peak_hour": None
            }

        # 计算总计
        total_person = sum(s.person_count for s in stats)
        total_vehicle = sum(s.vehicle_count for s in stats)
        avg_speed = sum(s.avg_speed for s in stats) / len(stats)
        avg_density = sum(s.density for s in stats) / len(stats)

        # 找出高峰时段
        max_total = 0
        peak_hour = None
        for s in stats:
            total = s.person_count + s.vehicle_count
            if total > max_total:
                max_total = total
                peak_hour = s.time_slot.strftime("%H:%M")

        return {
            "total_person": total_person,
            "total_vehicle": total_vehicle,
            "avg_speed": round(avg_speed, 2),
            "avg_density": round(avg_density, 4),
            "peak_hour": peak_hour,
            "record_count": len(stats)
        }


# 热力图生成器
class HeatmapGenerator:
    """
    热力图生成器
    
    根据目标位置数据生成热力图
    
    使用示例:
        generator = HeatmapGenerator(960, 540)
        heatmap = generator.generate(positions)
    """

    def __init__(
            self,
            width: int = 960,
            height: int = 540,
            grid_size: int = 20
    ):
        """
        初始化热力图生成器
        
        参数:
            width: 图像宽度
            height: 图像高度
            grid_size: 网格大小（像素）
        """
        self.width = width
        self.height = height
        self.grid_size = grid_size

        # 计算网格数量
        self.grid_x = width // grid_size
        self.grid_y = height // grid_size

    def generate(
            self,
            positions: List[Tuple[int, int]],
            use_gaussian: bool = True
    ) -> HeatmapData:
        """
        生成热力图数据
        
        参数:
            positions: 目标位置列表 [(x1,y1), (x2,y2), ...]
            use_gaussian: 是否使用高斯平滑
            
        返回:
            HeatmapData: 热力图数据对象
        """
        # 初始化热力矩阵
        heatmap = [[0.0 for _ in range(self.grid_x)] for _ in range(self.grid_y)]

        # 统计每个网格的目标数
        for x, y in positions:
            grid_x = int(x / self.grid_size)
            grid_y = int(y / self.grid_size)

            # 确保在有效范围内
            if 0 <= grid_x < self.grid_x and 0 <= grid_y < self.grid_y:
                heatmap[grid_y][grid_x] += 1

        # 高斯平滑
        if use_gaussian:
            heatmap = self._apply_gaussian(heatmap)

        # 找出最大值用于归一化
        max_value = max(max(row) for row in heatmap) if heatmap else 1.0

        # 归一化到0-1的范围
        if max_value > 0:
            heatmap = [[v / max_value for v in row] for row in heatmap]

        return HeatmapData(
            width=self.width,
            height=self.height,
            grid_size=self.grid_size,
            data=heatmap,
            max_value=max_value
        )

    def _apply_gaussian(
            self,
            heatmap: List[List[float]],
            sigma: float = 1.0
    ) -> List[List[float]]:
        """
        对热力图应用高斯平滑
        
        参数:
            heatmap: 原始热力矩阵
            sigma: 高斯核标准差
            
        返回:
            List[List[float]]: 平滑后的热力矩阵
        """
        # 简单的高斯平滑实现（3x3核）
        kernel_size = 3
        pad = kernel_size // 2

        rows = len(heatmap)
        cols = len(heatmap[0]) if rows > 0 else 0

        # 创建输出矩阵
        smoothed = [[0.0 for _ in range(cols)] for _ in range(rows)]

        # 3x3高斯核（sigma=1）
        kernel = [
            [0.075, 0.124, 0.075],
            [0.124, 0.204, 0.124],
            [0.075, 0.124, 0.075]
        ]

        # 应用卷积
        for i in range(rows):
            for j in range(cols):
                value = 0.0
                for ki in range(kernel_size):
                    for kj in range(kernel_size):
                        ni = i + ki - pad
                        nj = j + kj - pad

                        # 边界处理（使用镜像）
                        if ni < 0:
                            ni = -ni
                        if ni >= rows:
                            ni = 2 * rows - ni - 1
                        if nj < 0:
                            nj = -nj
                        if nj >= cols:
                            nj = 2 * cols - nj - 1

                        value += heatmap[ni][nj] * kernel[ki][kj]

                smoothed[i][j] = value

        return smoothed


# 数据分析器
class TrafficAnalyzer:
    """
    交通数据分析器
    
    提供各种交通数据分析功能
    
    使用示例:
        analyzer = TrafficAnalyzer(db_session)
        peak_hours = analyzer.find_peak_hours()
        trends = analyzer.analyze_trends()
    """

    def __init__(self, db_session: Session):
        """
        初始化分析器
        
        参数:
            db_session: SQLAlchemy数据库会话
        """
        self.db = db_session
        self.storage = DataStorageManager(db_session)

    def find_peak_hours(
            self,
            start_time: Optional[datetime] = None,
            end_time: Optional[datetime] = None,
            top_n: int = 3
    ) -> List[Dict[str, Any]]:
        """
        查找交通高峰时段
        
        参数:
            start_time: 开始时间（默认为今天）
            end_time: 结束时间（默认为明天）
            top_n: 返回前N个高峰时段
            
        返回:
            List[Dict]: 高峰时段列表
        """
        if start_time is None:
            start_time = datetime.now().replace(hour=0, minute=0, second=0)
        if end_time is None:
            end_time = start_time + timedelta(days=1)

        stats = self.storage.get_traffic_stats(start_time, end_time)

        if not stats:
            return []

        # 按总流量排序
        sorted_stats = sorted(
            stats,
            key=lambda s: s.person_count + s.vehicle_count,
            reverse=True
        )

        # 返回前N个
        peaks = []
        for s in sorted_stats[:top_n]:
            peaks.append({
                "time": s.time_slot.strftime("%H:%M"),
                "person_count": s.person_count,
                "vehicle_count": s.vehicle_count,
                "total": s.person_count + s.vehicle_count,
                "density": round(s.density, 4)
            })

        return peaks

    def analyze_trends(
            self,
            days: int = 7
    ) -> Dict[str, Any]:
        """
        分析交通趋势
        
        参数:
            days: 分析最近几天的数据
            
        返回:
            Dict: 趋势分析结果
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)

        stats = self.storage.get_traffic_stats(start_time, end_time)

        if not stats:
            return {"error": "没有足够的数据"}

        # 按天分组统计
        daily_stats = defaultdict(lambda: {"person": 0, "vehicle": 0, "count": 0})

        for s in stats:
            day = s.time_slot.strftime("%Y-%m-%d")
            daily_stats[day]["person"] += s.person_count
            daily_stats[day]["vehicle"] += s.vehicle_count
            daily_stats[day]["count"] += 1

        # 计算平均值
        trend_data = []
        for day, data in sorted(daily_stats.items()):
            if data["count"] > 0:
                trend_data.append({
                    "date": day,
                    "avg_person": round(data["person"] / data["count"], 1),
                    "avg_vehicle": round(data["vehicle"] / data["count"], 1)
                })

        return {
            "days_analyzed": days,
            "daily_trends": trend_data,
            "total_records": len(stats)
        }

    def get_person_vehicle_ratio(
            self,
            start_time: Optional[datetime] = None,
            end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        获取人车比例
        
        参数:
            start_time: 开始时间
            end_time: 结束时间
            
        返回:
            Dict: 人车比例数据
        """
        if start_time is None:
            start_time = datetime.now().replace(hour=0, minute=0, second=0)
        if end_time is None:
            end_time = start_time + timedelta(days=1)

        stats = self.storage.get_traffic_stats(start_time, end_time)

        if not stats:
            return {"person": 0, "vehicle": 0, "ratio": "0:0"}

        total_person = sum(s.person_count for s in stats)
        total_vehicle = sum(s.vehicle_count for s in stats)
        total = total_person + total_vehicle

        if total == 0:
            return {"person": 0, "vehicle": 0, "ratio": "0:0"}

        person_pct = round(total_person / total * 100, 1)
        vehicle_pct = round(total_vehicle / total * 100, 1)

        return {
            "person_count": total_person,
            "vehicle_count": total_vehicle,
            "person_percentage": person_pct,
            "vehicle_percentage": vehicle_pct,
            "ratio": f"{total_person}:{total_vehicle}"
        }
