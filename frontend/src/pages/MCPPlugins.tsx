import { useState, useEffect } from 'react';
import {
  Card,
  Button,
  Space,
  Typography,
  Modal,
  Form,
  Input,
  Switch,
  Select,
  message,
  Tag,
  Spin,
  Empty,
  Alert,
  Row,
  Col,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ThunderboltOutlined,
  InfoCircleOutlined,
  ToolOutlined,
  ApiOutlined,
  QuestionCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { mcpPluginApi, settingsApi } from '../services/api';
import type { MCPPlugin, MCPTool } from '../types';

const { Paragraph, Text, Title } = Typography;
const { TextArea } = Input;

export default function MCPPluginsPage() {
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);
  const [form] = Form.useForm();
  
  // 响应式监听窗口大小变化
  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth <= 768);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);
  const [modal, contextHolder] = Modal.useModal();
  const [loading, setLoading] = useState(false);
  const [plugins, setPlugins] = useState<MCPPlugin[]>([]);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingPlugin, setEditingPlugin] = useState<MCPPlugin | null>(null);
  const [testingPluginId, setTestingPluginId] = useState<string | null>(null);
  const [viewingTools, setViewingTools] = useState<{ pluginId: string; tools: MCPTool[] } | null>(null);
  const [checkingFunctionCalling, setCheckingFunctionCalling] = useState(false);
  const [modelSupportStatus, setModelSupportStatus] = useState<'unknown' | 'supported' | 'unsupported'>('unknown');

  useEffect(() => {
    const initPage = async () => {
      setLoading(true);
      try {
        // 1. 并行获取插件列表和当前设置
        const [pluginsData, settings] = await Promise.all([
          mcpPluginApi.getPlugins(),
          settingsApi.getSettings()
        ]);
        
        setPlugins(pluginsData);

        // 2. 检查配置一致性
        const verifiedConfigStr = localStorage.getItem('mcp_verified_config');
        if (verifiedConfigStr) {
          try {
            const verifiedConfig = JSON.parse(verifiedConfigStr);
            const currentConfig = {
              provider: settings.api_provider,
              baseUrl: settings.api_base_url,
              model: settings.llm_model
            };

            // 比较关键配置是否发生变更
            const isConfigChanged =
              verifiedConfig.provider !== currentConfig.provider ||
              verifiedConfig.baseUrl !== currentConfig.baseUrl ||
              verifiedConfig.model !== currentConfig.model;

            if (isConfigChanged) {
              // 配置已变更
              setModelSupportStatus('unknown');
              
              // 检查是否有正在运行的插件
              const activePlugins = pluginsData.filter(p => p.enabled);
              if (activePlugins.length > 0) {
                // 自动禁用所有插件
                message.loading({ content: '检测到模型配置变更，正在为了安全自动禁用插件...', key: 'auto_disable' });
                
                await Promise.all(activePlugins.map(p => mcpPluginApi.togglePlugin(p.id, false)));
                
                // 重新加载插件列表状态
                const updatedPlugins = await mcpPluginApi.getPlugins();
                setPlugins(updatedPlugins);
                
                message.success({ content: '已自动禁用所有插件，请重新检测模型能力', key: 'auto_disable' });
                
                modal.warning({
                  title: '配置变更提醒',
                  centered: true,
                  content: '检测到您更换了 AI 模型或接口地址。为了防止错误调用，系统已自动暂停所有 MCP 插件。请重新进行"模型能力检查"，确认新模型支持 Function Calling 后再启用插件。',
                  okText: '知道了',
                });
              } else {
                // 没有运行中的插件，仅提示
                message.info('检测到模型配置已变更，请重新检测模型能力');
              }
              
              // 清除旧的验证状态
              localStorage.removeItem('mcp_verified_config');
            } else {
              // 配置未变更，恢复验证状态（根据缓存的状态恢复）
              const cachedStatus = verifiedConfig.status || 'supported';
              setModelSupportStatus(cachedStatus as 'unknown' | 'supported' | 'unsupported');
            }
          } catch (e) {
            console.error('Failed to parse verified config:', e);
            localStorage.removeItem('mcp_verified_config');
          }
        }
      } catch (error) {
        console.error('Init page failed:', error);
        message.error('页面初始化失败');
      } finally {
        setLoading(false);
      }
    };
    initPage();
  }, [modal]);

  const loadPlugins = async () => {
    try {
      const data = await mcpPluginApi.getPlugins();
      setPlugins(data);
    } catch (error) {
      console.error('Load plugins failed:', error);
      message.error('加载插件列表失败');
    }
  };

  const handleCreate = () => {
    if (modelSupportStatus !== 'supported') {
      modal.confirm({
        title: '模型能力检查',
        centered: true,
        icon: <WarningOutlined />,
        content: '为了确保 MCP 插件正常工作，您当前使用的 AI 模型必须支持 Function Calling（工具调用）能力。请先进行模型支持检测。',
        okText: '去检测',
        cancelText: '取消',
        onOk: handleCheckFunctionCalling,
      });
      return;
    }
    setEditingPlugin(null);
    form.resetFields();
    form.setFieldsValue({
      enabled: true,
      category: 'search',
      config_json: `{
  "mcpServers": {
    "exa": {
      "type": "http",
      "url": "https://mcp.exa.ai/mcp?exaApiKey=YOUR_API_KEY",
      "headers": {}
    }
  }
}`
    });
    setModalVisible(true);
  };

  const handleEdit = (plugin: MCPPlugin) => {
    setEditingPlugin(plugin);

    // 重构为标准MCP配置格式
    const mcpConfig: Record<string, Record<string, Record<string, unknown>>> = {
      mcpServers: {
        [plugin.plugin_name]: {
          type: plugin.plugin_type || 'http'
        }
      }
    };

    if (plugin.plugin_type === 'http' || plugin.plugin_type === 'streamable_http' || plugin.plugin_type === 'sse') {
      mcpConfig.mcpServers[plugin.plugin_name].url = plugin.server_url;
      mcpConfig.mcpServers[plugin.plugin_name].headers = plugin.headers || {};
    } else {
      mcpConfig.mcpServers[plugin.plugin_name].command = plugin.command;
      mcpConfig.mcpServers[plugin.plugin_name].args = plugin.args || [];
      mcpConfig.mcpServers[plugin.plugin_name].env = plugin.env || {};
    }

    form.setFieldsValue({
      config_json: JSON.stringify(mcpConfig, null, 2),
      enabled: plugin.enabled,
      category: plugin.category || 'general',
    });
    setModalVisible(true);
  };

  const handleDelete = (plugin: MCPPlugin) => {
    modal.confirm({
      title: '删除插件',
      content: `确定要删除插件 "${plugin.display_name || plugin.plugin_name}" 吗？`,
      centered: true,
      okText: '确定',
      cancelText: '取消',
      okType: 'danger',
      onOk: async () => {
        try {
          await mcpPluginApi.deletePlugin(plugin.id);
          message.success('插件已删除');
          loadPlugins();
        } catch (error) {
          console.error('Delete plugin failed:', error);
          message.error('删除插件失败');
        }
      },
    });
  };

  const handleToggle = async (plugin: MCPPlugin, enabled: boolean) => {
    try {
      await mcpPluginApi.togglePlugin(plugin.id, enabled);
      message.success(enabled ? '插件已启用' : '插件已禁用');
      loadPlugins();
    } catch (error) {
      console.error('Toggle plugin failed:', error);
      message.error('切换插件状态失败');
    }
  };

  const handleTest = async (pluginId: string) => {
    setTestingPluginId(pluginId);
    try {
      const result = await mcpPluginApi.testPlugin(pluginId);

      // 测试完成后，无论成功失败都刷新插件列表以更新状态
      await loadPlugins();

      if (result.success) {
        const suggestions = result.suggestions || [];
        const aiChoice = suggestions.find((s: string) => s.startsWith('🤖'))?.replace('🤖 AI选择: ', '') || '';
        const paramsStr = suggestions.find((s: string) => s.startsWith('📝'))?.replace('📝 参数: ', '') || '';
        const callTime = suggestions.find((s: string) => s.startsWith('⏱️'))?.replace('⏱️ 耗时: ', '') || '';
        const resultStr = suggestions.find((s: string) => s.startsWith('📊'))?.replace('📊 结果:\n', '') || '';

        modal.success({
          title: '🎉 测试成功',
          centered: true,
          width: isMobile ? '95%' : 700,
          content: (
            <div style={{ padding: '8px 0' }}>
              <div style={{ marginBottom: 16, padding: 12, background: 'var(--color-success-bg)', border: '1px solid var(--color-success-border)', borderRadius: 8 }}>
                <Typography.Text strong style={{ color: 'var(--color-success)', fontSize: 14 }}>
                  ✓ {result.message}
                </Typography.Text>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 12, marginBottom: 16 }}>
                <div style={{ padding: 12, background: 'var(--color-bg-layout)', borderRadius: 8 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>可用工具数</Text>
                  <div><Text strong style={{ fontSize: 20 }}>{result.tools_count || 0}</Text></div>
                </div>
                <div style={{ padding: 12, background: 'var(--color-bg-layout)', borderRadius: 8 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>总响应时间</Text>
                  <div><Text strong style={{ fontSize: 20 }}>{result.response_time_ms?.toFixed(0) || 0}ms</Text></div>
                </div>
              </div>

              {aiChoice && (
                <div style={{ marginBottom: 12, padding: 12, background: 'var(--color-info-bg)', borderRadius: 8, border: '1px solid var(--color-info-border)' }}>
                  <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>🤖 AI选择的工具</Text>
                  <Text code strong>{aiChoice}</Text>
                  {callTime && <Tag color="blue" style={{ marginLeft: 8 }}>{callTime}</Tag>}
                </div>
              )}

              {paramsStr && (
                <div style={{ marginBottom: 12 }}>
                  <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>📝 调用参数</Text>
                  <pre style={{ margin: 0, padding: 8, background: 'var(--color-bg-layout)', borderRadius: 4, fontSize: 12, overflow: 'auto', maxHeight: 100 }}>
                    {(() => { try { return JSON.stringify(JSON.parse(paramsStr), null, 2); } catch { return paramsStr; } })()}
                  </pre>
                </div>
              )}

              {resultStr && (
                <div style={{ marginBottom: 12 }}>
                  <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>📊 返回结果预览</Text>
                  <pre style={{ margin: 0, padding: 8, background: 'var(--color-bg-layout)', borderRadius: 4, fontSize: 11, overflow: 'auto', maxHeight: 150, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {resultStr}
                  </pre>
                </div>
              )}

              <Alert message='插件状态已自动更新为"运行中"' type="success" showIcon />
            </div>
          ),
        });
      } else {
        modal.error({
          title: '测试失败',
          centered: true,
          width: isMobile ? '90%' : 600,
          content: (
            <div style={{ padding: '8px 0' }}>
              <div style={{ marginBottom: 16 }}>
                <Alert
                  message={result.message || 'MCP插件测试失败'}
                  type="error"
                  showIcon
                />
              </div>

              {result.error && (
                <div style={{
                  padding: 16,
                  background: 'var(--color-error-bg)',
                  border: '1px solid var(--color-error-border)',
                  borderRadius: 8,
                  marginBottom: 16
                }}>
                  <Text strong style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>错误信息:</Text>
                  <Text style={{ fontSize: 13, color: 'var(--color-error)', fontFamily: 'monospace', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                    {result.error}
                  </Text>
                </div>
              )}

              {result.suggestions && result.suggestions.length > 0 && (
                <div style={{
                  padding: 16,
                  background: 'var(--color-warning-bg)',
                  border: '1px solid var(--color-warning-border)',
                  borderRadius: 8,
                  marginBottom: 16
                }}>
                  <Text strong style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>💡 建议:</Text>
                  <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13 }}>
                    {result.suggestions.map((s: string, i: number) => (
                      <li key={i} style={{ marginBottom: 4 }}>{s}</li>
                    ))}
                  </ul>
                </div>
              )}

              <Alert
                message="插件状态已更新，请检查配置后重试"
                type="warning"
                showIcon
              />
            </div>
          ),
        });
      }
    } catch {
      message.error('测试插件失败');
    } finally {
      setTestingPluginId(null);
    }
  };

  const handleViewTools = async (pluginId: string) => {
    try {
      const result = await mcpPluginApi.getPluginTools(pluginId);
      setViewingTools({ pluginId, tools: result.tools });
    } catch (error) {
      console.error('Get tools failed:', error);
      message.error('获取工具列表失败');
    }
  };

  const handleCheckFunctionCalling = async () => {
    // 从设置中获取当前配置
    setCheckingFunctionCalling(true);
    try {
      const settings = await settingsApi.getSettings();
      
      if (!settings.api_key || !settings.llm_model) {
        message.warning('请先在设置页面配置 API Key 和模型');
        return;
      }

      const result = await settingsApi.checkFunctionCalling({
        api_key: settings.api_key,
        api_base_url: settings.api_base_url || '',
        provider: settings.api_provider || 'openai',
        llm_model: settings.llm_model,
      });

      // 无论成功失败，都缓存当前测试的配置和状态
      const configToCache = {
        provider: settings.api_provider,
        baseUrl: settings.api_base_url,
        model: settings.llm_model,
        status: result.success && result.supported ? 'supported' : 'unsupported',
        testedAt: new Date().toISOString()
      };
      localStorage.setItem('mcp_verified_config', JSON.stringify(configToCache));

      if (result.success && result.supported) {
        setModelSupportStatus('supported');

        modal.success({
          title: '✅ Function Calling 支持检测',
          centered: true,
          width: isMobile ? '95%' : 700,
          content: (
            <div style={{ padding: '8px 0' }}>
              <div style={{ marginBottom: 16, padding: 12, background: 'var(--color-success-bg)', border: '1px solid var(--color-success-border)', borderRadius: 8 }}>
                <Typography.Text strong style={{ color: 'var(--color-success)', fontSize: 14 }}>
                  ✓ {result.message}
                </Typography.Text>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: 12, marginBottom: 16 }}>
                <div style={{ padding: 12, background: 'var(--color-bg-layout)', borderRadius: 8 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>API 提供商</Text>
                  <div><Text strong style={{ fontSize: 16 }}>{result.provider}</Text></div>
                </div>
                <div style={{ padding: 12, background: 'var(--color-bg-layout)', borderRadius: 8 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>响应时间</Text>
                  <div><Text strong style={{ fontSize: 16 }}>{result.response_time_ms?.toFixed(0) || 0}ms</Text></div>
                </div>
              </div>

              <div style={{ marginBottom: 12, padding: 12, background: 'var(--color-info-bg)', borderRadius: 8, border: '1px solid var(--color-info-border)' }}>
                <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>🔧 模型信息</Text>
                <Text code strong>{result.model}</Text>
                {result.details?.finish_reason && (
                  <Tag color="green" style={{ marginLeft: 8 }}>finish_reason: {result.details.finish_reason}</Tag>
                )}
              </div>

              {result.details && (
                <div style={{ marginBottom: 12 }}>
                  <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>📊 检测详情</Text>
                  <div style={{ padding: 8, background: 'var(--color-bg-layout)', borderRadius: 4, fontSize: 12 }}>
                    <div>✓ 工具调用数量: {result.details.tool_call_count || 0}</div>
                    <div>✓ 测试工具: {result.details.test_tool || 'N/A'}</div>
                    <div>✓ 响应类型: {result.details.response_type || 'N/A'}</div>
                  </div>
                </div>
              )}

              {result.tool_calls && result.tool_calls.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>🔨 工具调用示例</Text>
                  <pre style={{ margin: 0, padding: 8, background: 'var(--color-bg-layout)', borderRadius: 4, fontSize: 11, overflow: 'auto', maxHeight: 150 }}>
                    {JSON.stringify(result.tool_calls[0], null, 2)}
                  </pre>
                </div>
              )}

              {result.suggestions && result.suggestions.length > 0 && (
                <div style={{ padding: 12, background: 'var(--color-success-bg)', border: '1px solid var(--color-success-border)', borderRadius: 8 }}>
                  <Text strong style={{ fontSize: 13, display: 'block', marginBottom: 8 }}>💡 建议</Text>
                  <ul style={{ margin: 0, paddingLeft: 20, fontSize: 12 }}>
                    {result.suggestions.map((s: string, i: number) => (
                      <li key={i} style={{ marginBottom: 4 }}>{s}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ),
        });
      } else {
        setModelSupportStatus('unsupported');
        modal.warning({
          title: '❌ Function Calling 支持检测',
          centered: true,
          width: isMobile ? '95%' : 700,
          content: (
            <div style={{ padding: '8px 0' }}>
              <div style={{ marginBottom: 16 }}>
                <Alert
                  message={result.message || '模型不支持 Function Calling'}
                  type="warning"
                  showIcon
                />
              </div>

              {result.error && (
                <div style={{
                  padding: 16,
                  background: 'var(--color-warning-bg)',
                  border: '1px solid var(--color-warning-border)',
                  borderRadius: 8,
                  marginBottom: 16
                }}>
                  <Text strong style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>错误信息:</Text>
                  <Text style={{ fontSize: 13, fontFamily: 'monospace' }}>
                    {result.error}
                  </Text>
                </div>
              )}

              {result.response_preview && (
                <div style={{ marginBottom: 12 }}>
                  <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>📝 模型返回内容（前200字符）</Text>
                  <pre style={{ margin: 0, padding: 8, background: 'var(--color-bg-layout)', borderRadius: 4, fontSize: 11, overflow: 'auto', maxHeight: 100, whiteSpace: 'pre-wrap' }}>
                    {result.response_preview}
                  </pre>
                </div>
              )}

              {result.suggestions && result.suggestions.length > 0 && (
                <div style={{
                  padding: 16,
                  background: 'var(--color-info-bg)',
                  border: '1px solid var(--color-info-border)',
                  borderRadius: 8
                }}>
                  <Text strong style={{ fontSize: 14, display: 'block', marginBottom: 8 }}>💡 建议:</Text>
                  <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13 }}>
                    {result.suggestions.map((s: string, i: number) => (
                      <li key={i} style={{ marginBottom: 4 }}>{s}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ),
        });
      }
    } catch (error) {
      console.error('Check function calling failed:', error);
      message.error('检测失败，请稍后重试');
      setModelSupportStatus('unsupported');
    } finally {
      setCheckingFunctionCalling(false);
    }
  };

  const handleSubmit = async (values: { config_json: string; enabled: boolean; category?: string }) => {
    setLoading(true);
    try {
      // 验证JSON格式
      try {
        JSON.parse(values.config_json);
      } catch {
        message.error('配置JSON格式错误，请检查');
        setLoading(false);
        return;
      }

      const data = {
        config_json: values.config_json,
        enabled: values.enabled,
        category: values.category || 'general',
      };

      // 统一使用简化API，后端会自动判断是创建还是更新
      await mcpPluginApi.createPluginSimple(data);
      message.success(editingPlugin ? '插件已更新' : '插件已创建');

      setModalVisible(false);
      form.resetFields();
      loadPlugins();
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      const errorMsg = err?.response?.data?.detail || '操作失败';
      message.error(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  const getStatusTag = (plugin: MCPPlugin) => {
    if (!plugin.enabled) {
      return <Tag color="default">已禁用</Tag>;
    }
    switch (plugin.status) {
      case 'active':
        return <Tag color="success" icon={<CheckCircleOutlined />}>运行中</Tag>;
      case 'error':
        return (
          <Tag color="error" icon={<CloseCircleOutlined />} title={plugin.last_error}>错误</Tag>
        );
      default:
        return <Tag color="default">未激活</Tag>;
    }
  };

  return (
    <>
      {contextHolder}
      <div style={{
        minHeight: '90vh',
        background: 'linear-gradient(180deg, var(--color-bg-base) 0%, #EEF2F3 100%)',
        padding: isMobile ? '20px 16px 70px' : '24px 24px 70px',
        display: 'flex',
        flexDirection: 'column',
      }}>
        <div style={{
          maxWidth: 1400,
          margin: '0 auto',
          width: '100%',
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
        }}>
          {/* 顶部导航卡片 */}
          <Card
            variant="borderless"
            style={{
              background: 'linear-gradient(135deg, var(--color-primary) 0%, #5A9BA5 50%, var(--color-primary-hover) 100%)',
              borderRadius: isMobile ? 16 : 24,
              boxShadow: '0 12px 40px rgba(77, 128, 136, 0.25), 0 4px 12px rgba(0, 0, 0, 0.06)',
              marginBottom: isMobile ? 20 : 24,
              border: 'none',
              position: 'relative',
              overflow: 'hidden'
            }}
          >
            {/* 装饰性背景元素 */}
            <div style={{ position: 'absolute', top: -60, right: -60, width: 200, height: 200, borderRadius: '50%', background: 'rgba(255, 255, 255, 0.08)', pointerEvents: 'none' }} />
            <div style={{ position: 'absolute', bottom: -40, left: '30%', width: 120, height: 120, borderRadius: '50%', background: 'rgba(255, 255, 255, 0.05)', pointerEvents: 'none' }} />
            <div style={{ position: 'absolute', top: '50%', right: '15%', width: 80, height: 80, borderRadius: '50%', background: 'rgba(255, 255, 255, 0.06)', pointerEvents: 'none' }} />

            <Row align="middle" justify="space-between" gutter={[16, 16]} style={{ position: 'relative', zIndex: 1 }}>
              <Col xs={24} sm={12}>
                <Space direction="vertical" size={4}>
                  <Space align="center">
                    <Title level={isMobile ? 3 : 2} style={{ margin: 0, color: '#fff', textShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
                      <ToolOutlined style={{ color: 'rgba(255,255,255,0.9)', marginRight: 8 }} />
                      MCP插件管理
                    </Title>
                  </Space>
                  <Text style={{ fontSize: isMobile ? 12 : 14, color: 'rgba(255,255,255,0.85)', marginLeft: isMobile ? 40 : 48 }}>
                    扩展AI能力，连接外部工具与服务
                  </Text>
                </Space>
              </Col>
              <Col xs={24} sm={12}>
                <Space size={12} style={{ display: 'flex', justifyContent: isMobile ? 'flex-start' : 'flex-end', width: '100%' }}>
                  <Button
                    type="primary"
                    icon={<PlusOutlined />}
                    onClick={handleCreate}
                    style={{
                      borderRadius: 12,
                      background: 'rgba(255, 193, 7, 0.95)',
                      border: '1px solid rgba(255, 255, 255, 0.3)',
                      boxShadow: '0 4px 16px rgba(255, 193, 7, 0.4)',
                      color: '#fff',
                      fontWeight: 600
                    }}
                  >
                    添加插件
                  </Button>
                </Space>
              </Col>
            </Row>

            <div style={{ marginTop: isMobile ? 16 : 24, display: 'flex', gap: isMobile ? 12 : 16, flexDirection: isMobile ? 'column' : 'row' }}>
              <Card
                variant="borderless"
                style={{
                  flex: 1,
                  borderRadius: 12,
                  background: 'rgba(255, 255, 255, 0.9)',
                  border: '1px solid rgba(255, 255, 255, 0.6)',
                  backdropFilter: 'blur(10px)',
                  boxShadow: '0 4px 12px rgba(0, 0, 0, 0.03)'
                }}
                styles={{ body: { padding: isMobile ? 14 : 20 } }}
              >
                <div style={{
                  display: 'flex',
                  flexDirection: isMobile ? 'column' : 'row',
                  justifyContent: 'space-between',
                  alignItems: isMobile ? 'stretch' : 'center',
                  gap: isMobile ? 12 : 0
                }}>
                  <Space align="start" style={{ flex: 1 }}>
                    <div style={{
                      width: isMobile ? 36 : 40,
                      height: isMobile ? 36 : 40,
                      borderRadius: '50%',
                      background: modelSupportStatus === 'supported' ? 'var(--color-success-bg)' : modelSupportStatus === 'unsupported' ? 'var(--color-error-bg)' : 'var(--color-info-bg)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      border: `1px solid ${modelSupportStatus === 'supported' ? 'var(--color-success-border)' : modelSupportStatus === 'unsupported' ? 'var(--color-error-border)' : 'var(--color-info-border)'}`,
                      flexShrink: 0
                    }}>
                      {modelSupportStatus === 'supported' ? (
                        <CheckCircleOutlined style={{ fontSize: isMobile ? 18 : 20, color: 'var(--color-success)' }} />
                      ) : modelSupportStatus === 'unsupported' ? (
                        <CloseCircleOutlined style={{ fontSize: isMobile ? 18 : 20, color: 'var(--color-error)' }} />
                      ) : (
                        <QuestionCircleOutlined style={{ fontSize: isMobile ? 18 : 20, color: 'var(--color-info)' }} />
                      )}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <Text strong style={{ fontSize: isMobile ? 14 : 16, display: 'block', color: 'var(--color-text-primary)' }}>模型能力检查</Text>
                      <Text type="secondary" style={{ fontSize: isMobile ? 12 : 13, display: 'block', lineHeight: 1.5 }}>
                        {modelSupportStatus === 'supported'
                          ? '当前模型支持 Function Calling，可正常使用 MCP 插件'
                          : modelSupportStatus === 'unsupported'
                            ? '当前模型不支持 Function Calling，无法使用 MCP 插件'
                            : '请先检测模型是否支持 Function Calling 能力'}
                      </Text>
                    </div>
                  </Space>
                  <Button
                    type={modelSupportStatus === 'supported' ? 'default' : 'primary'}
                    icon={<ApiOutlined />}
                    onClick={handleCheckFunctionCalling}
                    loading={checkingFunctionCalling}
                    style={{ borderRadius: 8, width: isMobile ? '100%' : 'auto' }}
                    size={isMobile ? 'middle' : 'middle'}
                  >
                    {modelSupportStatus === 'unknown' ? '开始检测' : '重新检测'}
                  </Button>
                </div>
              </Card>

              <Card
                variant="borderless"
                style={{
                  flex: 1,
                  borderRadius: 12,
                  background: 'rgba(230, 247, 255, 0.6)',
                  border: '1px solid rgba(145, 213, 255, 0.6)',
                  backdropFilter: 'blur(10px)',
                  boxShadow: '0 4px 12px rgba(0, 0, 0, 0.03)'
                }}
                styles={{ body: { padding: isMobile ? 14 : 20 } }}
              >
                <Space align="start">
                  <InfoCircleOutlined style={{ fontSize: isMobile ? 18 : 20, color: 'var(--color-primary)', marginTop: 2, flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <Text strong style={{ fontSize: isMobile ? 14 : 16, display: 'block', color: 'var(--color-text-primary)', marginBottom: 4 }}>什么是 MCP 插件？</Text>
                    <Text style={{ fontSize: isMobile ? 12 : 13, display: 'block', color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>
                      MCP (Model Context Protocol) 协议允许 AI 调用外部工具获取数据。通过添加插件，AI 可以访问搜索引擎、数据库、API 等服务，大幅增强创作能力。
                    </Text>
                  </div>
                </Space>
              </Card>
            </div>
          </Card>

          {/* 主内容区 */}
          <div style={{ flex: 1 }}>
            {/* 模型能力未验证时的警告提示 */}
            {modelSupportStatus !== 'supported' && plugins.length > 0 && (
              <Alert
                message={
                  modelSupportStatus === 'unsupported'
                    ? '当前模型不支持 Function Calling，所有插件操作已禁用'
                    : '请先完成模型能力检查，才能操作插件'
                }
                type={modelSupportStatus === 'unsupported' ? 'error' : 'warning'}
                showIcon
                icon={modelSupportStatus === 'unsupported' ? <CloseCircleOutlined /> : <WarningOutlined />}
                style={{ marginBottom: 16, borderRadius: 8 }}
                action={
                  <Button size="small" type="primary" onClick={handleCheckFunctionCalling} loading={checkingFunctionCalling}>
                    {modelSupportStatus === 'unknown' ? '开始检测' : '重新检测'}
                  </Button>
                }
              />
            )}

            {/* 插件列表 */}
            <Spin spinning={loading}>
              {plugins.length === 0 ? (
                <Empty
                  description="还没有添加任何插件"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  style={{ padding: isMobile ? '40px 0' : '60px 0' }}
                >
                  <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
                    添加第一个插件
                  </Button>
                </Empty>
              ) : (
                <Space direction="vertical" size={isMobile ? 'small' : 'middle'} style={{ width: '100%' }}>
                  {plugins.map((plugin) => (
                    <Card
                      key={plugin.id}
                      size="small"
                      style={{
                        borderRadius: 8,
                        border: '1px solid #f0f0f0',
                      }}
                      styles={{ body: { padding: isMobile ? 12 : 16 } }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          flexDirection: 'column',
                          gap: isMobile ? 12 : 16,
                        }}
                      >
                        {/* 插件信息区域 */}
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <Space direction="vertical" size="small" style={{ width: '100%' }}>
                            {/* 标题和状态标签 */}
                            <div style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '6px',
                              flexWrap: 'wrap',
                              justifyContent: 'space-between'
                            }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', flex: 1 }}>
                                <Text strong style={{ fontSize: isMobile ? '14px' : '16px' }}>
                                  {plugin.display_name || plugin.plugin_name}
                                </Text>
                                {getStatusTag(plugin)}
                              </div>
                              {/* 移动端：开关放在标题行右侧 */}
                              {isMobile && (
                                <Switch
                                  title={modelSupportStatus !== 'supported' ? '请先完成模型能力检查' : (plugin.enabled ? '禁用插件' : '启用插件')}
                                  checked={plugin.enabled}
                                  onChange={(checked) => handleToggle(plugin, checked)}
                                  disabled={modelSupportStatus !== 'supported'}
                                  size="small"
                                  checkedChildren="开"
                                  unCheckedChildren="关"
                                  style={{
                                    flexShrink: 0,
                                    height: 16,
                                    minHeight: 16,
                                    lineHeight: '16px'
                                  }}
                                />
                              )}
                            </div>
                            
                            {/* 类型和分类标签 */}
                            <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                              <Tag color={plugin.plugin_type === 'http' || plugin.plugin_type === 'streamable_http' || plugin.plugin_type === 'sse' ? 'blue' : 'cyan'} style={{ fontSize: isMobile ? 11 : 12 }}>
                                {plugin.plugin_type?.toUpperCase() || 'UNKNOWN'}
                              </Tag>
                              {plugin.category && plugin.category !== 'general' && (
                                <Tag color="purple" style={{ fontSize: isMobile ? 11 : 12 }}>{plugin.category}</Tag>
                              )}
                            </div>
                            
                            {plugin.description && (
                              <Paragraph
                                type="secondary"
                                style={{
                                  margin: 0,
                                  fontSize: isMobile ? '12px' : '13px',
                                }}
                                ellipsis={{ rows: 2 }}
                              >
                                {plugin.description}
                              </Paragraph>
                            )}

                            {/* 只显示有值的URL或命令，脱敏处理敏感信息 */}
                            {(plugin.plugin_type === 'http' || plugin.plugin_type === 'streamable_http' || plugin.plugin_type === 'sse') && plugin.server_url && (
                              <div style={{
                                fontSize: isMobile ? '11px' : '12px',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap'
                              }}>
                                <Text type="secondary" code style={{ fontSize: 'inherit' }}>
                                  {(() => {
                                    // 脱敏处理：隐藏URL中的API Key
                                    const url = plugin.server_url;
                                    try {
                                      const urlObj = new URL(url);
                                      // 替换查询参数中的敏感信息
                                      const params = new URLSearchParams(urlObj.search);
                                      let maskedUrl = `${urlObj.protocol}//${urlObj.host}${urlObj.pathname}`;

                                      const sensitiveKeys = ['apiKey', 'api_key', 'key', 'token', 'secret', 'password', 'auth'];
                                      let hasParams = false;

                                      params.forEach((value, key) => {
                                        const isSensitive = sensitiveKeys.some(k => key.toLowerCase().includes(k.toLowerCase()));
                                        const maskedValue = isSensitive ? '***' : value;
                                        maskedUrl += (hasParams ? '&' : '?') + `${key}=${maskedValue}`;
                                        hasParams = true;
                                      });

                                      return maskedUrl;
                                    } catch {
                                      // 如果URL解析失败，尝试简单替换
                                      return url.replace(/([?&])(apiKey|api_key|key|token|secret|password|auth)=([^&]+)/gi, '$1$2=***');
                                    }
                                  })()}
                                </Text>
                              </div>
                            )}

                            {plugin.plugin_type === 'stdio' && plugin.command && (
                              <div style={{
                                fontSize: isMobile ? '11px' : '12px',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap'
                              }}>
                                <Text type="secondary" code style={{ fontSize: 'inherit' }}>
                                  {plugin.command} {plugin.args?.join(' ')}
                                </Text>
                              </div>
                            )}

                            {/* 显示最后错误信息 */}
                            {plugin.last_error && (
                              <Text type="danger" style={{ fontSize: isMobile ? '11px' : '12px' }}>
                                错误: {plugin.last_error}
                              </Text>
                            )}
                          </Space>
                        </div>

                        {/* 操作按钮区域 */}
                        <div style={{
                          display: 'flex',
                          justifyContent: isMobile ? 'flex-end' : 'flex-start',
                          alignItems: 'center',
                          gap: isMobile ? 8 : 8,
                          flexWrap: 'wrap',
                          borderTop: isMobile ? '1px solid #f0f0f0' : 'none',
                          paddingTop: isMobile ? 12 : 0
                        }}>
                          {/* 桌面端显示开关 */}
                          {!isMobile && (
                            <Switch
                              title={modelSupportStatus !== 'supported' ? '请先完成模型能力检查' : (plugin.enabled ? '禁用插件' : '启用插件')}
                              checked={plugin.enabled}
                              onChange={(checked) => handleToggle(plugin, checked)}
                              disabled={modelSupportStatus !== 'supported'}
                              checkedChildren="开"
                              unCheckedChildren="关"
                            />
                          )}
                          <Button
                            title={modelSupportStatus !== 'supported' ? '请先完成模型能力检查' : '测试连接'}
                            icon={<ThunderboltOutlined />}
                            onClick={() => handleTest(plugin.id)}
                            loading={testingPluginId === plugin.id}
                            disabled={modelSupportStatus !== 'supported'}
                            size={isMobile ? 'small' : 'middle'}
                          >
                            {!isMobile && '测试'}
                          </Button>
                          <Button
                            title={modelSupportStatus !== 'supported' ? '请先完成模型能力检查' : '查看工具'}
                            icon={<ToolOutlined />}
                            onClick={() => handleViewTools(plugin.id)}
                            disabled={modelSupportStatus !== 'supported' || !plugin.enabled || plugin.status !== 'active'}
                            size={isMobile ? 'small' : 'middle'}
                          >
                            {!isMobile && '工具'}
                          </Button>
                          <Button
                            title={modelSupportStatus !== 'supported' ? '请先完成模型能力检查' : '编辑'}
                            icon={<EditOutlined />}
                            onClick={() => handleEdit(plugin)}
                            disabled={modelSupportStatus !== 'supported'}
                            size={isMobile ? 'small' : 'middle'}
                          >
                            {!isMobile && '编辑'}
                          </Button>
                          <Button
                            title={modelSupportStatus !== 'supported' ? '请先完成模型能力检查' : '删除'}
                            danger
                            icon={<DeleteOutlined />}
                            onClick={() => handleDelete(plugin)}
                            disabled={modelSupportStatus !== 'supported'}
                            size={isMobile ? 'small' : 'middle'}
                          >
                            {!isMobile && '删除'}
                          </Button>
                        </div>
                      </div>
                    </Card>
                  ))}
                </Space>
              )}
            </Spin>
          </div>
        </div>

        {/* 创建/编辑插件模态框 */}
        <Modal
          title={editingPlugin ? '编辑插件' : '添加插件'}
          open={modalVisible}
          centered
          onCancel={() => {
            setModalVisible(false);
            form.resetFields();
          }}
          onOk={() => form.submit()}
          width={isMobile ? '100%' : 600}
          confirmLoading={loading}
          okText="保存"
          cancelText="取消"
        >
          <Form form={form} layout="vertical" onFinish={handleSubmit}>
            <Form.Item
              label="MCP配置JSON"
              name="config_json"
              rules={[{ required: true, message: '请输入配置JSON' }]}
              extra="粘贴标准MCP配置，系统自动提取插件名称。支持HTTP和Stdio类型"
            >
              <TextArea
                rows={isMobile ? 12 : 16}
                placeholder={`示例：
{
  "mcpServers": {
    "exa": {
      "type": "streamable_http",
      "url": "https://mcp.exa.ai/mcp?exaApiKey=YOUR_API_KEY",
      "headers": {}
    }
  }
}`}
                style={{ fontFamily: 'monospace', fontSize: '13px' }}
              />
            </Form.Item>

            <Form.Item
              label="插件分类"
              name="category"
              rules={[{ required: true, message: '请选择插件分类' }]}
              extra="选择插件的功能类别，用于AI智能匹配使用场景"
            >
              <Select placeholder="请选择分类">
                <Select.Option value="search">搜索类 (Search) - 网络搜索、信息查询</Select.Option>
                <Select.Option value="analysis">分析类 (Analysis) - 数据分析、文本处理</Select.Option>
                <Select.Option value="filesystem">文件系统 (FileSystem) - 文件读写操作</Select.Option>
                <Select.Option value="database">数据库 (Database) - 数据库查询</Select.Option>
                <Select.Option value="api">API调用 (API) - 第三方服务接口</Select.Option>
                <Select.Option value="generation">生成类 (Generation) - 内容生成工具</Select.Option>
                <Select.Option value="general">通用 (General) - 其他功能</Select.Option>
              </Select>
            </Form.Item>
          </Form>
        </Modal>

        {/* 查看工具列表模态框 */}
        <Modal
          title={
            <Space>
              <ToolOutlined style={{ color: 'var(--color-primary)' }} />
              <span>可用工具列表</span>
              {viewingTools && viewingTools.tools.length > 0 && (
                <Tag color="blue">{viewingTools.tools.length} 个工具</Tag>
              )}
            </Space>
          }
          open={!!viewingTools}
          onCancel={() => setViewingTools(null)}
          footer={[
            <Button key="close" type="primary" onClick={() => setViewingTools(null)}>
              关闭
            </Button>,
          ]}
          width={isMobile ? '95%' : 800}
          centered
          styles={{
            body: {
              maxHeight: isMobile ? '60vh' : '70vh',
              overflowY: 'auto',
              padding: isMobile ? '16px' : '24px'
            }
          }}
        >
          {viewingTools && (
            <Space direction="vertical" size="middle" style={{ width: '100%' }}>
              {viewingTools.tools.length === 0 ? (
                <Empty
                  description="该插件没有提供任何工具"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  style={{ padding: '40px 0' }}
                />
              ) : (
                viewingTools.tools.map((tool, index) => (
                  <Card
                    key={index}
                    size="small"
                    style={{
                      borderRadius: 8,
                      border: '1px solid var(--color-border-secondary)',
                      boxShadow: '0 2px 4px rgba(0,0,0,0.05)'
                    }}
                    title={
                      <Space>
                        <Text code strong style={{ fontSize: isMobile ? '13px' : '14px', color: 'var(--color-primary)' }}>
                          {tool.name}
                        </Text>
                        <Tag color="processing" style={{ fontSize: '11px' }}>
                          #{index + 1}
                        </Tag>
                      </Space>
                    }
                  >
                    <Space direction="vertical" size="small" style={{ width: '100%' }}>
                      {tool.description && (
                        <div>
                          <Text type="secondary" style={{ fontSize: isMobile ? '12px' : '13px', display: 'block', marginBottom: 4 }}>
                            描述：
                          </Text>
                          <Paragraph
                            style={{
                              margin: 0,
                              fontSize: isMobile ? '12px' : '13px',
                              padding: '8px 12px',
                              background: 'var(--color-bg-layout)',
                              borderRadius: 4,
                              borderLeft: '3px solid var(--color-info)'
                            }}
                          >
                            {tool.description}
                          </Paragraph>
                        </div>
                      )}
                      {tool.inputSchema && (
                        <div>
                          <Text type="secondary" style={{ fontSize: isMobile ? '12px' : '13px', display: 'block', marginBottom: 4 }}>
                            输入参数：
                          </Text>
                          <pre
                            style={{
                              margin: 0,
                              padding: isMobile ? '8px' : '12px',
                              background: 'var(--color-bg-layout)',
                              borderRadius: 4,
                              fontSize: isMobile ? '11px' : '12px',
                              overflow: 'auto',
                              maxHeight: '200px',
                              border: '1px solid var(--color-border-secondary)',
                              lineHeight: 1.6
                            }}
                          >
                            {JSON.stringify(tool.inputSchema, null, 2)}
                          </pre>
                        </div>
                      )}
                    </Space>
                  </Card>
                ))
              )}
            </Space>
          )}
        </Modal>
      </div>
    </>
  );
}