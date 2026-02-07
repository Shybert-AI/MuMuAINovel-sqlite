/**
 * 章节阅读器组件
 * 提供沉浸式阅读体验，支持主题切换、字体调节、翻页导航等功能
 */
import { useState, useEffect, useCallback } from 'react';
import { Modal, Button, Slider, Radio, Space, Typography, Spin, message } from 'antd';
import {
  LeftOutlined,
  RightOutlined,
  SettingOutlined,
  FontSizeOutlined,
  BgColorsOutlined,
  CloseOutlined,
  ColumnHeightOutlined
} from '@ant-design/icons';
import type { Chapter } from '../types';

// 阅读器设置接口
interface ReaderSettings {
  fontSize: number;       // 字体大小
  theme: 'light' | 'sepia' | 'dark';  // 主题模式
  lineHeight: number;     // 行高
}

// 组件属性接口
interface ChapterReaderProps {
  visible: boolean;                           // 是否显示
  chapter: Chapter;                           // 当前章节
  onClose: () => void;                        // 关闭回调
  onChapterChange: (chapterId: string) => void;  // 章节切换回调
}

// 导航信息接口
interface NavigationInfo {
  previous: { id: string; chapter_number: number; title: string } | null;
  next: { id: string; chapter_number: number; title: string } | null;
  current: { id: string; chapter_number: number; title: string };
}

// 主题样式配置
const themeStyles = {
  light: { 
    bg: '#ffffff', 
    text: '#333333',
    headerBg: '#fafafa',
    border: '#e8e8e8'
  },
  sepia: { 
    bg: '#f5e6c8', 
    text: '#5b4636',
    headerBg: '#e8d9b8',
    border: '#d4c5a5'
  },
  dark: { 
    bg: '#1a1a1a', 
    text: '#cccccc',
    headerBg: '#252525',
    border: '#333333'
  }
};

// 本地存储key
const SETTINGS_STORAGE_KEY = 'chapter-reader-settings';

// 从本地存储加载设置
const loadSettings = (): ReaderSettings => {
  try {
    const saved = localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (saved) {
      return JSON.parse(saved);
    }
  } catch (e) {
    console.warn('加载阅读器设置失败:', e);
  }
  return {
    fontSize: 18,
    theme: 'light',
    lineHeight: 1.8
  };
};

// 保存设置到本地存储
const saveSettings = (settings: ReaderSettings) => {
  try {
    localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
  } catch (e) {
    console.warn('保存阅读器设置失败:', e);
  }
};

export default function ChapterReader({ 
  visible, 
  chapter, 
  onClose, 
  onChapterChange 
}: ChapterReaderProps) {
  // 阅读器设置
  const [settings, setSettings] = useState<ReaderSettings>(loadSettings);
  
  // 导航信息
  const [navigation, setNavigation] = useState<NavigationInfo | null>(null);
  
  // 加载状态
  const [loading, setLoading] = useState(false);
  
  // 设置面板显示状态
  const [showSettings, setShowSettings] = useState(false);
  
  // 移动端检测
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);

  // 响应式检测
  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth <= 768);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // 获取章节导航信息
  useEffect(() => {
    if (visible && chapter?.id) {
      setLoading(true);
      fetch(`/api/chapters/${chapter.id}/navigation`)
        .then(res => {
          if (!res.ok) throw new Error('获取导航失败');
          return res.json();
        })
        .then(data => {
          setNavigation(data);
          setLoading(false);
        })
        .catch(err => {
          console.error('获取导航信息失败:', err);
          message.error('获取章节导航信息失败');
          setLoading(false);
        });
    }
  }, [visible, chapter?.id]);

  // 保存设置变更
  useEffect(() => {
    saveSettings(settings);
  }, [settings]);

  // 上一章
  const handlePrevious = useCallback(() => {
    if (navigation?.previous) {
      setLoading(true);
      onChapterChange(navigation.previous.id);
    }
  }, [navigation?.previous, onChapterChange]);

  // 下一章
  const handleNext = useCallback(() => {
    if (navigation?.next) {
      setLoading(true);
      onChapterChange(navigation.next.id);
    }
  }, [navigation?.next, onChapterChange]);

  // 键盘快捷键
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!visible) return;
      
      // 忽略输入框中的按键
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }
      
      switch (e.key) {
        case 'ArrowLeft':
          handlePrevious();
          break;
        case 'ArrowRight':
          handleNext();
          break;
        case 'Escape':
          onClose();
          break;
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [visible, handlePrevious, handleNext, onClose]);

  // 章节变化后自动回到顶部
  useEffect(() => {
    if (chapter?.id) {
      setLoading(false);
      // 找到滚动容器并滚动到顶部
      const scrollContainer = document.querySelector('.reader-scroll-container');
      if (scrollContainer) {
        scrollContainer.scrollTop = 0;
      }
    }
  }, [chapter?.id]);

  // 当前主题样式
  const currentTheme = themeStyles[settings.theme];

  // 更新设置的便捷函数
  const updateSettings = (key: keyof ReaderSettings, value: number | string) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  };

  return (
    <Modal
      open={visible}
      onCancel={onClose}
      footer={null}
      width="100%"
      style={{
        maxWidth: '100vw',
        top: 0,
        margin: 0,
        padding: 0,
        height: '100vh',
        overflow: 'hidden'
      }}
      styles={{
        content: {
          height: '100vh',
          borderRadius: 0,
          boxShadow: 'none',
          padding: 0,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden'
        },
        body: {
          flex: 1,
          padding: 0,
          background: currentTheme.bg,
          overflow: 'hidden',
          height: '100%',
          scrollbarWidth: 'thin',
          display: 'flex',
          flexDirection: 'column'
        }
      }}
      closable={false}
      maskClosable={false}
    >
      {/* 顶部工具栏 */}
      <div style={{
        flex: 'none',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: isMobile ? '10px 12px' : '12px 20px',
        borderBottom: `1px solid ${currentTheme.border}`,
        background: currentTheme.headerBg,
        zIndex: 10
      }}>
        <Button 
          type="text" 
          icon={<CloseOutlined />} 
          onClick={onClose}
          style={{ color: currentTheme.text }}
        >
          {!isMobile && '关闭'}
        </Button>
        
        <Typography.Title 
          level={5} 
          style={{ 
            margin: 0, 
            color: currentTheme.text,
            maxWidth: isMobile ? '60%' : '70%',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            fontSize: isMobile ? 14 : 16
          }}
        >
          第{chapter.chapter_number}章：{chapter.title}
        </Typography.Title>
        
        <Button
          type={showSettings ? 'primary' : 'text'}
          icon={<SettingOutlined />}
          onClick={() => setShowSettings(!showSettings)}
          style={{ color: showSettings ? undefined : currentTheme.text }}
          title="阅读设置"
        />
      </div>

      {/* 设置面板 */}
      {showSettings && (
        <div style={{
          padding: isMobile ? '12px 16px' : '16px 24px',
          borderBottom: `1px solid ${currentTheme.border}`,
          background: currentTheme.headerBg
        }}>
          <Space 
            direction={isMobile ? 'vertical' : 'horizontal'} 
            size="large"
            style={{ width: '100%' }}
            wrap
          >
            {/* 字体大小 */}
            <div style={{ minWidth: isMobile ? '100%' : 200 }}>
              <Space style={{ marginBottom: 8, color: currentTheme.text }}>
                <FontSizeOutlined />
                <span>字体大小: {settings.fontSize}px</span>
              </Space>
              <Slider
                min={14}
                max={28}
                value={settings.fontSize}
                onChange={v => updateSettings('fontSize', v)}
                style={{ margin: '8px 0' }}
              />
            </div>

            {/* 行高 */}
            <div style={{ minWidth: isMobile ? '100%' : 200 }}>
              <Space style={{ marginBottom: 8, color: currentTheme.text }}>
                <ColumnHeightOutlined />
                <span>行高: {settings.lineHeight}</span>
              </Space>
              <Slider
                min={1.4}
                max={2.5}
                step={0.1}
                value={settings.lineHeight}
                onChange={v => updateSettings('lineHeight', v)}
                style={{ margin: '8px 0' }}
              />
            </div>

            {/* 主题 */}
            <div>
              <Space style={{ marginBottom: 8, color: currentTheme.text }}>
                <BgColorsOutlined />
                <span>主题</span>
              </Space>
              <div>
                <Radio.Group
                  value={settings.theme}
                  onChange={e => updateSettings('theme', e.target.value)}
                  buttonStyle="solid"
                  size={isMobile ? 'small' : 'middle'}
                >
                  <Radio.Button value="light">日间</Radio.Button>
                  <Radio.Button value="sepia">护眼</Radio.Button>
                  <Radio.Button value="dark">夜间</Radio.Button>
                </Radio.Group>
              </div>
            </div>
          </Space>
        </div>
      )}

      {/* 章节内容区域 */}
      <div
        className="reader-scroll-container"
        style={{
          flex: 1,
          overflowY: 'auto',
          position: 'relative',
          scrollBehavior: 'smooth'
        }}
      >
        <Spin spinning={loading} tip="加载中...">
          <div
            style={{
              maxWidth: 1000,
              margin: '0 auto',
              padding: isMobile ? '24px 16px 40px' : '40px 60px 40px',
              minHeight: '100%',
              fontSize: settings.fontSize,
            lineHeight: settings.lineHeight,
            color: currentTheme.text,
            whiteSpace: 'pre-wrap',
            textAlign: 'justify',
            wordBreak: 'break-word',
            overflowWrap: 'break-word'
          }}
        >
          {chapter.content ? (
            // 按段落渲染内容，优化阅读体验
            chapter.content.split('\n').map((paragraph, index) => (
              paragraph.trim() ? (
                <p
                  key={index}
                  style={{
                    textIndent: '2em',
                    margin: 0,
                    marginBottom: '0.8em'
                  }}
                >
                  {paragraph}
                </p>
              ) : (
                <br key={index} />
              )
            ))
          ) : (
            <div style={{ 
              textAlign: 'center', 
              padding: '60px 20px',
              color: currentTheme.text,
              opacity: 0.6
            }}>
              暂无内容
            </div>
          )}
          </div>
        </Spin>
      </div>

      {/* 底部导航栏 */}
      <div style={{
        flex: 'none',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: isMobile ? '12px 16px' : '16px 24px',
        borderTop: `1px solid ${currentTheme.border}`,
        background: currentTheme.headerBg,
        zIndex: 100
      }}>
        <Button
          type="primary"
          icon={<LeftOutlined />}
          disabled={!navigation?.previous || loading}
          onClick={handlePrevious}
          size={isMobile ? 'middle' : 'large'}
        >
          {!isMobile && '上一章'}
        </Button>
        
        <div style={{ 
          textAlign: 'center',
          color: currentTheme.text,
          fontSize: isMobile ? 12 : 14
        }}>
          <div>{chapter.word_count || 0} 字</div>
          {navigation && (
            <div style={{ fontSize: isMobile ? 10 : 12, opacity: 0.7 }}>
              {navigation.previous ? `← ${navigation.previous.title}` : '已是第一章'}
              {' | '}
              {navigation.next ? `${navigation.next.title} →` : '已是最后一章'}
            </div>
          )}
        </div>
        
        <Button
          type="primary"
          disabled={!navigation?.next || loading}
          onClick={handleNext}
          size={isMobile ? 'middle' : 'large'}
        >
          {!isMobile && '下一章'}
          <RightOutlined />
        </Button>
      </div>
    </Modal>
  );
}