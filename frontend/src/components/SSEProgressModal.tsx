import React from 'react';
import { Modal, Spin, Button } from 'antd';
import { LoadingOutlined, StopOutlined } from '@ant-design/icons';

interface SSEProgressModalProps {
  visible: boolean;
  progress: number;
  message: string;
  title?: string;
  showPercentage?: boolean;
  showIcon?: boolean;
  onCancel?: () => void;
  cancelButtonText?: string;
}

/**
 * 统一的SSE进度显示Modal组件
 * 用于在Modal中显示AI生成进度，样式与SSELoadingOverlay保持一致
 */
export const SSEProgressModal: React.FC<SSEProgressModalProps> = ({
  visible,
  progress,
  message,
  title = 'AI生成中...',
  showPercentage = true,
  showIcon = true,
  onCancel,
  cancelButtonText = '取消任务',
}) => {
  if (!visible) return null;

  return (
    <Modal
      title={null}
      open={visible}
      footer={null}
      closable={false}
      centered
      width={500}
      maskClosable={false}
      keyboard={false}
      styles={{
        body: {
          padding: '40px 40px 32px',
        }
      }}
    >
      <div>
        {/* 标题和图标 */}
        {showIcon && (
          <div style={{
            textAlign: 'center',
            marginBottom: 24
          }}>
            <Spin
              indicator={<LoadingOutlined style={{ fontSize: 48, color: 'var(--color-primary)' }} spin />}
            />
            <div style={{
              fontSize: 20,
              fontWeight: 'bold',
              marginTop: 16,
              color: 'var(--color-text-primary)'
            }}>
              {title}
            </div>
          </div>
        )}

        {/* 进度条 */}
        <div style={{
          marginBottom: showPercentage ? 16 : 24
        }}>
          <div style={{
            height: 12,
            background: 'var(--color-bg-layout)',
            borderRadius: 6,
            overflow: 'hidden',
            marginBottom: showPercentage ? 12 : 0
          }}>
            <div style={{
              height: '100%',
              background: progress === 100
                ? 'linear-gradient(90deg, var(--color-success) 0%, var(--color-success-active) 100%)'
                : 'linear-gradient(90deg, var(--color-primary) 0%, var(--color-primary-active) 100%)',
              width: `${progress}%`,
              transition: 'all 0.3s ease',
              borderRadius: 6,
              boxShadow: progress > 0 ? 'var(--shadow-card)' : 'none'
            }} />
          </div>

          {/* 进度百分比 */}
          {showPercentage && (
            <div style={{
              textAlign: 'center',
              fontSize: 32,
              fontWeight: 'bold',
              color: progress === 100 ? 'var(--color-success)' : 'var(--color-primary)',
              marginBottom: 8
            }}>
              {progress}%
            </div>
          )}
        </div>

        {/* 状态消息 */}
        <div style={{
          textAlign: 'center',
          fontSize: 16,
          color: 'var(--color-text-secondary)',
          minHeight: 24,
          padding: '0 20px',
          marginBottom: 16
        }}>
          {message || '准备生成...'}
        </div>

        {/* 提示文字 */}
        <div style={{
          textAlign: 'center',
          fontSize: 13,
          color: 'var(--color-text-tertiary)',
          marginBottom: onCancel ? 16 : 0
        }}>
          请勿关闭页面，生成过程需要一定时间
        </div>

        {/* 取消按钮 */}
        {onCancel && (
          <div style={{
            textAlign: 'center',
            marginTop: 16
          }}>
            <Button
              danger
              size="large"
              icon={<StopOutlined />}
              onClick={onCancel}
            >
              {cancelButtonText}
            </Button>
          </div>
        )}
      </div>
    </Modal>
  );
};

export default SSEProgressModal;