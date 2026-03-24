import random
import numpy as np
from datetime import datetime, timedelta
from backend.db import SessionLocal
from backend.db.models import DetectionLog, TrafficStat


class Config:
    START_HOUR = 6

    # 画面尺寸（用于密度计算 & bbox）
    FRAME_WIDTH = 960
    FRAME_HEIGHT = 540

    # 基础流量（每分钟）
    BASE_PERSON = 12
    BASE_VEHICLE = 6

    # 高峰时间
    PEAK_HOURS = [7, 8, 12, 13, 17, 18]
    PEAK_MULTIPLIER = 2.5


class DataGenerator:

    def __init__(self):
        self.db = SessionLocal()
        self.cfg = Config()

        random.seed(42)
        np.random.seed(42)

        # track_id计数器（模拟目标持续）
        self.track_id_counter = 1

    def clear_today_data(self):
        now = datetime.now()
        start = now.replace(hour=6, minute=0, second=0, microsecond=0)

        print("清理当天数据...")

        self.db.query(DetectionLog).filter(
            DetectionLog.timestamp >= start
        ).delete()

        self.db.query(TrafficStat).filter(
            TrafficStat.time_slot >= start
        ).delete()

        self.db.commit()

    # ==============================
    # 主入口
    # ==============================
    def run(self):
        self.clear_today_data()
        now = datetime.now()

        start_time = now.replace(
            hour=self.cfg.START_HOUR,
            minute=0,
            second=0,
            microsecond=0
        )

        print(f"生成数据: {start_time} -> {now}")

        current = start_time

        while current < now:
            # 每分钟生成统计
            stat = self.generate_minute_stat(current)
            self.db.add(stat)

            # 每秒生成检测
            for i in range(60):
                second_time = current + timedelta(seconds=i)
                if second_time > now:
                    break

                logs = self.generate_second_logs(second_time, stat)
                for log in logs:
                    self.db.add(log)

            # 每10分钟提交一次
            if current.minute % 10 == 0:
                self.db.commit()

            current += timedelta(minutes=1)

        self.db.commit()
        print("数据生成完成")

    # ==============================
    # 每分钟统计
    # ==============================
    def generate_minute_stat(self, time_slot):

        hour = time_slot.hour

        # 是否高峰
        is_peak = hour in self.cfg.PEAK_HOURS
        multiplier = self.cfg.PEAK_MULTIPLIER if is_peak else 1.0

        fluctuation = random.uniform(0.8, 1.2)

        person_count = int(self.cfg.BASE_PERSON * multiplier * fluctuation)
        vehicle_count = int(self.cfg.BASE_VEHICLE * multiplier * fluctuation)

        total = person_count + vehicle_count

        # 平均速度（高峰更慢）
        if is_peak:
            avg_speed = random.uniform(8, 15)
        else:
            avg_speed = random.uniform(15, 25)

        # 密度
        density = total / (self.cfg.FRAME_WIDTH * self.cfg.FRAME_HEIGHT)

        # 方向分布
        directions = self.random_direction_distribution(total)

        return TrafficStat(
            time_slot=time_slot,
            person_count=person_count,
            vehicle_count=vehicle_count,
            avg_speed=avg_speed,
            density=density,
            east_count=directions['East'],
            west_count=directions['West'],
            south_count=directions['South'],
            north_count=directions['North'],
            created_at=time_slot
        )

    # ==============================
    # 每秒检测（核心🔥）
    # ==============================
    def generate_second_logs(self, timestamp, stat):

        logs = []

        total_targets = stat.person_count + stat.vehicle_count
        if total_targets == 0:
            total_targets = 1

        # 👇 每秒生成多个目标（关键点）
        num_objects = max(1, int(np.random.poisson(total_targets / 60)))

        person_ratio = stat.person_count / total_targets

        for _ in range(num_objects):

            # 类型
            if random.random() < person_ratio:
                object_type = 'person'
                bbox_size = 60
            else:
                object_type = random.choice(['car', 'bus', 'truck', 'motorcycle'])
                bbox_size = 100

            # 坐标
            x = random.randint(50, self.cfg.FRAME_WIDTH - 50)
            y = random.randint(50, self.cfg.FRAME_HEIGHT - 50)

            # 速度（围绕平均值波动）
            speed = max(0, random.uniform(stat.avg_speed - 5, stat.avg_speed + 5))

            direction = random.choice(['East', 'West', 'North', 'South'])

            # bbox
            bbox_x1 = max(0, x - bbox_size // 2)
            bbox_y1 = max(0, y - bbox_size // 2)
            bbox_x2 = min(self.cfg.FRAME_WIDTH, x + bbox_size // 2)
            bbox_y2 = min(self.cfg.FRAME_HEIGHT, y + bbox_size // 2)

            log = DetectionLog(
                track_id=self.track_id_counter,
                object_type=object_type,
                timestamp=timestamp,
                x=x,
                y=y,
                pixel_speed=speed,
                direction=direction,
                confidence=random.uniform(0.7, 0.98),
                bbox_x1=bbox_x1,
                bbox_y1=bbox_y1,
                bbox_x2=bbox_x2,
                bbox_y2=bbox_y2,
                created_at=timestamp
            )

            logs.append(log)

            # 模拟部分目标“持续存在”
            if random.random() < 0.7:
                # 保持track_id（下一秒继续）
                pass
            else:
                self.track_id_counter += 1

        return logs

    # ==============================
    # 方向分布
    # ==============================
    def random_direction_distribution(self, total):

        weights = {
            'East': random.uniform(0.2, 0.4),
            'West': random.uniform(0.2, 0.4),
            'South': random.uniform(0.1, 0.3),
            'North': random.uniform(0.1, 0.3)
        }

        total_w = sum(weights.values())
        result = {}
        remaining = total

        for k in list(weights.keys())[:-1]:
            c = int(total * weights[k] / total_w)
            result[k] = c
            remaining -= c

        result[list(weights.keys())[-1]] = remaining
        return result

    def close(self):
        self.db.close()


# ==============================
# 运行
# ==============================
if __name__ == "__main__":
    generator = DataGenerator()
    try:
        generator.run()
    finally:
        generator.close()