import React, { useMemo, useEffect, useRef } from 'react';

// 标注数据类型
export interface MemoryAnnotation {
  id: string;
  type: 'hook' | 'foreshadow' | 'plot_point' | 'character_event';
  title: string;
  content: string;
  importance: number;
  position: number;
  length: number;
  tags: string[];
  metadata: {
    strength?: number;
    foreshadowType?: 'planted' | 'resolved';
    relatedCharacters?: string[];
    [key: string]: unknown;
  };
}

// 文本片段类型
interface TextSegment {
  type: 'text' | 'annotated';
  content: string;
  annotation?: MemoryAnnotation;
  annotations?: MemoryAnnotation[]; // 🔧 支持多个标注
}

interface AnnotatedTextProps {
  content: string;
  annotations: MemoryAnnotation[];
  onAnnotationClick?: (annotation: MemoryAnnotation) => void;
  activeAnnotationId?: string;
  scrollToAnnotation?: string;
  style?: React.CSSProperties;
}

// 类型颜色映射
const TYPE_COLORS = {
  hook: '#ff6b6b',
  foreshadow: '#6b7bff',
  plot_point: '#51cf66',
  character_event: '#ffd93d',
};

// 类型图标映射
const TYPE_ICONS = {
  hook: '🎣',
  foreshadow: '🌟',
  plot_point: '💎',
  character_event: '👤',
};

/**
 * 带标注的文本组件
 * 将记忆标注可视化地展示在章节文本中
 */
const AnnotatedText: React.FC<AnnotatedTextProps> = ({
  content,
  annotations,
  onAnnotationClick,
  activeAnnotationId,
  scrollToAnnotation,
  style,
}) => {
  const annotationRefs = useRef<Record<string, HTMLSpanElement | null>>({});

  // 当需要滚动到特定标注时
  useEffect(() => {
    if (scrollToAnnotation && annotationRefs.current[scrollToAnnotation]) {
      const element = annotationRefs.current[scrollToAnnotation];
      element?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    }
  }, [scrollToAnnotation]);
  // 处理标注重叠和排序
  const processedAnnotations = useMemo(() => {
    if (!annotations || annotations.length === 0) {
      console.log('AnnotatedText: 没有标注数据');
      return [];
    }
    
    console.log(`AnnotatedText: 收到${annotations.length}个标注，内容长度${content.length}`);
    
    // 过滤掉无效位置的标注
    const validAnnotations = annotations.filter(
      (a) => a.position >= 0 && a.position < content.length
    );
    
    const invalidCount = annotations.length - validAnnotations.length;
    if (invalidCount > 0) {
      console.warn(`AnnotatedText: ${invalidCount}个标注位置无效，有效标注${validAnnotations.length}个`);
      console.log('无效标注:', annotations.filter(a => a.position < 0 || a.position >= content.length));
    }
    
    // 按位置排序
    return validAnnotations.sort((a, b) => a.position - b.position);
  }, [annotations, content]);

  // 将文本分割为带标注的片段
  const segments = useMemo(() => {
    if (processedAnnotations.length === 0) {
      return [{ type: 'text' as const, content }];
    }

    const result: TextSegment[] = [];
    let lastPos = 0;

    // 🔧 智能分组：检测重叠和相邻的标注
    const annotationRanges: Array<{
      start: number;
      end: number;
      annotations: MemoryAnnotation[];
    }> = [];

    for (const annotation of processedAnnotations) {
      const { position, length } = annotation;
      const actualLength = length > 0 ? length : 30;
      const start = position;
      const end = position + actualLength;

      // 查找是否有重叠或紧邻的范围
      const overlappingRange = annotationRanges.find(
        (range) =>
          (start >= range.start && start <= range.end) || // 起始点在范围内
          (end >= range.start && end <= range.end) || // 结束点在范围内
          (start <= range.start && end >= range.end) || // 完全包含
          Math.abs(start - range.end) <= 5 || // 紧邻（容差5字符）
          Math.abs(end - range.start) <= 5
      );

      if (overlappingRange) {
        // 合并到现有范围
        overlappingRange.start = Math.min(overlappingRange.start, start);
        overlappingRange.end = Math.max(overlappingRange.end, end);
        overlappingRange.annotations.push(annotation);
      } else {
        // 创建新范围
        annotationRanges.push({
          start,
          end,
          annotations: [annotation],
        });
      }
    }

    // 按起始位置排序
    annotationRanges.sort((a, b) => a.start - b.start);

    // 🔧 智能分片：将重叠区域分成多个小片段
    for (const range of annotationRanges) {
      // 添加前面的普通文本
      if (range.start > lastPos) {
        result.push({
          type: 'text',
          content: content.slice(lastPos, range.start),
        });
      }

      if (range.annotations.length === 1) {
        // 单个标注，直接添加
        result.push({
          type: 'annotated',
          content: content.slice(range.start, range.end),
          annotation: range.annotations[0],
          annotations: range.annotations,
        });
      } else {
        // 🔧 多个标注：将文本分成多个小片段
        const totalLength = range.end - range.start;
        const segmentLength = Math.max(1, Math.floor(totalLength / range.annotations.length));

        // 按重要性排序标注
        const sortedAnnotations = [...range.annotations].sort((a, b) => b.importance - a.importance);

        for (let i = 0; i < sortedAnnotations.length; i++) {
          const segmentStart = range.start + i * segmentLength;
          const segmentEnd = i === sortedAnnotations.length - 1
            ? range.end
            : range.start + (i + 1) * segmentLength;

          result.push({
            type: 'annotated',
            content: content.slice(segmentStart, segmentEnd),
            annotation: sortedAnnotations[i],
            annotations: sortedAnnotations, // 保留所有标注信息
          });
        }
      }

      lastPos = range.end;
    }

    // 添加剩余文本
    if (lastPos < content.length) {
      result.push({
        type: 'text',
        content: content.slice(lastPos),
      });
    }

    console.log(`AnnotatedText: 处理${processedAnnotations.length}个标注，生成${result.length}个片段`);
    return result;
  }, [content, processedAnnotations]);

  // 渲染标注片段
  const renderAnnotatedSegment = (segment: TextSegment, index: number) => {
    if (segment.type === 'text') {
      return <span key={index}>{segment.content}</span>;
    }

    const { annotation, annotations } = segment;
    if (!annotation) return null;

    const color = TYPE_COLORS[annotation.type];
    const icon = TYPE_ICONS[annotation.type];
    const isActive = activeAnnotationId === annotation.id;

    // 简化工具提示内容，不再使用复杂的React元素，改为纯文本或移除Tooltip
    const tooltipText = annotations && annotations.length > 1
      ? `此处有 ${annotations.length} 个标注`
      : `${annotation.title}: ${annotation.content.slice(0, 100)}${annotation.content.length > 100 ? '...' : ''}`;

    return (
      <span
        key={index}
        title={tooltipText}
        ref={(el) => {
          if (annotation) {
            annotationRefs.current[annotation.id] = el;
          }
        }}
        data-annotation-id={annotation?.id}
        className={`annotated-text ${isActive ? 'active' : ''}`}
        style={{
          position: 'relative',
          borderBottom: `2px solid ${color}`,
          cursor: 'pointer',
          backgroundColor: isActive ? `${color}22` : 'transparent',
          transition: 'all 0.2s',
          padding: '2px 0',
        }}
        onClick={() => onAnnotationClick?.(annotation)}
        onMouseEnter={(e) => {
          e.currentTarget.style.backgroundColor = `${color}33`;
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.backgroundColor = isActive
            ? `${color}22`
            : 'transparent';
        }}
      >
        {segment.content}
        <span
          style={{
            position: 'absolute',
            top: -20,
            left: '50%',
            transform: 'translateX(-50%)',
            fontSize: 14,
            pointerEvents: 'none',
          }}
        >
          {icon}
        </span>
      </span>
    );
  };

  return (
    <div
      style={{
        lineHeight: 2,
        fontSize: 16,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        ...style,
      }}
    >
      {segments.map((segment, index) => renderAnnotatedSegment(segment, index))}
    </div>
  );
};

export default AnnotatedText;