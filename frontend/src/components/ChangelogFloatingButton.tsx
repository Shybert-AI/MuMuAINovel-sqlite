import { useState } from 'react';
import { FloatButton, Grid } from 'antd';
import { FileTextOutlined } from '@ant-design/icons';
import ChangelogModal from './ChangelogModal';

const { useBreakpoint } = Grid;

export default function ChangelogFloatingButton() {
  const [showChangelog, setShowChangelog] = useState(false);
  const screens = useBreakpoint();
  const isMobile = !screens.md;

  return (
    <>
      <FloatButton
        icon={<FileTextOutlined />}
        type="primary"
        tooltip="查看更新日志"
        style={{
          // 桌面端时，确保按钮在主内容区域内（侧边栏右侧）
          right: 24,
          bottom: 100,
          // 移动端无侧边栏，不需要额外处理
          ...(isMobile ? {} : {
            // 确保 zIndex 低于侧边栏但高于内容
            zIndex: 999,
          }),
        }}
        onClick={() => setShowChangelog(true)}
      />

      <ChangelogModal
        visible={showChangelog}
        onClose={() => setShowChangelog(false)}
      />
    </>
  );
}