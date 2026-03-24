from sqlalchemy import Column, Integer, String, Float, DateTime, Index
from sqlalchemy.sql import func
from backend.db.base import Base


"""
================================================================================
数据库模型模块 (db/models.py)
================================================================================
功能说明:
    本模块定义了系统使用的所有数据库表结构（ORM模型）。
    使用SQLAlchemy的声明式基类定义模型，自动映射到SQLite数据库表。
    
    数据表说明:
    1. DetectionLog: 检测日志表，存储每秒的原始检测结果
    2. TrafficStat: 交通统计表，存储每分钟的聚合统计数据

数据库设计原则:
    - 使用整数主键自增ID
    - 使用合适的数据类型节省空间
    - 添加索引提高查询效率
    - 使用外键维护数据一致性

作者: Nathan
创建日期: 2026-03-20
"""


# 检测日志表 (DetectionLog)
class DetectionLog(Base):
    """
    检测日志表

    功能说明:
        存储目标检测的原始数据，每秒记录一次每个检测到的目标。
        用于追踪单个目标的运动轨迹和状态。

    字段说明:
        id: 记录唯一标识（主键，自增）
        track_id: （同一目标在多帧中具有相同的track_id）
        object_type: 目标类型（person/car/motorcycle/bus/truck）
        timestamp: 采集的时间戳（精确到秒）
        x: 目标中心点X坐标（像素）
        y: 目标中心点Y坐标（像素）
        pixel_speed: 像素速度（pixel/s，反映运动快慢）
        direction: 移动方向（North/South/East/West）
        confidence: 检测置信度（0-1之间）
        bbox_x1, bbox_y1, bbox_x2, bbox_y2: 检测框坐标
        created_at: 记录上传到数据库的时间（自动填充）

    """

    # 表名
    __tablename__ = "detection_log"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        comment="记录唯一标识，自增主键"
    )

    track_id = Column(
        Integer,
        nullable=False,
        comment="目标跟踪ID，同一目标在多帧中保持相同ID"
    )

    object_type = Column(
        String(20),
        nullable=False,
        comment="目标类型: person/car/motorcycle/bus/truck"
    )

    timestamp = Column(
        DateTime,
        nullable=False,
        index=True,  # 添加索引，按时间查询很常见
        comment="检测时间戳，精确到秒"
    )

    x = Column(
        Integer,
        nullable=False,
        comment="目标中心点X坐标（像素）"
    )

    y = Column(
        Integer,
        nullable=False,
        comment="目标中心点Y坐标（像素）"
    )

    pixel_speed = Column(
        Float,
        default=0.0,
        comment="像素速度，单位: pixel/s"
    )

    direction = Column(
        String(10),
        default="Unknown",
        comment="移动方向: North/South/East/West/Unknown"
    )

    confidence = Column(
        Float,
        default=0.0,
        comment="检测置信度，范围0-1"
    )

    bbox_x1 = Column(
        Integer,
        nullable=True,
        comment="检测框左上角X坐标"
    )

    bbox_y1 = Column(
        Integer,
        nullable=True,
        comment="检测框左上角Y坐标"
    )

    bbox_x2 = Column(
        Integer,
        nullable=True,
        comment="检测框右下角X坐标"
    )

    bbox_y2 = Column(
        Integer,
        nullable=True,
        comment="检测框右下角Y坐标"
    )

    created_at = Column(
        DateTime,
        default=func.now(),
        comment="记录创建时间，自动填充"
    )

    # 复合索引：按时间和目标类型查询时更高效
    __table_args__ = (
        Index('idx_timestamp_type', 'timestamp', 'object_type'),
        Index('idx_track_id', 'track_id'),
    )

    def __repr__(self) -> str:
        """对象的字符串表示，便于调试"""
        return (
            f"<DetectionLog(id={self.id}, track_id={self.track_id}, "
            f"type={self.object_type}, time={self.timestamp})>"
        )

    def to_dict(self) -> dict:
        """
        将记录转换为字典格式

        返回:
            dict: 包含所有字段的字典，用于JSON序列化
        """
        return {
            "id": self.id,
            "track_id": self.track_id,
            "object_type": self.object_type,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "x": self.x,
            "y": self.y,
            "pixel_speed": self.pixel_speed,
            "direction": self.direction,
            "confidence": self.confidence,
            "bbox": {
                "x1": self.bbox_x1,
                "y1": self.bbox_y1,
                "x2": self.bbox_x2,
                "y2": self.bbox_y2
            },
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


# 交通统计表 (TrafficStat)
class TrafficStat(Base):
    """
    交通统计表
    
    功能说明:
        存储聚合后的交通统计数据，每分钟生成一条记录。
        用于趋势分析、图表展示和AI分析。
    
    字段说明:
        id: 记录唯一标识（主键，自增）
        time_slot: 时间段（精确到分钟，如 2026-03-16 08:30:00）
        person_count: 该时间段内的行人数量
        vehicle_count: 该时间段内的车辆数量（car+bus+truck+motorcycle）
        avg_speed: 平均像素速度
        density: 交通密度（目标数量/ROI面积）
        east_count: 东向流量
        west_count: 西向流量
        south_count: 南向流量
        north_count: 北向流量
        created_at: 记录创建时间

    """

    # 表名
    __tablename__ = "traffic_stat"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
        comment="记录唯一标识，自增主键"
    )

    time_slot = Column(
        DateTime,
        nullable=False,
        unique=True,  # 每分钟只有一条记录
        index=True,
        comment="时间段，精确到分钟"
    )

    person_count = Column(
        Integer,
        default=0,
        comment="行人数量"
    )

    vehicle_count = Column(
        Integer,
        default=0,
        comment="车辆总数（car+bus+truck+motorcycle）"
    )

    avg_speed = Column(
        Float,
        default=0.0,
        comment="平均像素速度，单位: pixel/s"
    )

    density = Column(
        Float,
        default=0.0,
        comment="交通密度，单位: 目标数/ROI面积"
    )

    east_count = Column(
        Integer,
        default=0,
        comment="东向流量"
    )

    west_count = Column(
        Integer,
        default=0,
        comment="西向流量"
    )

    south_count = Column(
        Integer,
        default=0,
        comment="南向流量"
    )

    north_count = Column(
        Integer,
        default=0,
        comment="北向流量"
    )

    created_at = Column(
        DateTime,
        default=func.now(),
        comment="记录创建时间，自动填充"
    )

    __table_args__ = (
        # 按时间范围查询的索引
        Index('idx_time_slot', 'time_slot'),
    )

    def __repr__(self) -> str:
        """对象的字符串表示"""
        return (
            f"<TrafficStat(id={self.id}, time={self.time_slot}, "
            f"person={self.person_count}, vehicle={self.vehicle_count})>"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "time_slot": self.time_slot.isoformat() if self.time_slot else None,
            "person_count": self.person_count,
            "vehicle_count": self.vehicle_count,
            "total_count": self.person_count + self.vehicle_count,
            "avg_speed": round(self.avg_speed, 2),
            "density": self.density,
            "direction_stats": {
                "east": self.east_count,
                "west": self.west_count,
                "south": self.south_count,
                "north": self.north_count
            },
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

    @property
    def total_count(self) -> int:
        """
        计算总流量（行人+车辆）
        
        返回:
            int: 总目标数量
        """
        return self.person_count + self.vehicle_count
