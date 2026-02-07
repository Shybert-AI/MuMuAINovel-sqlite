import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { List, Button, Modal, Form, Input, Select, message, Empty, Space, Badge, Tag, Card, InputNumber, Alert, Radio, Descriptions, Collapse, Popconfirm, FloatButton } from 'antd';
import { EditOutlined, FileTextOutlined, ThunderboltOutlined, LockOutlined, DownloadOutlined, SettingOutlined, FundOutlined, SyncOutlined, CheckCircleOutlined, CloseCircleOutlined, RocketOutlined, StopOutlined, InfoCircleOutlined, CaretRightOutlined, DeleteOutlined, BookOutlined, FormOutlined, PlusOutlined, ReadOutlined } from '@ant-design/icons';
import { useStore } from '../store';
import { useChapterSync } from '../store/hooks';
import { projectApi, writingStyleApi, chapterApi } from '../services/api';
import type { Chapter, ChapterUpdate, ApiError, WritingStyle, AnalysisTask, ExpansionPlanData } from '../types';
import type { TextAreaRef } from 'antd/es/input/TextArea';
import ChapterAnalysis from '../components/ChapterAnalysis';
import ExpansionPlanEditor from '../components/ExpansionPlanEditor';
import { SSELoadingOverlay } from '../components/SSELoadingOverlay';
import { SSEProgressModal } from '../components/SSEProgressModal';
import FloatingIndexPanel from '../components/FloatingIndexPanel';
import ChapterReader from '../components/ChapterReader';
import PartialRegenerateToolbar from '../components/PartialRegenerateToolbar';
import PartialRegenerateModal from '../components/PartialRegenerateModal';

const { TextArea } = Input;

// localStorage 缓存键名
const WORD_COUNT_CACHE_KEY = 'chapter_default_word_count';
const DEFAULT_WORD_COUNT = 3000;

// 从 localStorage 读取缓存的字数
const getCachedWordCount = (): number => {
  try {
    const cached = localStorage.getItem(WORD_COUNT_CACHE_KEY);
    if (cached) {
      const value = parseInt(cached, 10);
      if (!isNaN(value) && value >= 500 && value <= 10000) {
        return value;
      }
    }
  } catch (error) {
    console.warn('读取字数缓存失败:', error);
  }
  return DEFAULT_WORD_COUNT;
};

// 保存字数到 localStorage
const setCachedWordCount = (value: number): void => {
  try {
    localStorage.setItem(WORD_COUNT_CACHE_KEY, String(value));
  } catch (error) {
    console.warn('保存字数缓存失败:', error);
  }
};

export default function Chapters() {
  const { currentProject, chapters, outlines, setCurrentChapter, setCurrentProject } = useStore();
  const [modal, contextHolder] = Modal.useModal();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [isContinuing, setIsContinuing] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isGeneratingTitle, setIsGeneratingTitle] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form] = Form.useForm();
  const [editorForm] = Form.useForm();
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);
  const contentTextAreaRef = useRef<TextAreaRef>(null);
  const [writingStyles, setWritingStyles] = useState<WritingStyle[]>([]);
  const [selectedStyleId, setSelectedStyleId] = useState<number | undefined>();
  const [targetWordCount, setTargetWordCount] = useState<number>(getCachedWordCount);
  const [availableModels, setAvailableModels] = useState<Array<{ value: string, label: string }>>([]);
  const [selectedModel, setSelectedModel] = useState<string | undefined>();
  const [batchSelectedModel, setBatchSelectedModel] = useState<string | undefined>(); // 批量生成的模型选择
  const [temporaryNarrativePerspective, setTemporaryNarrativePerspective] = useState<string | undefined>(); // 临时人称选择
  const [analysisVisible, setAnalysisVisible] = useState(false);
  const [analysisChapterId, setAnalysisChapterId] = useState<string | null>(null);
  // 分析任务状态管理
  const [analysisTasksMap, setAnalysisTasksMap] = useState<Record<string, AnalysisTask>>({});
  const pollingIntervalsRef = useRef<Record<string, number>>({});
  const [isIndexPanelVisible, setIsIndexPanelVisible] = useState(false);

  // 阅读器状态
  const [readerVisible, setReaderVisible] = useState(false);
  const [readingChapter, setReadingChapter] = useState<Chapter | null>(null);

  // 规划编辑状态
  const [planEditorVisible, setPlanEditorVisible] = useState(false);
  const [editingPlanChapter, setEditingPlanChapter] = useState<Chapter | null>(null);

  // 局部重写状态
  const [partialRegenerateToolbarVisible, setPartialRegenerateToolbarVisible] = useState(false);
  const [partialRegenerateToolbarPosition, setPartialRegenerateToolbarPosition] = useState({ top: 0, left: 0 });
  const [selectedTextForRegenerate, setSelectedTextForRegenerate] = useState('');
  const [selectionStartPosition, setSelectionStartPosition] = useState(0);
  const [selectionEndPosition, setSelectionEndPosition] = useState(0);
  const [partialRegenerateModalVisible, setPartialRegenerateModalVisible] = useState(false);

  // 单章节生成进度状态
  const [singleChapterProgress, setSingleChapterProgress] = useState(0);
  const [singleChapterProgressMessage, setSingleChapterProgressMessage] = useState('');

  // 批量生成相关状态
  const [batchGenerateVisible, setBatchGenerateVisible] = useState(false);
  const [batchGenerating, setBatchGenerating] = useState(false);
  const [batchTaskId, setBatchTaskId] = useState<string | null>(null);
  const [batchForm] = Form.useForm();
  const [manualCreateForm] = Form.useForm();
  const [batchProgress, setBatchProgress] = useState<{
    status: string;
    total: number;
    completed: number;
    current_chapter_number: number | null;
    estimated_time_minutes?: number;
  } | null>(null);
  const batchPollingIntervalRef = useRef<number | null>(null);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth <= 768);
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // 处理文本选中 - 检测选中文本并显示浮动工具栏
  const handleTextSelection = useCallback(() => {
    // 只在编辑器打开时处理选中
    if (!isEditorOpen || isGenerating) {
      setPartialRegenerateToolbarVisible(false);
      return;
    }

    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) {
      setPartialRegenerateToolbarVisible(false);
      return;
    }

    const selectedText = selection.toString().trim();
    
    // 至少选中10个字符才显示工具栏
    if (selectedText.length < 10) {
      setPartialRegenerateToolbarVisible(false);
      return;
    }

    // 检查选中是否在 TextArea 内
    const textArea = contentTextAreaRef.current?.resizableTextArea?.textArea;
    if (!textArea) {
      setPartialRegenerateToolbarVisible(false);
      return;
    }
    
    // 检查选中是否在 textarea 内（需要特殊处理，因为 textarea 的选中不会创建 range）
    if (document.activeElement !== textArea) {
      setPartialRegenerateToolbarVisible(false);
      return;
    }

    // 获取 textarea 中的选中位置
    const start = textArea.selectionStart;
    const end = textArea.selectionEnd;
    const textContent = textArea.value;
    const selectedInTextArea = textContent.substring(start, end);

    if (selectedInTextArea.trim().length < 10) {
      setPartialRegenerateToolbarVisible(false);
      return;
    }

    // 计算浮动工具栏位置
    const rect = textArea.getBoundingClientRect();
    const computedStyle = window.getComputedStyle(textArea);
    const lineHeight = parseFloat(computedStyle.lineHeight) || 24;
    const paddingTop = parseFloat(computedStyle.paddingTop) || 0;
    
    // 计算选中文本起始位置所在的行号
    const textBeforeSelection = textContent.substring(0, start);
    const startLine = textBeforeSelection.split('\n').length - 1;
    
    // 计算选中文本在 textarea 中的视觉位置
    // 需要考虑 scrollTop（textarea 内部滚动偏移）
    const scrollTop = textArea.scrollTop;
    const visualTop = (startLine * lineHeight) + paddingTop - scrollTop;
    
    // 工具栏位置：textarea 顶部 + 选中文本的视觉位置 - 工具栏高度偏移
    const toolbarTop = rect.top + visualTop - 45;
    
    // 水平位置：放在 textarea 的右侧区域，避免遮挡文本
    const toolbarLeft = rect.right - 180;

    setSelectedTextForRegenerate(selectedInTextArea);
    setSelectionStartPosition(start);
    setSelectionEndPosition(end);
    
    // 计算工具栏位置，如果选中位置不在可视区域内，固定在边缘
    let finalTop = toolbarTop;
    if (visualTop < 0) {
      finalTop = rect.top + 10;
    } else if (visualTop > textArea.clientHeight) {
      finalTop = rect.bottom - 50;
    }
    
    setPartialRegenerateToolbarPosition({
      top: Math.max(rect.top + 10, Math.min(finalTop, rect.bottom - 50)),
      left: Math.min(Math.max(rect.left + 20, toolbarLeft), window.innerWidth - 200),
    });
    setPartialRegenerateToolbarVisible(true);
  }, [isEditorOpen, isGenerating]);

  // 更新工具栏位置的函数（不检测选中，只更新位置）
  const updateToolbarPosition = useCallback(() => {
    if (!partialRegenerateToolbarVisible || !selectedTextForRegenerate) return;
    
    const textArea = contentTextAreaRef.current?.resizableTextArea?.textArea;
    if (!textArea) return;
    
    const rect = textArea.getBoundingClientRect();
    const computedStyle = window.getComputedStyle(textArea);
    const lineHeight = parseFloat(computedStyle.lineHeight) || 24;
    const paddingTop = parseFloat(computedStyle.paddingTop) || 0;
    
    const textContent = textArea.value;
    const textBeforeSelection = textContent.substring(0, selectionStartPosition);
    const startLine = textBeforeSelection.split('\n').length - 1;
    
    const scrollTop = textArea.scrollTop;
    const visualTop = (startLine * lineHeight) + paddingTop - scrollTop;
    
    const toolbarTop = rect.top + visualTop - 45;
    // 固定在 textarea 右上角，不随选中位置变化
    const toolbarLeft = rect.right - 180;
    
    // 工具栏固定在 textarea 可视区域内，即使选中文本滚出视野也保持显示
    // 如果选中位置在可视区域内，跟随选中位置
    // 如果滚出视野，固定在顶部或底部边缘
    let finalTop = toolbarTop;
    if (visualTop < 0) {
      // 选中位置在上方视野外，工具栏固定在顶部
      finalTop = rect.top + 10;
    } else if (visualTop > textArea.clientHeight) {
      // 选中位置在下方视野外，工具栏固定在底部
      finalTop = rect.bottom - 50;
    }
    
    setPartialRegenerateToolbarPosition({
      top: Math.max(rect.top + 10, Math.min(finalTop, rect.bottom - 50)),
      left: Math.min(Math.max(rect.left + 20, toolbarLeft), window.innerWidth - 200),
    });
  }, [partialRegenerateToolbarVisible, selectedTextForRegenerate, selectionStartPosition]);

  // 监听选中事件
  useEffect(() => {
    if (!isEditorOpen) return;

    const textArea = contentTextAreaRef.current?.resizableTextArea?.textArea;
    if (!textArea) return;

    const handleMouseUp = () => {
      // 鼠标释放时检查选中
      setTimeout(handleTextSelection, 50);
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      // Shift + 方向键选中时检查
      if (e.shiftKey && ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) {
        setTimeout(handleTextSelection, 50);
      }
    };

    const handleScroll = () => {
      // 滚动时更新位置（使用 requestAnimationFrame 优化性能）
      requestAnimationFrame(updateToolbarPosition);
    };

    // 监听 textarea 滚动
    textArea.addEventListener('mouseup', handleMouseUp);
    textArea.addEventListener('keyup', handleKeyUp);
    textArea.addEventListener('scroll', handleScroll);

    // 同时监听 Modal body 滚动（Modal 内容可能在外层容器滚动）
    const modalBody = textArea.closest('.ant-modal-body');
    if (modalBody) {
      modalBody.addEventListener('scroll', handleScroll);
    }

    // 监听窗口大小变化
    window.addEventListener('resize', handleScroll);

    return () => {
      textArea.removeEventListener('mouseup', handleMouseUp);
      textArea.removeEventListener('keyup', handleKeyUp);
      textArea.removeEventListener('scroll', handleScroll);
      if (modalBody) {
        modalBody.removeEventListener('scroll', handleScroll);
      }
      window.removeEventListener('resize', handleScroll);
    };
  }, [isEditorOpen, handleTextSelection, updateToolbarPosition]);

  // 点击其他区域时隐藏工具栏
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      
      // 如果点击的是工具栏，不隐藏
      if (target.closest('[data-partial-regenerate-toolbar]')) {
        return;
      }
      
      // 如果点击的是 textarea，不隐藏
      if (target.tagName === 'TEXTAREA') {
        return;
      }
      
      // 如果点击的是 Modal 内部（包括滚动条），不隐藏
      if (target.closest('.ant-modal-content')) {
        return;
      }
      
      // 点击 Modal 外部才隐藏工具栏
      setPartialRegenerateToolbarVisible(false);
    };

    if (partialRegenerateToolbarVisible) {
      document.addEventListener('click', handleClickOutside);
      return () => document.removeEventListener('click', handleClickOutside);
    }
  }, [partialRegenerateToolbarVisible]);

  const {
    refreshChapters,
    updateChapter,
    deleteChapter,
    generateChapterContentStream
  } = useChapterSync();

  useEffect(() => {
    if (currentProject?.id) {
      refreshChapters();
      loadWritingStyles();
      loadAnalysisTasks();
      checkAndRestoreBatchTask();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentProject?.id]);

  // 清理轮询定时器
  useEffect(() => {
    const pollingIntervals = pollingIntervalsRef.current;
    const batchPollingInterval = batchPollingIntervalRef.current;
    return () => {
      Object.values(pollingIntervals).forEach(interval => {
        clearInterval(interval);
      });
      if (batchPollingInterval) {
        clearInterval(batchPollingInterval);
      }
    };
  }, []);

  // 加载所有章节的分析任务状态
  // 接受可选的 chaptersToLoad 参数，解决 React 状态更新延迟导致的问题
  const loadAnalysisTasks = async (chaptersToLoad?: typeof chapters) => {
    const targetChapters = chaptersToLoad || chapters;
    if (!targetChapters || targetChapters.length === 0) return;

    const tasksMap: Record<string, AnalysisTask> = {};

    for (const chapter of targetChapters) {
      // 只查询有内容的章节
      if (chapter.content && chapter.content.trim() !== '') {
        try {
          const response = await fetch(`/api/chapters/${chapter.id}/analysis/status`);
          if (response.ok) {
            const task: AnalysisTask = await response.json();
            tasksMap[chapter.id] = task;

            // 如果任务正在运行，启动轮询
            if (task.status === 'pending' || task.status === 'running') {
              startPollingTask(chapter.id);
            }
          }
        } catch {
          // 404或其他错误表示没有分析任务，忽略
          console.debug(`章节 ${chapter.id} 暂无分析任务`);
        }
      }
    }

    setAnalysisTasksMap(tasksMap);
  };

  // 启动单个章节的任务轮询
  const startPollingTask = (chapterId: string) => {
    // 如果已经在轮询，先清除
    if (pollingIntervalsRef.current[chapterId]) {
      clearInterval(pollingIntervalsRef.current[chapterId]);
    }

    const interval = window.setInterval(async () => {
      try {
        const response = await fetch(`/api/chapters/${chapterId}/analysis/status`);
        if (!response.ok) return;

        const task: AnalysisTask = await response.json();

        setAnalysisTasksMap(prev => ({
          ...prev,
          [chapterId]: task
        }));

        // 任务完成或失败，停止轮询
        if (task.status === 'completed' || task.status === 'failed') {
          clearInterval(pollingIntervalsRef.current[chapterId]);
          delete pollingIntervalsRef.current[chapterId];

          if (task.status === 'completed') {
            message.success(`章节分析完成`);
          } else if (task.status === 'failed') {
            message.error(`章节分析失败: ${task.error_message || '未知错误'}`);
          }
        }
      } catch (error) {
        console.error('轮询分析任务失败:', error);
      }
    }, 2000);

    pollingIntervalsRef.current[chapterId] = interval;

    // 5分钟超时
    setTimeout(() => {
      if (pollingIntervalsRef.current[chapterId]) {
        clearInterval(pollingIntervalsRef.current[chapterId]);
        delete pollingIntervalsRef.current[chapterId];
      }
    }, 300000);
  };

  const loadWritingStyles = async () => {
    if (!currentProject?.id) return;

    try {
      const response = await writingStyleApi.getProjectStyles(currentProject.id);
      setWritingStyles(response.styles);

      // 设置默认风格为初始选中
      const defaultStyle = response.styles.find(s => s.is_default);
      if (defaultStyle) {
        setSelectedStyleId(defaultStyle.id);
      }
    } catch (error) {
      console.error('加载写作风格失败:', error);
      message.error('加载写作风格失败');
    }
  };

  const loadAvailableModels = async () => {
    try {
      // 从设置API获取用户配置的模型列表
      const settingsResponse = await fetch('/api/settings');
      if (settingsResponse.ok) {
        const settings = await settingsResponse.json();
        const { api_key, api_base_url, api_provider } = settings;

        if (api_key && api_base_url) {
          try {
            const modelsResponse = await fetch(
              `/api/settings/models?api_key=${encodeURIComponent(api_key)}&api_base_url=${encodeURIComponent(api_base_url)}&provider=${api_provider}`
            );
            if (modelsResponse.ok) {
              const data = await modelsResponse.json();
              if (data.models && data.models.length > 0) {
                setAvailableModels(data.models);
                // 设置默认模型为当前配置的模型
                setSelectedModel(settings.llm_model);
                return settings.llm_model; // 返回模型名称
              }
            }
          } catch {
            console.log('获取模型列表失败，将使用默认模型');
          }
        }
      }
    } catch (error) {
      console.error('加载可用模型失败:', error);
    }
    return null;
  };

  // 检查并恢复批量生成任务
  const checkAndRestoreBatchTask = async () => {
    if (!currentProject?.id) return;

    try {
      const response = await fetch(`/api/chapters/project/${currentProject.id}/batch-generate/active`);
      if (!response.ok) return;

      const data = await response.json();

      if (data.has_active_task && data.task) {
        const task = data.task;

        // 恢复任务状态
        setBatchTaskId(task.batch_id);
        setBatchProgress({
          status: task.status,
          total: task.total,
          completed: task.completed,
          current_chapter_number: task.current_chapter_number,
        });
        setBatchGenerating(true);
        setBatchGenerateVisible(true);

        // 启动轮询
        startBatchPolling(task.batch_id);

        message.info('检测到未完成的批量生成任务，已自动恢复');
      }
    } catch (error) {
      console.error('检查批量生成任务失败:', error);
    }
  };

  // 🔔 显示浏览器通知
  const showBrowserNotification = (title: string, body: string, type: 'success' | 'error' | 'info' = 'info') => {
    // 检查浏览器是否支持通知
    if (!('Notification' in window)) {
      console.log('浏览器不支持通知功能');
      return;
    }

    // 检查通知权限
    if (Notification.permission === 'granted') {
      // 选择图标
      const icon = type === 'success' ? '/logo.svg' : type === 'error' ? '/favicon.ico' : '/logo.svg';
      
      const notification = new Notification(title, {
        body,
        icon,
        badge: '/favicon.ico',
        tag: 'batch-generation', // 相同tag会替换旧通知
        requireInteraction: false, // 自动关闭
        silent: false, // 播放提示音
      });

      // 点击通知时聚焦到窗口
      notification.onclick = () => {
        window.focus();
        notification.close();
      };

      // 5秒后自动关闭
      setTimeout(() => {
        notification.close();
      }, 5000);
    } else if (Notification.permission !== 'denied') {
      // 如果权限未被明确拒绝，尝试请求权限
      Notification.requestPermission().then(permission => {
        if (permission === 'granted') {
          showBrowserNotification(title, body, type);
        }
      });
    }
  };

  // 按章节号排序并按大纲分组章节 (必须在早返回之前调用，避免违反 Hooks 规则)
  const { sortedChapters, groupedChapters } = useMemo(() => {
    const sorted = [...chapters].sort((a, b) => a.chapter_number - b.chapter_number);
    
    const groups: Record<string, {
      outlineId: string | null;
      outlineTitle: string;
      outlineOrder: number;
      chapters: Chapter[];
    }> = {};

    sorted.forEach(chapter => {
      const key = chapter.outline_id || 'uncategorized';

      if (!groups[key]) {
        groups[key] = {
          outlineId: chapter.outline_id || null,
          outlineTitle: chapter.outline_title || '未分类章节',
          outlineOrder: chapter.outline_order ?? 999,
          chapters: []
        };
      }

      groups[key].chapters.push(chapter);
    });

    // 转换为数组并按大纲顺序排序
    const grouped = Object.values(groups).sort((a, b) => a.outlineOrder - b.outlineOrder);
    
    return { sortedChapters: sorted, groupedChapters: grouped };
  }, [chapters]);

  if (!currentProject) return null;

  // 获取人称的中文显示文本
  const getNarrativePerspectiveText = (perspective?: string): string => {
    const texts: Record<string, string> = {
      'first_person': '第一人称（我）',
      'third_person': '第三人称（他/她）',
      'omniscient': '全知视角',
    };
    return texts[perspective || ''] || '第三人称（默认）';
  };

  const canGenerateChapter = (chapter: Chapter): boolean => {
    if (chapter.chapter_number === 1) {
      return true;
    }

    const previousChapters = chapters.filter(
      c => c.chapter_number < chapter.chapter_number
    );

    // 检查所有前置章节是否有内容
    const allHaveContent = previousChapters.every(c => c.content && c.content.trim() !== '');
    if (!allHaveContent) {
      return false;
    }

    // 检查所有前置章节是否分析成功
    const allAnalyzed = previousChapters.every(c => {
      const task = analysisTasksMap[c.id];
      // 如果没有分析任务或分析失败，则不允许生成
      if (!task || !task.has_task) {
        return false;
      }
      // 只有completed状态才算分析成功
      return task.status === 'completed';
    });

    return allAnalyzed;
  };

  const getGenerateDisabledReason = (chapter: Chapter): string => {
    if (chapter.chapter_number === 1) {
      return '';
    }

    const previousChapters = chapters.filter(
      c => c.chapter_number < chapter.chapter_number
    );

    // 首先检查是否有未完成内容的章节
    const incompleteChapters = previousChapters.filter(
      c => !c.content || c.content.trim() === ''
    );

    if (incompleteChapters.length > 0) {
      const numbers = incompleteChapters.map(c => c.chapter_number).join('、');
      return `需要先完成前置章节：第 ${numbers} 章`;
    }

    // 检查是否有未分析或分析失败的章节
    const unanalyzedChapters = previousChapters.filter(c => {
      const task = analysisTasksMap[c.id];
      if (!task || !task.has_task) {
        return true; // 没有分析任务
      }
      return task.status !== 'completed'; // 分析未完成或失败
    });

    if (unanalyzedChapters.length > 0) {
      const numbers = unanalyzedChapters.map(c => c.chapter_number).join('、');
      const reasons = unanalyzedChapters.map(c => {
        const task = analysisTasksMap[c.id];
        if (!task || !task.has_task) {
          return '未分析';
        }
        if (task.status === 'pending') {
          return '等待分析';
        }
        if (task.status === 'running') {
          return '分析中';
        }
        if (task.status === 'failed') {
          return '分析失败';
        }
        return '状态未知';
      });
      return `需要先分析前置章节：第 ${numbers} 章 (${reasons.join('、')})`;
    }

    return '';
  };

  const handleOpenModal = (id: string) => {
    const chapter = chapters.find(c => c.id === id);
    if (chapter) {
      form.setFieldsValue(chapter);
      setEditingId(id);
      setIsModalOpen(true);
    }
  };

  const handleSubmit = async (values: ChapterUpdate) => {
    if (!editingId) return;

    try {
      await updateChapter(editingId, values);

      // 刷新章节列表以获取完整的章节数据（包括outline_title等联查字段）
      await refreshChapters();

      message.success('章节更新成功');
      setIsModalOpen(false);
      form.resetFields();
    } catch {
      message.error('操作失败');
    }
  };

  const handleOpenEditor = (id: string) => {
    const chapter = chapters.find(c => c.id === id);
    if (chapter) {
      setCurrentChapter(chapter);
      editorForm.setFieldsValue({
        title: chapter.title,
        content: chapter.content,
      });
      setEditingId(id);
      setTemporaryNarrativePerspective(undefined); // 重置人称选择
      setIsEditorOpen(true);
      // 打开编辑窗口时加载模型列表
      loadAvailableModels();
    }
  };

  const handleEditorSubmit = async (values: ChapterUpdate) => {
    if (!editingId || !currentProject) return;

    try {
      await updateChapter(editingId, values);

      // 刷新项目信息以更新总字数统计
      const updatedProject = await projectApi.getProject(currentProject.id);
      setCurrentProject(updatedProject);

      message.success('章节保存成功');
      setIsEditorOpen(false);
    } catch {
      message.error('保存失败');
    }
  };

  const handleGenerate = async () => {
    if (!editingId) return;

    try {
      setIsContinuing(true);
      setIsGenerating(true);
      setSingleChapterProgress(0);
      setSingleChapterProgressMessage('准备开始生成...');

      const result = await generateChapterContentStream(
        editingId,
        (content) => {
          editorForm.setFieldsValue({ content });

          if (contentTextAreaRef.current) {
            const textArea = contentTextAreaRef.current.resizableTextArea?.textArea;
            if (textArea) {
              textArea.scrollTop = textArea.scrollHeight;
            }
          }
        },
        selectedStyleId,
        targetWordCount,
        (progressMsg, progressValue) => {
          // 进度回调
          setSingleChapterProgress(progressValue);
          setSingleChapterProgressMessage(progressMsg);
        },
        selectedModel,  // 传递选中的模型
        temporaryNarrativePerspective  // 传递临时人称参数
      );

      message.success('AI创作成功，正在分析章节内容...');

      // 如果返回了分析任务ID，启动轮询
      if (result?.analysis_task_id) {
        const taskId = result.analysis_task_id;
        setAnalysisTasksMap(prev => ({
          ...prev,
          [editingId]: {
            has_task: true,
            task_id: taskId,
            chapter_id: editingId,
            status: 'pending',
            progress: 0
          }
        }));

        // 启动轮询
        startPollingTask(editingId);
      }
    } catch (error) {
      const apiError = error as ApiError;
      message.error('AI创作失败：' + (apiError.response?.data?.detail || apiError.message || '未知错误'));
    } finally {
      setIsContinuing(false);
      setIsGenerating(false);
      setSingleChapterProgress(0);
      setSingleChapterProgressMessage('');
    }
  };

  const handleGenerateTitle = async (chapterId: string | null) => {
    if (!chapterId) return;
    
    try {
      setIsGeneratingTitle(true);
      
      const response = await fetch(`/api/chapters/${chapterId}/generate-title`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || '生成标题失败');
      }
      
      const result = await response.json();
      console.log('生成标题结果:', result);
      
      // 更新表单中的标题字段
      form.setFieldsValue({ title: result.generated_title });
      
      // 验证字段是否已设置
      const currentTitle = form.getFieldValue('title');
      console.log('当前表单标题字段:', currentTitle);
      
      // 触发表单验证以更新UI
      try {
        await form.validateFields(['title']);
      } catch (error) {
        // 验证可能失败，但没关系
        console.log('标题字段验证:', error);
      }
      
      message.success('标题生成成功');
    } catch (error: unknown) {
      const err = error as Error;
      message.error('生成标题失败：' + (err.message || '未知错误'));
    } finally {
      setIsGeneratingTitle(false);
    }
  };

  const showGenerateModal = (chapter: Chapter) => {
    const previousChapters = chapters.filter(
      c => c.chapter_number < chapter.chapter_number
    ).sort((a, b) => a.chapter_number - b.chapter_number);

    const selectedStyle = writingStyles.find(s => s.id === selectedStyleId);

    const instance = modal.confirm({
      title: 'AI创作章节内容',
      width: 700,
      centered: true,
      content: (
        <div style={{ marginTop: 16 }}>
          <p>AI将根据以下信息创作本章内容：</p>
          <ul>
            <li>章节大纲和要求</li>
            <li>项目的世界观设定</li>
            <li>相关角色信息</li>
            <li><strong>前面已完成章节的内容（确保剧情连贯）</strong></li>
            {selectedStyle && (
              <li><strong>写作风格：{selectedStyle.name}</strong></li>
            )}
            <li><strong>目标字数：{targetWordCount}字</strong></li>
          </ul>

          {previousChapters.length > 0 && (
            <div style={{
              marginTop: 16,
              padding: 12,
              background: 'var(--color-info-bg)',
              borderRadius: 4,
              border: '1px solid var(--color-info-border)'
            }}>
              <div style={{ marginBottom: 8, fontWeight: 500, color: 'var(--color-primary)' }}>
                📚 将引用的前置章节（共{previousChapters.length}章）：
              </div>
              <div style={{ maxHeight: 150, overflowY: 'auto' }}>
                {previousChapters.map(ch => (
                  <div key={ch.id} style={{ padding: '4px 0', fontSize: 13 }}>
                    ✓ 第{ch.chapter_number}章：{ch.title} ({ch.word_count || 0}字)
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 8, fontSize: 12, color: '#666' }}>
                💡 AI会参考这些章节内容，确保情节连贯、角色状态一致
              </div>
            </div>
          )}

          <p style={{ color: '#ff4d4f', marginTop: 16, marginBottom: 0 }}>
            ⚠️ 注意：此操作将覆盖当前章节内容
          </p>
        </div>
      ),
      okText: '开始创作',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        instance.update({
          okButtonProps: { danger: true, loading: true },
          cancelButtonProps: { disabled: true },
          closable: false,
          maskClosable: false,
          keyboard: false,
        });

        try {
          if (!selectedStyleId) {
            message.error('请先选择写作风格');
            instance.update({
              okButtonProps: { danger: true, loading: false },
              cancelButtonProps: { disabled: false },
              closable: true,
              maskClosable: true,
              keyboard: true,
            });
            return;
          }
          await handleGenerate();
          instance.destroy();
        } catch {
          instance.update({
            okButtonProps: { danger: true, loading: false },
            cancelButtonProps: { disabled: false },
            closable: true,
            maskClosable: true,
            keyboard: true,
          });
        }
      },
      onCancel: () => {
        if (isGenerating) {
          message.warning('AI正在创作中，请等待完成');
          return false;
        }
      },
    });
  };

  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      'draft': 'default',
      'writing': 'processing',
      'completed': 'success',
    };
    return colors[status] || 'default';
  };

  const getStatusText = (status: string) => {
    const texts: Record<string, string> = {
      'draft': '草稿',
      'writing': '创作中',
      'completed': '已完成',
    };
    return texts[status] || status;
  };

  const handleExport = () => {
    if (chapters.length === 0) {
      message.warning('当前项目没有章节，无法导出');
      return;
    }

    modal.confirm({
      title: '导出项目章节',
      content: `确定要将《${currentProject.title}》的所有章节导出为TXT文件吗？`,
      centered: true,
      okText: '确定导出',
      cancelText: '取消',
      onOk: () => {
        try {
          projectApi.exportProject(currentProject.id);
          message.success('开始下载导出文件');
        } catch {
          message.error('导出失败，请重试');
        }
      },
    });
  };

  const handleShowAnalysis = (chapterId: string) => {
    setAnalysisChapterId(chapterId);
    setAnalysisVisible(true);
  };

  // 批量生成函数
  const handleBatchGenerate = async (values: {
    startChapterNumber: number;
    count: number;
    enableAnalysis: boolean;
    styleId?: number;
    targetWordCount?: number;
    model?: string;
  }) => {
    if (!currentProject?.id) return;

    // 调试日志
    console.log('[批量生成] 表单values:', values);
    console.log('[批量生成] batchSelectedModel状态:', batchSelectedModel);

    // 使用批量生成对话框中选择的风格和字数，如果没有选择则使用默认值
    const styleId = values.styleId || selectedStyleId;
    const wordCount = values.targetWordCount || targetWordCount;

    // 使用批量生成专用的模型状态
    const model = batchSelectedModel;

    console.log('[批量生成] 最终使用的model:', model);

    if (!styleId) {
      message.error('请选择写作风格');
      return;
    }

    try {
      setBatchGenerating(true);
      setBatchGenerateVisible(false); // 关闭配置对话框，避免遮挡进度弹窗

      const requestBody: {
        start_chapter_number: number;
        count: number;
        enable_analysis: boolean;
        style_id: number;
        target_word_count: number;
        model?: string;
      } = {
        start_chapter_number: values.startChapterNumber,
        count: values.count,
        enable_analysis: true,
        style_id: styleId,
        target_word_count: wordCount,
      };

      // 如果有模型参数，添加到请求体中
      if (model) {
        requestBody.model = model;
        console.log('[批量生成] 请求体包含model:', model);
      } else {
        console.log('[批量生成] 请求体不包含model，使用后端默认模型');
      }

      console.log('[批量生成] 完整请求体:', JSON.stringify(requestBody, null, 2));

      const response = await fetch(`/api/chapters/project/${currentProject.id}/batch-generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || '创建批量生成任务失败');
      }

      const result = await response.json();
      setBatchTaskId(result.batch_id);
      setBatchProgress({
        status: 'running',
        total: result.chapters_to_generate.length,
        completed: 0,
        current_chapter_number: values.startChapterNumber,
        estimated_time_minutes: result.estimated_time_minutes,
      });

      message.success(`批量生成任务已创建，预计需要 ${result.estimated_time_minutes} 分钟`);

      // 🔔 触发浏览器通知（任务开始）
      showBrowserNotification(
        '批量生成已启动',
        `开始生成 ${result.chapters_to_generate.length} 章，预计需要 ${result.estimated_time_minutes} 分钟`,
        'info'
      );

      // 开始轮询任务状态
      startBatchPolling(result.batch_id);

    } catch (error: unknown) {
      const err = error as Error;
      message.error('创建批量生成任务失败：' + (err.message || '未知错误'));
      setBatchGenerating(false);
      setBatchGenerateVisible(false);
    }
  };

  // 轮询批量生成任务状态
  const startBatchPolling = (taskId: string) => {
    if (batchPollingIntervalRef.current) {
      clearInterval(batchPollingIntervalRef.current);
    }

    const poll = async () => {
      try {
        const response = await fetch(`/api/chapters/batch-generate/${taskId}/status`);
        if (!response.ok) return;

        const status = await response.json();
        setBatchProgress({
          status: status.status,
          total: status.total,
          completed: status.completed,
          current_chapter_number: status.current_chapter_number,
        });

        // 每次轮询时刷新章节列表和分析状态，实时显示新生成的章节和分析进度
        // 使用 await 确保获取最新章节列表后再加载分析任务状态
        if (status.completed > 0) {
          const latestChapters = await refreshChapters();
          await loadAnalysisTasks(latestChapters);

          // 刷新项目信息以实时更新总字数统计
          if (currentProject?.id) {
            const updatedProject = await projectApi.getProject(currentProject.id);
            setCurrentProject(updatedProject);
          }
        }

        // 任务完成或失败，停止轮询
        if (status.status === 'completed' || status.status === 'failed' || status.status === 'cancelled') {
          if (batchPollingIntervalRef.current) {
            clearInterval(batchPollingIntervalRef.current);
            batchPollingIntervalRef.current = null;
          }

          setBatchGenerating(false);

          // 立即刷新章节列表和分析任务状态（在显示消息前）
          // 使用 refreshChapters 返回的最新章节列表传递给 loadAnalysisTasks
          const finalChapters = await refreshChapters();
          await loadAnalysisTasks(finalChapters);

          // 刷新项目信息以更新总字数统计
          if (currentProject?.id) {
            const updatedProject = await projectApi.getProject(currentProject.id);
            setCurrentProject(updatedProject);
          }

          if (status.status === 'completed') {
            message.success(`批量生成完成！成功生成 ${status.completed} 章`);
            // 🔔 触发浏览器通知
            showBrowserNotification(
              '批量生成完成',
              `《${currentProject?.title || '项目'}》成功生成 ${status.completed} 章节`,
              'success'
            );
          } else if (status.status === 'failed') {
            message.error(`批量生成失败：${status.error_message || '未知错误'}`);
            // 🔔 触发浏览器通知
            showBrowserNotification(
              '批量生成失败',
              status.error_message || '未知错误',
              'error'
            );
          } else if (status.status === 'cancelled') {
            message.warning('批量生成已取消');
          }

          // 延迟关闭对话框，让用户看到最终状态
          setTimeout(() => {
            setBatchGenerateVisible(false);
            setBatchTaskId(null);
            setBatchProgress(null);
          }, 2000);
        }
      } catch (error) {
        console.error('轮询批量生成状态失败:', error);
      }
    };

    // 立即执行一次
    poll();

    // 每2秒轮询一次
    batchPollingIntervalRef.current = window.setInterval(poll, 2000);
  };

  // 取消批量生成
  const handleCancelBatchGenerate = async () => {
    if (!batchTaskId) return;

    try {
      const response = await fetch(`/api/chapters/batch-generate/${batchTaskId}/cancel`, {
        method: 'POST',
      });

      if (!response.ok) {
        throw new Error('取消失败');
      }

      message.success('批量生成已取消');

      // 取消后立即刷新章节列表和分析任务，显示已生成的章节
      await refreshChapters();
      await loadAnalysisTasks();

      // 刷新项目信息以更新总字数统计
      if (currentProject?.id) {
        const updatedProject = await projectApi.getProject(currentProject.id);
        setCurrentProject(updatedProject);
      }
    } catch (error: unknown) {
      const err = error as Error;
      message.error('取消失败：' + (err.message || '未知错误'));
    }
  };

  // 打开批量生成对话框
  const handleOpenBatchGenerate = async () => {
    // 找到第一个未生成的章节
    const firstIncompleteChapter = sortedChapters.find(
      ch => !ch.content || ch.content.trim() === ''
    );

    if (!firstIncompleteChapter) {
      message.info('所有章节都已生成内容');
      return;
    }

    // 检查该章节是否可以生成
    if (!canGenerateChapter(firstIncompleteChapter)) {
      const reason = getGenerateDisabledReason(firstIncompleteChapter);
      message.warning(reason);
      return;
    }

    // 打开对话框时加载模型列表，等待完成
    const defaultModel = await loadAvailableModels();

    console.log('[打开批量生成] defaultModel:', defaultModel);
    console.log('[打开批量生成] selectedStyleId:', selectedStyleId);

    // 设置批量生成的模型选择状态
    setBatchSelectedModel(defaultModel || undefined);

    // 重置表单并设置初始值（使用缓存的字数）
    batchForm.setFieldsValue({
      startChapterNumber: firstIncompleteChapter.chapter_number,
      count: 5,
      enableAnalysis: false,
      styleId: selectedStyleId,
      targetWordCount: getCachedWordCount(),
    });

    setBatchGenerateVisible(true);
  };

  // 手动创建章节(仅one-to-many模式)
  const showManualCreateChapterModal = () => {
    // 计算下一个章节号
    const nextChapterNumber = chapters.length > 0
      ? Math.max(...chapters.map(c => c.chapter_number)) + 1
      : 1;

    modal.confirm({
      title: '手动创建章节',
      width: 600,
      centered: true,
      content: (
        <Form
          form={manualCreateForm}
          layout="vertical"
          initialValues={{
            chapter_number: nextChapterNumber,
            status: 'draft'
          }}
          style={{ marginTop: 16 }}
        >
          <Form.Item
            label="章节序号"
            name="chapter_number"
            rules={[{ required: true, message: '请输入章节序号' }]}
            tooltip="建议按顺序创建章节，确保内容连贯性"
          >
            <InputNumber min={1} style={{ width: '100%' }} placeholder="自动计算的下一个序号" />
          </Form.Item>

          <Form.Item
            label="章节标题"
            name="title"
            rules={[{ required: true, message: '请输入标题' }]}
          >
            <Input placeholder="例如：第一章 初遇" />
          </Form.Item>

          <Form.Item
            label="关联大纲"
            name="outline_id"
            rules={[{ required: true, message: '请选择关联的大纲' }]}
            tooltip="one-to-many模式下，章节必须关联到大纲"
          >
            <Select placeholder="请选择所属大纲">
              {/* 直接使用 store 中的 outlines 数据，而不是从现有章节中提取 */}
              {[...outlines]
                .sort((a, b) => a.order_index - b.order_index)
                .map(outline => (
                  <Select.Option key={outline.id} value={outline.id}>
                    第{outline.order_index}卷：{outline.title}
                  </Select.Option>
                ))}
            </Select>
          </Form.Item>

          <Form.Item
            label="章节摘要（可选）"
            name="summary"
            tooltip="简要描述本章的主要内容和情节发展"
          >
            <TextArea
              rows={4}
              placeholder="简要描述本章内容..."
            />
          </Form.Item>

          <Form.Item
            label="状态"
            name="status"
          >
            <Select>
              <Select.Option value="draft">草稿</Select.Option>
              <Select.Option value="writing">创作中</Select.Option>
              <Select.Option value="completed">已完成</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      ),
      okText: '创建',
      cancelText: '取消',
      onOk: async () => {
        const values = await manualCreateForm.validateFields();

        // 检查章节序号是否已存在
        const conflictChapter = chapters.find(
          ch => ch.chapter_number === values.chapter_number
        );

        if (conflictChapter) {
          // 显示冲突提示Modal
          modal.confirm({
            title: '章节序号冲突',
            icon: <InfoCircleOutlined style={{ color: '#ff4d4f' }} />,
            width: 500,
            centered: true,
            content: (
              <div>
                <p style={{ marginBottom: 12 }}>
                  第 <strong>{values.chapter_number}</strong> 章已存在：
                </p>
                <div style={{
                  padding: 12,
                  background: '#fff7e6',
                  borderRadius: 4,
                  border: '1px solid #ffd591',
                  marginBottom: 12
                }}>
                  <div><strong>标题：</strong>{conflictChapter.title}</div>
                  <div><strong>状态：</strong>{getStatusText(conflictChapter.status)}</div>
                  <div><strong>字数：</strong>{conflictChapter.word_count || 0}字</div>
                  {conflictChapter.outline_title && (
                    <div><strong>所属大纲：</strong>{conflictChapter.outline_title}</div>
                  )}
                </div>
                <p style={{ color: '#ff4d4f', marginBottom: 8 }}>
                  ⚠️ 是否删除旧章节并创建新章节？
                </p>
                <p style={{ fontSize: 12, color: '#666', marginBottom: 0 }}>
                  删除后将无法恢复，章节内容和分析结果都将被删除。
                </p>
              </div>
            ),
            okText: '删除并创建',
            okButtonProps: { danger: true },
            cancelText: '取消',
            onOk: async () => {
              try {
                // 先删除旧章节
                await handleDeleteChapter(conflictChapter.id);

                // 等待一小段时间确保删除完成
                await new Promise(resolve => setTimeout(resolve, 300));

                // 创建新章节
                await chapterApi.createChapter({
                  project_id: currentProject.id,
                  ...values
                });

                message.success('已删除旧章节并创建新章节');
                await refreshChapters();

                // 刷新项目信息以更新字数统计
                const updatedProject = await projectApi.getProject(currentProject.id);
                setCurrentProject(updatedProject);

                manualCreateForm.resetFields();
              } catch (error: unknown) {
                const err = error as Error;
                message.error('操作失败：' + (err.message || '未知错误'));
                throw error;
              }
            }
          });

          // 阻止外层Modal关闭
          return Promise.reject();
        }

        // 没有冲突，直接创建
        try {
          await chapterApi.createChapter({
            project_id: currentProject.id,
            ...values
          });
          message.success('章节创建成功');
          await refreshChapters();

          // 刷新项目信息以更新字数统计
          const updatedProject = await projectApi.getProject(currentProject.id);
          setCurrentProject(updatedProject);

          manualCreateForm.resetFields();
        } catch (error: unknown) {
          const err = error as Error;
          message.error('创建失败：' + (err.message || '未知错误'));
          throw error;
        }
      }
    });
  };

  // 渲染分析状态标签
  const renderAnalysisStatus = (chapterId: string) => {
    const task = analysisTasksMap[chapterId];

    if (!task) {
      return null;
    }

    switch (task.status) {
      case 'pending':
        return (
          <Tag icon={<SyncOutlined spin />} color="processing">
            等待分析
          </Tag>
        );
      case 'running': {
        // 检查是否正在重试（后端会在error_message中包含"重试"信息）
        const isRetrying = task.error_message && task.error_message.includes('重试');
        return (
          <Tag
            icon={<SyncOutlined spin />}
            color={isRetrying ? "warning" : "processing"}
            title={task.error_message || undefined}
          >
            {isRetrying ? `重试中 ${task.progress}%` : `分析中 ${task.progress}%`}
          </Tag>
        );
      }
      case 'completed':
        return (
          <Tag icon={<CheckCircleOutlined />} color="success">
            已分析
          </Tag>
        );
      case 'failed':
        return (
          <Tag icon={<CloseCircleOutlined />} color="error" title={task.error_message || undefined}>
            分析失败
          </Tag>
        );
      default:
        return null;
    }
  };

  // 显示展开规划详情
  const showExpansionPlanModal = (chapter: Chapter) => {
    if (!chapter.expansion_plan) return;

    try {
      const planData: ExpansionPlanData = JSON.parse(chapter.expansion_plan);

      modal.info({
        title: (
          <Space style={{ flexWrap: 'wrap' }}>
            <InfoCircleOutlined style={{ color: 'var(--color-primary)' }} />
            <span style={{ wordBreak: 'break-word' }}>第{chapter.chapter_number}章展开规划</span>
          </Space>
        ),
        width: isMobile ? 'calc(100vw - 32px)' : 800,
        centered: true,
        style: isMobile ? {
          maxWidth: 'calc(100vw - 32px)',
          margin: '0 auto',
          padding: '0 16px'
        } : undefined,
        styles: {
          body: {
            maxHeight: isMobile ? 'calc(100vh - 200px)' : 'calc(80vh - 110px)',
            overflowY: 'auto'
          }
        },
        content: (
          <div style={{ marginTop: 16 }}>
            <Descriptions
              column={1}
              size="small"
              bordered
              labelStyle={{
                whiteSpace: 'normal',
                wordBreak: 'break-word',
                width: isMobile ? '80px' : '100px'
              }}
              contentStyle={{
                whiteSpace: 'normal',
                wordBreak: 'break-word',
                overflowWrap: 'break-word'
              }}
            >
              <Descriptions.Item label="章节标题">
                <strong style={{
                  wordBreak: 'break-word',
                  whiteSpace: 'normal',
                  overflowWrap: 'break-word'
                }}>
                  {chapter.title}
                </strong>
              </Descriptions.Item>
              <Descriptions.Item label="情感基调">
                <Tag
                  color="blue"
                  style={{
                    whiteSpace: 'normal',
                    wordBreak: 'break-word',
                    height: 'auto',
                    lineHeight: '1.5',
                    padding: '4px 8px'
                  }}
                >
                  {planData.emotional_tone}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="冲突类型">
                <Tag
                  color="orange"
                  style={{
                    whiteSpace: 'normal',
                    wordBreak: 'break-word',
                    height: 'auto',
                    lineHeight: '1.5',
                    padding: '4px 8px'
                  }}
                >
                  {planData.conflict_type}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="预估字数">
                <Tag color="green">{planData.estimated_words}字</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="叙事目标">
                <span style={{
                  wordBreak: 'break-word',
                  whiteSpace: 'normal',
                  overflowWrap: 'break-word'
                }}>
                  {planData.narrative_goal}
                </span>
              </Descriptions.Item>
              <Descriptions.Item label="关键事件">
                <Space direction="vertical" size="small" style={{ width: '100%' }}>
                  {planData.key_events.map((event, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: '4px 0',
                        wordBreak: 'break-word',
                        whiteSpace: 'normal',
                        overflowWrap: 'break-word'
                      }}
                    >
                      <Tag color="purple" style={{ flexShrink: 0 }}>{idx + 1}</Tag>{' '}
                      <span style={{
                        wordBreak: 'break-word',
                        whiteSpace: 'normal',
                        overflowWrap: 'break-word'
                      }}>
                        {event}
                      </span>
                    </div>
                  ))}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="涉及角色">
                <Space wrap style={{ maxWidth: '100%' }}>
                  {planData.character_focus.map((char, idx) => (
                    <Tag
                      key={idx}
                      color="cyan"
                      style={{
                        whiteSpace: 'normal',
                        wordBreak: 'break-word',
                        height: 'auto',
                        lineHeight: '1.5'
                      }}
                    >
                      {char}
                    </Tag>
                  ))}
                </Space>
              </Descriptions.Item>
              {planData.scenes && planData.scenes.length > 0 && (
                <Descriptions.Item label="场景规划">
                  <Space direction="vertical" size="small" style={{ width: '100%' }}>
                    {planData.scenes.map((scene, idx) => (
                      <Card
                        key={idx}
                        size="small"
                        style={{
                          backgroundColor: '#fafafa',
                          maxWidth: '100%',
                          overflow: 'hidden'
                        }}
                      >
                        <div style={{
                          marginBottom: 4,
                          wordBreak: 'break-word',
                          whiteSpace: 'normal',
                          overflowWrap: 'break-word'
                        }}>
                          <strong>📍 地点：</strong>
                          <span style={{
                            wordBreak: 'break-word',
                            whiteSpace: 'normal',
                            overflowWrap: 'break-word'
                          }}>
                            {scene.location}
                          </span>
                        </div>
                        <div style={{ marginBottom: 4 }}>
                          <strong>👥 角色：</strong>
                          <Space
                            size="small"
                            wrap
                            style={{
                              marginLeft: isMobile ? 0 : 8,
                              marginTop: isMobile ? 4 : 0,
                              display: isMobile ? 'flex' : 'inline-flex'
                            }}
                          >
                            {scene.characters.map((char, charIdx) => (
                              <Tag
                                key={charIdx}
                                style={{
                                  whiteSpace: 'normal',
                                  wordBreak: 'break-word',
                                  height: 'auto'
                                }}
                              >
                                {char}
                              </Tag>
                            ))}
                          </Space>
                        </div>
                        <div style={{
                          wordBreak: 'break-word',
                          whiteSpace: 'normal',
                          overflowWrap: 'break-word'
                        }}>
                          <strong>🎯 目的：</strong>
                          <span style={{
                            wordBreak: 'break-word',
                            whiteSpace: 'normal',
                            overflowWrap: 'break-word'
                          }}>
                            {scene.purpose}
                          </span>
                        </div>
                      </Card>
                    ))}
                  </Space>
                </Descriptions.Item>
              )}
            </Descriptions>
            <Alert
              message="提示"
              description="这些是AI在大纲展开时生成的规划信息，可以作为创作章节内容时的参考。"
              type="info"
              showIcon
              style={{ marginTop: 16 }}
            />
          </div>
        ),
        okText: '关闭',
      });
    } catch (error) {
      console.error('解析展开规划失败:', error);
      message.error('展开规划数据格式错误');
    }
  };

  // 删除章节处理函数
  const handleDeleteChapter = async (chapterId: string) => {
    try {
      await deleteChapter(chapterId);

      // 刷新章节列表
      await refreshChapters();

      // 刷新项目信息以更新总字数统计
      if (currentProject) {
        const updatedProject = await projectApi.getProject(currentProject.id);
        setCurrentProject(updatedProject);
      }

      message.success('章节删除成功');
    } catch (error: unknown) {
      const err = error as Error;
      message.error('删除章节失败：' + (err.message || '未知错误'));
    }
  };

  // 打开规划编辑器
  const handleOpenPlanEditor = (chapter: Chapter) => {
    // 直接打开编辑器,如果没有规划数据则创建新的
    setEditingPlanChapter(chapter);
    setPlanEditorVisible(true);
  };

  // 保存规划信息
  const handleSavePlan = async (planData: ExpansionPlanData) => {
    if (!editingPlanChapter) return;

    try {
      const response = await fetch(`/api/chapters/${editingPlanChapter.id}/expansion-plan`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(planData),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || '更新失败');
      }

      // 刷新章节列表
      await refreshChapters();

      message.success('规划信息更新成功');

      // 关闭编辑器
      setPlanEditorVisible(false);
      setEditingPlanChapter(null);
    } catch (error: unknown) {
      const err = error as Error;
      message.error('保存规划失败：' + (err.message || '未知错误'));
      throw error;
    }
  };

  const handleChapterSelect = (chapterId: string) => {
    const element = document.getElementById(`chapter-item-${chapterId}`);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'center' });
      // Optional: add a visual highlight effect
      element.style.transition = 'background-color 0.5s ease';
      element.style.backgroundColor = '#e6f7ff';
      setTimeout(() => {
        element.style.backgroundColor = '';
      }, 1500);
    }
  };

  // 打开阅读器
  const handleOpenReader = (chapter: Chapter) => {
    setReadingChapter(chapter);
    setReaderVisible(true);
  };

  // 阅读器切换章节
  const handleReaderChapterChange = async (chapterId: string) => {
    try {
      const response = await fetch(`/api/chapters/${chapterId}`);
      if (!response.ok) throw new Error('获取章节失败');
      const newChapter = await response.json();
      setReadingChapter(newChapter);
    } catch {
      message.error('加载章节失败');
    }
  };

  // 打开局部重写弹窗
  const handleOpenPartialRegenerate = () => {
    setPartialRegenerateToolbarVisible(false);
    setPartialRegenerateModalVisible(true);
  };

  // 应用局部重写结果
  const handleApplyPartialRegenerate = (newText: string, startPos: number, endPos: number) => {
    // 获取当前内容
    const currentContent = editorForm.getFieldValue('content') || '';
    
    // 替换选中部分
    const newContent = currentContent.substring(0, startPos) + newText + currentContent.substring(endPos);
    
    // 更新表单
    editorForm.setFieldsValue({ content: newContent });
    
    // 关闭弹窗
    setPartialRegenerateModalVisible(false);
    
    message.success('局部重写已应用');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {contextHolder}
      <div style={{
        position: 'sticky',
        top: 0,
        zIndex: 10,
        backgroundColor: 'var(--color-bg-container)',
        padding: isMobile ? '12px 0' : '16px 0',
        marginBottom: isMobile ? 12 : 16,
        borderBottom: '1px solid #f0f0f0',
        display: 'flex',
        flexDirection: isMobile ? 'column' : 'row',
        gap: isMobile ? 12 : 0,
        justifyContent: 'space-between',
        alignItems: isMobile ? 'stretch' : 'center'
      }}>
        <h2 style={{ margin: 0, fontSize: isMobile ? 18 : 24 }}>
          <BookOutlined style={{ marginRight: 8 }} />
          章节管理
        </h2>
        <Space direction={isMobile ? 'vertical' : 'horizontal'} style={{ width: isMobile ? '100%' : 'auto' }}>
          {currentProject.outline_mode === 'one-to-many' && (
            <Button
              icon={<PlusOutlined />}
              onClick={showManualCreateChapterModal}
              block={isMobile}
              size={isMobile ? 'middle' : 'middle'}
            >
              手动创建
            </Button>
          )}
          <Button
            type="primary"
            icon={<RocketOutlined />}
            onClick={handleOpenBatchGenerate}
            disabled={chapters.length === 0}
            block={isMobile}
            size={isMobile ? 'middle' : 'middle'}
            style={{ background: '#722ed1', borderColor: '#722ed1' }}
          >
            批量生成
          </Button>
          <Button
            type="default"
            icon={<DownloadOutlined />}
            onClick={handleExport}
            disabled={chapters.length === 0}
            block={isMobile}
            size={isMobile ? 'middle' : 'middle'}
          >
            导出为TXT
          </Button>
          {!isMobile && (
            <Tag color="blue">
              {currentProject.outline_mode === 'one-to-one'
                ? '传统模式：章节由大纲管理，请在大纲页面操作'
                : '细化模式：章节可在大纲页面展开'}
            </Tag>
          )}
        </Space>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {chapters.length === 0 ? (
          <Empty description="还没有章节，开始创作吧！" />
        ) : currentProject.outline_mode === 'one-to-one' ? (
          // one-to-one 模式：直接显示扁平列表
          <List
            dataSource={sortedChapters}
            renderItem={(item) => (
              <List.Item
                id={`chapter-item-${item.id}`}
                style={{
                  padding: '16px',
                  marginBottom: 16,
                  background: '#fff',
                  borderRadius: 8,
                  border: '1px solid #f0f0f0',
                  flexDirection: isMobile ? 'column' : 'row',
                  alignItems: isMobile ? 'flex-start' : 'center',
                }}
                actions={isMobile ? undefined : [
                  <Button
                    type="text"
                    icon={<ReadOutlined />}
                    onClick={() => handleOpenReader(item)}
                    disabled={!item.content || item.content.trim() === ''}
                    title={!item.content || item.content.trim() === '' ? '暂无内容' : '沉浸式阅读'}
                  >
                    阅读
                  </Button>,
                  <Button
                    type="text"
                    icon={<EditOutlined />}
                    onClick={() => handleOpenEditor(item.id)}
                  >
                    编辑
                  </Button>,
                  (() => {
                    const task = analysisTasksMap[item.id];
                    const isAnalyzing = task && (task.status === 'pending' || task.status === 'running');
                    const hasContent = item.content && item.content.trim() !== '';

                    return (
                      <Button
                        type="text"
                        icon={isAnalyzing ? <SyncOutlined spin /> : <FundOutlined />}
                        onClick={() => handleShowAnalysis(item.id)}
                        disabled={!hasContent || isAnalyzing}
                        loading={isAnalyzing}
                        title={
                          !hasContent ? '请先生成章节内容' :
                            isAnalyzing ? '分析进行中，请稍候...' :
                              ''
                        }
                      >
                        {isAnalyzing ? '分析中' : '分析'}
                      </Button>
                    );
                  })(),
                  <Button
                    type="text"
                    icon={<SettingOutlined />}
                    onClick={() => handleOpenModal(item.id)}
                  >
                    修改
                  </Button>,
                ]}
              >
                <div style={{ width: '100%' }}>
                  <List.Item.Meta
                    avatar={!isMobile && <FileTextOutlined style={{ fontSize: 32, color: 'var(--color-primary)' }} />}
                    title={
                      <div style={{
                        display: 'flex',
                        flexDirection: isMobile ? 'column' : 'row',
                        alignItems: isMobile ? 'flex-start' : 'center',
                        gap: isMobile ? 6 : 12,
                        width: '100%'
                      }}>
                        <span style={{ fontSize: isMobile ? 14 : 16, fontWeight: 500, flexShrink: 0 }}>
                          第{item.chapter_number}章：{item.title}
                        </span>
                        <Space wrap size={isMobile ? 4 : 8}>
                          <Tag color={getStatusColor(item.status)}>{getStatusText(item.status)}</Tag>
                          <Badge count={`${item.word_count || 0}字`} style={{ backgroundColor: 'var(--color-success)' }} />
                          {renderAnalysisStatus(item.id)}
                          {!canGenerateChapter(item) && (
                            <Tag icon={<LockOutlined />} color="warning" title={getGenerateDisabledReason(item)}>
                              需前置章节
                            </Tag>
                          )}
                        </Space>
                      </div>
                    }
                    description={
                      item.content ? (
                        <div style={{ marginTop: 8, color: 'rgba(0,0,0,0.65)', lineHeight: 1.6, fontSize: isMobile ? 12 : 14 }}>
                          {item.content.substring(0, isMobile ? 80 : 150)}
                          {item.content.length > (isMobile ? 80 : 150) && '...'}
                        </div>
                      ) : (
                        <span style={{ color: 'rgba(0,0,0,0.45)', fontSize: isMobile ? 12 : 14 }}>暂无内容</span>
                      )
                    }
                  />

                  {isMobile && (
                    <Space style={{ marginTop: 12, width: '100%', justifyContent: 'flex-end' }} wrap>
                      <Button
                        type="text"
                        icon={<ReadOutlined />}
                        onClick={() => handleOpenReader(item)}
                        size="small"
                        disabled={!item.content || item.content.trim() === ''}
                        title={!item.content || item.content.trim() === '' ? '暂无内容' : '阅读'}
                      />
                      <Button
                        type="text"
                        icon={<EditOutlined />}
                        onClick={() => handleOpenEditor(item.id)}
                        size="small"
                        title="编辑"
                      />
                      {(() => {
                        const task = analysisTasksMap[item.id];
                        const isAnalyzing = task && (task.status === 'pending' || task.status === 'running');
                        const hasContent = item.content && item.content.trim() !== '';

                        return (
                          <Button
                            type="text"
                            icon={isAnalyzing ? <SyncOutlined spin /> : <FundOutlined />}
                            onClick={() => handleShowAnalysis(item.id)}
                            size="small"
                            disabled={!hasContent || isAnalyzing}
                            loading={isAnalyzing}
                            title={
                              !hasContent ? '请先生成章节内容' :
                                isAnalyzing ? '分析中' :
                                  '分析'
                            }
                          />
                        );
                      })()}
                      <Button
                        type="text"
                        icon={<SettingOutlined />}
                        onClick={() => handleOpenModal(item.id)}
                        size="small"
                        title="修改"
                      />
                    </Space>
                  )}
                </div>
              </List.Item>
            )}
          />
        ) : (
          // one-to-many 模式：按大纲分组显示
          <Collapse
            bordered={false}
            defaultActiveKey={groupedChapters.map((_, idx) => idx.toString())}
            expandIcon={({ isActive }) => <CaretRightOutlined rotate={isActive ? 90 : 0} />}
            style={{ background: 'transparent' }}
          >
            {groupedChapters.map((group, groupIndex) => (
              <Collapse.Panel
                key={groupIndex.toString()}
                header={
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <Tag color={group.outlineId ? 'blue' : 'default'} style={{ margin: 0 }}>
                      {group.outlineId ? `📖 大纲 ${group.outlineOrder}` : '📝 未分类'}
                    </Tag>
                    <span style={{ fontWeight: 600, fontSize: 16 }}>
                      {group.outlineTitle}
                    </span>
                    <Badge
                      count={`${group.chapters.length} 章`}
                      style={{ backgroundColor: 'var(--color-success)' }}
                    />
                    <Badge
                      count={`${group.chapters.reduce((sum, ch) => sum + (ch.word_count || 0), 0)} 字`}
                      style={{ backgroundColor: 'var(--color-primary)' }}
                    />
                  </div>
                }
                style={{
                  marginBottom: 16,
                  background: '#fff',
                  borderRadius: 8,
                  border: '1px solid #f0f0f0',
                }}
              >
                <List
                  dataSource={group.chapters}
                  renderItem={(item) => (
                    <List.Item
                      id={`chapter-item-${item.id}`}
                      style={{
                        padding: '16px 0',
                        borderRadius: 8,
                        transition: 'background 0.3s ease',
                        flexDirection: isMobile ? 'column' : 'row',
                        alignItems: isMobile ? 'flex-start' : 'center',
                      }}
                      actions={isMobile ? undefined : [
                        <Button
                          type="text"
                          icon={<ReadOutlined />}
                          onClick={() => handleOpenReader(item)}
                          disabled={!item.content || item.content.trim() === ''}
                          title={!item.content || item.content.trim() === '' ? '暂无内容' : '沉浸式阅读'}
                        >
                          阅读
                        </Button>,
                        <Button
                          type="text"
                          icon={<EditOutlined />}
                          onClick={() => handleOpenEditor(item.id)}
                        >
                          编辑
                        </Button>,
                        (() => {
                          const task = analysisTasksMap[item.id];
                          const isAnalyzing = task && (task.status === 'pending' || task.status === 'running');
                          const hasContent = item.content && item.content.trim() !== '';

                          return (
                            <Button
                              type="text"
                              icon={isAnalyzing ? <SyncOutlined spin /> : <FundOutlined />}
                              onClick={() => handleShowAnalysis(item.id)}
                              disabled={!hasContent || isAnalyzing}
                              loading={isAnalyzing}
                              title={
                                !hasContent ? '请先生成章节内容' :
                                  isAnalyzing ? '分析进行中，请稍候...' :
                                    ''
                              }
                            >
                              {isAnalyzing ? '分析中' : '分析'}
                            </Button>
                          );
                        })(),
                        <Button
                          type="text"
                          icon={<SettingOutlined />}
                          onClick={() => handleOpenModal(item.id)}
                        >
                          修改
                        </Button>,
                        // 只在 one-to-many 模式下显示删除按钮
                        ...(currentProject.outline_mode === 'one-to-many' ? [
                          <Popconfirm
                            title="确定删除这个章节吗？"
                            description="删除后将无法恢复，章节内容和分析结果都将被删除。"
                            onConfirm={() => handleDeleteChapter(item.id)}
                            okText="确定删除"
                            cancelText="取消"
                            okButtonProps={{ danger: true }}
                          >
                            <Button
                              type="text"
                              danger
                              icon={<DeleteOutlined />}
                            >
                              删除
                            </Button>
                          </Popconfirm>
                        ] : []),
                      ]}
                    >
                      <div style={{ width: '100%' }}>
                        <List.Item.Meta
                          avatar={!isMobile && <FileTextOutlined style={{ fontSize: 32, color: 'var(--color-primary)' }} />}
                          title={
                            <div style={{
                              display: 'flex',
                              flexDirection: isMobile ? 'column' : 'row',
                              alignItems: isMobile ? 'flex-start' : 'center',
                              gap: isMobile ? 6 : 12,
                              width: '100%'
                            }}>
                              <span style={{ fontSize: isMobile ? 14 : 16, fontWeight: 500, flexShrink: 0 }}>
                                第{item.chapter_number}章：{item.title}
                              </span>
                              <Space wrap size={isMobile ? 4 : 8}>
                                <Tag color={getStatusColor(item.status)}>{getStatusText(item.status)}</Tag>
                                <Badge count={`${item.word_count || 0}字`} style={{ backgroundColor: 'var(--color-success)' }} />
                                {renderAnalysisStatus(item.id)}
                                {!canGenerateChapter(item) && (
                                  <Tag icon={<LockOutlined />} color="warning" title={getGenerateDisabledReason(item)}>
                                    需前置章节
                                  </Tag>
                                )}
                                <Space size={4}>
                                  {item.expansion_plan && (
                                    <InfoCircleOutlined
                                      title="查看展开详情"
                                      style={{ color: 'var(--color-primary)', cursor: 'pointer', fontSize: 16 }}
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        showExpansionPlanModal(item);
                                      }}
                                    />
                                  )}
                                  <FormOutlined
                                    title={item.expansion_plan ? "编辑规划信息" : "创建规划信息"}
                                    style={{ color: 'var(--color-success)', cursor: 'pointer', fontSize: 16 }}
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleOpenPlanEditor(item);
                                    }}
                                  />
                                </Space>
                              </Space>
                            </div>
                          }
                          description={
                            item.content ? (
                              <div style={{ marginTop: 8, color: 'rgba(0,0,0,0.65)', lineHeight: 1.6, fontSize: isMobile ? 12 : 14 }}>
                                {item.content.substring(0, isMobile ? 80 : 150)}
                                {item.content.length > (isMobile ? 80 : 150) && '...'}
                              </div>
                            ) : (
                              <span style={{ color: 'rgba(0,0,0,0.45)', fontSize: isMobile ? 12 : 14 }}>暂无内容</span>
                            )
                          }
                        />

                        {isMobile && (
                          <Space style={{ marginTop: 12, width: '100%', justifyContent: 'flex-end' }} wrap>
                            <Button
                              type="text"
                              icon={<ReadOutlined />}
                              onClick={() => handleOpenReader(item)}
                              size="small"
                              disabled={!item.content || item.content.trim() === ''}
                              title={!item.content || item.content.trim() === '' ? '暂无内容' : '阅读'}
                            />
                            <Button
                              type="text"
                              icon={<EditOutlined />}
                              onClick={() => handleOpenEditor(item.id)}
                              size="small"
                              title="编辑"
                            />
                            {(() => {
                              const task = analysisTasksMap[item.id];
                              const isAnalyzing = task && (task.status === 'pending' || task.status === 'running');
                              const hasContent = item.content && item.content.trim() !== '';

                              return (
                                <Button
                                  type="text"
                                  icon={isAnalyzing ? <SyncOutlined spin /> : <FundOutlined />}
                                  onClick={() => handleShowAnalysis(item.id)}
                                  size="small"
                                  disabled={!hasContent || isAnalyzing}
                                  loading={isAnalyzing}
                                  title={
                                    !hasContent ? '请先生成章节内容' :
                                      isAnalyzing ? '分析中' :
                                        '分析'
                                  }
                                />
                              );
                            })()}
                            <Button
                              type="text"
                              icon={<SettingOutlined />}
                              onClick={() => handleOpenModal(item.id)}
                              size="small"
                              title="修改"
                            />
                            {/* 只在 one-to-many 模式下显示删除按钮 */}
                            {currentProject.outline_mode === 'one-to-many' && (
                              <Popconfirm
                                title="确定删除？"
                                description="删除后无法恢复"
                                onConfirm={() => handleDeleteChapter(item.id)}
                                okText="删除"
                                cancelText="取消"
                                okButtonProps={{ danger: true }}
                              >
                                <Button
                                  type="text"
                                  danger
                                  icon={<DeleteOutlined />}
                                  size="small"
                                  title="删除章节"
                                />
                              </Popconfirm>
                            )}
                          </Space>
                        )}
                      </div>
                    </List.Item>
                  )}
                />
              </Collapse.Panel>
            ))}
          </Collapse>
        )}
      </div>

      <Modal
        title={editingId ? '编辑章节信息' : '添加章节'}
        open={isModalOpen}
        onCancel={() => setIsModalOpen(false)}
        footer={null}
        centered
        width={isMobile ? 'calc(100vw - 32px)' : 520}
        style={isMobile ? {
          maxWidth: 'calc(100vw - 32px)',
          margin: '0 auto',
          padding: '0 16px'
        } : undefined}
        styles={{
          body: {
            maxHeight: isMobile ? 'calc(100vh - 200px)' : 'calc(80vh - 110px)',
            overflowY: 'auto'
          }
        }}
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
           <Form.Item
             label="章节标题"
             tooltip={
               currentProject.outline_mode === 'one-to-one'
                 ? "章节标题由大纲管理，请在大纲页面修改"
                 : "一对多模式下可以修改章节标题"
             }
             required={currentProject.outline_mode === 'one-to-many'}
           >
              <Space.Compact style={{ width: '100%' }}>
                <Form.Item 
                  name="title" 
                  noStyle
                  rules={
                    currentProject.outline_mode === 'one-to-many'
                      ? [{ required: true, message: '请输入章节标题' }]
                      : undefined
                  }
                >
                  <Input
                    placeholder="输入章节标题"
                    disabled={currentProject.outline_mode === 'one-to-one'}
                    style={{ flex: 1 }}
                  />
                </Form.Item>
                <Button
                  type="primary"
                  onClick={() => handleGenerateTitle(editingId)}
                  loading={isGeneratingTitle}
                  disabled={currentProject.outline_mode === 'one-to-one'}
                  title="AI生成标题"
                >
                  AI生成
                </Button>
              </Space.Compact>
            </Form.Item>

          <Form.Item
            label="章节序号"
            name="chapter_number"
            tooltip="章节序号不允许修改，请删除对应大纲，重新生成"
          >
            <Input type="number" placeholder="章节排序序号" disabled />
          </Form.Item>

          <Form.Item label="状态" name="status">
            <Select placeholder="选择状态">
              <Select.Option value="draft">草稿</Select.Option>
              <Select.Option value="writing">创作中</Select.Option>
              <Select.Option value="completed">已完成</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item>
            <Space style={{ float: 'right' }}>
              <Button onClick={() => setIsModalOpen(false)}>取消</Button>
              <Button type="primary" htmlType="submit">
                更新
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="编辑章节内容"
        open={isEditorOpen}
        onCancel={() => {
          if (isGenerating) {
            message.warning('AI正在创作中，请等待完成后再关闭');
            return;
          }
          setIsEditorOpen(false);
        }}
        closable={!isGenerating}
        maskClosable={false}
        keyboard={!isGenerating}
        width={isMobile ? 'calc(100vw - 32px)' : '85%'}
        centered
        style={isMobile ? {
          maxWidth: 'calc(100vw - 32px)',
          margin: '0 auto',
          padding: '0 16px'
        } : undefined}
        styles={{
          body: {
            maxHeight: isMobile ? 'calc(100vh - 200px)' : 'calc(100vh - 110px)',
            overflowY: 'auto',
            padding: isMobile ? '16px 12px' : '8px'
          }
        }}
        footer={null}
      >
        <Form form={editorForm} layout="vertical" onFinish={handleEditorSubmit}>
          {/* 章节标题和AI创作按钮 */}
          <Form.Item
            label="章节标题"
            tooltip="（1-1模式请在大纲修改，1-N模式请使用修改按钮编辑）"
            style={{ marginBottom: isMobile ? 16 : 12 }}
          >
            <Space.Compact style={{ width: '100%' }}>
              <Form.Item name="title" noStyle>
                <Input disabled style={{ flex: 1 }} />
              </Form.Item>
              {editingId && (() => {
                const currentChapter = chapters.find(c => c.id === editingId);
                const canGenerate = currentChapter ? canGenerateChapter(currentChapter) : false;
                const disabledReason = currentChapter ? getGenerateDisabledReason(currentChapter) : '';

                return (
                  <Button
                    type="primary"
                    icon={canGenerate ? <ThunderboltOutlined /> : <LockOutlined />}
                    onClick={() => currentChapter && showGenerateModal(currentChapter)}
                    loading={isContinuing}
                    disabled={!canGenerate}
                    danger={!canGenerate}
                    style={{ fontWeight: 'bold' }}
                    title={!canGenerate ? disabledReason : '根据大纲和前置章节内容创作'}
                  >
                    {isMobile ? 'AI' : 'AI创作'}
                  </Button>
                );
              })()}
            </Space.Compact>
          </Form.Item>

          {/* 第一行：写作风格 + 叙事角度 */}
          <div style={{
            display: isMobile ? 'block' : 'flex',
            gap: isMobile ? 0 : 16,
            marginBottom: isMobile ? 0 : 12
          }}>
            <Form.Item
              label="写作风格"
              tooltip="选择AI创作时使用的写作风格"
              required
              style={{ flex: 1, marginBottom: isMobile ? 16 : 0 }}
            >
              <Select
                placeholder="请选择写作风格"
                value={selectedStyleId}
                onChange={setSelectedStyleId}
                disabled={isGenerating}
                status={!selectedStyleId ? 'error' : undefined}
              >
                {writingStyles.map(style => (
                  <Select.Option key={style.id} value={style.id}>
                    {style.name}{style.is_default && ' (默认)'}
                  </Select.Option>
                ))}
              </Select>
              {!selectedStyleId && (
                <div style={{ color: '#ff4d4f', fontSize: 12, marginTop: 4 }}>请选择写作风格</div>
              )}
            </Form.Item>

            <Form.Item
              label="叙事角度"
              tooltip="第一人称(我)代入感强；第三人称(他/她)更客观；全知视角洞悉一切"
              style={{ flex: 1, marginBottom: isMobile ? 16 : 0 }}
            >
              <Select
                placeholder={`项目默认: ${getNarrativePerspectiveText(currentProject?.narrative_perspective)}`}
                value={temporaryNarrativePerspective}
                onChange={setTemporaryNarrativePerspective}
                allowClear
                disabled={isGenerating}
              >
                <Select.Option value="first_person">第一人称(我)</Select.Option>
                <Select.Option value="third_person">第三人称(他/她)</Select.Option>
                <Select.Option value="omniscient">全知视角</Select.Option>
              </Select>
              {temporaryNarrativePerspective && (
                <div style={{ color: 'var(--color-success)', fontSize: 12, marginTop: 4 }}>
                  ✓ {getNarrativePerspectiveText(temporaryNarrativePerspective)}
                </div>
              )}
            </Form.Item>
          </div>

          {/* 第二行：目标字数 + AI模型 */}
          <div style={{
            display: isMobile ? 'block' : 'flex',
            gap: isMobile ? 0 : 16,
            marginBottom: isMobile ? 16 : 12
          }}>
            <Form.Item
              label="目标字数"
              tooltip="AI生成章节时的目标字数，实际可能略有偏差（修改后会自动记住）"
              style={{ flex: 1, marginBottom: isMobile ? 16 : 0 }}
            >
              <InputNumber
                min={500}
                max={10000}
                step={100}
                value={targetWordCount}
                onChange={(value) => {
                  const newValue = value || DEFAULT_WORD_COUNT;
                  setTargetWordCount(newValue);
                  setCachedWordCount(newValue);
                }}
                disabled={isGenerating}
                style={{ width: '100%' }}
                formatter={(value) => `${value} 字`}
                parser={(value) => parseInt(value?.replace(' 字', '') || '0', 10) as unknown as 500}
              />
            </Form.Item>

            <Form.Item
              label="AI模型"
              tooltip="选择用于生成章节内容的AI模型，不选择则使用默认模型"
              style={{ flex: 1, marginBottom: isMobile ? 16 : 0 }}
            >
              <Select
                placeholder={selectedModel ? `默认: ${availableModels.find(m => m.value === selectedModel)?.label || selectedModel}` : "使用默认模型"}
                value={selectedModel}
                onChange={setSelectedModel}
                allowClear
                disabled={isGenerating}
                showSearch
                optionFilterProp="label"
              >
                {availableModels.map(model => (
                  <Select.Option key={model.value} value={model.value} label={model.label}>
                    {model.label}
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>
          </div>

          <Form.Item label="章节内容" name="content">
            <TextArea
              ref={contentTextAreaRef}
              rows={isMobile ? 12 : 20}
              placeholder="开始写作..."
              style={{ fontFamily: 'monospace', fontSize: isMobile ? 12 : 14 }}
              disabled={isGenerating}
            />
          </Form.Item>

          {/* 局部重写浮动工具栏 */}
          <div data-partial-regenerate-toolbar>
            <PartialRegenerateToolbar
              visible={partialRegenerateToolbarVisible && !isGenerating}
              position={partialRegenerateToolbarPosition}
              selectedText={selectedTextForRegenerate}
              onRegenerate={handleOpenPartialRegenerate}
            />
          </div>

          <Form.Item>
            <Space style={{ width: '100%', justifyContent: 'flex-end', flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'stretch' : 'center' }}>
              <Space style={{ width: isMobile ? '100%' : 'auto' }}>
                <Button
                  onClick={() => {
                    if (isGenerating) {
                      message.warning('AI正在创作中，请等待完成后再关闭');
                      return;
                    }
                    setIsEditorOpen(false);
                  }}
                  block={isMobile}
                  disabled={isGenerating}
                >
                  取消
                </Button>
                <Button
                  type="primary"
                  htmlType="submit"
                  block={isMobile}
                  disabled={isGenerating}
                >
                  保存章节
                </Button>
              </Space>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {analysisChapterId && (
        <ChapterAnalysis
          chapterId={analysisChapterId}
          visible={analysisVisible}
          onClose={() => {
            setAnalysisVisible(false);

            // 刷新章节列表以显示最新内容
            refreshChapters();

            // 刷新项目信息以更新字数统计
            if (currentProject) {
              projectApi.getProject(currentProject.id)
                .then(updatedProject => {
                  setCurrentProject(updatedProject);
                })
                .catch(error => {
                  console.error('刷新项目信息失败:', error);
                });
            }

            // 延迟500ms后刷新该章节的分析状态，给后端足够时间完成数据库写入
            if (analysisChapterId) {
              const chapterIdToRefresh = analysisChapterId;

              setTimeout(() => {
                fetch(`/api/chapters/${chapterIdToRefresh}/analysis/status`)
                  .then(response => {
                    if (response.ok) {
                      return response.json();
                    }
                    throw new Error('获取状态失败');
                  })
                  .then((task: AnalysisTask) => {
                    setAnalysisTasksMap(prev => ({
                      ...prev,
                      [chapterIdToRefresh]: task
                    }));

                    // 如果任务正在运行，启动轮询
                    if (task.status === 'pending' || task.status === 'running') {
                      startPollingTask(chapterIdToRefresh);
                    }
                  })
                  .catch(error => {
                    console.error('刷新分析状态失败:', error);
                    // 如果查询失败，再延迟尝试一次
                    setTimeout(() => {
                      fetch(`/api/chapters/${chapterIdToRefresh}/analysis/status`)
                        .then(response => response.ok ? response.json() : null)
                        .then((task: AnalysisTask | null) => {
                          if (task) {
                            setAnalysisTasksMap(prev => ({
                              ...prev,
                              [chapterIdToRefresh]: task
                            }));
                            if (task.status === 'pending' || task.status === 'running') {
                              startPollingTask(chapterIdToRefresh);
                            }
                          }
                        })
                        .catch(err => console.error('第二次刷新失败:', err));
                    }, 1000);
                  });
              }, 500);
            }

            setAnalysisChapterId(null);
          }}
        />
      )}

      {/* 批量生成对话框 */}
      <Modal
        title={
          <Space>
            <RocketOutlined style={{ color: '#722ed1' }} />
            <span>批量生成章节内容</span>
          </Space>
        }
        open={batchGenerateVisible}
        onCancel={() => {
          if (batchGenerating) {
            modal.confirm({
              title: '确认取消',
              content: '批量生成正在进行中，确定要取消吗？',
              okText: '确定取消',
              cancelText: '继续生成',
              centered: true,
              onOk: () => {
                handleCancelBatchGenerate();
                setBatchGenerateVisible(false);
              },
            });
          } else {
            setBatchGenerateVisible(false);
          }
        }}
        footer={!batchGenerating ? (
          <Space style={{ width: '100%', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
            <Button onClick={() => setBatchGenerateVisible(false)}>
              取消
            </Button>
            <Button type="primary" icon={<RocketOutlined />} onClick={() => batchForm.submit()}>
              开始批量生成
            </Button>
          </Space>
        ) : null}
        width={isMobile ? 'calc(100vw - 32px)' : 700}
        centered
        closable={!batchGenerating}
        maskClosable={!batchGenerating}
        style={isMobile ? {
          maxWidth: 'calc(100vw - 32px)',
          margin: '0 auto',
          padding: '0 16px'
        } : undefined}
        styles={{
          body: {
            maxHeight: isMobile ? 'calc(100vh - 200px)' : 'calc(100vh - 260px)',
            overflowY: 'auto',
            overflowX: 'hidden'
          }
        }}
      >
        {!batchGenerating ? (
          <Form
            form={batchForm}
            layout="vertical"
            onFinish={handleBatchGenerate}
            initialValues={{
              startChapterNumber: sortedChapters.find(ch => !ch.content || ch.content.trim() === '')?.chapter_number || 1,
              count: 5,
              enableAnalysis: true,
              styleId: selectedStyleId,
              targetWordCount: getCachedWordCount(),
              model: selectedModel,
            }}
          >
            <Alert
              message="批量生成说明：严格按序生成 | 统一风格字数 | 任一失败则终止"
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />

            {/* 第一行：起始章节 + 生成数量 */}
            <div style={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', gap: isMobile ? 0 : 16 }}>
              <Form.Item
                label="起始章节"
                name="startChapterNumber"
                rules={[{ required: true, message: '请选择' }]}
                style={{ flex: 1, marginBottom: 12 }}
              >
                <Select placeholder="选择起始章节">
                  {sortedChapters
                    .filter(ch => !ch.content || ch.content.trim() === '')
                    .filter(ch => canGenerateChapter(ch))
                    .map(ch => (
                      <Select.Option key={ch.id} value={ch.chapter_number}>
                        第{ch.chapter_number}章：{ch.title}
                      </Select.Option>
                    ))}
                </Select>
              </Form.Item>

              <Form.Item
                label="生成数量"
                name="count"
                rules={[{ required: true, message: '请选择' }]}
                style={{ marginBottom: 12 }}
              >
                <Radio.Group buttonStyle="solid" size={isMobile ? 'small' : 'middle'}>
                  <Radio.Button value={5}>5章</Radio.Button>
                  <Radio.Button value={10}>10章</Radio.Button>
                  <Radio.Button value={15}>15章</Radio.Button>
                  <Radio.Button value={20}>20章</Radio.Button>
                </Radio.Group>
              </Form.Item>
            </div>

            {/* 第二行：写作风格 + 目标字数 */}
            <div style={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', gap: isMobile ? 0 : 16 }}>
              <Form.Item
                label="写作风格"
                name="styleId"
                rules={[{ required: true, message: '请选择' }]}
                style={{ flex: 1, marginBottom: 12 }}
              >
                <Select placeholder="请选择写作风格" showSearch optionFilterProp="children">
                  {writingStyles.map(style => (
                    <Select.Option key={style.id} value={style.id}>
                      {style.name}{style.is_default && ' (默认)'}
                    </Select.Option>
                  ))}
                </Select>
              </Form.Item>

              <Form.Item
                label="目标字数"
                name="targetWordCount"
                rules={[{ required: true, message: '请设置' }]}
                tooltip="修改后自动记住"
                style={{ flex: 1, marginBottom: 12 }}
              >
                <InputNumber
                  min={500}
                  max={10000}
                  step={100}
                  style={{ width: '100%' }}
                  formatter={(value) => `${value} 字`}
                  parser={(value) => parseInt(value?.replace(' 字', '') || '0', 10) as unknown as 500}
                  onChange={(value) => {
                    if (value) {
                      setCachedWordCount(value);
                    }
                  }}
                />
              </Form.Item>
            </div>

            {/* 第三行：AI模型 + 同步分析 */}
            <div style={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', gap: isMobile ? 0 : 16 }}>
              <Form.Item
                label="AI模型"
                tooltip="不选则使用默认模型"
                style={{ flex: 1, marginBottom: 12 }}
              >
                <Select
                  placeholder={batchSelectedModel ? `默认: ${availableModels.find(m => m.value === batchSelectedModel)?.label || batchSelectedModel}` : "使用默认模型"}
                  value={batchSelectedModel}
                  onChange={setBatchSelectedModel}
                  allowClear
                  showSearch
                  optionFilterProp="label"
                >
                  {availableModels.map(model => (
                    <Select.Option key={model.value} value={model.value} label={model.label}>
                      {model.label}
                    </Select.Option>
                  ))}
                </Select>
              </Form.Item>

              <Form.Item
                label="同步分析"
                name="enableAnalysis"
                tooltip="必须开启，确保剧情连贯"
                style={{ marginBottom: 12 }}
              >
                <Radio.Group disabled>
                  <Radio value={true}>
                    <span style={{ fontSize: 12, color: '#52c41a' }}>✓ 自动更新角色状态</span>
                  </Radio>
                </Radio.Group>
              </Form.Item>
            </div>
          </Form>
        ) : (
          <div>
            <Alert
              message="温馨提示"
              description={
                <ul style={{ margin: '8px 0 0 0', paddingLeft: 20 }}>
                  <li>批量生成需要一定时间，可以切换到其他页面</li>
                  <li>关闭页面后重新打开，会自动恢复任务进度</li>
                  <li>可以随时点击"取消任务"按钮中止生成</li>
                  {batchProgress?.estimated_time_minutes && batchProgress.completed === 0 && (
                    <li>⏱️ 预计耗时：约 {batchProgress.estimated_time_minutes} 分钟</li>
                  )}
                </ul>
              }
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />

            <div style={{ textAlign: 'center' }}>
              <Button
                danger
                icon={<StopOutlined />}
                onClick={() => {
                  modal.confirm({
                    title: '确认取消',
                    content: '确定要取消批量生成吗？已生成的章节将保留。',
                    okText: '确定取消',
                    cancelText: '继续生成',
                    okButtonProps: { danger: true },
                    onOk: handleCancelBatchGenerate,
                  });
                }}
              >
                取消任务
              </Button>
            </div>
          </div>
        )}
      </Modal>

      {/* 单章节生成进度显示 */}
      <SSELoadingOverlay
        loading={isGenerating}
        progress={singleChapterProgress}
        message={singleChapterProgressMessage}
      />

      {/* 批量生成进度显示 - 使用统一的进度组件 */}
      <SSEProgressModal
        visible={batchGenerating}
        progress={batchProgress ? Math.round((batchProgress.completed / batchProgress.total) * 100) : 0}
        message={
          batchProgress?.current_chapter_number
            ? `正在生成第 ${batchProgress.current_chapter_number} 章... (${batchProgress.completed}/${batchProgress.total})`
            : `批量生成进行中... (${batchProgress?.completed || 0}/${batchProgress?.total || 0})`
        }
        title="批量生成章节"
        onCancel={() => {
          modal.confirm({
            title: '确认取消',
            content: '确定要取消批量生成吗？已生成的章节将保留。',
            okText: '确定取消',
            cancelText: '继续生成',
            okButtonProps: { danger: true },
            centered: true,
            onOk: handleCancelBatchGenerate,
          });
        }}
        cancelButtonText="取消任务"
      />

      <FloatButton
        icon={<BookOutlined />}
        type="primary"
        tooltip="章节目录"
        onClick={() => setIsIndexPanelVisible(true)}
        style={{ right: isMobile ? 24 : 48, bottom: isMobile ? 80 : 48 }}
      />

      <FloatingIndexPanel
        visible={isIndexPanelVisible}
        onClose={() => setIsIndexPanelVisible(false)}
        groupedChapters={groupedChapters}
        onChapterSelect={handleChapterSelect}
      />

      {/* 章节阅读器 */}
      {readingChapter && (
        <ChapterReader
          visible={readerVisible}
          chapter={readingChapter}
          onClose={() => {
            setReaderVisible(false);
            setReadingChapter(null);
          }}
          onChapterChange={handleReaderChapterChange}
        />
      )}

      {/* 局部重写弹窗 */}
      {editingId && (
        <PartialRegenerateModal
          visible={partialRegenerateModalVisible}
          chapterId={editingId}
          selectedText={selectedTextForRegenerate}
          startPosition={selectionStartPosition}
          endPosition={selectionEndPosition}
          styleId={selectedStyleId}
          onClose={() => setPartialRegenerateModalVisible(false)}
          onApply={handleApplyPartialRegenerate}
        />
      )}

      {/* 规划编辑器 */}
      {editingPlanChapter && currentProject && (() => {
        let parsedPlanData = null;
        try {
          if (editingPlanChapter.expansion_plan) {
            parsedPlanData = JSON.parse(editingPlanChapter.expansion_plan);
          }
        } catch (error) {
          console.error('解析规划数据失败:', error);
        }

        return (
          <ExpansionPlanEditor
            visible={planEditorVisible}
            planData={parsedPlanData}
            chapterSummary={editingPlanChapter.summary || null}
            projectId={currentProject.id}
            onSave={handleSavePlan}
            onCancel={() => {
              setPlanEditorVisible(false);
              setEditingPlanChapter(null);
            }}
          />
        );
      })()}
    </div>
  );
}