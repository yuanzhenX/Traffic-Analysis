/**
 * 视频分析页面 - 交互逻辑
 */


// ============================================
// 全局状态
// ============================================
const state = {
    isConnected: false,
    isDetecting: false,
    isPaused: false,
    sourceType: null, // 'file' 或 'camera'
    currentFile: null,
    roiPoints: [],
    ws: null,
    frameData: null, // 用于 ROI 设置的帧数据
    roiCanvas: null,
    roiCtx: null,
    roiImage: null,
    roiSet: false, // ROI 是否已设置
    directionAngle: 0, // 北方方向角度（相对于屏幕上方）
    directionCanvas: null,
    directionCtx: null,
    directionSet: false // 方向是否已设置
};

// ============================================
// 初始化
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    highlightCurrentNav();
    initEventListeners();
});

function initEventListeners() {
    // 文件上传监听
    const videoInput = document.getElementById('videoInput');
    videoInput.addEventListener('change', handleFileSelect);
    
    // 方向角度滑块监听
    const directionSlider = document.getElementById('directionAngle');
    if (directionSlider) {
        directionSlider.addEventListener('input', handleDirectionChange);
    }
}

// ============================================
// 视频上传
// ============================================
function uploadVideo() {
    document.getElementById('videoInput').click();
}

async function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    // 检查文件格式
    const supportedFormats = ['.mp4', '.avi', '.mov', '.mkv', '.flv'];
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!supportedFormats.includes(ext)) {
        showMessage('不支持的文件格式，请上传 MP4/AVI/MOV/MKV/FLV 格式视频', 'error');
        return;
    }
    
    try {
        showLoading(true);
        
        // 上传文件
        const formData = new FormData();
        formData.append('file', file);
        
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error(`上传失败: ${response.statusText}`);
        }
        
        const result = await response.json();
        
        if (result.success) {
            state.currentFile = result.filename;
            state.sourceType = 'file';
            state.isConnected = true;
            state.isDetecting = false;
            state.isPaused = false;
                    
            // 获取视频帧用于预览和 ROI 设置
            await loadVideoFrame(result.filename);
                    
            showMessage('视频上传成功，请设置 ROI 区域和方向标定', 'success');
            updateUIState();
            updateSetupPrompt();
        } else {
            throw new Error(result.message || '上传失败');
        }
        
    } catch (error) {
        console.error('上传错误:', error);
        showMessage(error.message, 'error');
    } finally {
        showLoading(false);
        // 清空input，允许重复选择同一文件
        document.getElementById('videoInput').value = '';
    }
}

// ============================================
// 连接摄像头
// ============================================
async function connectCamera() {
    try {
        showLoading(true);
        
        // 先获取摄像头一帧用于ROI设置
        const response = await fetch('/api/video_status');
        const status = await response.json();
        
        state.sourceType = 'camera';
        state.isConnected = true;
        state.currentFile = null;
        state.isDetecting = false;
        state.isPaused = false;
                
        // 使用默认图像提示用户设置 ROI
        showMessage('摄像头已连接，请设置 ROI 区域和方向标定', 'success');
        updateUIState();
        updateSetupPrompt();
        
        // 尝试获取摄像头预览帧
        await loadCameraFrame();
        
    } catch (error) {
        console.error('连接摄像头错误:', error);
        showMessage('连接摄像头失败: ' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 加载视频帧
async function loadVideoFrame(filename) {
    // 创建一个视频元素来获取第一帧
    const videoUrl = `/api/video/${filename}`;
    
    return new Promise((resolve, reject) => {
        const video = document.createElement('video');
        video.crossOrigin = 'anonymous';
        video.src = videoUrl;
        video.muted = true;
        
        video.onloadeddata = () => {
            // 创建canvas捕获第一帧
            const canvas = document.createElement('canvas');
            canvas.width = video.videoWidth || 640;
            canvas.height = video.videoHeight || 480;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(video, 0, 0);
            
            // 保存帧数据用于ROI设置
            state.frameData = canvas.toDataURL('image/jpeg', 0.8);
            
            // 显示在视频区域
            const videoFrame = document.getElementById('videoFrame');
            videoFrame.src = state.frameData;
            videoFrame.style.display = 'block';
            document.getElementById('emptyState').style.display = 'none';
            
            video.remove();
            resolve();
        };
        
        video.onerror = () => {
            reject(new Error('无法加载视频'));
        };
        
        video.load();
    });
}

// 加载摄像头帧（使用占位图或尝试获取）
async function loadCameraFrame() {
    // 首先尝试通过浏览器获取摄像头实时预览
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ 
            video: { 
                width: { ideal: 1280 },
                height: { ideal: 720 }
            } 
        });
        
        // 创建视频元素显示摄像头画面
        const video = document.createElement('video');
        video.srcObject = stream;
        video.autoplay = true;
        video.playsInline = true;
        
        await new Promise((resolve, reject) => {
            video.onloadedmetadata = () => {
                video.play();
                resolve();
            };
            video.onerror = reject;
            setTimeout(() => reject(new Error('摄像头加载超时')), 5000);
        });
        
        // 等待一帧画面
        await new Promise(resolve => setTimeout(resolve, 500));
        
        // 捕获一帧用于ROI设置
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth || 640;
        canvas.height = video.videoHeight || 480;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0);
        
        // 保存帧数据用于ROI设置
        state.frameData = canvas.toDataURL('image/jpeg', 0.8);
        
        // 停止预览流（ROI设置完成后会通过后端重新获取）
        stream.getTracks().forEach(track => track.stop());
        video.remove();
        
        console.log(`[摄像头] 预览已获取: ${canvas.width}x${canvas.height}`);
        
    } catch (error) {
        console.warn('[摄像头] 无法获取浏览器摄像头预览:', error);
        
        // 使用默认的提示图像
        const canvas = document.createElement('canvas');
        canvas.width = 640;
        canvas.height = 480;
        const ctx = canvas.getContext('2d');
        
        // 绘制提示背景
        ctx.fillStyle = '#1a1a2e';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        // 绘制提示文字
        ctx.fillStyle = 'rgba(255,255,255,0.5)';
        ctx.font = '20px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('摄像头预览', canvas.width/2, canvas.height/2 - 20);
        ctx.font = '14px Arial';
        ctx.fillText('点击"开始检测"后显示实时画面', canvas.width/2, canvas.height/2 + 20);
        
        state.frameData = canvas.toDataURL('image/jpeg');
    }
    
    const videoFrame = document.getElementById('videoFrame');
    videoFrame.src = state.frameData;
    videoFrame.style.display = 'block';
    document.getElementById('emptyState').style.display = 'none';
}

// ============================================
// 检测控制
// ============================================
async function startDetection() {
    if (!state.isConnected) {
        showMessage('请先上传视频或连接摄像头', 'warning');
        return;
    }
    
    if (state.isDetecting) {
        showMessage('检测已在运行中', 'warning');
        return;
    }
    
    try {
        let response;

        if (state.isPaused) {
            response = await post('/api/pause_detection', {});
            if (!response.success || response.is_paused) {
                throw new Error(response.message || '恢复检测失败');
            }
            state.isPaused = false;
            state.isDetecting = true;
            showMessage(response.message || '检测已恢复', 'success');
        } else {
            const requestData = {
                source_type: state.sourceType,
                filename: state.currentFile
            };

            response = await post('/api/start_detection', requestData);
            if (!response.success) {
                throw new Error(response.message || '启动失败');
            }

            state.isDetecting = true;
            state.isPaused = false;
            showMessage('检测已开始', 'success');
        }

        updateUIState();
        showStatusIndicator(true);

        // 连接WebSocket接收实时数据
        connectWebSocket();

    } catch (error) {
        console.error('启动检测错误:', error);
        showMessage('启动检测失败: ' + error.message, 'error');
    }
}

async function stopDetection() {
    if (!state.isDetecting) {
        showMessage('检测未在运行', 'warning');
        return;
    }
    
    try {
        const response = await post('/api/pause_detection', {});
        
        if (response.success) {
            state.isPaused = !!response.is_paused;
            state.isDetecting = !state.isPaused;
            showMessage(response.message || '检测已暂停', 'success');
            updateUIState();
            showStatusIndicator(state.isDetecting || state.isPaused);
            
            // 关闭WebSocket
            if (state.ws) {
                state.ws.close();
                state.ws = null;
            }
        } else {
            throw new Error(response.message || '暂停失败');
        }
        
    } catch (error) {
        console.error('停止检测错误:', error);
        showMessage('停止检测失败: ' + error.message, 'error');
    }
}

// ============================================
// WebSocket连接
// ============================================
function connectWebSocket() {
    // 关闭已有连接
    if (state.ws) {
        state.ws.close();
    }
    
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/api/ws`;
    
    state.ws = new WebSocket(wsUrl);
    
    state.ws.onopen = () => {
        console.log('WebSocket已连接');
    };
    
    state.ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleWebSocketMessage(data);
        } catch (error) {
            console.error('解析WebSocket消息失败:', error);
        }
    };
    
    state.ws.onerror = (error) => {
        console.error('WebSocket错误:', error);
        showMessage('实时连接出错', 'error');
    };
    
    state.ws.onclose = () => {
        console.log('WebSocket已关闭');
    };
}

function handleWebSocketMessage(data) {
    if (data.type === 'frame') {
        // 更新视频画面
        if (data.image) {
            const videoFrame = document.getElementById('videoFrame');
            videoFrame.src = 'data:image/jpeg;base64,' + data.image;
            videoFrame.style.display = 'block';
            document.getElementById('emptyState').style.display = 'none';
        }
        
        // 更新统计数据
        if (data.stats) {
            updateStats(data.stats);
        }
        
        // 更新处理信息
        document.getElementById('processFrames').textContent = data.frame_id || 0;
    } else if (data.type === 'pong' || data.type === 'heartbeat') {
        // 心跳响应，无需处理
    }
}

function updateStats(stats) {
    // 更新主要统计
    document.getElementById('statPersonCount').textContent = stats.person_count || 0;
    document.getElementById('statVehicleCount').textContent = stats.vehicle_count || 0;
    document.getElementById('statTotalCount').textContent = stats.total_count || 0;
    document.getElementById('statAvgSpeed').innerHTML = `${(stats.avg_speed || 0).toFixed(1)} <span class="unit">px/s</span>`;
    
    // 更新方向统计
    if (stats.direction_counts) {
        document.getElementById('dirNorth').textContent = stats.direction_counts['North'] || 0;
        document.getElementById('dirSouth').textContent = stats.direction_counts['South'] || 0;
        document.getElementById('dirWest').textContent = stats.direction_counts['West'] || 0;
        document.getElementById('dirEast').textContent = stats.direction_counts['East'] || 0;
    }
    
    // 更新处理帧率
    document.getElementById('processFps').textContent = '30 fps';
}

// ============================================
// ROI设置
// ============================================
function openROIModal() {
    if (!state.isConnected) {
        showMessage('请先上传视频或连接摄像头', 'warning');
        return;
    }
    
    const modal = document.getElementById('roiModal');
    modal.style.display = 'flex';
    
    // 初始化Canvas
    initROICanvas();
}

function closeROIModal() {
    const modal = document.getElementById('roiModal');
    modal.style.display = 'none';
}

function initROICanvas() {
    const canvas = document.getElementById('roiCanvas');
    const ctx = canvas.getContext('2d');
    
    state.roiCanvas = canvas;
    state.roiCtx = ctx;
    state.roiPoints = [];
    
    // 初始化方向画布
    initDirectionCanvas();
    
    // 加载图像
    const img = new Image();
    img.onload = () => {
        state.roiImage = img;
        
        // 设置canvas尺寸适应容器，保持比例
        const container = canvas.parentElement;
        const maxWidth = container.clientWidth - 40;
        const maxHeight = window.innerHeight * 0.6;
        
        let width = img.width;
        let height = img.height;
        
        // 缩放以适应
        const scale = Math.min(maxWidth / width, maxHeight / height, 1);
        width *= scale;
        height *= scale;
        
        canvas.width = width;
        canvas.height = height;
        
        // 保存缩放比例用于坐标转换
        state.roiScale = scale;
        
        drawROI();
    };
    
    img.src = state.frameData || '';
    
    // 绑定点击事件
    canvas.onclick = (e) => handleROIClick(e);
    
    // 右键完成绘制
    canvas.oncontextmenu = (e) => {
        e.preventDefault();
        if (state.roiPoints.length >= 3) {
            confirmROI();
        } else {
            showMessage('请至少设置3个点', 'warning');
        }
    };
}

function handleROIClick(event) {
    if (!state.roiCanvas) return;
    
    const rect = state.roiCanvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    
    // 转换为原始图像坐标
    const originalX = Math.round(x / state.roiScale);
    const originalY = Math.round(y / state.roiScale);
    
    state.roiPoints.push([originalX, originalY]);
    drawROI();
}

function drawROI() {
    if (!state.roiCtx || !state.roiImage) return;
    
    const ctx = state.roiCtx;
    const canvas = state.roiCanvas;
    
    // 清空并绘制图像
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(state.roiImage, 0, 0, canvas.width, canvas.height);
    
    if (state.roiPoints.length === 0) return;
    
    // 绘制多边形
    ctx.beginPath();
    ctx.strokeStyle = '#409EFF';
    ctx.lineWidth = 2;
    ctx.fillStyle = 'rgba(64, 158, 255, 0.2)';
    
    state.roiPoints.forEach((point, index) => {
        const x = point[0] * state.roiScale;
        const y = point[1] * state.roiScale;
        
        if (index === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
        
        // 绘制顶点
        ctx.fillStyle = '#409EFF';
        ctx.beginPath();
        ctx.arc(x, y, 5, 0, Math.PI * 2);
        ctx.fill();
        
        // 显示序号
        ctx.fillStyle = '#fff';
        ctx.font = '12px Arial';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(index + 1, x, y);
        
        ctx.strokeStyle = '#409EFF';
        ctx.fillStyle = 'rgba(64, 158, 255, 0.2)';
        ctx.beginPath();
    });
    
    // 闭合多边形
    if (state.roiPoints.length > 2) {
        const firstX = state.roiPoints[0][0] * state.roiScale;
        const firstY = state.roiPoints[0][1] * state.roiScale;
        ctx.lineTo(firstX, firstY);
    }
    
    ctx.stroke();
    ctx.fill();
}

function clearROIPoints() {
    state.roiPoints = [];
    drawROI();
}

// ============================================
// 方向标定功能
// ============================================
function handleDirectionChange(e) {
    const angle = parseInt(e.target.value);
    state.directionAngle = angle;
    document.getElementById('angleValue').textContent = `${angle}°`;
    drawDirectionArrow(angle);
}

function initDirectionCanvas() {
    const canvas = document.getElementById('directionCanvas');
    if (!canvas) return;
    
    state.directionCanvas = canvas;
    state.directionCtx = canvas.getContext('2d');
    
    // 初始化绘制
    drawDirectionArrow(0);
}

function drawDirectionArrow(angle) {
    const ctx = state.directionCtx;
    const canvas = state.directionCanvas;
    if (!ctx || !canvas) return;
    
    const centerX = canvas.width / 2;
    const centerY = canvas.height / 2;
    const radius = 35;
    
    // 清空画布
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // 转换为弧度（角度 0 度指向屏幕上方，顺时针旋转）
    const radian = (angle - 90) * Math.PI / 180;
    
    // 计算箭头终点
    const endX = centerX + Math.cos(radian) * radius;
    const endY = centerY + Math.sin(radian) * radius;
    
    // 绘制箭头
    ctx.beginPath();
    ctx.strokeStyle = '#F56C6C';
    ctx.lineWidth = 3;
    ctx.lineCap = 'round';
    
    // 箭杆
    ctx.moveTo(centerX, centerY);
    ctx.lineTo(endX, endY);
    ctx.stroke();
    
    // 箭头头部
    const arrowSize = 8;
    const arrowAngle = Math.PI / 6; // 30 度
    
    ctx.beginPath();
    ctx.fillStyle = '#F56C6C';
    
    // 左翼
    const leftX = endX - arrowSize * Math.cos(radian - arrowAngle);
    const leftY = endY - arrowSize * Math.sin(radian - arrowAngle);
    
    // 右翼
    const rightX = endX - arrowSize * Math.cos(radian + arrowAngle);
    const rightY = endY - arrowSize * Math.sin(radian + arrowAngle);
    
    ctx.moveTo(endX, endY);
    ctx.lineTo(leftX, leftY);
    ctx.lineTo(rightX, rightY);
    ctx.closePath();
    ctx.fill();
    
    // 绘制中心点
    ctx.beginPath();
    ctx.fillStyle = '#409EFF';
    ctx.arc(centerX, centerY, 4, 0, Math.PI * 2);
    ctx.fill();
}

async function getSourceResolution() {
    // 默认后端处理分辨率
    let videoWidth = 960;
    let videoHeight = 540;

    // 文件模式使用原始视频分辨率，用于后端 ROI 坐标缩放
    if (state.sourceType === 'file' && state.currentFile) {
        const video = document.createElement('video');
        video.src = `/api/video/${state.currentFile}`;

        await new Promise((resolve) => {
            video.onloadedmetadata = () => {
                videoWidth = video.videoWidth;
                videoHeight = video.videoHeight;
                resolve();
            };
            video.onerror = () => resolve();
        });

        video.remove();
    }

    return { videoWidth, videoHeight };
}

async function confirmROI() {
    if (state.roiPoints.length < 3) {
        showMessage('请至少设置3个点形成有效区域', 'warning');
        return;
    }
    
    try {
        const { videoWidth, videoHeight } = await getSourceResolution();
        
        const response = await post('/api/set_roi', {
            points: state.roiPoints,
            video_width: videoWidth,
            video_height: videoHeight,
            direction_angle: state.directionAngle // 发送方向角度
        });
        
        if (response.success) {
            showMessage('ROI 区域已设置', 'success');
            state.roiSet = true;
            closeROIModal();
            updateSetupPrompt();
            updateUIState();
        } else {
            throw new Error(response.message || '设置失败');
        }
        
    } catch (error) {
        console.error('设置ROI错误:', error);
        showMessage('设置ROI失败: ' + error.message, 'error');
    }
}

// ============================================
// UI 状态管理
// ============================================
function updateUIState() {
    const btnUpload = document.getElementById('btnUpload');
    const btnCamera = document.getElementById('btnCamera');
    const btnStart = document.getElementById('btnStart');
    const btnStop = document.getElementById('btnStop');
    const btnROI = document.getElementById('btnROI');
    const btnDirection = document.getElementById('btnDirection');
    
    // 更新视频源显示
    const sourceText = state.sourceType === 'camera' ? '摄像头' : 
                       state.currentFile ? state.currentFile : '未连接';
    document.getElementById('videoSource').textContent = sourceText;
    
    if (state.isDetecting) {
        // 检测中状态
        btnUpload.disabled = true;
        btnCamera.disabled = true;
        btnStart.disabled = true;
        btnStop.disabled = false;
        btnROI.disabled = true;
        btnDirection.disabled = true;
    } else if (state.isPaused) {
        // 暂停状态
        btnUpload.disabled = true;
        btnCamera.disabled = true;
        btnStart.disabled = false;
        btnStop.disabled = true;
        btnROI.disabled = true;
        btnDirection.disabled = true;
    } else {
        // 未检测状态
        btnUpload.disabled = false;
        btnCamera.disabled = false;
        btnROI.disabled = !state.isConnected; // 连接后才可设置 ROI
        btnDirection.disabled = !state.isConnected; // 连接后才可设置方向
        
        // 只有 ROI 和方向都设置后，才能开始检测
        btnStart.disabled = !(state.isConnected && state.roiSet && state.directionSet);
        btnStop.disabled = true;
    }
}

// 更新提示信息
function updateSetupPrompt() {
    const prompt = document.getElementById('setupPrompt');
    
    // 如果已连接且未全部设置，则显示提示
    if (state.isConnected && (!state.roiSet || !state.directionSet)) {
        prompt.style.display = 'flex';
    } else {
        prompt.style.display = 'none';
    }
}

function showLoading(show) {
    const loadingState = document.getElementById('loadingState');
    const emptyState = document.getElementById('emptyState');
    
    if (show) {
        loadingState.style.display = 'flex';
        emptyState.style.display = 'none';
    } else {
        loadingState.style.display = 'none';
        // 如果视频未加载，显示空状态
        if (!state.isConnected) {
            emptyState.style.display = 'flex';
        }
    }
}

function showStatusIndicator(show) {
    const indicator = document.getElementById('statusIndicator');
    const statusText = document.getElementById('statusText');
    
    if (show) {
        indicator.style.display = 'flex';
        statusText.textContent = state.isDetecting ? '检测中' : '已暂停';
    } else {
        indicator.style.display = 'none';
    }
}

// ============================================
// 方向标定功能（独立弹窗）
// ============================================
function openDirectionModal() {
    if (!state.isConnected) {
        showMessage('请先上传视频或连接摄像头', 'warning');
        return;
    }
    
    const modal = document.getElementById('directionModal');
    modal.style.display = 'flex';
    
    // 加载视频帧到方向标定弹窗
    loadDirectionVideoFrame();
    
    // 初始化方向画布
    initDirectionCanvas();
    
    // 设置当前角度值
    const slider = document.getElementById('directionAngle');
    slider.value = state.directionAngle;
    document.getElementById('angleValue').textContent = `${state.directionAngle}°`;
    drawDirectionArrow(state.directionAngle);
}

// 加载视频帧到方向标定弹窗
function loadDirectionVideoFrame() {
    const directionVideoFrame = document.getElementById('directionVideoFrame');
    
    if (state.sourceType === 'file' && state.frameData) {
        // 使用已保存的帧数据
        directionVideoFrame.src = state.frameData;
        directionVideoFrame.style.display = 'block';
        
        // 等待图片加载后调整 canvas 尺寸
        directionVideoFrame.onload = () => {
            const overlayCanvas = document.getElementById('directionOverlayCanvas');
            // 设置 canvas 尺寸与实际显示的视频尺寸一致
            overlayCanvas.width = directionVideoFrame.clientWidth;
            overlayCanvas.height = directionVideoFrame.clientHeight;
            console.log('[方向标定] Canvas 尺寸:', overlayCanvas.width, 'x', overlayCanvas.height);
        };
    } else {
        // 摄像头模式：使用占位图或提示
        directionVideoFrame.style.display = 'none';
    }
}

function closeDirectionModal() {
    const modal = document.getElementById('directionModal');
    modal.style.display = 'none';
}

function resetDirectionAngle() {
    state.directionAngle = 0;
    const slider = document.getElementById('directionAngle');
    slider.value = 0;
    document.getElementById('angleValue').textContent = '0°';
    drawDirectionArrow(0);
}

async function confirmDirection() {
    try {
        const { videoWidth, videoHeight } = await getSourceResolution();

        // 发送方向角度到后端
        const response = await post('/api/set_roi', {
            points: state.roiPoints || [], // 只更新角度，保持 ROI 不变
            video_width: videoWidth,
            video_height: videoHeight,
            direction_angle: state.directionAngle
        });
        
        if (response.success) {
            showMessage('方向标定已完成', 'success');
            state.directionSet = true;
            closeDirectionModal();
            updateSetupPrompt();
            updateUIState();
        } else {
            throw new Error(response.message || '设置失败');
        }
    } catch (error) {
        console.error('设置方向错误:', error);
        showMessage('设置方向失败：' + error.message, 'error');
    }
}

// 点击弹窗外部关闭
window.onclick = (event) => {
    const roiModal = document.getElementById('roiModal');
    const directionModal = document.getElementById('directionModal');
    
    if (event.target === roiModal) {
        closeROIModal();
    }
    if (event.target === directionModal) {
        closeDirectionModal();
    }
};

// 页面卸载时清理
window.onbeforeunload = () => {
    if (state.ws) {
        state.ws.close();
    }
    if (state.isDetecting || state.isPaused) {
        // 发送停止请求
        navigator.sendBeacon('/api/stop_detection', JSON.stringify({}));
    }
};
