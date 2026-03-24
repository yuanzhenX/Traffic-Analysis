import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional, Any
from collections import defaultdict, deque
from dataclasses import dataclass, field
from ultralytics import YOLO
from deep_sort_realtime.deepsort_tracker import DeepSort
from backend.config import ModelConfig, VideoConfig

"""
================================================================================
目标检测与跟踪模块 (core/detect_track.py)
================================================================================
功能说明:
    本模块实现了基于YOLOv8的目标检测和基于DeepSort的多目标跟踪功能。
    
    主要功能:
    1. 使用YOLOv8检测视频帧中的行人和车辆
    2. 使用DeepSort算法为检测到的目标分配唯一ID并持续跟踪
    3. 维护每个目标的历史轨迹（最近90帧位置）
    4. 计算目标的速度和移动方向
    5. 支持ROI区域过滤

处理流程:
    视频帧 → YOLOv8检测 → DeepSort跟踪 → 轨迹更新 → 速度/方向计算

作者: Nathan
创建日期: 2026-03-20
"""


# 数据类定义
@dataclass
class DetectionResult:
    """
    检测结果数据类
    
    用于封装单个目标的检测和跟踪信息
    
    属性:
        track_id: 跟踪ID，同一目标在多帧中保持不变
        class_id: 类别ID（0=person, 2=car等）
        class_name: 类别名称（'person', 'car'等）
        confidence: 检测置信度（0-1）
        bbox: 检测框坐标 (x1, y1, x2, y2)
        center: 中心点坐标 (x, y)
        speed: 像素速度（pixel/s）
        direction: 移动方向（North/South/East/West/Unknown）
        trajectory: 历史轨迹点列表
    """
    track_id: int
    class_id: int
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]
    center: Tuple[int, int]
    speed: float = 0.0
    direction: str = "Unknown"
    trajectory: List[Tuple[int, int]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式，便于JSON序列化"""
        return {
            "track_id": self.track_id,
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": round(self.confidence, 3) if self.confidence is not None else 0.0,
            "bbox": self.bbox,
            "center": self.center,
            "speed": round(self.speed, 2) if self.speed is not None else 0.0,
            "direction": self.direction,
            "trajectory": self.trajectory
        }


@dataclass
class FrameResult:
    """
    帧处理结果数据类
    
    封装一帧图像的所有检测结果和统计信息
    
    属性:
        frame_id: 帧序号
        timestamp: 时间戳
        detections: 检测到的目标列表
        person_count: 行人数量
        vehicle_count: 车辆数量
        avg_speed: 平均速度
        annotated_frame: 标注后的帧图像（用于显示）
    """
    frame_id: int
    timestamp: float
    detections: List[DetectionResult]
    person_count: int = 0
    vehicle_count: int = 0
    avg_speed: float = 0.0
    annotated_frame: Optional[np.ndarray] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "detections": [d.to_dict() for d in self.detections],
            "person_count": self.person_count,
            "vehicle_count": self.vehicle_count,
            "avg_speed": round(self.avg_speed, 2)
        }


# =============================================================================
# 检测器类
# =============================================================================
class ObjectDetector:
    """
    目标检测器类
    
    基于YOLOv8实现目标检测功能
    
    使用示例:
        detector = ObjectDetector()
        results = detector.detect(frame)
    """
    
    def __init__(self):
        """
        初始化检测器
        
        加载YOLOv8模型并设置检测参数
        """
        print(f"[检测器初始化] 正在加载YOLOv8模型: {ModelConfig.MODEL_PATH}")
        
        # 加载YOLOv8模型
        # 模型文件需提前下载并放置在models目录下
        self.model = YOLO(ModelConfig.MODEL_PATH)
        
        # 设置推理设备（GPU/CPU）
        self.device = ModelConfig.DEVICE
        print(f"[检测器初始化] 使用设备: {self.device}")
        
        # 检测参数
        self.conf_threshold = ModelConfig.CONFIDENCE_THRESHOLD
        self.iou_threshold = ModelConfig.IOU_THRESHOLD
        self.classes = ModelConfig.DETECT_CLASSES
        
        print("[检测器初始化] 完成")
    
    def detect(self, frame: np.ndarray) -> List[Tuple[int, float, Tuple[int, int, int, int]]]:
        """
        检测单帧图像中的目标
        
        参数:
            frame: 输入图像（BGR格式，OpenCV读取）
            
        返回:
            List[Tuple]: 检测结果列表，每个元素为 (class_id, confidence, bbox)
                - class_id: 类别ID
                - confidence: 置信度
                - bbox: 检测框坐标 (x1, y1, x2, y2)
        
        使用示例:
            detections = detector.detect(frame)
            for class_id, conf, bbox in detections:
                print(f"检测到: {class_id}, 置信度: {conf}")
        """
        # 执行推理
        # verbose=False 禁用YOLO的输出信息
        results = self.model(
            frame,
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            classes=self.classes,
            device=self.device,
            verbose=False
        )
        
        # 解析检测结果
        detections = []
        
        # results[0] 包含当前帧的检测结果
        if len(results) > 0 and results[0].boxes is not None:
            boxes = results[0].boxes
            
            # 遍历所有检测框
            for box in boxes:
                # 获取类别ID
                class_id = int(box.cls.item())
                
                # 获取置信度
                confidence = float(box.conf.item())
                
                # 获取检测框坐标并转换为整数
                xyxy = box.xyxy[0].cpu().numpy().astype(int)
                bbox = (xyxy[0], xyxy[1], xyxy[2], xyxy[3])
                
                detections.append((class_id, confidence, bbox))
        
        return detections
    
    def get_class_name(self, class_id: int) -> str:
        """
        获取类别名称
        
        参数:
            class_id: 类别ID
            
        返回:
            str: 类别名称
        """
        return ModelConfig.CLASS_NAMES.get(class_id, "unknown")


# =============================================================================
# 跟踪器类
# =============================================================================
class ObjectTracker:
    """
    目标跟踪器类
    
    基于DeepSort实现多目标跟踪功能
    
    使用示例:
        tracker = ObjectTracker()
        tracks = tracker.update(detections, frame)
    """
    
    def __init__(self):
        """
        初始化跟踪器
        
        配置DeepSort参数
        """
        print("[跟踪器初始化] 正在初始化DeepSort跟踪器")
        
        # 初始化DeepSort跟踪器
        # max_age: 目标丢失后保留的最大帧数
        # n_init: 确认跟踪所需的最小检测次数
        # max_cosine_distance: 特征距离阈值
        self.tracker = DeepSort(
            max_age=30,           # 目标丢失30帧后删除
            n_init=3,             # 连续检测3次后确认跟踪
            max_cosine_distance=0.4,  # 外观特征匹配阈值
            embedder="mobilenet",     # 使用MobileNet提取外观特征
            half=True,                # 使用半精度加速
            bgr=True                  # 输入为BGR格式
        )
        
        print("[跟踪器初始化] 完成")
    
    def update(
        self, 
        detections: List[Tuple[int, float, Tuple[int, int, int, int]]], 
        frame: np.ndarray
    ) -> List[Tuple[int, int, float, Tuple[int, int, int, int]]]:
        """
        更新跟踪状态
        
        参数:
            detections: 检测结果列表 [(class_id, confidence, bbox), ...]
            frame: 当前帧图像
            
        返回:
            List[Tuple]: 跟踪结果列表 [(track_id, class_id, confidence, bbox), ...]
        
        说明:
            DeepSort会为每个检测到的目标分配一个唯一的track_id
            同一目标在多帧中会保持相同的track_id
        """
        # 转换检测格式为DeepSort要求的格式
        # DeepSort要求: [(bbox, confidence, class_id), ...]
        # bbox格式: [left, top, w, h]（注意是宽高而非右下角坐标）
        deepsort_detections = []
        for class_id, confidence, (x1, y1, x2, y2) in detections:
            width = x2 - x1
            height = y2 - y1
            bbox = [x1, y1, width, height]
            deepsort_detections.append((bbox, confidence, class_id))
        
        # 更新跟踪器
        tracks = self.tracker.update_tracks(deepsort_detections, frame=frame)
        
        # 解析跟踪结果
        results = []
        for track in tracks:
            if not track.is_confirmed():
                # 跳过未确认的跟踪（新目标需要连续检测n_init次才会确认）
                continue
            
            track_id = track.track_id
            class_id = track.det_class
            
            # 获取检测框坐标
            ltrb = track.to_ltrb()  # 返回 [left, top, right, bottom]
            bbox = (int(ltrb[0]), int(ltrb[1]), int(ltrb[2]), int(ltrb[3]))
            
            # 获取置信度（从原始检测中获取）
            confidence = track.get_det_conf() if hasattr(track, 'get_det_conf') else 0.9
            
            results.append((track_id, class_id, confidence, bbox))
        
        return results


# =============================================================================
# 轨迹管理类
# =============================================================================
class TrajectoryManager:
    """
    轨迹管理器类
    
    管理所有目标的轨迹历史，计算速度和方向
    
    使用示例:
        manager = TrajectoryManager()
        manager.update(track_id, center)
        speed = manager.get_speed(track_id)
        direction = manager.get_direction(track_id)
    """
    
    def __init__(self, max_history: int = 30):
        """
        初始化轨迹管理器
            
        参数:
            max_history: 最大历史长度（帧数），默认 30 帧（约 1 秒@30fps）
        """
        # 存储每个目标的轨迹历史
        # key: track_id, value: 双端队列存储位置点
        self.trajectories: Dict[int, deque] = defaultdict(
            lambda: deque(maxlen=max_history)
        )
        
        # 最大历史长度
        self.max_history = max_history
        
        # 帧率，用于计算速度
        self.fps = VideoConfig.MAX_FPS
    
    def update(self, track_id: int, center: Tuple[int, int]) -> None:
        """
        更新目标的轨迹
        
        参数:
            track_id: 目标跟踪ID
            center: 目标中心点坐标 (x, y)
        """
        self.trajectories[track_id].append(center)
    
    def get_trajectory(self, track_id: int) -> List[Tuple[int, int]]:
        """
        获取目标的轨迹历史
        
        参数:
            track_id: 目标跟踪ID
            
        返回:
            List[Tuple]: 轨迹点列表 [(x1,y1), (x2,y2), ...]
        """
        return list(self.trajectories[track_id])
    
    def get_speed(self, track_id: int) -> float:
        """
        计算目标的像素速度
        
        使用最近两帧的位置计算瞬时速度
        
        公式: speed = sqrt((x2-x1)^2 + (y2-y1)^2) * fps
        
        参数:
            track_id: 目标跟踪ID
            
        返回:
            float: 像素速度（pixel/s）
        """
        trajectory = self.trajectories[track_id]
        
        # 需要至少2个点才能计算速度
        if len(trajectory) < 2:
            return 0.0
        
        # 获取最近两个位置点
        (x1, y1) = trajectory[-2]  # 上一帧位置
        (x2, y2) = trajectory[-1]  # 当前帧位置
        
        # 计算像素位移
        pixel_distance = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        
        # 计算速度: 位移 * 帧率
        # 假设两帧之间的时间间隔为 1/fps 秒
        speed = pixel_distance * self.fps
        
        return speed
    
    def get_direction(self, track_id: int) -> str:
        """
        判断目标的移动方向
        
        使用最近两帧的位置变化判断方向
        
        判断规则:
            |dx| > |dy| 时:
                dx > 0 → East（向东）
                dx < 0 → West（向西）
            |dy| > |dx| 时:
                dy > 0 → South（向南）
                dy < 0 → North（向北）
        
        参数:
            track_id: 目标跟踪ID
            
        返回:
            str: 方向字符串（North/South/East/West/Unknown）
        """
        trajectory = self.trajectories[track_id]
        
        # 需要至少2个点才能判断方向
        if len(trajectory) < 2:
            return "Unknown"
        
        # 获取最近两个位置点
        (x1, y1) = trajectory[-2]
        (x2, y2) = trajectory[-1]
        
        # 计算位移向量
        dx = x2 - x1
        dy = y2 - y1
        
        # 判断方向
        if abs(dx) > abs(dy):
            # 水平方向移动为主
            if dx > 0:
                return "East"
            elif dx < 0:
                return "West"
        else:
            # 垂直方向移动为主
            if dy > 0:
                return "South"
            elif dy < 0:
                return "North"
        
        return "Unknown"
    
    def remove_track(self, track_id: int) -> None:
        """
        删除目标的轨迹记录
        
        当目标离开画面或跟踪丢失时调用
        
        参数:
            track_id: 目标跟踪ID
        """
        if track_id in self.trajectories:
            del self.trajectories[track_id]
    
    def clear(self) -> None:
        """清空所有轨迹记录"""
        self.trajectories.clear()


# =============================================================================
# 检测跟踪管道类
# =============================================================================
class DetectionPipeline:
    """
    检测跟踪管道类
    
    整合检测器、跟踪器和轨迹管理器，提供完整的检测跟踪流程
    
    使用示例:
        pipeline = DetectionPipeline()
        result = pipeline.process(frame, frame_id)
    """
    
    def __init__(self):
        """
        初始化检测跟踪管道
        
        创建检测器、跟踪器和轨迹管理器实例
        """
        print("[检测管道] 正在初始化...")
        
        # 创建检测器
        self.detector = ObjectDetector()
        
        # 创建跟踪器
        self.tracker = ObjectTracker()
        
        # 创建轨迹管理器
        self.trajectory_manager = TrajectoryManager(
            max_history=VideoConfig.TRACK_HISTORY_LENGTH
        )
        
        # ROI 区域（多边形顶点列表）
        self.roi_points: Optional[List[Tuple[int, int]]] = None
                
        # 北方方向角度（相对于屏幕上方，顺时针）
        self.direction_angle: float = 0.0
        
        # 当前活跃的跟踪ID集合
        self.active_tracks: set = set()
        
        print("[检测管道] 初始化完成")
    
    def set_roi(self, points: List[Tuple[int, int]]) -> None:
        """
        设置 ROI 区域
                
        参数:
            points: 多边形顶点坐标列表 [(x1,y1), (x2,y2), ...]
                   如果为 None 或空列表，则使用全画面
        """
        self.roi_points = points if points else None
        print(f"[检测管道] ROI 区域已设置：{points}")
        
    def set_direction_angle(self, angle: float) -> None:
        """
        设置北方方向角度
                
        参数:
            angle: 北方方向角度（相对于屏幕上方，顺时针）
        """
        self.direction_angle = angle
        print(f"[检测管道] 北方方向角度已设置：{angle}°")
    
    def is_in_roi(self, point: Tuple[int, int]) -> bool:
        """
        判断点是否在ROI区域内
        
        使用OpenCV的pointPolygonTest函数判断点是否在多边形内
        
        参数:
            point: 点坐标 (x, y)
            
        返回:
            bool: 是否在ROI内（True表示在区域内或ROI未设置）
        """
        # 如果未设置ROI，则全画面有效
        if self.roi_points is None or len(self.roi_points) < 3:
            return True
        
        # 转换为numpy数组
        roi_array = np.array(self.roi_points, dtype=np.int32)
        
        # pointPolygonTest返回值:
        # >0: 点在多边形内部
        # =0: 点在多边形边界上
        # <0: 点在多边形外部
        result = cv2.pointPolygonTest(roi_array, point, False)
        
        return result >= 0
    
    def _convert_direction(self, raw_direction: str) -> str:
        """
        根据北方方向角度转换实际方向
        
        原理：
            - 默认情况下（角度=0），屏幕上方为北，下方为南，左西右东
            - 当用户设置北方角度后，需要旋转方向判断
            - 例如：北方角度=90°时，屏幕右侧为北，左侧为南
        
        参数:
            raw_direction: 基于屏幕坐标的原始方向（North/South/East/West）
            
        返回:
            str: 实际地理方向
        """
        if raw_direction == "Unknown":
            return raw_direction
        
        # 如果未设置角度或角度为 0，直接返回原始方向
        if self.direction_angle == 0.0:
            return raw_direction
        
        # 定义方向到角度的映射（以屏幕上方为 0°，顺时针）
        direction_angles = {
            "North": 0,      # 向上
            "East": 90,      # 向右
            "South": 180,    # 向下
            "West": 270      # 向左
        }
        
        # 获取原始方向的角度
        raw_angle = direction_angles.get(raw_direction, 0)
        
        # 加上北方偏移角度，得到实际地理方向的角度
        actual_angle = (raw_angle + self.direction_angle) % 360
        
        # 将角度转换回方向（每个方向占 90°）
        # 0-45°和 315-360° → North
        # 45-135° → East
        # 135-225° → South
        # 225-315° → West
        if actual_angle < 45 or actual_angle >= 315:
            return "North"
        elif actual_angle < 135:
            return "East"
        elif actual_angle < 225:
            return "South"
        else:
            return "West"
    
    def process(self, frame: np.ndarray, frame_id: int = 0) -> FrameResult:
        """
        处理单帧图像
        
        完整流程: 检测 → 跟踪 → 轨迹更新 → 速度/方向计算 → 统计
        
        参数:
            frame: 输入图像（BGR格式）
            frame_id: 帧序号，用于标识
            
        返回:
            FrameResult: 包含所有检测结果和统计信息的对象
        """
        import time
        timestamp = time.time()
        
        # 步骤1: 目标检测
        # 使用YOLOv8检测当前帧中的所有目标
        detections = self.detector.detect(frame)
        
        # 步骤2: 目标跟踪
        # 使用DeepSort更新跟踪状态，获取跟踪ID
        tracks = self.tracker.update(detections, frame)
        
        # 步骤3: 处理每个跟踪目标
        detection_results = []
        current_tracks = set()
        
        print(f"[检测管道] 跟踪到 {len(tracks)} 个目标")
        for track_id, class_id, confidence, bbox in tracks:
            # 计算中心点
            x1, y1, x2, y2 = bbox
            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2
            center = (center_x, center_y)
            
            # ROI过滤: 只处理在ROI区域内的目标
            in_roi = self.is_in_roi(center)
            print(f"[检测管道] 目标 {track_id} 中心点 {center} 在ROI内: {in_roi}")
            if not in_roi:
                continue
            
            # 更新轨迹
            self.trajectory_manager.update(track_id, center)
            
            # 记录当前活跃的跟踪
            current_tracks.add(track_id)
            
            # 计算速度和方向
            speed = self.trajectory_manager.get_speed(track_id)
            raw_direction = self.trajectory_manager.get_direction(track_id)
            
            # 根据北方方向角度转换实际方向
            direction = self._convert_direction(raw_direction)
            
            # 获取轨迹历史
            trajectory = self.trajectory_manager.get_trajectory(track_id)
            
            # 创建检测结果对象
            result = DetectionResult(
                track_id=track_id,
                class_id=class_id,
                class_name=self.detector.get_class_name(class_id),
                confidence=confidence,
                bbox=bbox,
                center=center,
                speed=speed,
                direction=direction,
                trajectory=trajectory.copy()
            )
            
            detection_results.append(result)
        
        # 步骤4: 清理丢失目标的轨迹
        lost_tracks = self.active_tracks - current_tracks
        for track_id in lost_tracks:
            self.trajectory_manager.remove_track(track_id)
        self.active_tracks = current_tracks
        
        # 步骤5: 统计信息
        person_count = sum(1 for d in detection_results if d.class_name == "person")
        vehicle_count = sum(1 for d in detection_results if d.class_name != "person")
        
        # 计算平均速度
        if detection_results:
            avg_speed = sum(d.speed for d in detection_results) / len(detection_results)
        else:
            avg_speed = 0.0
        
        # 步骤6: 创建标注帧
        annotated_frame = self._annotate_frame(frame.copy(), detection_results)
        
        # 返回帧处理结果
        return FrameResult(
            frame_id=frame_id,
            timestamp=timestamp,
            detections=detection_results,
            person_count=person_count,
            vehicle_count=vehicle_count,
            avg_speed=avg_speed,
            annotated_frame=annotated_frame
        )
    
    def _annotate_frame(
        self, 
        frame: np.ndarray, 
        detections: List[DetectionResult]
    ) -> np.ndarray:
        """
        在帧上绘制检测结果
        
        绘制内容:
        - 检测框
        - 目标ID和类别
        - 运动轨迹
        - ROI区域
        
        参数:
            frame: 原始帧图像
            detections: 检测结果列表
            
        返回:
            np.ndarray: 标注后的帧图像
        """
        # 定义颜色映射
        colors = {
            "person": (0, 255, 0),      # 绿色: 行人
            "car": (255, 0, 0),         # 蓝色: 汽车
            "motorcycle": (0, 0, 255),  # 红色: 摩托车
            "bus": (255, 255, 0),       # 青色: 公交车
            "truck": (255, 0, 255)      # 紫色: 卡车
        }
        
        # 绘制ROI区域
        if self.roi_points is not None and len(self.roi_points) >= 3:
            roi_array = np.array(self.roi_points, dtype=np.int32)
            cv2.polylines(
                frame, 
                [roi_array], 
                isClosed=True, 
                color=(0, 255, 255),  # 黄色
                thickness=2
            )
            # 填充半透明
            overlay = frame.copy()
            cv2.fillPoly(overlay, [roi_array], (0, 255, 255))
            cv2.addWeighted(frame, 0.7, overlay, 0.3, 0, frame)
        
        # 绘制每个目标的检测框和轨迹
        for det in detections:
            x1, y1, x2, y2 = det.bbox
            color = colors.get(det.class_name, (128, 128, 128))
            
            # 绘制检测框
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            
            # 绘制标签
            label = f"{det.class_name} #{det.track_id}"
            label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            label_y = y1 - 10 if y1 - 10 > 10 else y1 + 20
            
            # 标签背景
            cv2.rectangle(
                frame, 
                (x1, label_y - label_size[1] - 5), 
                (x1 + label_size[0], label_y + 5),
                color, 
                -1
            )
            # 标签文字
            cv2.putText(
                frame, label, (x1, label_y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2
            )
            
            # 绘制速度和方向
            info = f"{det.speed:.1f}px/s {det.direction}"
            cv2.putText(
                frame, info, (x1, y2 + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1
            )
            
            # 绘制轨迹
            if len(det.trajectory) > 1:
                points = np.array(det.trajectory, dtype=np.int32)
                cv2.polylines(frame, [points], False, color, 2)
                
                # 绘制轨迹点
                for point in det.trajectory[::10]:  # 每10帧画一个点
                    cv2.circle(frame, point, 3, color, -1)
        
        # 绘制统计信息
        stats_text = [
            f"Persons: {sum(1 for d in detections if d.class_name == 'person')}",
            f"Vehicles: {sum(1 for d in detections if d.class_name != 'person')}",
            f"Total: {len(detections)}"
        ]
        
        y_offset = 30
        for text in stats_text:
            cv2.putText(
                frame, text, (10, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2
            )
            y_offset += 30
        
        return frame
    
    def reset(self) -> None:
        """
        重置检测管道状态
        
        用于重新开始检测时清理历史数据
        """
        self.trajectory_manager.clear()
        self.active_tracks.clear()
        print("[检测管道] 状态已重置")


# =============================================================================
# 模块测试
# =============================================================================
if __name__ == "__main__":
    """
    模块测试代码
    
    运行此文件可测试检测跟踪功能
    """
    print("=" * 60)
    print("检测跟踪模块测试")
    print("=" * 60)
    
    # 创建测试视频（使用摄像头）
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("错误: 无法打开摄像头")
        exit(1)
    
    # 创建检测管道
    pipeline = DetectionPipeline()
    
    frame_id = 0
    
    print("按 'q' 键退出测试")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # 处理帧
        result = pipeline.process(frame, frame_id)
        
        # 显示结果
        cv2.imshow("Detection Test", result.annotated_frame)
        
        # 打印统计信息
        if frame_id % 30 == 0:
            print(f"Frame {frame_id}: {result.person_count} persons, "
                  f"{result.vehicle_count} vehicles")
        
        frame_id += 1
        
        # 按'q'退出
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()
    print("测试结束")
