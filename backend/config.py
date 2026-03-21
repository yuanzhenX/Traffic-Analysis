import os
from pathlib import Path
from dotenv import load_dotenv
"""
================================================================================
配置文件模块 (config.py)
================================================================================
功能说明:
    本模块负责管理系统的所有配置参数，包括数据库连接、文件路径、API密钥等。
    采用单例模式设计，确保全局配置一致性。
    
配置分类:
    1. 数据库配置DatabaseConfig: SQLite数据库路径和连接参数
    2. 模型配置ModelConfig: YOLOv8模型路径和检测参数
    3. 路径配置PathConfig: 上传文件、缓存文件的存储路径
    4. API配置APIConfig: 智谱AI的API密钥和接口地址
    5. 视频处理配置VideoConfig: 帧率限制、ROI区域等

作者: Nathan
创建日期: 2026-03-20
"""


# 加载环境变量
# 获取当前文件所在目录的绝对路径，用于定位.env文件
BASE_DIR = Path(__file__).parent.absolute()

# 加载.env文件中的环境变量，用于存储敏感信息如API密钥
# 如果.env文件不存在，不会报错，只是不会加载任何变量
load_dotenv(BASE_DIR / ".env")


# 数据库配置类
class DatabaseConfig:

    # SQLite数据库URL格式，使用本地文件存储
    # 数据库文件位于backend目录下的traffic_analysis.db
    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/traffic_analysis.db"
    
    # 数据库连接池配置（SQLite通常不需要连接池，但保留配置项）
    POOL_SIZE: int = 5           # 连接池大小
    MAX_OVERFLOW: int = 10       # 最大溢出连接数
    POOL_TIMEOUT: int = 30       # 连接池超时时间（秒）


# 模型配置类
class ModelConfig:

    # YOLOv8n模型文件路径，n表示nano版本，是速度最快的轻量级模型
    # 模型文件需要提前下载并放置在models目录下
    MODEL_PATH: str = str(BASE_DIR / "models" / "yolov8n.pt")
    
    # 置信度阈值: 0.5表示只保留置信度≥50%的检测结果
    # 调高此值可减少误检，但可能漏检；调低可增加召回率，但误检增多
    CONFIDENCE_THRESHOLD: float = 0.5
    
    # IoU阈值: 0.45表示当两个检测框重叠度≥45%时，保留置信度高的那个
    IOU_THRESHOLD: float = 0.45
    
    # 推理设备自动选择: 优先使用CUDA GPU加速，否则回退到CPU
    # 可以通过设置环境变量 FORCE_CPU=1 强制使用CPU
    DEVICE: str = "cuda" if os.getenv("FORCE_CPU") is None else "cpu"
    
    # 检测的类别列表，只关注行人和车辆
    # COCO数据集中: 0=person, 2=car, 3=motorcycle, 5=bus, 7=truck
    DETECT_CLASSES: list = [0, 2, 3, 5, 7]
    
    # 类别名称映射，用于显示友好的类别名称
    CLASS_NAMES: dict = {
        0: "person",      # 行人
        2: "car",         # 汽车
        3: "motorcycle",  # 摩托车
        5: "bus",         # 公交车
        7: "truck"        # 卡车
    }


# 路径配置类
class PathConfig:

    # 静态文件根目录，用于存放上传的视频、缓存的帧等
    STATIC_DIR: Path = BASE_DIR / "static"
    
    # 上传视频文件存储目录，用户上传的视频文件将保存在此处
    UPLOADS_DIR: Path = STATIC_DIR / "uploads"
    
    # 视频帧缓存目录，用于临时存储视频处理过程中的帧
    FRAMES_DIR: Path = STATIC_DIR / "frames"
    
    # 确保所有目录都存在，不存在则自动创建
    @classmethod
    def ensure_directories(cls) -> None:
        """
        确保所有配置的目录都存在
        
        此方法应在应用启动时调用，自动创建缺失的目录
        """
        cls.STATIC_DIR.mkdir(parents=True, exist_ok=True)
        cls.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        cls.FRAMES_DIR.mkdir(parents=True, exist_ok=True)


# API配置类
class APIConfig:

    # 智谱AI API密钥，从环境变量读取
    # 需要在.env文件中设置: ZHIPU_API_KEY=your_api_key
    ZHIPU_API_KEY: str = os.getenv("ZHIPU_API_KEY", "")
    
    # 智谱AI API接口地址，使用GLM-4模型
    # GLM-4是智谱AI最新的大语言模型，支持长文本和复杂推理
    ZHIPU_API_URL: str = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    
    # 请求超时时间（秒）
    REQUEST_TIMEOUT: int = 60
    
    # 最大重试次数
    MAX_RETRIES: int = 3


# 视频处理配置类
class VideoConfig:

    # 最大处理帧率: 30fps
    # 限制帧率可减少计算负载，同时保持检测稳定性
    MAX_FPS: int = 30
    
    # 处理帧的目标尺寸: 960x540
    # 统一尺寸便于后续处理和显示
    FRAME_WIDTH: int = 960
    FRAME_HEIGHT: int = 540
    
    # 轨迹历史长度: 90帧（约3秒，按30fps计算）
    # 记录每个目标最近90帧的位置，用于计算速度和方向
    TRACK_HISTORY_LENGTH: int = 90
    
    # 速度计算的时间窗口（秒）
    # 用于平滑速度计算，避免单帧噪声
    SPEED_TIME_WINDOW: float = 0.5
    
    # 默认ROI区域（全画面）
    # 格式: [(x1,y1), (x2,y2), ...] 多边形顶点坐标
    # 默认值为None表示使用全画面
    DEFAULT_ROI: list = None


# 应用配置类（整合所有配置）
class AppConfig:

    db = DatabaseConfig()
    model = ModelConfig()
    path = PathConfig()
    api = APIConfig()
    video = VideoConfig()
    
    # 应用元信息
    APP_NAME: str = "校园主干道人流车流分析系统"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"


# 初始化配置
# 应用启动时自动确保目录存在
PathConfig.ensure_directories()

# 验证API密钥是否配置
if not APIConfig.ZHIPU_API_KEY:
    import warnings
    warnings.warn(
        "智谱AI API密钥未配置，AI分析功能将不可用。"
        "请在.env文件中设置 ZHIPU_API_KEY=your_api_key",
        RuntimeWarning
    )
