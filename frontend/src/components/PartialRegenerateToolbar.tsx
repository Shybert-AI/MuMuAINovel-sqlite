import React from 'react';
import { Button, Tooltip } from 'antd';
import { EditOutlined } from '@ant-design/icons';

interface PartialRegenerateToolbarProps {
  visible: boolean;
  position: { top: number; left: number };
  onRegenerate: () => void;
  selectedText: string;
}

/**
 * 局部重写浮动工具栏
 * 当用户在章节内容编辑器中选中文本时显示
 */
export const PartialRegenerateToolbar: React.FC<PartialRegenerateToolbarProps> = ({
  visible,
  position,
  onRegenerate,
  selectedText
}) => {
  if (!visible || !selectedText) return null;

  // 限制显示的选中文本长度
  const displayText = selectedText.length > 20 
    ? selectedText.substring(0, 20) + '...' 
    : selectedText;

  return (
    <div
      style={{
        position: 'fixed',
        top: position.top,
        left: position.left,
        zIndex: 10000,
        background: '#fff',
        borderRadius: 8,
        boxShadow: '0 4px 16px rgba(0, 0, 0, 0.15)',
        padding: '6px 8px',
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        animation: 'fadeIn 0.2s ease-out',
        border: '1px solid #e8e8e8',
      }}
    >
      <Tooltip
        title={`AI重写选中内容: "${displayText}"`}
        placement="top"
      >
        <Button
          type="primary"
          size="small"
          icon={<EditOutlined />}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onRegenerate();
          }}
          style={{
            background: 'linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-hover) 100%)',
            border: 'none',
            fontWeight: 500,
            boxShadow: '0 4px 12px rgba(77, 128, 136, 0.3)',
          }}
        >
          AI重写
        </Button>
      </Tooltip>
      <span style={{ 
        fontSize: 12, 
        color: '#8c8c8c',
        maxWidth: 150,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}>
        已选 {selectedText.length} 字
      </span>
    </div>
  );
};

// 添加动画样式
const style = document.createElement('style');
style.textContent = `
  @keyframes fadeIn {
    from {
      opacity: 0;
      transform: translateY(-4px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
`;
if (!document.head.querySelector('style[data-partial-regenerate-toolbar]')) {
  style.setAttribute('data-partial-regenerate-toolbar', 'true');
  document.head.appendChild(style);
}

export default PartialRegenerateToolbar;