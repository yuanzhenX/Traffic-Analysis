from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from typing import Generator
from backend.config import DatabaseConfig
from backend.db.base import Base


"""
================================================================================
数据库初始化模块 (db/__init__.py)
================================================================================
功能说明:
    本模块负责数据库连接的初始化和会话管理。
    使用SQLAlchemy作为ORM工具，提供数据库操作的统一入口。
    
    主要功能:
    1. 创建数据库引擎（Engine）
    2. 管理数据库会话（Session）
    3. 提供依赖注入函数供FastAPI使用
    4. 初始化数据库表结构

数据库类型: SQLite（轻量级，适合单机部署）

作者: Nathan
创建日期: 2026-03-20
"""

# 创建数据库引擎
# Engine是SQLAlchemy的核心，负责管理数据库连接池和与数据库的通信
engine = create_engine(
    DatabaseConfig.DATABASE_URL,
    echo=False,  # 设置为True可查看生成的SQL语句
    connect_args={
        "check_same_thread": False  # SQLite特定配置: 启用外键约束检查
    }
)
# SessionLocal是一个工厂类，用于创建数据库会话实例
SessionLocal = sessionmaker(
    autocommit=False,  # 禁用自动提交，需要手动调用session.commit()
    autoflush=False,  # 禁用自动刷新，提高性能
    bind=engine
)


# 数据库会话依赖函数
def get_db() -> Generator[Session, None, None]:
    # 创建新的数据库会话
    db = SessionLocal()
    try:
        # 将会话对象返回给调用者
        yield db
        # 如果执行到这里没有异常，提交事务
        db.commit()
    except Exception:
        # 发生异常时回滚事务，确保数据一致性
        db.rollback()
        raise
    finally:
        # 无论成功或失败，最后都关闭会话
        db.close()


# 数据库初始化函数，应用启动时调用，如果表不存在则创建所有数据表
# models中写的模型类会被自动添加到Base.metadata中
def init_db() -> None:
    from backend.db import models
    Base.metadata.create_all(bind=engine, checkfirst=True)  # 根据模型定义在数据库中创建表，checkfirst=True 表示如果表已存在则跳过
    print("[数据库初始化] 数据表创建完成")


# 数据库清理函数
def drop_db() -> None:
    Base.metadata.drop_all(bind=engine)
    print("[数据库清理] 所有数据表已删除")
