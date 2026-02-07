import React from 'react';
import { Spin } from 'antd';
import { LoadingOutlined } from '@ant-design/icons';

interface SSELoadingOverlayProps {
  loading: boolean;
  progress: number;
  message: string;
}

export const SSELoadingOverlay: React.FC<SSELoadingOverlayProps> = ({
  loading,
  progress,
  message
}) => {
  if (!loading) return null;

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: 'rgba(0, 0, 0, 0.45)',
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      zIndex: 9999
    }}>
      <div style={{
        background: '#fff',
        borderRadius: 12,
        padding: '40px 60px',
        minWidth: 400,
        maxWidth: 600,
        boxShadow: '0 8px 32px rgba(0,0,0,0.2)'
      }}>
        {/* 标题和图标 */}
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
            AI生成中...
          </div>
        </div>

        {/* 进度条 */}
        <div style={{
          marginBottom: 16
        }}>
          <div style={{
            height: 12,
            background: 'var(--color-bg-layout)',
            borderRadius: 6,
            overflow: 'hidden',
            marginBottom: 12
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
          <div style={{
            textAlign: 'center',
            fontSize: 32,
            fontWeight: 'bold',
            color: progress === 100 ? 'var(--color-success)' : 'var(--color-primary)',
            marginBottom: 8
          }}>
            {progress}%
          </div>
        </div>

        {/* 状态消息 */}
        <div style={{
          textAlign: 'center',
          fontSize: 16,
          color: '#595959',
          minHeight: 24,
          padding: '0 20px'
        }}>
          {message || '准备生成...'}
        </div>

        {/* 提示文字 */}
        <div style={{
          textAlign: 'center',
          fontSize: 13,
          color: '#8c8c8c',
          marginTop: 16
        }}>
          请勿关闭页面,生成过程需要一定时间
        </div>
      </div>
    </div>
  );
};