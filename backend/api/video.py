from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
import asyncio
import json
from backend.core.video_process import (
    VideoFileManager,
    get_video_processor,
    reset_video_processor,
    ProcessedFrame
)
from backend.core.data_calc import DataStorageManager, RealtimeStatsCalculator
from backend.db import get_db
from sqlalchemy.orm import Session
import time

"""
================================================================================
视频API路由模块 (api/video.py)
================================================================================
功能说明:
    本模块提供视频相关的REST API接口，包括视频上传、检测控制等功能。
    
    提供的接口:
    1. POST /api/upload_video - 上传视频文件
    2. POST /api/start_detection - 开始视频检测
    3. POST /api/stop_detection - 停止视频检测
    4. POST /api/pause_detection - 暂停/恢复检测
    5. GET /api/video_status - 获取视频处理状态
    6. GET /api/video_list - 获取已上传视频列表
    7. DELETE /api/video/{filename} - 删除视频文件
    8. POST /api/set_roi - 设置ROI区域

作者: Nathan
创建日期: 2026-03-20
"""


# 创建路由
router = APIRouter(
    prefix="/api",
    tags=["video"],
    responses={404: {"description": "Not found"}}
)


# 数据模型
class ROIRequest(BaseModel):
    """ROI设置请求模型"""
    points: List[List[int]]  # [[x1,y1], [x2,y2], ...]
    video_width: Optional[int] = None  # 原始视频宽度，用于坐标转换
    video_height: Optional[int] = None  # 原始视频高度，用于坐标转换


class VideoControlRequest(BaseModel):
    """视频控制请求模型"""
    action: Optional[str] = "start"  # "start", "stop", "pause", "resume"
    source_type: Optional[str] = "file"  # "file" 或 "camera"
    filename: Optional[str] = None  # 当source_type="file"时指定


class DetectionStatusResponse(BaseModel):
    """检测状态响应模型"""
    is_running: bool
    is_paused: bool
    frame_count: int
    processing_fps: float
    video_info: Optional[Dict[str, Any]] = None


# 文件管理器实例
file_manager = VideoFileManager()


@router.post("/upload")
async def upload_video(file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    上传视频文件

    功能:
        接收用户上传的视频文件并保存到服务器

    参数:
        file: 上传的视频文件（支持mp4/avi/mov/mkv/flv格式）

    返回:
        {
            "success": true,
            "filename": "video_20260316_120000.mp4",
            "message": "视频上传成功"
        }

    异常:
        400: 不支持的文件格式
        500: 文件保存失败
    """
    try:
        # 读取文件内容
        content = await file.read()

        # 保存文件
        saved_path = file_manager.save_uploaded_file(content, file.filename)

        return {
            "success": True,
            "filename": saved_path.name,
            "message": "视频上传成功"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")


@router.get("/video_list")
async def get_video_list() -> Dict[str, Any]:
    """
    获取已上传的视频列表

    返回:
        {
            "videos": [
                {
                    "filename": "video_20260316_120000.mp4",
                    "path": "...",
                    "size": 1234567,
                    "created": "2026-03-16T12:00:00"
                }
            ]
        }
    """
    videos = file_manager.list_videos()
    return {"videos": videos}


@router.get("/video/{filename}")
async def get_video_file(filename: str):
    """
    获取视频文件

    参数:
        filename: 视频文件名

    返回:
        视频文件流
    """
    file_path = file_manager.get_video_path(filename)

    if not file_path:
        raise HTTPException(status_code=404, detail="视频文件不存在")

    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        filename=filename
    )


@router.delete("/video/{filename}")
async def delete_video(filename: str) -> Dict[str, Any]:
    """
    删除视频文件

    参数:
        filename: 要删除的文件名

    返回:
        {"success": true, "message": "视频已删除"}
    """
    success = file_manager.delete_video(filename)

    if not success:
        raise HTTPException(status_code=404, detail="视频文件不存在")

    return {
        "success": True,
        "message": "视频已删除"
    }


@router.post("/start_detection")
async def start_detection(
    request: VideoControlRequest
) -> Dict[str, Any]:
    """
    开始视频检测

    功能:
        启动视频处理流程，开始目标检测和跟踪

    参数:
        request: 控制请求
            - source_type: "file" 或 "camera"
            - filename: 视频文件名（source_type="file"时必需）

    返回:
        {"success": true, "message": "检测已启动"}

    异常:
        400: 参数错误
        404: 视频文件不存在
        409: 检测已在运行中
    """
    processor = get_video_processor()

    # 检查是否已在运行
    if processor.is_running:
        raise HTTPException(status_code=409, detail="检测已在运行中，请先停止当前任务")

    try:
        # 确定视频源
        if request.source_type == "camera":
            source = 0  # 默认摄像头
        else:
            if not request.filename:
                raise HTTPException(status_code=400, detail="请指定视频文件名")

            video_path = file_manager.get_video_path(request.filename)
            if not video_path:
                raise HTTPException(status_code=404, detail="视频文件不存在")
            source = str(video_path)

        # 启动检测（在后台运行）
        _ = asyncio.create_task(
            processor.start(
                source=source,
                source_type=request.source_type,
                send_callback=None  # WebSocket单独处理
            )
        )

        return {
            "success": True,
            "message": "检测已启动",
            "source": str(source)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动检测失败: {str(e)}")


@router.post("/stop_detection")
async def stop_detection() -> Dict[str, Any]:
    """
    停止视频检测

    返回:
        {"success": true, "message": "检测已停止", "stats": {...}}
    """
    processor = get_video_processor()

    if not processor.is_running:
        return {
            "success": True,
            "message": "检测未在运行",
            "stats": None
        }

    # 停止处理
    processor.stop()

    # 获取统计信息
    stats = processor.get_current_info()

    # 重置处理器
    reset_video_processor()

    return {
        "success": True,
        "message": "检测已停止",
        "stats": stats
    }


@router.post("/pause_detection")
async def pause_detection() -> Dict[str, Any]:
    """
    暂停/恢复视频检测

    功能:
        切换暂停状态，如果当前在运行则暂停，如果已暂停则恢复

    返回:
        {"success": true, "is_paused": true, "message": "检测已暂停"}
    """
    processor = get_video_processor()

    if not processor.is_running:
        raise HTTPException(status_code=400, detail="检测未在运行")

    if processor.is_paused:
        processor.resume()
        return {
            "success": True,
            "is_paused": False,
            "message": "检测已恢复"
        }
    else:
        processor.pause()
        return {
            "success": True,
            "is_paused": True,
            "message": "检测已暂停"
        }


@router.get("/video_status", response_model=DetectionStatusResponse)
async def get_video_status() -> DetectionStatusResponse:
    """
    获取视频处理状态

    返回:
        当前检测状态，包括是否运行、帧数、帧率等
    """
    processor = get_video_processor()
    info = processor.get_current_info()

    return DetectionStatusResponse(
        is_running=info["is_running"],
        is_paused=info["is_paused"],
        frame_count=info["frame_count"],
        processing_fps=info["processing_fps"],
        video_info=info.get("video_info")
    )


@router.post("/set_roi")
async def set_roi(
    request: ROIRequest
) -> Dict[str, Any]:
    """
    设置ROI区域

    功能:
        设置感兴趣区域，只有区域内的目标才会被统计
        自动将前端坐标（基于原始视频分辨率）转换为后端处理分辨率

    参数:
        request: ROI请求
            - points: 多边形顶点坐标列表 [[x1,y1], [x2,y2], ...]
            - video_width: 原始视频宽度（可选，用于坐标转换）
            - video_height: 原始视频高度（可选，用于坐标转换）

    返回:
        {"success": true, "message": "ROI区域已设置"}
    """
    try:
        from backend.config import VideoConfig

        # 获取前端传来的视频原始分辨率（如果有）
        video_width = getattr(request, 'video_width', None)
        video_height = getattr(request, 'video_height', None)

        # 转换坐标格式
        points = [(p[0], p[1]) for p in request.points]
        print(f"[ROI设置] 原始坐标: {points}")
        print(f"[ROI设置] 原始视频分辨率: {video_width}x{video_height}")
        print(f"[ROI设置] 后端处理分辨率: {VideoConfig.FRAME_WIDTH}x{VideoConfig.FRAME_HEIGHT}")

        # 如果提供了原始分辨率，进行坐标缩放
        if video_width and video_height and video_width > 0 and video_height > 0:
            scale_x = VideoConfig.FRAME_WIDTH / video_width
            scale_y = VideoConfig.FRAME_HEIGHT / video_height

            scaled_points = [
                (int(x * scale_x), int(y * scale_y)) for x, y in points
            ]
            print(f"[ROI设置] 缩放后坐标: {scaled_points} (scale_x={scale_x:.4f}, scale_y={scale_y:.4f})")
            points = scaled_points
        else:
            print(f"[ROI设置] 未提供原始分辨率，使用原始坐标（假设与处理分辨率一致）")

        # 设置到视频处理器
        processor = get_video_processor()
        processor.set_roi(points)

        return {
            "success": True,
            "message": "ROI区域已设置",
            "points": points
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"设置ROI失败: {str(e)}")


# WebSocket端点（实时数据传输）
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    """
    WebSocket实时数据传输

    功能:
        通过WebSocket实时推送检测画面和统计数据

    数据格式:
        {
            "type": "frame",
            "frame_id": 123,
            "image": "base64_encoded_image",
            "stats": {
                "person_count": 10,
                "vehicle_count": 5,
                "avg_speed": 12.5
            }
        }
    """
    await websocket.accept()

    # 创建数据存储管理器
    storage_manager = DataStorageManager(db)
    stats_calculator = RealtimeStatsCalculator()

    last_save_time = 0

    try:
        # 获取视频处理器
        processor = get_video_processor()

        # 定义帧处理回调
        async def send_frame(processed_frame: ProcessedFrame):
            nonlocal last_save_time
            """发送处理后的帧数据"""
            try:
                # 计算实时统计
                detections = [
                    d.to_dict() for d in processed_frame.detection_result.detections
                ]
                stats = stats_calculator.calculate(detections)

                current_time = time.perf_counter()

                if current_time - last_save_time >= 1.0:
                    try:
                        loop = asyncio.get_event_loop()

                        await loop.run_in_executor(
                            None,
                            lambda: storage_manager.save_detections(
                                detections, stats.timestamp
                            )
                        )

                        last_save_time = current_time

                    except Exception as save_error:
                        print(f"[WebSocket] 数据保存失败: {save_error}")

                # 发送数据
                data = {
                    "type": "frame",
                    "frame_id": processed_frame.frame_id,
                    "timestamp": processed_frame.timestamp,
                    "image": processed_frame.base64_image,
                    "stats": {
                        "person_count": stats.person_count,
                        "vehicle_count": stats.vehicle_count,
                        "total_count": stats.total_count,
                        "avg_speed": round(stats.avg_speed, 2),
                        "density": round(stats.density, 4),
                        "direction_counts": stats.direction_counts
                    }
                }

                await websocket.send_json(data)
            except Exception as e:
                print(f"[WebSocket] 发送帧数据失败: {e}")

        # 设置回调函数
        processor.on_frame_processed = send_frame

        # 保持连接
        while True:
            # 接收客户端消息（用于心跳检测）
            try:
                message = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=30.0
                )

                # 处理客户端消息
                try:
                    msg_data = json.loads(message)
                    if msg_data.get("action") == "ping":
                        await websocket.send_json({"type": "pong"})
                except json.JSONDecodeError:
                    pass

            except asyncio.TimeoutError:
                # 发送心跳
                await websocket.send_json({"type": "heartbeat"})

    except WebSocketDisconnect:
        print("[WebSocket] 客户端断开连接")
    except Exception as e:
        print(f"[WebSocket] 错误: {e}")
    finally:
        # 清理
        processor = get_video_processor()
        processor.on_frame_processed = None
