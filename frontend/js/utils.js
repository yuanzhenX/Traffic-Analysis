/**
 * 交通分析系统 - 公共工具函数
 */

// ============================================
// HTTP请求工具
// ============================================

/**
 * 发送GET请求
 * @param {string} url - 请求地址
 * @returns {Promise<any>} 响应数据
 */
async function get(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
}

/**
 * 发送POST请求
 * @param {string} url - 请求地址
 * @param {object} data - 请求数据
 * @returns {Promise<any>} 响应数据
 */
async function post(url, data = {}) {
    const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json();
}

// ============================================
// 日期时间工具
// ============================================

/**
 * 格式化日期时间
 * @param {Date|string} date - 日期对象或字符串
 * @param {string} format - 格式模板
 * @returns {string} 格式化后的字符串
 */
function formatDate(date, format = 'YYYY-MM-DD HH:mm:ss') {
    const d = new Date(date);
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const hour = String(d.getHours()).padStart(2, '0');
    const minute = String(d.getMinutes()).padStart(2, '0');
    const second = String(d.getSeconds()).padStart(2, '0');
    
    return format
        .replace('YYYY', year)
        .replace('MM', month)
        .replace('DD', day)
        .replace('HH', hour)
        .replace('mm', minute)
        .replace('ss', second);
}

/**
 * 获取今天的开始和结束时间
 * @returns {object} {startTime, endTime}
 */
function getTodayRange() {
    const now = new Date();
    const startTime = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0);
    const endTime = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59);
    return { startTime, endTime };
}

/**
 * 获取最近N小时的开始时间
 * @param {number} hours - 小时数
 * @returns {Date} 开始时间
 */
function getHoursAgo(hours) {
    return new Date(Date.now() - hours * 60 * 60 * 1000);
}

// ============================================
// 消息提示工具
// ============================================

/**
 * 显示消息提示
 * @param {string} message - 消息内容
 * @param {string} type - 消息类型: success/error/warning
 * @param {number} duration - 显示时长(毫秒)
 */
function showMessage(message, type = 'success', duration = 3000) {
    // 移除旧的消息
    const oldMessage = document.querySelector('.global-message');
    if (oldMessage) oldMessage.remove();
    
    // 创建消息元素
    const messageEl = document.createElement('div');
    messageEl.className = `message message-${type} global-message`;
    messageEl.style.cssText = `
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 9999;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        animation: slideDown 0.3s ease;
    `;
    
    const iconMap = {
        success: '✓',
        error: '✕',
        warning: '⚠'
    };
    
    messageEl.innerHTML = `<span>${iconMap[type]}</span><span>${message}</span>`;
    document.body.appendChild(messageEl);
    
    // 自动移除
    setTimeout(() => {
        messageEl.style.animation = 'slideUp 0.3s ease';
        setTimeout(() => messageEl.remove(), 300);
    }, duration);
}

// ============================================
// 图表工具
// ============================================

/**
 * 创建ECharts实例
 * @param {string} elementId - 容器ID
 * @returns {object} ECharts实例
 */
function createChart(elementId) {
    const element = document.getElementById(elementId);
    if (!element) {
        console.error(`Chart container #${elementId} not found`);
        return null;
    }
    return echarts.init(element);
}

/**
 * 响应式图表
 * @param {object} chart - ECharts实例
 */
function makeChartResponsive(chart) {
    window.addEventListener('resize', () => {
        chart && chart.resize();
    });
}

// ============================================
// 文件工具
// ============================================

/**
 * 格式化文件大小
 * @param {number} bytes - 字节数
 * @returns {string} 格式化后的字符串
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * 获取文件扩展名
 * @param {string} filename - 文件名
 * @returns {string} 扩展名
 */
function getFileExtension(filename) {
    return filename.slice((filename.lastIndexOf('.') - 1 >>> 0) + 2).toLowerCase();
}

// ============================================
// 导航工具
// ============================================

/**
 * 高亮当前导航项
 */
function highlightCurrentNav() {
    const currentPath = window.location.pathname;
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.classList.remove('active');
        const href = item.getAttribute('href');
        // 处理路径匹配：兼容带/和不带/的情况
        if (href === currentPath || 
            href === currentPath.substring(1) || 
            '/' + href === currentPath) {
            item.classList.add('active');
        }
    });
}

// ============================================
// 防抖节流
// ============================================

/**
 * 防抖函数
 * @param {Function} func - 原函数
 * @param {number} wait - 等待时间
 * @returns {Function} 防抖后的函数
 */
function debounce(func, wait = 300) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * 节流函数
 * @param {Function} func - 原函数
 * @param {number} limit - 限制时间
 * @returns {Function} 节流后的函数
 */
function throttle(func, limit = 300) {
    let inThrottle;
    return function executedFunction(...args) {
        if (!inThrottle) {
            func(...args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// ============================================
// 动画CSS
// ============================================

const animationStyles = `
    @keyframes slideDown {
        from { opacity: 0; transform: translate(-50%, -20px); }
        to { opacity: 1; transform: translate(-50%, 0); }
    }
    @keyframes slideUp {
        from { opacity: 1; transform: translate(-50%, 0); }
        to { opacity: 0; transform: translate(-50%, -20px); }
    }
`;

// 注入动画样式
const styleEl = document.createElement('style');
styleEl.textContent = animationStyles;
document.head.appendChild(styleEl);
