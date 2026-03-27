import cv2
import os

# 输入视频文件路径和输出图像目录
video_path = "train_video.mp4"
output_dir = 'images/'

if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# 打开视频文件
cap = cv2.VideoCapture(video_path)

frame_count = 0
while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    # 保存每一帧为图像
    frame_filename = os.path.join(output_dir, f"frame_{frame_count:04d}.jpg")
    cv2.imwrite(frame_filename, frame)
    frame_count += 1
    print(f"Saved {frame_filename}")

cap.release()
print(f"Extracted {frame_count} frames.")