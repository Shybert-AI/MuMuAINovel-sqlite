import type { CSSProperties } from 'react';

// 统一的卡片样式配置
export const cardStyles = {
  // 基础卡片样式
  base: {
    borderRadius: 12,
    transition: 'all 0.3s ease',
  } as CSSProperties,

  // 悬浮效果
  hoverable: {
    cursor: 'pointer',
    position: 'relative' as const,
  } as CSSProperties,

  // 角色卡片样式
  character: {
    // height: 320,
    display: 'flex',
    flexDirection: 'column',
    borderColor: 'var(--color-info)',
    borderRadius: 12,
  } as CSSProperties,

  // 组织卡片样式
  organization: {
    // height: 320,
    display: 'flex',
    flexDirection: 'column',
    borderColor: 'var(--color-success)',
    backgroundColor: 'var(--color-bg-base)', // 使用柔和的背景色
    borderRadius: 12,
  } as CSSProperties,

  // 项目卡片样式 - 书籍风格 (Book Style)
  project: {
    height: '100%',
    borderRadius: '6px 16px 16px 6px', // 左侧稍直(书脊)，右侧圆润
    overflow: 'hidden',
    background: '#fff',
    // 基础阴影 + 书籍厚度阴影
    boxShadow: `
      0 2px 8px rgba(0, 0, 0, 0.04),
      4px 0 8px rgba(0, 0, 0, 0.02)
    `,
    transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
    border: '1px solid rgba(0,0,0,0.02)',
    borderLeft: '6px solid var(--color-primary)', // 书脊效果
    display: 'flex',
    flexDirection: 'column',
    position: 'relative',
  } as CSSProperties,

  // 新建项目卡片样式 - 统一书籍风格
  newProjectBook: {
    height: '100%',
    borderRadius: '6px 16px 16px 6px',
    overflow: 'hidden',
    background: '#fff',
    // 基础阴影 + 书籍厚度阴影 (与普通项目一致)
    boxShadow: `
      0 2px 8px rgba(0, 0, 0, 0.04),
      4px 0 8px rgba(0, 0, 0, 0.02)
    `,
    border: '1px solid rgba(0,0,0,0.02)',
    borderLeft: '6px solid var(--color-primary)', // 与普通项目一致的书脊颜色
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'center',
    alignItems: 'center',
    transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
    position: 'relative',
  } as CSSProperties,

  // 书架风格容器
  bookshelf: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
    gap: '24px',
    padding: '24px 0',
  } as CSSProperties,

  // 卡片内容区域样式
  body: {
    padding: 20,
    display: 'flex',
    flexDirection: 'column' as const,
  } as CSSProperties,

  // 卡片描述区域样式（固定高度，内容截断）
  description: {
    marginTop: 12,
    maxHeight: 200,
    overflow: 'hidden' as const,
  } as CSSProperties,

  // 文本截断样式
  ellipsis: {
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap' as const,
  } as CSSProperties,

  // 多行文本截断
  ellipsisMultiline: (lines: number = 2) => ({
    display: '-webkit-box',
    WebkitLineClamp: lines,
    WebkitBoxOrient: 'vertical' as const,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  } as CSSProperties),
};

// 卡片悬浮动画 - 增强版 (Subtle Lift)
export const cardHoverHandlers = {
  onMouseEnter: (e: React.MouseEvent<HTMLDivElement>) => {
    const target = e.currentTarget;
    target.style.transform = 'translateY(-6px) rotateY(-2deg)'; // 悬浮时轻微翻起
    
    // 统一书本悬浮态
    target.style.boxShadow = `
      -2px 0 4px rgba(0, 0, 0, 0.1), // 书脊阴影加深
      8px 12px 24px rgba(0, 0, 0, 0.12)
    `;

  },
  onMouseLeave: (e: React.MouseEvent<HTMLDivElement>) => {
    const target = e.currentTarget;
    target.style.transform = 'translateY(0) rotateY(0)';
    
    // 统一恢复基础阴影
    target.style.boxShadow = `
      0 2px 8px rgba(0, 0, 0, 0.04),
      4px 0 8px rgba(0, 0, 0, 0.02)
    `;
  },
};

// 响应式网格配置
export const gridConfig = {
  gutter: [16, 16] as [number, number],
  xs: 24,
  sm: 12,
  lg: 8,
  xl: 6,
};

// 角色卡片网格配置
export const characterGridConfig = {
  gutter: 0,  // 移除 gutter，避免负边距
  xs: 24,  // 手机：1列
  sm: 12,  // 平板：2列
  md: 12,   // 中等屏幕：3列
  lg: 6,   // 大屏：4列
  xl: 6,   // 超大屏：4列
  xxl: 5,  // 超超大屏：6列
};

// 文本样式
export const textStyles = {
  label: {
    fontSize: 12,
    color: 'rgba(0, 0, 0, 0.45)',
  } as CSSProperties,

  value: {
    fontSize: 14,
    color: 'rgba(0, 0, 0, 0.85)',
  } as CSSProperties,

  description: {
    fontSize: 12,
    color: 'rgba(0, 0, 0, 0.45)',
    lineHeight: 1.6,
  } as CSSProperties,
};