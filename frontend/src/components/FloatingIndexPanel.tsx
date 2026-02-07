import { useState, useMemo } from 'react';
import { Drawer, Input, List, Typography, Empty, Tag } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import type { Chapter } from '../types';

const { Link } = Typography;

interface GroupedChapters {
  outlineId: string | null;
  outlineTitle: string;
  chapters: Chapter[];
}

interface FloatingIndexPanelProps {
  visible: boolean;
  onClose: () => void;
  groupedChapters: GroupedChapters[];
  onChapterSelect: (chapterId: string) => void;
}

export default function FloatingIndexPanel({
  visible,
  onClose,
  groupedChapters,
  onChapterSelect,
}: FloatingIndexPanelProps) {
  const [searchTerm, setSearchTerm] = useState('');

  const filteredGroups = useMemo(() => {
    if (!searchTerm) {
      return groupedChapters;
    }
    return groupedChapters
      .map(group => {
        const filteredChapters = group.chapters.filter(chapter =>
          chapter.title.toLowerCase().includes(searchTerm.toLowerCase())
        );
        return { ...group, chapters: filteredChapters };
      })
      .filter(group => group.chapters.length > 0);
  }, [searchTerm, groupedChapters]);

  const handleChapterClick = (chapterId: string) => {
    onChapterSelect(chapterId);
    onClose();
  };

  return (
    <Drawer
      title="章节目录"
      placement="right"
      onClose={onClose}
      open={visible}
      width={320}
      styles={{
        body: { padding: 0 },
      }}
    >
      <div style={{ padding: '16px', borderBottom: '1px solid #f0f0f0' }}>
        <Input
          placeholder="搜索章节标题"
          prefix={<SearchOutlined />}
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          allowClear
        />
      </div>

      {filteredGroups.length > 0 ? (
        <List
          dataSource={filteredGroups}
          renderItem={group => (
            <List.Item style={{ padding: '0 16px', flexDirection: 'column', alignItems: 'flex-start' }}>
              <div style={{ padding: '12px 0', fontWeight: 'bold' }}>
                <Tag color={group.outlineId ? 'blue' : 'default'}>
                  {group.outlineTitle}
                </Tag>
              </div>
              <List
                size="small"
                dataSource={group.chapters}
                renderItem={chapter => (
                  <List.Item style={{ paddingLeft: 16, borderBlockStart: 'none' }}>
                    <Link onClick={() => handleChapterClick(chapter.id)}>
                      {`第${chapter.chapter_number}章: ${chapter.title}`}
                    </Link>
                  </List.Item>
                )}
                split={false}
              />
            </List.Item>
          )}
          style={{ height: 'calc(100vh - 120px)', overflowY: 'auto' }}
        />
      ) : (
        <Empty description="没有找到匹配的章节" style={{ marginTop: 48 }} />
      )}
    </Drawer>
  );
}