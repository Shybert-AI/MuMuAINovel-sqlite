import { useEffect, useState } from 'react';
import { Button, Card, Space, Typography, message, Spin, Form, Input, Tabs } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { authApi } from '../services/api';
import { useNavigate, useSearchParams } from 'react-router-dom';
import AnnouncementModal from '../components/AnnouncementModal';

const { Title, Paragraph } = Typography;

export default function Login() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(true);
  const [localAuthEnabled, setLocalAuthEnabled] = useState(false);
  const [linuxdoEnabled, setLinuxdoEnabled] = useState(false);
  const [form] = Form.useForm();
  const [showAnnouncement, setShowAnnouncement] = useState(false);

  // 检查是否已登录和获取认证配置
  useEffect(() => {
    const checkAuth = async () => {
      try {
        await authApi.getCurrentUser();
        // 已登录，重定向到首页
        const redirect = searchParams.get('redirect') || '/';
        navigate(redirect);
      } catch {
        // 未登录，获取认证配置
        try {
          const config = await authApi.getAuthConfig();
          setLocalAuthEnabled(config.local_auth_enabled);
          setLinuxdoEnabled(config.linuxdo_enabled);
        } catch (error) {
          console.error('获取认证配置失败:', error);
          // 默认显示LinuxDO登录
          setLinuxdoEnabled(true);
        }
        setChecking(false);
      }
    };
    checkAuth();
  }, [navigate, searchParams]);

  const handleLocalLogin = async (values: { username: string; password: string }) => {
    try {
      setLoading(true);
      const response = await authApi.localLogin(values.username, values.password);

      if (response.success) {
        message.success('登录成功！');

        // 检查是否永久隐藏公告
        const hideForever = localStorage.getItem('announcement_hide_forever');
        const hideToday = localStorage.getItem('announcement_hide_today');
        const today = new Date().toDateString();

        // 如果永久隐藏或今日已隐藏，则不显示公告
        if (hideForever === 'true' || hideToday === today) {
          const redirect = searchParams.get('redirect') || '/';
          navigate(redirect);
        } else {
          setShowAnnouncement(true);
        }
      }
    } catch (error) {
      console.error('本地登录失败:', error);
      setLoading(false);
    }
  };

  const handleLinuxDOLogin = async () => {
    try {
      setLoading(true);
      const response = await authApi.getLinuxDOAuthUrl();

      // 保存重定向地址到 sessionStorage
      const redirect = searchParams.get('redirect');
      if (redirect) {
        sessionStorage.setItem('login_redirect', redirect);
      }

      // 跳转到 LinuxDO 授权页面
      window.location.href = response.auth_url;
    } catch (error) {
      console.error('获取授权地址失败:', error);
      message.error('获取授权地址失败，请稍后重试');
      setLoading(false);
    }
  };

  if (checking) {
    return (
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '100vh',
        background: 'var(--color-bg-base)',
      }}>
        <Spin size="large" style={{ color: 'var(--color-primary)' }} />
      </div>
    );
  }

  // 渲染本地登录表单
  const renderLocalLogin = () => (
    <Form
      form={form}
      onFinish={handleLocalLogin}
      size="large"
      style={{ marginTop: '24px' }}
    >
      <Form.Item
        name="username"
        rules={[{ required: true, message: '请输入用户名' }]}
      >
        <Input
          prefix={<UserOutlined style={{ color: '#999' }} />}
          placeholder="用户名"
          autoComplete="username"
        />
      </Form.Item>
      <Form.Item
        name="password"
        rules={[{ required: true, message: '请输入密码' }]}
      >
        <Input.Password
          prefix={<LockOutlined style={{ color: '#999' }} />}
          placeholder="密码"
          autoComplete="current-password"
        />
      </Form.Item>
      <Form.Item style={{ marginBottom: 0 }}>
        <Button
          type="primary"
          htmlType="submit"
          loading={loading}
          block
          style={{
            height: 48,
            fontSize: 16,
            fontWeight: 600,
            background: 'var(--color-primary)',
            border: 'none',
            borderRadius: '12px',
            boxShadow: 'var(--shadow-primary)',
          }}
        >
          登录
        </Button>
      </Form.Item>
    </Form>
  );

  // 渲染LinuxDO登录
  const renderLinuxDOLogin = () => (
    <div style={{ padding: '24px 0 8px' }}>
      <Button
        type="primary"
        size="large"
        icon={
          <img
            src="/favicon.ico"
            alt="LinuxDO"
            style={{
              width: 20,
              height: 20,
              marginRight: 8,
              verticalAlign: 'middle',
            }}
          />
        }
        loading={loading}
        onClick={handleLinuxDOLogin}
        block
        style={{
          height: 52,
          fontSize: 16,
          fontWeight: 600,
          background: 'var(--color-primary)',
          border: 'none',
          borderRadius: '12px',
          boxShadow: 'var(--shadow-primary)',
          transition: 'all 0.3s ease',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.transform = 'translateY(-2px)';
          e.currentTarget.style.boxShadow = 'var(--shadow-elevated)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.transform = 'translateY(0)';
          e.currentTarget.style.boxShadow = 'var(--shadow-primary)';
        }}
      >
        使用 LinuxDO 登录
      </Button>
    </div>
  );

  const handleAnnouncementClose = () => {
    setShowAnnouncement(false);
    const redirect = searchParams.get('redirect') || '/';
    navigate(redirect);
  };

  const handleDoNotShowToday = () => {
    // 设置今日不再显示
    const today = new Date().toDateString();
    localStorage.setItem('announcement_hide_today', today);
  };

  const handleNeverShow = () => {
    // 设置永久不再显示
    localStorage.setItem('announcement_hide_forever', 'true');
  };

  return (
    <>
      <AnnouncementModal
        visible={showAnnouncement}
        onClose={handleAnnouncementClose}
        onDoNotShowToday={handleDoNotShowToday}
        onNeverShow={handleNeverShow}
      />
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '100vh',
        background: 'var(--color-bg-base)',
        padding: '20px',
        position: 'relative',
        overflow: 'hidden',
      }}>
        {/* 装饰性背景元素 */}
        <div style={{
          position: 'absolute',
          top: '-10%',
          right: '-5%',
          width: '400px',
          height: '400px',
          background: 'var(--color-primary)',
          opacity: 0.1,
          borderRadius: '50%',
          filter: 'blur(60px)',
        }} />
        <div style={{
          position: 'absolute',
          bottom: '-10%',
          left: '-5%',
          width: '350px',
          height: '350px',
          background: 'var(--color-success)',
          opacity: 0.08,
          borderRadius: '50%',
          filter: 'blur(60px)',
        }} />

        <Card
          style={{
            width: '100%',
            maxWidth: 420,
            background: 'var(--color-bg-container)',
            backdropFilter: 'blur(20px)',
            WebkitBackdropFilter: 'blur(20px)',
            boxShadow: 'var(--shadow-card)',
            border: '1px solid var(--color-border)',
            borderRadius: '16px',
            position: 'relative',
            zIndex: 1,
          }}
          bodyStyle={{
            padding: '40px 32px',
          }}
        >
          <Space direction="vertical" size="large" style={{ width: '100%', textAlign: 'center' }}>
            {/* Logo区域 */}
            <div style={{ marginBottom: '8px' }}>
              <div style={{
                width: '72px',
                height: '72px',
                margin: '0 auto 20px',
                background: 'var(--color-primary)',
                borderRadius: '20px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: 'var(--shadow-primary)',
              }}>
                <img
                  src="/logo.svg"
                  alt="Logo"
                  style={{
                    width: '48px',
                    height: '48px',
                    filter: 'brightness(0) invert(1)',
                  }}
                />
              </div>
              <Title level={2} style={{
                marginBottom: 8,
                color: 'var(--color-primary)',
                fontWeight: 700,
              }}>
                AI小说创作助手
              </Title>
              <Paragraph style={{
                color: 'var(--color-text-secondary)',
                fontSize: '14px',
                marginBottom: 0,
              }}>
                {localAuthEnabled && linuxdoEnabled ? '选择登录方式' :
                  localAuthEnabled ? '使用账户密码登录' :
                    '使用 LinuxDO 账号登录'}
              </Paragraph>
            </div>

            {/* 登录方式 */}
            {localAuthEnabled && linuxdoEnabled ? (
              <Tabs
                defaultActiveKey="local"
                centered
                items={[
                  {
                    key: 'local',
                    label: '账户密码',
                    children: renderLocalLogin(),
                  },
                  {
                    key: 'linuxdo',
                    label: 'LinuxDO',
                    children: renderLinuxDOLogin(),
                  },
                ]}
              />
            ) : localAuthEnabled ? (
              renderLocalLogin()
            ) : (
              renderLinuxDOLogin()
            )}

            {/* 提示信息 */}
            <div style={{
              padding: '16px',
              background: 'rgba(77, 128, 136, 0.08)',
              borderRadius: '12px',
              border: '1px solid var(--color-border)',
            }}>
              <Paragraph style={{
                fontSize: 13,
                color: 'var(--color-text-secondary)',
                marginBottom: 0,
                lineHeight: 1.6,
              }}>
                🎉 首次登录将自动创建账号
                <br />
                🔒 每个用户拥有独立的数据空间
              </Paragraph>
            </div>
          </Space>
        </Card>
      </div>
    </>
  );
}