import { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Row,
  Col,
  Input,
  Select,
  Button,
  Tag,
  Space,
  Empty,
  Spin,
  Modal,
  Form,
  message,
  Tooltip,
  Badge,
  Tabs,
  Typography,
  Pagination,
  Alert,
  Statistic,
} from 'antd';
import {
  SearchOutlined,
  DownloadOutlined,
  HeartOutlined,
  HeartFilled,
  CloudUploadOutlined,
  EyeOutlined,
  UserOutlined,
  ClockCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  DeleteOutlined,
  CloudOutlined,
  DisconnectOutlined,
  SettingOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { promptWorkshopApi, authApi } from '../services/api';
import type {
  PromptWorkshopItem,
  PromptSubmission,
  PromptSubmissionCreate,
  User,
} from '../types';
import { PROMPT_CATEGORIES } from '../types';

const { TextArea } = Input;
const { Text, Paragraph } = Typography;

export default function PromptWorkshop() {
  const [items, setItems] = useState<PromptWorkshopItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize] = useState(12);
  
  // 筛选条件
  const [category, setCategory] = useState<string>('');
  const [searchKeyword, setSearchKeyword] = useState('');
  const [sortBy, setSortBy] = useState<'newest' | 'popular' | 'downloads'>('newest');
  
  // 服务状态
  const [serviceStatus, setServiceStatus] = useState<{
    mode: string;
    instance_id: string;
    cloud_connected?: boolean;
  } | null>(null);
  
  // 提交相关
  const [isSubmitModalOpen, setIsSubmitModalOpen] = useState(false);
  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitForm] = Form.useForm();
  
  // 我的提交
  const [mySubmissions, setMySubmissions] = useState<PromptSubmission[]>([]);
  const [submissionsLoading, setSubmissionsLoading] = useState(false);
  
  // 详情弹窗
  const [detailItem, setDetailItem] = useState<PromptWorkshopItem | null>(null);
  const [isDetailModalOpen, setIsDetailModalOpen] = useState(false);
  
  // 导入状态
  const [importingId, setImportingId] = useState<string | null>(null);
  
  // 当前用户
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  
  // 管理员审核相关
  const [adminSubmissions, setAdminSubmissions] = useState<PromptSubmission[]>([]);
  const [adminSubmissionsLoading, setAdminSubmissionsLoading] = useState(false);
  const [adminPendingCount, setAdminPendingCount] = useState(0);
  const [adminStats, setAdminStats] = useState<{
    total_items: number;
    total_official: number;
    total_pending: number;
    total_downloads: number;
    total_likes: number;
  } | null>(null);
  const [reviewModalOpen, setReviewModalOpen] = useState(false);
  const [reviewingSubmission, setReviewingSubmission] = useState<PromptSubmission | null>(null);
  const [reviewForm] = Form.useForm();
  const [reviewLoading, setReviewLoading] = useState(false);
  const [addOfficialModalOpen, setAddOfficialModalOpen] = useState(false);
  const [addOfficialForm] = Form.useForm();
  const [addOfficialLoading, setAddOfficialLoading] = useState(false);
  
  // 已发布提示词管理
  const [publishedItems, setPublishedItems] = useState<PromptWorkshopItem[]>([]);
  const [publishedLoading, setPublishedLoading] = useState(false);
  const [editingItem, setEditingItem] = useState<PromptWorkshopItem | null>(null);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editForm] = Form.useForm();
  const [editLoading, setEditLoading] = useState(false);
  
  // 当前活动的 Tab
  const [activeTab, setActiveTab] = useState<string>('browse');
  
  const isMobile = window.innerWidth <= 768;
  
  // 判断是否为服务端管理员
  const isServerAdmin = serviceStatus?.mode === 'server' && currentUser?.is_admin;

  // 卡片网格配置 - 与 WritingStyles 保持一致
  const gridConfig = {
    gutter: isMobile ? 8 : 16,
    xs: 24,
    sm: 24,
    md: 12,
    lg: 8,
    xl: 6,
  };

  // 加载服务状态和用户信息
  useEffect(() => {
    const init = async () => {
      try {
        const [status, user] = await Promise.all([
          promptWorkshopApi.getStatus(),
          authApi.getCurrentUser().catch(() => null),
        ]);
        setServiceStatus(status);
        setCurrentUser(user);
      } catch (error) {
        console.error('Failed to initialize:', error);
      }
    };
    init();
  }, []);

  // 加载工坊列表
  const loadItems = useCallback(async () => {
    setLoading(true);
    try {
      const response = await promptWorkshopApi.getItems({
        category: category || undefined,
        search: searchKeyword || undefined,
        sort: sortBy,
        page: currentPage,
        limit: pageSize,
      });
      setItems(response.data?.items || []);
      setTotal(response.data?.total || 0);
    } catch (error) {
      console.error('Failed to load workshop items:', error);
      message.error('加载提示词工坊失败');
    } finally {
      setLoading(false);
    }
  }, [category, searchKeyword, sortBy, currentPage, pageSize]);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  // 加载我的提交
  const loadMySubmissions = async () => {
    setSubmissionsLoading(true);
    try {
      const response = await promptWorkshopApi.getMySubmissions();
      setMySubmissions(response.data?.items || []);
    } catch (error) {
      console.error('Failed to load submissions:', error);
    } finally {
      setSubmissionsLoading(false);
    }
  };

  // 导入到本地
  const handleImport = async (item: PromptWorkshopItem) => {
    setImportingId(item.id);
    try {
      await promptWorkshopApi.importItem(item.id);
      message.success(`已导入「${item.name}」到本地写作风格`);
      // 刷新列表更新下载计数
      loadItems();
    } catch (error) {
      console.error('Failed to import item:', error);
      message.error('导入失败');
    } finally {
      setImportingId(null);
    }
  };

  // 点赞
  const handleLike = async (item: PromptWorkshopItem) => {
    try {
      const response = await promptWorkshopApi.toggleLike(item.id);
      // 更新本地状态
      setItems(prev => prev.map(i => 
        i.id === item.id 
          ? { ...i, is_liked: response.liked, like_count: response.like_count }
          : i
      ));
    } catch (error) {
      console.error('Failed to toggle like:', error);
      message.error('操作失败');
    }
  };

  // 提交新提示词
  const handleSubmit = async (values: PromptSubmissionCreate) => {
    setSubmitLoading(true);
    try {
      await promptWorkshopApi.submit({
        ...values,
        tags: values.tags ? (values.tags as unknown as string).split(',').map((t: string) => t.trim()).filter(Boolean) : [],
      });
      message.success('提交成功，等待管理员审核');
      setIsSubmitModalOpen(false);
      submitForm.resetFields();
      loadMySubmissions();
      // 如果是服务端管理员，刷新待审核列表
      if (isServerAdmin) {
        loadAdminSubmissions();
      }
    } catch (error) {
      console.error('Failed to submit:', error);
      message.error('提交失败');
    } finally {
      setSubmitLoading(false);
    }
  };

  // 撤回提交（pending状态）
  const handleWithdraw = async (submissionId: string) => {
    try {
      await promptWorkshopApi.withdrawSubmission(submissionId);
      message.success('已撤回');
      loadMySubmissions();
      // 如果是服务端管理员，刷新待审核列表
      if (isServerAdmin) {
        loadAdminSubmissions();
      }
    } catch (error) {
      console.error('Failed to withdraw:', error);
      message.error('撤回失败');
    }
  };

  // 删除提交记录（已审核状态）
  const handleDeleteSubmission = async (submission: PromptSubmission) => {
    Modal.confirm({
      title: '删除提交记录',
      content: `确定要删除「${submission.name}」的提交记录吗？此操作不可恢复。`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      centered: true,
      onOk: async () => {
        try {
          await promptWorkshopApi.deleteSubmission(submission.id);
          message.success('删除成功');
          loadMySubmissions();
          // 如果是服务端管理员，刷新相关列表
          if (isServerAdmin) {
            loadAdminSubmissions();
          }
        } catch (error) {
          console.error('Failed to delete submission:', error);
          message.error('删除失败');
        }
      },
    });
  };

  // 查看详情
  const handleViewDetail = async (item: PromptWorkshopItem) => {
    try {
      const response = await promptWorkshopApi.getItem(item.id);
      setDetailItem(response.data);
      setIsDetailModalOpen(true);
    } catch (error) {
      console.error('Failed to load detail:', error);
      message.error('加载详情失败');
    }
  };

  // 获取分类标签颜色
  const getCategoryColor = (cat: string) => {
    const colors: Record<string, string> = {
      general: 'blue',
      fantasy: 'purple',
      martial: 'orange',
      romance: 'pink',
      scifi: 'cyan',
      horror: 'red',
      history: 'gold',
      urban: 'green',
      game: 'magenta',
      other: 'default',
    };
    return colors[cat] || 'default';
  };

  // 获取分类名称
  const getCategoryName = (cat: string) => {
    return PROMPT_CATEGORIES[cat] || cat;
  };
  
  // 获取分类选项列表
  const categoryOptions = Object.entries(PROMPT_CATEGORIES).map(([value, label]) => ({
    value,
    label,
  }));

  // 获取提交状态标签
  const getStatusTag = (status: string) => {
    const config: Record<string, { color: string; icon: React.ReactNode; text: string }> = {
      pending: { color: 'processing', icon: <ClockCircleOutlined />, text: '待审核' },
      approved: { color: 'success', icon: <CheckCircleOutlined />, text: '已通过' },
      rejected: { color: 'error', icon: <CloseCircleOutlined />, text: '已拒绝' },
    };
    const cfg = config[status] || config.pending;
    return <Tag color={cfg.color} icon={cfg.icon}>{cfg.text}</Tag>;
  };

  // 渲染筛选区域（固定在顶部）
  const renderFilterBar = () => (
    <div style={{ marginBottom: 16 }}>
      {/* 服务状态 */}
      {serviceStatus && !serviceStatus.cloud_connected && serviceStatus.mode === 'client' && (
        <Alert
          type="warning"
          message="云端服务未连接"
          description="无法访问提示词工坊，请检查网络连接或稍后重试"
          icon={<DisconnectOutlined />}
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}
      
      {/* 筛选区域 */}
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: 12,
        alignItems: 'center',
      }}>
        <Input
          placeholder="搜索提示词..."
          prefix={<SearchOutlined />}
          value={searchKeyword}
          onChange={e => setSearchKeyword(e.target.value)}
          onPressEnter={() => { setCurrentPage(1); loadItems(); }}
          style={{ width: isMobile ? '100%' : 200 }}
          allowClear
        />
        <Select
          placeholder="选择分类"
          value={category}
          onChange={v => { setCategory(v); setCurrentPage(1); }}
          style={{ width: isMobile ? '100%' : 150 }}
          allowClear
        >
          {categoryOptions.map(cat => (
            <Select.Option key={cat.value} value={cat.value}>{cat.label}</Select.Option>
          ))}
        </Select>
        <Select
          value={sortBy}
          onChange={v => { setSortBy(v); setCurrentPage(1); }}
          style={{ width: isMobile ? '100%' : 120 }}
        >
          <Select.Option value="newest">最新发布</Select.Option>
          <Select.Option value="popular">最受欢迎</Select.Option>
          <Select.Option value="downloads">下载最多</Select.Option>
        </Select>
        <Button
          icon={<SyncOutlined />}
          onClick={() => { setCurrentPage(1); loadItems(); }}
        >
          刷新
        </Button>
      </div>
    </div>
  );

  // 渲染工坊列表（只有卡片部分，用于滚动区域）
  const renderWorkshopList = () => (
    <Spin spinning={loading}>
          {items.length === 0 ? (
            <Empty description="暂无提示词" />
          ) : (
            <>
              <Row
                gutter={[0, gridConfig.gutter]}
                style={{ marginLeft: 0, marginRight: 0 }}
              >
              {items.map(item => (
                <Col
                  key={item.id}
                  xs={gridConfig.xs}
                  sm={gridConfig.sm}
                  md={gridConfig.md}
                  lg={gridConfig.lg}
                  xl={gridConfig.xl}
                  style={{
                    paddingLeft: 0,
                    paddingRight: gridConfig.gutter / 2,
                    marginBottom: gridConfig.gutter
                  }}
                >
                  <Card
                    hoverable
                    style={{ 
                      height: '100%', 
                      borderRadius: 12,
                      display: 'flex',
                      flexDirection: 'column',
                      border: '1px solid #f0f0f0',
                    }}
                    bodyStyle={{ 
                      padding: 16, 
                      display: 'flex', 
                      flexDirection: 'column', 
                      flex: 1,
                    }}
                    actions={[
                      <Tooltip title="查看详情" key="view">
                        <EyeOutlined onClick={() => handleViewDetail(item)} />
                      </Tooltip>,
                      <Tooltip title={item.is_liked ? '取消点赞' : '点赞'} key="like">
                        <span onClick={() => handleLike(item)}>
                          {item.is_liked ? (
                            <HeartFilled style={{ color: '#ff4d4f' }} />
                          ) : (
                            <HeartOutlined />
                          )}
                          <span style={{ marginLeft: 4 }}>{item.like_count || 0}</span>
                        </span>
                      </Tooltip>,
                      <Tooltip title="导入到本地" key="import">
                        <Button
                          type="link"
                          size="small"
                          icon={<DownloadOutlined />}
                          loading={importingId === item.id}
                          onClick={() => handleImport(item)}
                        >
                          {item.download_count || 0}
                        </Button>
                      </Tooltip>,
                    ]}
                  >
                    <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
                      <Space style={{ marginBottom: 12 }} wrap>
                        <Text strong style={{ fontSize: 16 }}>{item.name}</Text>
                        <Tag color={getCategoryColor(item.category)}>
                          {getCategoryName(item.category)}
                        </Tag>
                      </Space>
                      
                      {item.description && (
                        <Paragraph
                          type="secondary"
                          style={{ fontSize: 13, marginBottom: 12 }}
                          ellipsis={{ rows: 2, tooltip: item.description }}
                        >
                          {item.description}
                        </Paragraph>
                      )}
                      
                      <Paragraph
                        type="secondary"
                        style={{
                          fontSize: 12,
                          marginBottom: 0,
                          backgroundColor: '#fafafa',
                          padding: 8,
                          borderRadius: 4,
                          flex: 1,
                          minHeight: 60,
                        }}
                        ellipsis={{ rows: 3 }}
                      >
                        {item.prompt_content}
                      </Paragraph>
                      
                      {item.tags && item.tags.length > 0 && (
                        <Space size={4} wrap style={{ marginTop: 8 }}>
                          {item.tags.slice(0, 3).map(tag => (
                            <Tag key={tag} style={{ fontSize: 11 }}>{tag}</Tag>
                          ))}
                          {item.tags.length > 3 && (
                            <Tag style={{ fontSize: 11 }}>+{item.tags.length - 3}</Tag>
                          )}
                        </Space>
                      )}
                    </div>
                    
                    <div style={{ marginTop: 8, color: '#999', fontSize: 12 }}>
                      <Space>
                        <span><UserOutlined /> {item.author_name || '匿名'}</span>
                      </Space>
                    </div>
                  </Card>
                </Col>
              ))}
              </Row>
              
              {total > pageSize && (
                <div style={{ marginTop: 24, textAlign: 'center', paddingBottom: 16 }}>
                  <Pagination
                    current={currentPage}
                    total={total}
                    pageSize={pageSize}
                    onChange={page => setCurrentPage(page)}
                    showSizeChanger={false}
                    showTotal={t => `共 ${t} 个提示词`}
                  />
                </div>
              )}
            </>
          )}
    </Spin>
  );

  // 渲染我的提交
  const renderMySubmissions = () => (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text>查看您提交的提示词及审核状态</Text>
        <Button icon={<SyncOutlined />} onClick={loadMySubmissions}>
          刷新
        </Button>
      </div>
      
      <Spin spinning={submissionsLoading}>
          {mySubmissions.length === 0 ? (
            <Empty description="暂无提交记录" />
          ) : (
            <Row gutter={[0, gridConfig.gutter]} style={{ marginLeft: 0, marginRight: 0 }}>
              {mySubmissions.map(sub => (
              <Col 
                key={sub.id} 
                xs={gridConfig.xs} 
                sm={gridConfig.sm} 
                md={gridConfig.md} 
                lg={gridConfig.lg}
                xl={gridConfig.xl}
                style={{
                  paddingLeft: 0,
                  paddingRight: gridConfig.gutter / 2,
                  marginBottom: gridConfig.gutter
                }}
              >
                <Card
                  style={{ borderRadius: 12, height: '100%', border: '1px solid #f0f0f0' }}
                  bodyStyle={{ padding: 16 }}
                >
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Text strong>{sub.name}</Text>
                      {getStatusTag(sub.status)}
                    </div>
                    
                    <Tag color={getCategoryColor(sub.category)}>
                      {getCategoryName(sub.category)}
                    </Tag>
                    
                    <Paragraph
                      type="secondary"
                      style={{ fontSize: 12, marginBottom: 0 }}
                      ellipsis={{ rows: 2 }}
                    >
                      {sub.prompt_content}
                    </Paragraph>
                    
                    {sub.status === 'rejected' && sub.review_note && (
                      <Alert
                        type="error"
                        message="拒绝原因"
                        description={sub.review_note}
                        style={{ fontSize: 12 }}
                      />
                    )}
                    
                    <div style={{ fontSize: 12, color: '#999' }}>
                      提交时间: {sub.created_at ? new Date(sub.created_at).toLocaleDateString() : '-'}
                    </div>
                    
                    <Space>
                      {sub.status === 'pending' && (
                        <Button
                          type="link"
                          danger
                          size="small"
                          icon={<DeleteOutlined />}
                          onClick={() => handleWithdraw(sub.id)}
                        >
                          撤回
                        </Button>
                      )}
                      {sub.status !== 'pending' && (
                        <Button
                          type="link"
                          danger
                          size="small"
                          icon={<DeleteOutlined />}
                          onClick={() => handleDeleteSubmission(sub)}
                        >
                          删除记录
                        </Button>
                      )}
                    </Space>
                  </Space>
                </Card>
              </Col>
            ))}
            </Row>
          )}
      </Spin>
    </div>
  );

  // 加载管理员待审核列表
  const loadAdminSubmissions = async () => {
    if (!isServerAdmin) return;
    
    setAdminSubmissionsLoading(true);
    try {
      const [subsResponse, statsResponse] = await Promise.all([
        promptWorkshopApi.adminGetSubmissions({ status: 'pending', limit: 50 }),
        promptWorkshopApi.adminGetStats(),
      ]);
      setAdminSubmissions(subsResponse.data?.items || []);
      setAdminPendingCount(subsResponse.data?.pending_count || 0);
      setAdminStats(statsResponse.data || null);
    } catch (error) {
      console.error('Failed to load admin submissions:', error);
    } finally {
      setAdminSubmissionsLoading(false);
    }
  };

  // 加载已发布的提示词列表（管理员用）
  const loadPublishedItems = async () => {
    if (!isServerAdmin) return;
    
    setPublishedLoading(true);
    try {
      const response = await promptWorkshopApi.getItems({ limit: 100 });
      setPublishedItems(response.data?.items || []);
    } catch (error) {
      console.error('Failed to load published items:', error);
    } finally {
      setPublishedLoading(false);
    }
  };

  // 删除已发布的提示词
  const handleDeleteItem = async (item: PromptWorkshopItem) => {
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除「${item.name}」吗？此操作不可恢复。`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      centered: true,
      onOk: async () => {
        try {
          await promptWorkshopApi.adminDeleteItem(item.id);
          message.success('删除成功');
          loadPublishedItems();
          loadAdminSubmissions();
          loadItems();
        } catch (error) {
          console.error('Failed to delete item:', error);
          message.error('删除失败');
        }
      },
    });
  };

  // 编辑已发布的提示词
  const handleEditItem = async (values: { name: string; category: string; description?: string; prompt_content: string; tags?: string }) => {
    if (!editingItem) return;
    
    setEditLoading(true);
    try {
      await promptWorkshopApi.adminUpdateItem(editingItem.id, {
        ...values,
        tags: values.tags ? values.tags.split(',').map(t => t.trim()).filter(Boolean) : undefined,
      });
      message.success('修改成功');
      setEditModalOpen(false);
      setEditingItem(null);
      editForm.resetFields();
      loadPublishedItems();
      loadItems();
    } catch (error) {
      console.error('Failed to update item:', error);
      message.error('修改失败');
    } finally {
      setEditLoading(false);
    }
  };

  // 打开编辑弹窗
  const openEditModal = (item: PromptWorkshopItem) => {
    setEditingItem(item);
    editForm.setFieldsValue({
      name: item.name,
      category: item.category,
      description: item.description,
      prompt_content: item.prompt_content,
      tags: item.tags?.join(', '),
    });
    setEditModalOpen(true);
  };

  // 审核提交
  const handleReview = async (action: 'approve' | 'reject') => {
    if (!reviewingSubmission) return;
    
    setReviewLoading(true);
    try {
      const values = reviewForm.getFieldsValue();
      await promptWorkshopApi.adminReviewSubmission(reviewingSubmission.id, {
        action,
        review_note: values.review_note,
        category: values.category,
        tags: values.tags ? values.tags.split(',').map((t: string) => t.trim()).filter(Boolean) : undefined,
      });
      message.success(action === 'approve' ? '已通过审核' : '已拒绝');
      setReviewModalOpen(false);
      setReviewingSubmission(null);
      reviewForm.resetFields();
      // 刷新所有相关数据
      loadAdminSubmissions();
      loadItems();
      loadPublishedItems();  // 通过时会新增到已发布列表
    } catch (error) {
      console.error('Failed to review:', error);
      message.error('审核失败');
    } finally {
      setReviewLoading(false);
    }
  };

  // 添加官方提示词
  const handleAddOfficial = async (values: { name: string; category: string; description?: string; prompt_content: string; tags?: string }) => {
    setAddOfficialLoading(true);
    try {
      await promptWorkshopApi.adminCreateItem({
        ...values,
        tags: values.tags ? values.tags.split(',').map(t => t.trim()).filter(Boolean) : undefined,
      });
      message.success('添加成功');
      setAddOfficialModalOpen(false);
      addOfficialForm.resetFields();
      loadItems();
      loadAdminSubmissions();
      loadPublishedItems();
    } catch (error) {
      console.error('Failed to add official item:', error);
      message.error('添加失败');
    } finally {
      setAddOfficialLoading(false);
    }
  };

  // 渲染管理员面板
  const renderAdminPanel = () => (
    <div>
      {/* 统计数据 */}
      {adminStats && (
        <Row gutter={16} style={{ marginBottom: 24 }}>
          <Col span={4}>
            <Card size="small">
              <Statistic title="总提示词" value={adminStats.total_items} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="官方提示词" value={adminStats.total_official} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="待审核" value={adminStats.total_pending} valueStyle={{ color: '#faad14' }} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="总下载" value={adminStats.total_downloads} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="总点赞" value={adminStats.total_likes} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddOfficialModalOpen(true)}>
                添加官方
              </Button>
            </Card>
          </Col>
        </Row>
      )}
      
      {/* 待审核列表 */}
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text strong>待审核提交 ({adminPendingCount})</Text>
        <Button icon={<SyncOutlined />} onClick={loadAdminSubmissions}>
          刷新
        </Button>
      </div>
      
      <Spin spinning={adminSubmissionsLoading}>
        {adminSubmissions.length === 0 ? (
          <Empty description="暂无待审核提交" />
        ) : (
          <Row gutter={[0, gridConfig.gutter]} style={{ marginLeft: 0, marginRight: 0 }}>
            {adminSubmissions.map(sub => (
              <Col 
                key={sub.id} 
                xs={gridConfig.xs} 
                sm={gridConfig.sm} 
                md={gridConfig.md} 
                lg={gridConfig.lg}
                xl={gridConfig.xl}
                style={{
                  paddingLeft: 0,
                  paddingRight: gridConfig.gutter / 2,
                  marginBottom: gridConfig.gutter
                }}
              >
                <Card
                  style={{ borderRadius: 12, border: '1px solid #f0f0f0' }}
                  bodyStyle={{ padding: 16 }}
                  actions={[
                    <Button
                      key="approve"
                      type="link"
                      style={{ color: '#52c41a' }}
                      onClick={() => {
                        setReviewingSubmission(sub);
                        reviewForm.setFieldsValue({
                          category: sub.category,
                          tags: sub.tags?.join(', '),
                        });
                        setReviewModalOpen(true);
                      }}
                    >
                      审核
                    </Button>,
                  ]}
                >
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Text strong>{sub.name}</Text>
                    <Tag color={getCategoryColor(sub.category)}>
                      {getCategoryName(sub.category)}
                    </Tag>
                    
                    <Paragraph
                      type="secondary"
                      style={{ fontSize: 12, marginBottom: 0 }}
                      ellipsis={{ rows: 3 }}
                    >
                      {sub.prompt_content}
                    </Paragraph>
                    
                    <div style={{ fontSize: 11, color: '#999' }}>
                      <div>提交者: {sub.submitter_name || '未知'}</div>
                      <div>来源: {sub.source_instance}</div>
                      <div>时间: {sub.created_at ? new Date(sub.created_at).toLocaleDateString() : '-'}</div>
                    </div>
                  </Space>
                </Card>
              </Col>
            ))}
          </Row>
        )}
      </Spin>
      
      {/* 已发布提示词管理 */}
      <div style={{ marginTop: 32, marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text strong>已发布提示词管理 ({publishedItems.length})</Text>
        <Button icon={<SyncOutlined />} onClick={loadPublishedItems}>
          刷新
        </Button>
      </div>
      
      <Spin spinning={publishedLoading}>
        {publishedItems.length === 0 ? (
          <Empty description="暂无已发布提示词" />
        ) : (
          <Row gutter={[0, gridConfig.gutter]} style={{ marginLeft: 0, marginRight: 0 }}>
            {publishedItems.map(item => (
              <Col 
                key={item.id} 
                xs={gridConfig.xs} 
                sm={gridConfig.sm} 
                md={gridConfig.md} 
                lg={gridConfig.lg}
                xl={gridConfig.xl}
                style={{
                  paddingLeft: 0,
                  paddingRight: gridConfig.gutter / 2,
                  marginBottom: gridConfig.gutter
                }}
              >
                <Card
                  style={{ borderRadius: 12, border: '1px solid #f0f0f0' }}
                  bodyStyle={{ padding: 16 }}
                  actions={[
                    <Tooltip title="编辑" key="edit">
                      <Button
                        type="link"
                        icon={<SettingOutlined />}
                        onClick={() => openEditModal(item)}
                      />
                    </Tooltip>,
                    <Tooltip title="删除" key="delete">
                      <Button
                        type="link"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => handleDeleteItem(item)}
                      />
                    </Tooltip>,
                  ]}
                >
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Text strong ellipsis style={{ maxWidth: 120 }}>{item.name}</Text>
                      {item.is_official && <Tag color="gold">官方</Tag>}
                    </div>
                    <Tag color={getCategoryColor(item.category)}>
                      {getCategoryName(item.category)}
                    </Tag>
                    
                    <Paragraph
                      type="secondary"
                      style={{ fontSize: 12, marginBottom: 0 }}
                      ellipsis={{ rows: 2 }}
                    >
                      {item.prompt_content}
                    </Paragraph>
                    
                    <div style={{ fontSize: 11, color: '#999' }}>
                      <Space>
                        <span><HeartOutlined /> {item.like_count || 0}</span>
                        <span><DownloadOutlined /> {item.download_count || 0}</span>
                      </Space>
                    </div>
                  </Space>
                </Card>
              </Col>
            ))}
          </Row>
        )}
      </Spin>
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* 固定区域：标题 + Tabs切换栏 + 筛选栏 */}
      <div style={{ flexShrink: 0 }}>
        {/* 标题和操作区 */}
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: isMobile ? '12px 0' : '16px 0',
          marginBottom: isMobile ? 12 : 16,
          borderBottom: '1px solid #f0f0f0',
          flexWrap: 'wrap',
          gap: 12,
        }}>
          <h2 style={{ margin: 0, fontSize: isMobile ? 18 : 24, display: 'flex', alignItems: 'center', gap: 8 }}>
            <CloudOutlined />
            提示词工坊
            {serviceStatus?.mode === 'server' && (
              <Badge status="success" text="服务端模式" style={{ marginLeft: 8, fontSize: 12 }} />
            )}
          </h2>
          <Button
            type="primary"
            icon={<CloudUploadOutlined />}
            onClick={() => setIsSubmitModalOpen(true)}
          >
            分享我的提示词
          </Button>
        </div>

        {/* Tabs 切换栏（不含内容） */}
        <Tabs
          activeKey={activeTab}
          onChange={key => {
            setActiveTab(key);
            if (key === 'submissions') loadMySubmissions();
            if (key === 'admin') {
              loadAdminSubmissions();
              loadPublishedItems();
            }
          }}
          items={[
            { key: 'browse', label: '浏览工坊' },
            {
              key: 'submissions',
              label: (
                <Badge count={mySubmissions.filter(s => s.status === 'pending').length} size="small">
                  我的提交
                </Badge>
              ),
            },
            ...(isServerAdmin ? [{
              key: 'admin',
              label: (
                <Badge count={adminPendingCount} size="small">
                  <span><SettingOutlined /> 管理审核</span>
                </Badge>
              ),
            }] : []),
          ]}
          tabBarStyle={{ marginBottom: 16 }}
        />

        {/* 筛选栏（仅在浏览工坊时显示） */}
        {activeTab === 'browse' && renderFilterBar()}
      </div>

      {/* 滚动区域：只有卡片列表滚动 */}
      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {activeTab === 'browse' && renderWorkshopList()}
        {activeTab === 'submissions' && renderMySubmissions()}
        {activeTab === 'admin' && renderAdminPanel()}
      </div>

      {/* 提交弹窗 */}
      <Modal
        title="分享提示词到工坊"
        open={isSubmitModalOpen}
        onCancel={() => {
          setIsSubmitModalOpen(false);
          submitForm.resetFields();
        }}
        footer={null}
        width={isMobile ? '100%' : 600}
        centered
      >
        <Alert
          type="info"
          message="提交须知"
          description="您的提示词将提交给管理员审核，审核通过后会在工坊中展示。请确保内容原创且不含敏感信息。"
          style={{ marginBottom: 16 }}
          showIcon
        />
        
        <Form
          form={submitForm}
          layout="vertical"
          onFinish={handleSubmit}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="给您的提示词起个名字" maxLength={50} />
          </Form.Item>
          
          <Form.Item
            name="category"
            label="分类"
            rules={[{ required: true, message: '请选择分类' }]}
          >
            <Select placeholder="选择分类">
              {categoryOptions.map(cat => (
                <Select.Option key={cat.value} value={cat.value}>{cat.label}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          
          <Form.Item name="description" label="描述">
            <TextArea rows={2} placeholder="简要描述这个提示词的用途和效果" maxLength={200} />
          </Form.Item>
          
          <Form.Item
            name="prompt_content"
            label="提示词内容"
            rules={[{ required: true, message: '请输入提示词内容' }]}
          >
            <TextArea rows={6} placeholder="输入完整的提示词内容..." />
          </Form.Item>
          
          <Form.Item
            name="author_display_name"
            label="作者署名"
            rules={[{ required: true, message: '请输入作者署名' }]}
            tooltip="发布后显示的作者名称"
          >
            <Input placeholder="请输入作者署名（必填）" maxLength={50} />
          </Form.Item>
          
          <Form.Item name="tags" label="标签">
            <Input placeholder="输入标签，多个用逗号分隔，如: 武侠,对话,细腻" />
          </Form.Item>
          
          <Form.Item>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => {
                setIsSubmitModalOpen(false);
                submitForm.resetFields();
              }}>
                取消
              </Button>
              <Button type="primary" htmlType="submit" loading={submitLoading}>
                提交审核
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* 详情弹窗 */}
      <Modal
        title={detailItem?.name}
        open={isDetailModalOpen}
        onCancel={() => {
          setIsDetailModalOpen(false);
          setDetailItem(null);
        }}
        footer={[
          <Button key="close" onClick={() => setIsDetailModalOpen(false)}>
            关闭
          </Button>,
          <Button
            key="import"
            type="primary"
            icon={<DownloadOutlined />}
            loading={importingId === detailItem?.id}
            onClick={() => detailItem && handleImport(detailItem)}
          >
            导入到本地
          </Button>,
        ]}
        width={isMobile ? '100%' : 700}
        centered
      >
        {detailItem && (
          <div>
            <Space style={{ marginBottom: 16 }} wrap>
              <Tag color={getCategoryColor(detailItem.category)}>
                {getCategoryName(detailItem.category)}
              </Tag>
              {detailItem.tags?.map(tag => (
                <Tag key={tag}>{tag}</Tag>
              ))}
            </Space>
            
            {detailItem.description && (
              <Paragraph style={{ marginBottom: 16 }}>
                {detailItem.description}
              </Paragraph>
            )}
            
            <div style={{
              backgroundColor: '#f5f5f5',
              padding: 16,
              borderRadius: 8,
              marginBottom: 16,
              maxHeight: 400,
              overflow: 'auto',
            }}>
              <Text strong style={{ display: 'block', marginBottom: 8 }}>提示词内容</Text>
              <pre style={{
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                margin: 0,
                fontSize: 13,
              }}>
                {detailItem.prompt_content}
              </pre>
            </div>
            
            <Row gutter={16}>
              <Col span={8}>
                <Text type="secondary">作者</Text>
                <div><UserOutlined /> {detailItem.author_name || '匿名'}</div>
              </Col>
              <Col span={8}>
                <Text type="secondary">点赞</Text>
                <div><HeartOutlined /> {detailItem.like_count || 0}</div>
              </Col>
              <Col span={8}>
                <Text type="secondary">下载</Text>
                <div><DownloadOutlined /> {detailItem.download_count || 0}</div>
              </Col>
            </Row>
          </div>
        )}
      </Modal>
      {/* 审核弹窗 */}
      <Modal
        title={`审核: ${reviewingSubmission?.name}`}
        open={reviewModalOpen}
        onCancel={() => {
          setReviewModalOpen(false);
          setReviewingSubmission(null);
          reviewForm.resetFields();
        }}
        footer={null}
        width={700}
        centered
      >
        {reviewingSubmission && (
          <div>
            <div style={{
              backgroundColor: '#f5f5f5',
              padding: 16,
              borderRadius: 8,
              marginBottom: 16,
              maxHeight: 300,
              overflow: 'auto',
            }}>
              <Text strong style={{ display: 'block', marginBottom: 8 }}>提示词内容预览</Text>
              <pre style={{
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                margin: 0,
                fontSize: 13,
              }}>
                {reviewingSubmission.prompt_content}
              </pre>
            </div>
            
            <Form form={reviewForm} layout="vertical">
              <Form.Item name="category" label="分类（可修改）">
                <Select>
                  {categoryOptions.map(cat => (
                    <Select.Option key={cat.value} value={cat.value}>{cat.label}</Select.Option>
                  ))}
                </Select>
              </Form.Item>
              
              <Form.Item name="tags" label="标签（可修改，逗号分隔）">
                <Input placeholder="武侠, 对话, 细腻" />
              </Form.Item>
              
              <Form.Item name="review_note" label="审核备注">
                <TextArea rows={2} placeholder="拒绝时请填写原因..." />
              </Form.Item>
              
              <Form.Item>
                <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
                  <Button onClick={() => setReviewModalOpen(false)}>
                    取消
                  </Button>
                  <Button danger loading={reviewLoading} onClick={() => handleReview('reject')}>
                    拒绝
                  </Button>
                  <Button type="primary" loading={reviewLoading} onClick={() => handleReview('approve')}>
                    通过
                  </Button>
                </Space>
              </Form.Item>
            </Form>
          </div>
        )}
      </Modal>

      {/* 添加官方提示词弹窗 */}
      <Modal
        title="添加官方提示词"
        open={addOfficialModalOpen}
        onCancel={() => {
          setAddOfficialModalOpen(false);
          addOfficialForm.resetFields();
        }}
        footer={null}
        width={600}
        centered
      >
        <Form
          form={addOfficialForm}
          layout="vertical"
          onFinish={handleAddOfficial}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="提示词名称" maxLength={50} />
          </Form.Item>
          
          <Form.Item
            name="category"
            label="分类"
            rules={[{ required: true, message: '请选择分类' }]}
          >
            <Select placeholder="选择分类">
              {categoryOptions.map(cat => (
                <Select.Option key={cat.value} value={cat.value}>{cat.label}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          
          <Form.Item name="description" label="描述">
            <TextArea rows={2} placeholder="简要描述" maxLength={200} />
          </Form.Item>
          
          <Form.Item
            name="prompt_content"
            label="提示词内容"
            rules={[{ required: true, message: '请输入提示词内容' }]}
          >
            <TextArea rows={8} placeholder="输入完整的提示词内容..." />
          </Form.Item>
          
          <Form.Item name="tags" label="标签">
            <Input placeholder="逗号分隔，如: 武侠,对话,细腻" />
          </Form.Item>
          
          <Form.Item>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => {
                setAddOfficialModalOpen(false);
                addOfficialForm.resetFields();
              }}>
                取消
              </Button>
              <Button type="primary" htmlType="submit" loading={addOfficialLoading}>
                添加
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑提示词弹窗 */}
      <Modal
        title={`编辑: ${editingItem?.name}`}
        open={editModalOpen}
        onCancel={() => {
          setEditModalOpen(false);
          setEditingItem(null);
          editForm.resetFields();
        }}
        footer={null}
        width={600}
        centered
      >
        <Form
          form={editForm}
          layout="vertical"
          onFinish={handleEditItem}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="提示词名称" maxLength={50} />
          </Form.Item>
          
          <Form.Item
            name="category"
            label="分类"
            rules={[{ required: true, message: '请选择分类' }]}
          >
            <Select placeholder="选择分类">
              {categoryOptions.map(cat => (
                <Select.Option key={cat.value} value={cat.value}>{cat.label}</Select.Option>
              ))}
            </Select>
          </Form.Item>
          
          <Form.Item name="description" label="描述">
            <TextArea rows={2} placeholder="简要描述" maxLength={200} />
          </Form.Item>
          
          <Form.Item
            name="prompt_content"
            label="提示词内容"
            rules={[{ required: true, message: '请输入提示词内容' }]}
          >
            <TextArea rows={8} placeholder="输入完整的提示词内容..." />
          </Form.Item>
          
          <Form.Item name="tags" label="标签">
            <Input placeholder="逗号分隔，如: 武侠,对话,细腻" />
          </Form.Item>
          
          <Form.Item>
            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
              <Button onClick={() => {
                setEditModalOpen(false);
                setEditingItem(null);
                editForm.resetFields();
              }}>
                取消
              </Button>
              <Button type="primary" htmlType="submit" loading={editLoading}>
                保存修改
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}