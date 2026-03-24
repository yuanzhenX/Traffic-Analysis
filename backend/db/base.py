from sqlalchemy.orm import declarative_base

# Base是所有模型类的基类，使用declarative_base()创建，所有数据表模型都需要继承此类
Base = declarative_base()
