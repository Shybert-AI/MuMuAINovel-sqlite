import React, { useState } from 'react';
import { Modal, Button, Card, Statistic, Row, Col, message } from 'antd';
import { CheckOutlined, CloseOutlined, SwapOutlined } from '@ant-design/icons';
import ReactDiffViewer from 'react-diff-viewer-continued';

interface ChapterContentComparisonProps {
  visible: boolean;
  onClose: () => void;
  chapterId: string;
  chapterTitle: string;
  originalContent: string;
  newContent: string;
  wordCount: number;
  onApply: () => void;
  onDiscard: () => void;
}

const ChapterContentComparison: React.FC<ChapterContentComparisonProps> = ({
  visible,
  onClose,
  chapterId,
  chapterTitle,
  originalContent,
  newContent,
  wordCount,
  onApply,
  onDiscard
}) => {
  const [applying, setApplying] = useState(false);
  const [viewMode, setViewMode] = useState<'split' | 'unified'>('split');
  const [modal, contextHolder] = Modal.useModal();

  const originalWordCount = originalContent.length;
  const wordCountDiff = wordCount - originalWordCount;
  const wordCountDiffPercent = ((wordCountDiff / originalWordCount) * 100).toFixed(1);

  const handleApply = async () => {
    setApplying(true);
    try {
      const response = await fetch(`/api/chapters/${chapterId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          content: newContent
        })
      });

      if (!response.ok) {
        throw new Error('应用新内容失败');
      }

      message.success('新内容已应用！');

      // 先调用 onApply 通知父组件刷新
      onApply();

      // 延迟触发章节分析，给父组件时间刷新
      setTimeout(async () => {
        try {
          const analysisResponse = await fetch(`/api/chapters/${chapterId}/analyze`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            }
          });

          if (analysisResponse.ok) {
            message.success('章节分析已开始，请稍后查看结果');
          } else {
            message.warning('章节分析触发失败，您可以手动触发分析');
          }
        } catch (analysisError) {
          console.error('触发分析失败:', analysisError);
          message.warning('章节分析触发失败，您可以手动触发分析');
        }
      }, 500);

      onClose();
    } catch (error: unknown) {
      const err = error as Error;
      message.error(err.message || '应用失败');
    } finally {
      setApplying(false);
    }
  };

  const handleDiscard = () => {
    modal.confirm({
      title: '确认放弃',
      content: '确定要放弃新生成的内容吗？此操作不可恢复。',
      centered: true,
      okText: '确定放弃',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: () => {
        onDiscard();
        onClose();
        message.info('已放弃新内容');
      }
    });
  };

  return (
    <>
      {contextHolder}
      <Modal
      title={`内容对比 - ${chapterTitle}`}
      open={visible}
      onCancel={onClose}
      width="95%"
      centered
      style={{ maxWidth: 1600 }}
      footer={[
        <Button
          key="discard"
          danger
          icon={<CloseOutlined />}
          onClick={handleDiscard}
        >
          放弃新内容
        </Button>,
        <Button
          key="toggle"
          icon={<SwapOutlined />}
          onClick={() => setViewMode(viewMode === 'split' ? 'unified' : 'split')}
        >
          切换视图
        </Button>,
        <Button
          key="apply"
          type="primary"
          icon={<CheckOutlined />}
          loading={applying}
          onClick={handleApply}
        >
          应用新内容
        </Button>
      ]}
    >
      {/* 统计信息 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Row gutter={16}>
          <Col span={6}>
            <Statistic
              title="原内容字数"
              value={originalWordCount}
              suffix="字"
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="新内容字数"
              value={wordCount}
              suffix="字"
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="字数变化"
              value={wordCountDiff}
              suffix="字"
              valueStyle={{ color: wordCountDiff > 0 ? 'var(--color-success)' : 'var(--color-error)' }}
              prefix={wordCountDiff > 0 ? '+' : ''}
            />
          </Col>
          <Col span={6}>
            <Statistic
              title="变化比例"
              value={wordCountDiffPercent}
              suffix="%"
              valueStyle={{ color: Math.abs(parseFloat(wordCountDiffPercent)) < 10 ? 'var(--color-primary)' : 'var(--color-warning)' }}
              prefix={wordCountDiff > 0 ? '+' : ''}
            />
          </Col>
        </Row>
      </Card>

      {/* 内容对比 */}
      <div style={{
        maxHeight: 'calc(90vh - 300px)',
        overflow: 'auto',
        border: '1px solid var(--color-border)',
        borderRadius: 4
      }}>
        <ReactDiffViewer
          oldValue={originalContent}
          newValue={newContent}
          splitView={viewMode === 'split'}
          leftTitle="原内容"
          rightTitle="新内容"
          showDiffOnly={false}
          useDarkTheme={false}
          styles={{
            variables: {
              light: {
                diffViewerBackground: '#fff', // Keep white for diff viewer readability
                addedBackground: 'var(--color-success-bg)',
                addedColor: 'var(--color-text-primary)',
                removedBackground: 'var(--color-error-bg)',
                removedColor: 'var(--color-text-primary)',
                wordAddedBackground: 'var(--color-success-border)',
                wordRemovedBackground: 'var(--color-error-border)',
                addedGutterBackground: 'var(--color-success-bg)',
                removedGutterBackground: 'var(--color-error-bg)',
                gutterBackground: 'var(--color-bg-layout)',
                gutterBackgroundDark: 'var(--color-bg-container)',
                highlightBackground: 'var(--color-warning-bg)',
                highlightGutterBackground: 'var(--color-warning-border)',
              },
            },
            line: {
              padding: '10px 2px',
              fontSize: '14px',
              lineHeight: '20px',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word'
            }
          }}
        />
      </div>
      </Modal>
    </>
  );
};

export default ChapterContentComparison;