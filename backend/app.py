from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from contextlib import asynccontextmanager
from pathlib import Path
from backend.config import AppConfig, PathConfig
from backend.db import init_db
from backend.api import video, data, ai

"""
================================================================================
FastAPI主应用入口 (app.py)
================================================================================
功能说明:
    本文件是后端服务的入口点，使用FastAPI框架构建REST API服务。
    
    主要功能:
    1. 创建FastAPI应用实例
    2. 配置CORS跨域支持
    3. 挂载静态文件服务（前端文件）
    4. 注册API路由
    5. 初始化数据库
    6. 提供应用生命周期管理（启动/关闭事件）

作者: Nathan
创建日期: 2026-03-20
"""


# 管理应用的启动和关闭事件
@asynccontextmanager
async def lifespan(app):

    # ===== 启动事件 =====
    print("=" * 60)
    print(f"{AppConfig.APP_NAME} v{AppConfig.APP_VERSION}")   # 打印应用名字和版本
    print("=" * 60)

    # 初始化数据库
    print("[启动] 正在初始化数据库...")
    init_db()

    # 确保目录存在
    PathConfig.ensure_directories()

    print(f"[启动] 服务已启动，访问地址: http://localhost:8000")
    print("[启动] API文档地址: http://localhost:8000/docs")
    print("=" * 60)

    yield  # 应用运行期间

    # ===== 关闭事件 =====
    print("[关闭] 正在关闭服务...")
    # 这里可以添加资源清理代码
    print("[关闭] 服务已关闭")


# 创建FastAPI应用实例
app = FastAPI(
    title=AppConfig.APP_NAME,
    description="基于YOLOv8和DeepSort的校园主干道交通流量分析系统",
    version=AppConfig.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",  # API文档地址
    redoc_url="/redoc",  # 替代API文档
)


# 配置CORS跨域支持
# 允许前端应用访问API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源（生产环境应限制为特定域名）
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有HTTP方法
    allow_headers=["*"],  # 允许所有请求头
)


# 挂载静态文件服务
# 获取前端目录路径
BASE_DIR = Path(__file__).parent.absolute()
FRONTEND_DIR = BASE_DIR.parent / "frontend"

# 检查前端目录是否存在
if FRONTEND_DIR.exists():
    # 挂载前端静态文件
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
    print(f"[配置] 静态文件服务已挂载: {FRONTEND_DIR}")
else:
    print(f"[警告] 前端目录不存在: {FRONTEND_DIR}")


# 注册API路由
# 视频相关API
app.include_router(video.router)

# 数据相关API
app.include_router(data.router)

# AI相关API
app.include_router(ai.router)

print("[配置] API路由已注册")


# 页面路由
@app.get("/", response_class=HTMLResponse)
async def root():
    """
    根路径重定向到主页
    """
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/index.html", response_class=HTMLResponse)
async def index():
    """
    系统主页
    
    返回仪表盘页面，展示今日交通概况
    """
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/analysis.html", response_class=HTMLResponse)
async def analysis():
    """
    视频分析页面
    
    核心功能页面，提供视频上传、实时检测、ROI设置等功能
    """
    return FileResponse(str(FRONTEND_DIR / "analysis.html"))


@app.get("/visualize.html", response_class=HTMLResponse)
async def visualize():
    """
    数据可视化页面
    
    展示各种交通数据图表：流量趋势、密度变化、热力图等
    """
    return FileResponse(str(FRONTEND_DIR / "visualize.html"))


@app.get("/history.html", response_class=HTMLResponse)
async def history():
    """
    历史数据查询页面
    
    提供历史数据查询、导出功能
    """
    return FileResponse(str(FRONTEND_DIR / "history.html"))


@app.get("/ai.html", response_class=HTMLResponse)
async def ai_analysis_page():
    """
    AI分析页面
    
    提供大模型交互分析功能
    """
    return FileResponse(str(FRONTEND_DIR / "ai.html"))


# 健康检查接口
@app.get("/health")
async def health_check():
    """
    健康检查接口
    
    用于监控服务运行状态
    
    返回:
        {"status": "healthy", "version": "1.0.0"}
    """
    return {
        "status": "healthy",
        "version": AppConfig.APP_VERSION,
        "app_name": AppConfig.APP_NAME
    }


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    全局异常处理器
    
    捕获所有未处理的异常，返回统一的错误响应
    """
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "服务器内部错误",
            "detail": str(exc) if AppConfig.DEBUG else "请联系管理员"
        }
    )


# 主入口
if __name__ == "__main__":
    """
    直接运行此文件启动服务:
        python -m backend.app
    
    """
    import uvicorn

    # 启动参数
    host = "0.0.0.0"  # 监听所有网络接口
    port = 8000  # 服务端口
    reload = AppConfig.DEBUG  # 调试模式下启用热重载

    print(f"\n启动服务: http://{host}:{port}")
    print(f"调试模式: {reload}\n")

    uvicorn.run(
        "backend.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )
