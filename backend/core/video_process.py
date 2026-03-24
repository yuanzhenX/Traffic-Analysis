import asyncio
import base64
import time
import cv2
import numpy as np
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List
from backend.config import VideoConfig, PathConfig
from backend.core.detect_track import DetectionPipeline, FrameResult

"""
================================================================================
视频处理模块 (core/video_process.py)
================================================================================
功能说明:
    本模块负责视频的读取、处理和流式传输。
    
    主要功能:
    1. 支持多种视频源（文件上传、摄像头实时流）
    2. 视频帧的读取和预处理（尺寸调整、格式转换）
    3. 帧率控制，确保处理速度稳定
    4. 视频编码和Base64编码，用于WebSocket传输
    5. 支持暂停、恢复、停止等控制操作

处理流程:
    视频源 → 帧读取 → 预处理 → 检测跟踪 → 编码 → WebSocket发送

作者: Nathan
创建日期: 2026-03-20
"""


# 数据类定义
@dataclass
class VideoInfo:
    """
    视频信息数据类
    
    存储视频文件或视频流的基本信息
    
    属性:
        source_type: 视频源类型（'file'/'camera'）
        source_path: 视频源路径或摄像头索引
        width: 视频宽度（像素）
        height: 视频高度（像素）
        fps: 原始帧率
        total_frames: 总帧数（文件视频）或-1（实时流）
        duration: 视频时长（秒）或-1（实时流）
    """
    source_type: str  # 'file' 或 'camera'
    source_path: str
    width: int
    height: int
    fps: float
    total_frames: int = -1
    duration: float = -1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "source_type": self.source_type,
            "source_path": self.source_path,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "total_frames": self.total_frames,
            "duration": self.duration
        }


@dataclass
class ProcessedFrame:
    """
    处理后的帧数据类
    
    封装处理后的帧图像和相关元数据
    
    属性:
        frame_id: 帧序号
        timestamp: 处理时间戳
        original_frame: 原始帧图像
        annotated_frame: 标注后的帧图像
        detection_result: 检测结果
        base64_image: Base64编码的图像（用于传输）
    """
    frame_id: int
    timestamp: float
    original_frame: np.ndarray
    annotated_frame: np.ndarray
    detection_result: FrameResult
    base64_image: Optional[str] = None
    
    def encode_to_base64(self, quality: int = 80) -> str:
        """
        将标注帧编码为Base64字符串
        
        参数:
            quality: JPEG编码质量（1-100）
            
        返回:
            str: Base64编码的图像字符串
        """
        # 将图像编码为JPEG格式
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        _, buffer = cv2.imencode('.jpg', self.annotated_frame, encode_params)
        
        # 转换为Base64字符串
        base64_str = base64.b64encode(buffer).decode('utf-8')
        self.base64_image = base64_str
        
        return base64_str


# =============================================================================
# 视频捕获类
# =============================================================================
class VideoCapture:
    """
    视频捕获类
    
    封装OpenCV的视频捕获功能，支持文件和摄像头
    
    使用示例:
        # 从文件捕获
        capture = VideoCapture("video.mp4")
        
        # 从摄像头捕获
        capture = VideoCapture(0, source_type='camera')
        
        # 读取帧
        ret, frame = capture.read()
    """
    
    def __init__(self, source: str or int, source_type: str = 'file'):
        """
        初始化视频捕获
        
        参数:
            source: 视频源（文件路径或摄像头索引）
            source_type: 源类型（'file'/'camera'）
        """
        self.source = source
        self.source_type = source_type
        self.cap: Optional[cv2.VideoCapture] = None
        self.video_info: Optional[VideoInfo] = None
        
        # 打开视频源
        self._open()
    
    def _open(self) -> None:
        """
        打开视频源
        
        内部方法，初始化OpenCV VideoCapture对象
        """
        print(f"[视频捕获] 正在打开视频源: {self.source}")
        
        # 创建VideoCapture对象
        if self.source_type == 'camera':
            # 摄像头模式
            camera_index = int(self.source) if isinstance(self.source, str) else self.source
            self.cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)  # Windows使用DirectShow
            
            # 设置摄像头分辨率
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, VideoConfig.FRAME_WIDTH)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, VideoConfig.FRAME_HEIGHT)
            self.cap.set(cv2.CAP_PROP_FPS, VideoConfig.MAX_FPS)
        else:
            # 文件模式
            self.cap = cv2.VideoCapture(str(self.source))
        
        # 检查是否成功打开
        if not self.cap.isOpened():
            raise RuntimeError(f"无法打开视频源: {self.source}")
        
        # 获取视频信息
        self._extract_video_info()
        
        print(f"[视频捕获] 视频源已打开: {self.video_info.width}x{self.video_info.height} @ {self.video_info.fps}fps")
    
    def _extract_video_info(self) -> None:
        """
        提取视频信息
        
        从OpenCV获取视频的基本参数
        """
        # 获取视频属性
        width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        
        # 如果是文件，获取总帧数和时长
        if self.source_type == 'file':
            total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps if fps > 0 else 0
        else:
            total_frames = -1
            duration = -1.0
        
        self.video_info = VideoInfo(
            source_type=self.source_type,
            source_path=str(self.source),
            width=width,
            height=height,
            fps=fps,
            total_frames=total_frames,
            duration=duration
        )
    
    def read(self) -> tuple:
        """
        读取一帧
        
        返回:
            tuple: (ret, frame)
                - ret: 是否成功读取
                - frame: 图像数据（numpy数组）
        """
        if self.cap is None:
            return False, None
        return self.cap.read()
    
    def get_position(self) -> float:
        """
        获取当前播放位置（秒）
        
        返回:
            float: 当前位置（秒）
        """
        if self.cap is None:
            return 0.0
        
        current_frame = self.cap.get(cv2.CAP_PROP_POS_FRAMES)
        fps = self.video_info.fps if self.video_info else 30.0
        return current_frame / fps
    
    def set_position(self, position_sec: float) -> bool:
        """
        设置播放位置（秒）
        
        参数:
            position_sec: 目标位置（秒）
            
        返回:
            bool: 是否设置成功
        """
        if self.cap is None or self.source_type == 'camera':
            return False
        
        fps = self.video_info.fps if self.video_info else 30.0
        target_frame = int(position_sec * fps)
        return self.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
    
    def release(self) -> None:
        """
        释放视频资源
        
        调用此方法释放摄像头或关闭视频文件
        """
        if self.cap is not None:
            self.cap.release()
            self.cap = None
            print("[视频捕获] 视频源已释放")
    
    def is_opened(self) -> bool:
        """
        检查视频源是否打开
        
        返回:
            bool: 是否已打开
        """
        return self.cap is not None and self.cap.isOpened()
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口，自动释放资源"""
        self.release()


# =============================================================================
# 视频处理器类
# =============================================================================
class VideoProcessor:
    """
    视频处理器类
    
    整合视频捕获、检测跟踪、帧处理和结果发送
    
    使用示例:
        processor = VideoProcessor()
        await processor.start("video.mp4", websocket)
    """
    
    def __init__(self):
        """
        初始化视频处理器
        """
        # 视频捕获对象
        self.capture: Optional[VideoCapture] = None
        
        # 检测管道
        self.pipeline: Optional[DetectionPipeline] = None
        
        # 控制标志
        self.is_running: bool = False
        self.is_paused: bool = False
        self.should_stop: bool = False
        
        # 处理统计
        self.frame_count: int = 0
        self.start_time: Optional[float] = None
        self.processing_fps: float = 0.0
        
        # ROI 区域设置
        self.roi_points: Optional[List[tuple]] = None
                
        # 北方方向角度（相对于屏幕上方，顺时针）
        self.direction_angle: float = 0.0
        
        # 回调函数（用于发送结果）
        self.on_frame_processed: Optional[Callable] = None
        
        print("[视频处理器] 初始化完成")
    
    def set_roi(self, points: List[tuple]) -> None:
        """
        设置 ROI 区域
            
        参数:
            points: 多边形顶点列表 [(x1,y1), (x2,y2), ...]
        """
        self.roi_points = points
        if self.pipeline is not None:
            self.pipeline.set_roi(points)
        print(f"[视频处理器] ROI 已设置：{points}")
        
    def set_direction_angle(self, angle: float) -> None:
        """
        设置北方方向角度
            
        参数:
            angle: 北方方向角度（相对于屏幕上方，顺时针）
        """
        self.direction_angle = angle
        if self.pipeline is not None:
            self.pipeline.set_direction_angle(angle)
        print(f"[视频处理器] 北方方向角度已设置：{angle}°")
    
    async def start(
        self, 
        source: str or int, 
        source_type: str = 'file',
        send_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        开始处理视频
        
        参数:
            source: 视频源（文件路径或摄像头索引）
            source_type: 源类型（'file'/'camera'）
            send_callback: 帧处理完成后的回调函数，用于发送结果
            
        返回:
            Dict: 处理统计信息
        """
        print(f"[视频处理器] 开始处理视频: {source}")
        
        # 重置状态
        self.is_running = True
        self.is_paused = False
        self.should_stop = False
        self.frame_count = 0
        self.start_time = time.time()
        self.on_frame_processed = send_callback
        
        try:
            # 创建视频捕获对象
            self.capture = VideoCapture(source, source_type)
            
            # 创建检测管道
            self.pipeline = DetectionPipeline()
            
            # 设置ROI
            if self.roi_points is not None:
                self.pipeline.set_roi(self.roi_points)
            
            # 获取视频原始帧率和目标帧率
            original_fps = self.capture.video_info.fps if self.capture.video_info else 30.0
            target_fps = min(original_fps, VideoConfig.MAX_FPS)
            
            # 计算初始跳帧间隔（每 N 帧处理 1 帧）
            frame_skip = max(1, int(round(original_fps / target_fps)))
            
            # 计算每帧的目标时间间隔（秒）
            frame_duration = 1.0 / target_fps
            
            print(f"[视频处理器] 原始帧率：{original_fps:.1f}fps, 目标帧率：{target_fps:.1f}fps, 初始跳帧间隔：每{frame_skip}帧处理 1 帧，帧间隔：{frame_duration*1000:.1f}ms")
            
            # 主处理循环
            frame_id = 0
            processed_count = 0
            start_time = time.time()  # 记录开始时间
            expected_frame_time = start_time  # 预期帧发送时间（初始为开始时间）
            
            # 【动态跳帧】记录最近处理耗时，用于自适应调整
            recent_processing_times = []
            max_recent_count = 10  # 保留最近 10 次的处理时间
            
            # 等待回调函数被设置（最多等待10秒）
            wait_count = 0
            while self.on_frame_processed is None and self.is_running and not self.should_stop:
                if wait_count % 10 == 0:
                    print(f"[视频处理器] 等待 WebSocket 连接... ({wait_count//10}s)")
                await asyncio.sleep(0.1)
                wait_count += 1
                if wait_count > 100:  # 10秒超时
                    print("[视频处理器] 警告: 等待 WebSocket 连接超时，将继续处理但不发送帧")
                    break
            
            while self.is_running and not self.should_stop:
                # 检查是否暂停
                if self.is_paused:
                    await asyncio.sleep(0.1)
                    continue
                
                # 读取帧
                ret, frame = self.capture.read()
                if not ret:
                    # 视频结束
                    if source_type == 'file':
                        print("[视频处理器] 视频播放完毕")
                        break
                    else:
                        # 摄像头读取失败，重试
                        await asyncio.sleep(0.1)
                        continue
                
                # 跳帧处理：只处理每N帧中的第1帧
                if processed_count % frame_skip != 0:
                    processed_count += 1
                    continue
                
                processed_count += 1
                current_time = time.time()
                
                # 预处理帧
                frame = self._preprocess_frame(frame)
                
                # 执行检测跟踪
                print(f"[视频处理器] 开始处理帧 {frame_id}")
                result = self.pipeline.process(frame, frame_id)
                print(f"[视频处理器] 帧 {frame_id} 检测完成，检测到 {len(result.detections)} 个目标")
                
                # 创建处理后的帧对象
                processed_frame = ProcessedFrame(
                    frame_id=frame_id,
                    timestamp=current_time,
                    original_frame=frame,
                    annotated_frame=result.annotated_frame,
                    detection_result=result
                )
                
                # 编码为Base64
                processed_frame.encode_to_base64(quality=70)
                print(f"[视频处理器] 帧 {frame_id} 编码完成，base64长度: {len(processed_frame.base64_image or '')}")
                
                # 更新统计
                self.frame_count += 1
                self._update_processing_fps()
                
                # 调用回调函数发送结果
                if self.on_frame_processed is not None:
                    print(f"[视频处理器] 发送帧 {frame_id} 到前端")
                    await self.on_frame_processed(processed_frame)
                    print(f"[视频处理器] 帧 {frame_id} 发送完成")
                                    
                    # 【关键优化】帧率控制：基于理想时间戳同步
                    current_time_after_send = time.time()
                    processing_time = current_time_after_send - current_time
                    
                    # 【动态跳帧】记录处理时间
                    recent_processing_times.append(processing_time)
                    if len(recent_processing_times) > max_recent_count:
                        recent_processing_times.pop(0)
                    
                    # 计算下一帧的预期发送时间
                    expected_next_frame_time = expected_frame_time + frame_duration
                    
                    # 如果当前帧发送早于预期，sleep 到预期时间
                    if current_time_after_send < expected_next_frame_time:
                        sleep_time = expected_next_frame_time - current_time_after_send
                        
                        # 【防止视频加速】限制最大 sleep 时间不超过帧间隔的 2 倍
                        max_sleep = frame_duration * 2
                        if sleep_time > max_sleep:
                            print(f"[视频处理器] ⚠️ 检测到时间偏差过大！计划 sleep {sleep_time*1000:.1f}ms，限制为 {max_sleep*1000:.1f}ms")
                            sleep_time = max_sleep
                            # 重置预期时间，避免继续追赶
                            expected_frame_time = current_time_after_send
                        
                        await asyncio.sleep(sleep_time)
                        actual_send_time = time.time()
                        print(f"[视频处理器] 帧率同步：sleep {sleep_time*1000:.1f}ms (处理耗时 {processing_time*1000:.1f}ms, 目标间隔 {frame_duration*1000:.1f}ms)")
                    else:
                        # 已经超时，直接更新预期时间，不追赶
                        actual_send_time = current_time_after_send
                        print(f"[视频处理器] 警告：帧超时 {processing_time*1000:.1f}ms (目标间隔 {frame_duration*1000:.1f}ms)")
                        
                        # 【防止视频加速】如果超时太多，重置预期时间到当前时间
                        timeout_threshold = frame_duration * 3
                        if actual_send_time - expected_next_frame_time > timeout_threshold:
                            print(f"[视频处理器] ⚠️ 严重超时！重置预期时间轴")
                            expected_frame_time = actual_send_time
                        else:
                            # 更新预期帧时间（基于理想节奏，避免累积误差）
                            expected_frame_time = expected_next_frame_time
                    
                    # 【动态跳帧】每 30 帧评估一次，自动调整跳帧间隔
                    if frame_id > 0 and frame_id % 30 == 0:
                        avg_processing_time = sum(recent_processing_times) / len(recent_processing_times)
                        
                        # 如果平均处理时间超过帧间隔的 80%，增加跳帧
                        if avg_processing_time > frame_duration * 0.8:
                            old_skip = frame_skip
                            frame_skip = min(frame_skip + 1, 5)  # 最多跳到每 5 帧处理 1 帧
                            if frame_skip != old_skip:
                                print(f"[视频处理器] 🚨 检测到处理延迟！平均耗时 {avg_processing_time*1000:.1f}ms > 阈值 {frame_duration*1000*0.8:.1f}ms，调整跳帧间隔：{old_skip} → {frame_skip}")
                        # 如果平均处理时间低于帧间隔的 40% 且跳帧>1，减少跳帧
                        elif avg_processing_time < frame_duration * 0.4 and frame_skip > 1:
                            old_skip = frame_skip
                            frame_skip = max(frame_skip - 1, 1)
                            if frame_skip != old_skip:
                                print(f"[视频处理器] ✅ 检测到处理轻松！平均耗时 {avg_processing_time*1000:.1f}ms < 阈值 {frame_duration*1000*0.4:.1f}ms，调整跳帧间隔：{old_skip} → {frame_skip}")
                else:
                    print(f"[视频处理器] 警告：on_frame_processed 回调为 None，帧 {frame_id} 未发送")
                
                frame_id += 1
            
        except Exception as e:
            print(f"[视频处理器] 处理出错: {e}")
            raise
        
        finally:
            # 清理资源
            self._cleanup()
        
        # 返回统计信息
        return self._get_stats()
    
    def _preprocess_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        预处理帧图像
        
        调整尺寸为目标大小，保持纵横比
        
        参数:
            frame: 原始帧图像
            
        返回:
            np.ndarray: 预处理后的帧
        """
        target_width = VideoConfig.FRAME_WIDTH
        target_height = VideoConfig.FRAME_HEIGHT
        
        # 获取原始尺寸
        h, w = frame.shape[:2]
        
        # 如果尺寸已经符合要求，直接返回
        if w == target_width and h == target_height:
            return frame
        
        # 调整尺寸（使用双线性插值）
        resized = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_LINEAR)
        
        return resized
    
    def _update_processing_fps(self) -> None:
        """
        更新处理帧率统计
        """
        if self.start_time is None:
            return
        
        elapsed = time.time() - self.start_time
        if elapsed > 0:
            self.processing_fps = self.frame_count / elapsed
    
    def _cleanup(self) -> None:
        """
        清理资源
        """
        self.is_running = False
        
        # 释放视频捕获
        if self.capture is not None:
            self.capture.release()
            self.capture = None
        
        # 重置检测管道
        if self.pipeline is not None:
            self.pipeline.reset()
        
        print("[视频处理器] 资源已清理")
    
    def _get_stats(self) -> Dict[str, Any]:
        """
        获取处理统计信息
        
        返回:
            Dict: 统计信息字典
        """
        elapsed = time.time() - self.start_time if self.start_time else 0
        
        return {
            "total_frames": self.frame_count,
            "elapsed_time": round(elapsed, 2),
            "average_fps": round(self.processing_fps, 2),
            "status": "completed"
        }
    
    def pause(self) -> None:
        """暂停处理"""
        self.is_paused = True
        print("[视频处理器] 已暂停")
    
    def resume(self) -> None:
        """恢复处理"""
        self.is_paused = False
        print("[视频处理器] 已恢复")
    
    def stop(self) -> None:
        """停止处理"""
        self.should_stop = True
        self.is_running = False
        print("[视频处理器] 已停止")
    
    def get_current_info(self) -> Dict[str, Any]:
        """
        获取当前处理信息
        
        返回:
            Dict: 当前状态信息
        """
        return {
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "frame_count": self.frame_count,
            "processing_fps": round(self.processing_fps, 2),
            "video_info": self.capture.video_info.to_dict() if self.capture else None
        }


# =============================================================================
# 视频文件管理
# =============================================================================
class VideoFileManager:
    """
    视频文件管理类
    
    管理上传的视频文件
    
    使用示例:
        manager = VideoFileManager()
        saved_path = manager.save_uploaded_file(uploaded_file)
    """
    
    def __init__(self, upload_dir: Path = None):
        """
        初始化文件管理器
        
        参数:
            upload_dir: 上传文件保存目录
        """
        self.upload_dir = upload_dir or PathConfig.UPLOADS_DIR
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        
        # 支持的文件格式
        self.supported_formats = {'.mp4', '.avi', '.mov', '.mkv', '.flv'}
    
    def save_uploaded_file(self, file_content: bytes, filename: str) -> Path:
        """
        保存上传的视频文件
        
        参数:
            file_content: 文件内容（字节）
            filename: 原始文件名
            
        返回:
            Path: 保存后的文件路径
            
        异常:
            ValueError: 不支持的文件格式
        """
        # 检查文件格式
        file_ext = Path(filename).suffix.lower()
        if file_ext not in self.supported_formats:
            raise ValueError(f"不支持的文件格式: {file_ext}，支持的格式: {self.supported_formats}")
        
        # 生成唯一文件名（使用时间戳）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_filename = f"video_{timestamp}{file_ext}"
        file_path = self.upload_dir / new_filename
        
        # 保存文件
        with open(file_path, 'wb') as f:
            f.write(file_content)
        
        print(f"[文件管理] 视频已保存: {file_path}")
        return file_path
    
    def get_video_path(self, filename: str) -> Optional[Path]:
        """
        获取视频文件路径
        
        参数:
            filename: 文件名
            
        返回:
            Path: 文件路径，如果不存在则返回None
        """
        file_path = self.upload_dir / filename
        if file_path.exists():
            return file_path
        return None
    
    def list_videos(self) -> List[Dict[str, Any]]:
        """
        列出所有上传的视频
        
        返回:
            List[Dict]: 视频信息列表
        """
        videos = []
        
        for file_path in self.upload_dir.iterdir():
            if file_path.suffix.lower() in self.supported_formats:
                stat = file_path.stat()
                videos.append({
                    "filename": file_path.name,
                    "path": str(file_path),
                    "size": stat.st_size,
                    "created": datetime.fromtimestamp(stat.st_ctime).isoformat()
                })
        
        # 按创建时间排序（最新的在前）
        videos.sort(key=lambda x: x["created"], reverse=True)
        return videos
    
    def delete_video(self, filename: str) -> bool:
        """
        删除视频文件
        
        参数:
            filename: 文件名
            
        返回:
            bool: 是否删除成功
        """
        file_path = self.upload_dir / filename
        if file_path.exists():
            file_path.unlink()
            print(f"[文件管理] 视频已删除: {filename}")
            return True
        return False


# =============================================================================
# 全局视频处理器实例（单例模式）
# =============================================================================
_video_processor: Optional[VideoProcessor] = None


def get_video_processor() -> VideoProcessor:
    """
    获取全局视频处理器实例
    
    使用单例模式确保只有一个处理器实例
    
    返回:
        VideoProcessor: 视频处理器实例
    """
    global _video_processor
    if _video_processor is None:
        _video_processor = VideoProcessor()
    return _video_processor


def reset_video_processor() -> None:
    """
    重置全局视频处理器实例
    
    用于重新开始新的视频处理任务
    """
    global _video_processor
    if _video_processor is not None:
        _video_processor.stop()
        _video_processor = None


# =============================================================================
# 模块测试
# =============================================================================
if __name__ == "__main__":
    """
    模块测试代码
    """
    print("=" * 60)
    print("视频处理模块测试")
    print("=" * 60)
    
    # 测试视频捕获
    print("\n测试1: 摄像头捕获")
    try:
        cap = VideoCapture(0, 'camera')
        print(f"视频信息: {cap.video_info}")
        
        # 读取几帧
        for i in range(10):
            ret, frame = cap.read()
            if ret:
                print(f"帧 {i+1}: {frame.shape}")
        
        cap.release()
        print("摄像头测试通过")
    except Exception as e:
        print(f"摄像头测试失败: {e}")
    
    print("\n测试完成")





