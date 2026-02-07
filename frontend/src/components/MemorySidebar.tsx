import React, { useMemo, useEffect, useRef } from 'react';
import { Card, Tag, Badge, Empty, Collapse, Divider } from 'antd';
import {
  FireOutlined,
  StarOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from '@ant-design/icons';
import type { MemoryAnnotation } from './AnnotatedText';

const { Panel } = Collapse;

interface MemorySidebarProps {
  annotations: MemoryAnnotation[];
  activeAnnotationId?: string;
  onAnnotationClick?: (annotation: MemoryAnnotation) => void;
  scrollToAnnotation?: string;
}

// 类型配置
const TYPE_CONFIG = {
  hook: {
    label: '钩子',
    icon: <FireOutlined />,
    color: '#ff6b6b',
  },
  foreshadow: {
    label: '伏笔',
    icon: <StarOutlined />,
    color: '#6b7bff',
  },
  plot_point: {
    label: '情节点',
    icon: <ThunderboltOutlined />,
    color: '#51cf66',
  },
  character_event: {
    label: '角色事件',
    icon: <UserOutlined />,
    color: '#ffd93d',
  },
};

/**
 * 记忆侧边栏组件
 * 展示章节的所有记忆标注
 */
const MemorySidebar: React.FC<MemorySidebarProps> = ({
  annotations,
  activeAnnotationId,
  onAnnotationClick,
  scrollToAnnotation,
}) => {
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // 当需要滚动到特定标注卡片时
  useEffect(() => {
    if (scrollToAnnotation && cardRefs.current[scrollToAnnotation]) {
      const element = cardRefs.current[scrollToAnnotation];
      element?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    }
  }, [scrollToAnnotation]);
  // 按类型分组
  const groupedAnnotations = useMemo(() => {
    const groups: Record<string, MemoryAnnotation[]> = {
      hook: [],
      foreshadow: [],
      plot_point: [],
      character_event: [],
    };

    annotations.forEach((annotation) => {
      if (groups[annotation.type]) {
        groups[annotation.type].push(annotation);
      }
    });

    // 每组按重要性排序
    Object.keys(groups).forEach((type) => {
      groups[type].sort((a, b) => b.importance - a.importance);
    });

    return groups;
  }, [annotations]);

  // 统计信息
  const stats = useMemo(() => {
    return {
      total: annotations.length,
      hooks: groupedAnnotations.hook.length,
      foreshadows: groupedAnnotations.foreshadow.length,
      plotPoints: groupedAnnotations.plot_point.length,
      characterEvents: groupedAnnotations.character_event.length,
    };
  }, [annotations, groupedAnnotations]);

  // 渲染单个记忆卡片
  const renderMemoryCard = (annotation: MemoryAnnotation) => {
    const config = TYPE_CONFIG[annotation.type];
    const isActive = activeAnnotationId === annotation.id;

    return (
      <div
        key={annotation.id}
        ref={(el) => {
          cardRefs.current[annotation.id] = el;
        }}
      >
        <Card
          size="small"
          hoverable
          onClick={() => onAnnotationClick?.(annotation)}
          style={{
            marginBottom: 12,
            borderLeft: `4px solid ${config.color}`,
            backgroundColor: isActive ? `${config.color}11` : 'transparent',
            cursor: 'pointer',
            transition: 'all 0.2s',
          }}
          bodyStyle={{ padding: 12 }}
        >
        <div style={{ marginBottom: 8 }}>
          <Badge
            count={`${(annotation.importance * 10).toFixed(1)}`}
            style={{
              backgroundColor: config.color,
              float: 'right',
            }}
          />
          <div style={{ fontWeight: 600, fontSize: 14, paddingRight: 50 }}>
            {config.icon} {annotation.title}
          </div>
        </div>

        <div
          style={{
            fontSize: 13,
            color: '#666',
            lineHeight: 1.6,
            marginBottom: 8,
          }}
        >
          {annotation.content.length > 100
            ? `${annotation.content.slice(0, 100)}...`
            : annotation.content}
        </div>

        {annotation.tags && annotation.tags.length > 0 && (
          <div>
            {annotation.tags.map((tag, index) => (
              <Tag key={index} style={{ fontSize: 11, margin: '2px 4px 2px 0' }}>
                {tag}
              </Tag>
            ))}
          </div>
        )}

        {/* 特殊元数据 */}
        {annotation.metadata.strength && (
          <div style={{ marginTop: 4, fontSize: 11, color: '#999' }}>
            强度: {annotation.metadata.strength}/10
          </div>
        )}
        {annotation.metadata.foreshadowType && (
          <Tag
            color={annotation.metadata.foreshadowType === 'planted' ? 'blue' : 'green'}
            style={{ marginTop: 4 }}
          >
            {annotation.metadata.foreshadowType === 'planted' ? '已埋下' : '已回收'}
          </Tag>
        )}
        </Card>
      </div>
    );
  };

  if (annotations.length === 0) {
    return (
      <div style={{ padding: 24 }}>
        <Empty description="暂无分析数据" />
      </div>
    );
  }

  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: '16px' }}>
      {/* 统计概览 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <div style={{ fontWeight: 600, marginBottom: 12 }}>📊 分析概览</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <div>
            <div style={{ fontSize: 12, color: '#999' }}>钩子</div>
            <div style={{ fontSize: 20, fontWeight: 600, color: TYPE_CONFIG.hook.color }}>
              {stats.hooks}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, color: '#999' }}>伏笔</div>
            <div style={{ fontSize: 20, fontWeight: 600, color: TYPE_CONFIG.foreshadow.color }}>
              {stats.foreshadows}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, color: '#999' }}>情节点</div>
            <div style={{ fontSize: 20, fontWeight: 600, color: TYPE_CONFIG.plot_point.color }}>
              {stats.plotPoints}
            </div>
          </div>
          <div>
            <div style={{ fontSize: 12, color: '#999' }}>角色事件</div>
            <div
              style={{ fontSize: 20, fontWeight: 600, color: TYPE_CONFIG.character_event.color }}
            >
              {stats.characterEvents}
            </div>
          </div>
        </div>
      </Card>

      <Divider style={{ margin: '16px 0' }} />

      {/* 分类展示 */}
      <Collapse defaultActiveKey={['hook', 'foreshadow', 'plot_point']} ghost>
        {Object.entries(groupedAnnotations).map(([type, items]) => {
          if (items.length === 0) return null;

          const config = TYPE_CONFIG[type as keyof typeof TYPE_CONFIG];

          return (
            <Panel
              key={type}
              header={
                <span style={{ fontWeight: 600 }}>
                  {config.icon} {config.label} ({items.length})
                </span>
              }
            >
              {items.map((annotation) => renderMemoryCard(annotation))}
            </Panel>
          );
        })}
      </Collapse>
    </div>
  );
};

export default MemorySidebar;