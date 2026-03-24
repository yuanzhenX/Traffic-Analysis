import sys
from pathlib import Path
from sqlalchemy.orm import Session
from backend.db import SessionLocal
from backend.db.models import DetectionLog, TrafficStat


# 解决导入路径问题（让 database 可以访问 backend）
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))


# 获取数据库会话
def get_db_session() -> Session:
    return SessionLocal()


# 删除 DetectionLog（按ID）
def delete_detection_by_id(record_id: int):
    db = get_db_session()
    try:
        record = db.query(DetectionLog).filter(DetectionLog.id == record_id).first()
        if not record:
            print(f"[删除] DetectionLog ID={record_id} 不存在")
            return

        db.delete(record)
        db.commit()
        print(f"[删除] DetectionLog ID={record_id} 删除成功")

    except Exception as e:
        db.rollback()
        print(f"[错误] 删除失败: {e}")
    finally:
        db.close()


# 按时间范围删除 DetectionLog
def delete_detection_by_time(start_time, end_time):
    db = get_db_session()
    try:
        count = db.query(DetectionLog).filter(
            DetectionLog.timestamp >= start_time,
            DetectionLog.timestamp <= end_time
        ).delete()

        db.commit()
        print(f"[删除] 删除 {count} 条 DetectionLog 记录")

    except Exception as e:
        db.rollback()
        print(f"[错误] 删除失败: {e}")
    finally:
        db.close()


# 清空 DetectionLog 表
def clear_detection_table():
    db = get_db_session()
    try:
        count = db.query(DetectionLog).delete()
        db.commit()
        print(f"[清空] DetectionLog 表已清空，共删除 {count} 条记录")

    except Exception as e:
        db.rollback()
        print(f"[错误] 清空失败: {e}")
    finally:
        db.close()


# 清空 TrafficStat 表
def clear_traffic_stat_table():
    db = get_db_session()
    try:
        count = db.query(TrafficStat).delete()
        db.commit()
        print(f"[清空] TrafficStat 表已清空，共删除 {count} 条记录")

    except Exception as e:
        db.rollback()
        print(f"[错误] 清空失败: {e}")
    finally:
        db.close()


# 查询所有 DetectionLog
def get_all_detection_logs(limit: int = 100):
    db = get_db_session()
    try:
        results = db.query(DetectionLog).order_by(DetectionLog.timestamp.desc()).limit(limit).all()
        print(f"[查询] 共获取 {len(results)} 条记录")

        for r in results:
            print(r)

        return results

    finally:
        db.close()


# 按时间范围查询
def get_detection_by_time(start_time, end_time):
    db = get_db_session()
    try:
        results = db.query(DetectionLog).filter(
            DetectionLog.timestamp >= start_time,
            DetectionLog.timestamp <= end_time
        ).all()

        print(f"[查询] 时间范围内共 {len(results)} 条记录")
        return results

    finally:
        db.close()


# 按目标类型查询（人 / 车）
def get_detection_by_type(object_type: str):
    db = get_db_session()
    try:
        results = db.query(DetectionLog).filter(
            DetectionLog.object_type == object_type
        ).all()

        print(f"[查询] 类型 {object_type} 共 {len(results)} 条")
        return results

    finally:
        db.close()


# 查询某个 track_id
def get_by_track_id(track_id: int):
    db = get_db_session()
    try:
        results = db.query(DetectionLog).filter(
            DetectionLog.track_id == track_id
        ).order_by(DetectionLog.timestamp).all()

        print(f"[查询] track_id={track_id} 共 {len(results)} 条")
        return results

    finally:
        db.close()


# 查询统计数据
def get_traffic_stats(limit: int = 50):
    db = get_db_session()
    try:
        results = db.query(TrafficStat).order_by(
            TrafficStat.time_slot.desc()
        ).limit(limit).all()

        print(f"[查询] 获取统计数据 {len(results)} 条")
        return results

    finally:
        db.close()


# 查询时间段统计
def get_stats_by_time(start_time, end_time):
    db = get_db_session()
    try:
        results = db.query(TrafficStat).filter(
            TrafficStat.time_slot >= start_time,
            TrafficStat.time_slot <= end_time
        ).all()

        print(f"[查询] 时间段统计数据 {len(results)} 条")
        return results

    finally:
        db.close()


# 获取总流量
def get_total_count():
    db = get_db_session()
    try:
        stats = db.query(TrafficStat).all()

        total_person = sum(s.person_count for s in stats)
        total_vehicle = sum(s.vehicle_count for s in stats)

        print(f"[统计] 行人总数: {total_person}")
        print(f"[统计] 车辆总数: {total_vehicle}")

        return {
            "person": total_person,
            "vehicle": total_vehicle
        }

    finally:
        db.close()


if __name__ == "__main__":
    from datetime import datetime

    print("===== 数据库操作测试 =====")

    # 删除指定ID
    # delete_detection_by_id(1)

    # 按时间删除
    # delete_detection_by_time(
    #     datetime(2026, 3, 20, 8, 0, 0),
    #     datetime(2026, 3, 20, 9, 0, 0)
    # )

    # 清空表
    clear_detection_table()

    # 清空统计表
    clear_traffic_stat_table()

    # 查询全部（最近100条）
    # get_all_detection_logs()

    # 按时间查询
    # get_detection_by_time(
    #     datetime(2026, 3, 20, 8, 0, 0),
    #     datetime(2026, 3, 20, 9, 0, 0)
    # )

    # 查询人
    # get_detection_by_type("person")

    # 查询某个track
    # get_by_track_id(1)

    # 查询统计
    # get_traffic_stats()

    # 获取总量
    # get_total_count()

    print("===== 操作结束 =====")
