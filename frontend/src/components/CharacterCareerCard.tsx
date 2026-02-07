import { useState, useEffect, useCallback } from 'react';
import { Card, Button, Modal, Form, Select, InputNumber, Input, message, Progress, Tag, Space, Divider, Typography } from 'antd';
import { EditOutlined, PlusOutlined, DeleteOutlined, TrophyOutlined } from '@ant-design/icons';
import axios from 'axios';

const { TextArea } = Input;
const { Text, Paragraph } = Typography;

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

interface CareerDetail {
    id: string;
    character_id: string;
    career_id: string;
    career_name: string;
    career_type: 'main' | 'sub';
    current_stage: number;
    stage_name: string;
    stage_description?: string;
    stage_progress: number;
    max_stage: number;
    started_at?: string;
    reached_current_stage_at?: string;
    notes?: string;
}

interface Career {
    id: string;
    name: string;
    type: 'main' | 'sub';
    max_stage: number;
}

interface Props {
    characterId: string;
    projectId: string;
    editable?: boolean;
    onUpdate?: () => void;
}

export const CharacterCareerCard: React.FC<Props> = ({
    characterId,
    projectId,
    editable = false,
    onUpdate
}) => {
    const [mainCareer, setMainCareer] = useState<CareerDetail | null>(null);
    const [subCareers, setSubCareers] = useState<CareerDetail[]>([]);
    const [allCareers, setAllCareers] = useState<Career[]>([]);
    const [loading, setLoading] = useState(true);

    const [isMainModalOpen, setIsMainModalOpen] = useState(false);
    const [isSubModalOpen, setIsSubModalOpen] = useState(false);
    const [isProgressModalOpen, setIsProgressModalOpen] = useState(false);
    const [selectedCareer, setSelectedCareer] = useState<CareerDetail | null>(null);

    const [mainForm] = Form.useForm();
    const [subForm] = Form.useForm();
    const [progressForm] = Form.useForm();
    const [modal, contextHolder] = Modal.useModal();

    const fetchCharacterCareers = useCallback(async () => {
        try {
            setLoading(true);
            const response = await axios.get(
                `${API_BASE_URL}/api/careers/character/${characterId}/careers`,
                { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } }
            );
            setMainCareer(response.data.main_career || null);
            setSubCareers(response.data.sub_careers || []);
        } catch (error: unknown) {
            const axiosError = error as { response?: { data?: { detail?: string } } };
            message.error(axiosError.response?.data?.detail || '获取职业信息失败');
        } finally {
            setLoading(false);
        }
    }, [characterId]);

    const fetchAllCareers = useCallback(async () => {
        try {
            const response = await axios.get(`${API_BASE_URL}/api/careers`, {
                params: { project_id: projectId },
                headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
            });
            const main = response.data.main_careers || [];
            const sub = response.data.sub_careers || [];
            setAllCareers([...main, ...sub]);
        } catch (error: unknown) {
            console.error('获取职业列表失败:', error);
        }
    }, [projectId]);

    useEffect(() => {
        fetchCharacterCareers();
        if (editable) {
            fetchAllCareers();
        }
    }, [characterId, editable, fetchCharacterCareers, fetchAllCareers]);

    const handleSetMainCareer = async (values: { career_id: string; current_stage?: number; started_at?: string }) => {
        try {
            await axios.post(
                `${API_BASE_URL}/api/careers/character/${characterId}/careers/main`,
                values,
                { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } }
            );
            message.success('主职业设置成功');
            setIsMainModalOpen(false);
            mainForm.resetFields();
            fetchCharacterCareers();
            onUpdate?.();
        } catch (error: unknown) {
            const axiosError = error as { response?: { data?: { detail?: string } } };
            message.error(axiosError.response?.data?.detail || '设置主职业失败');
        }
    };

    const handleAddSubCareer = async (values: { career_id: string; current_stage?: number; started_at?: string }) => {
        try {
            await axios.post(
                `${API_BASE_URL}/api/careers/character/${characterId}/careers/sub`,
                values,
                { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } }
            );
            message.success('副职业添加成功');
            setIsSubModalOpen(false);
            subForm.resetFields();
            fetchCharacterCareers();
            onUpdate?.();
        } catch (error: unknown) {
            const axiosError = error as { response?: { data?: { detail?: string } } };
            message.error(axiosError.response?.data?.detail || '添加副职业失败');
        }
    };

    const handleUpdateProgress = async (values: { current_stage: number; stage_progress: number; reached_current_stage_at?: string; notes?: string }) => {
        if (!selectedCareer) return;

        try {
            await axios.put(
                `${API_BASE_URL}/api/careers/character/${characterId}/careers/${selectedCareer.career_id}/stage`,
                values,
                { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } }
            );
            message.success('职业阶段更新成功');
            setIsProgressModalOpen(false);
            progressForm.resetFields();
            fetchCharacterCareers();
            onUpdate?.();
        } catch (error: unknown) {
            const axiosError = error as { response?: { data?: { detail?: string } } };
            message.error(axiosError.response?.data?.detail || '更新职业阶段失败');
        }
    };

    const handleRemoveSubCareer = (careerId: string) => {
        modal.confirm({
            title: '确认删除',
            content: '确定要移除这个副职业吗？',
            centered: true,
            onOk: async () => {
                try {
                    await axios.delete(
                        `${API_BASE_URL}/api/careers/character/${characterId}/careers/${careerId}`,
                        { headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } }
                    );
                    message.success('副职业删除成功');
                    fetchCharacterCareers();
                    onUpdate?.();
                } catch (error: unknown) {
                    const axiosError = error as { response?: { data?: { detail?: string } } };
                    message.error(axiosError.response?.data?.detail || '删除副职业失败');
                }
            }
        });
    };

    const openEditProgress = (career: CareerDetail) => {
        setSelectedCareer(career);
        progressForm.setFieldsValue({
            current_stage: career.current_stage,
            stage_progress: career.stage_progress,
            reached_current_stage_at: career.reached_current_stage_at || '',
            notes: career.notes || ''
        });
        setIsProgressModalOpen(true);
    };

    const renderCareerInfo = (career: CareerDetail, isMain: boolean = false) => (
        <div key={career.id} style={{ marginBottom: 16 }}>
            <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                <Space>
                    <TrophyOutlined style={{ color: isMain ? '#1890ff' : '#8c8c8c' }} />
                    <Text strong={isMain}>{career.career_name}</Text>
                    {isMain && <Tag color="blue">主</Tag>}
                </Space>
                {editable && (
                    <Space>
                        <Button size="small" icon={<EditOutlined />} onClick={() => openEditProgress(career)} />
                        {!isMain && (
                            <Button
                                size="small"
                                danger
                                icon={<DeleteOutlined />}
                                onClick={() => handleRemoveSubCareer(career.career_id)}
                            />
                        )}
                    </Space>
                )}
            </Space>

            <div style={{ marginLeft: 24, marginTop: 8 }}>
                <Text type="secondary">
                    {career.stage_name}（第{career.current_stage}/{career.max_stage}阶段）
                </Text>
                {career.stage_description && (
                    <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 4 }}>
                        {career.stage_description}
                    </Paragraph>
                )}
                <Progress
                    percent={career.stage_progress}
                    size="small"
                    style={{ marginTop: 8 }}
                    format={(percent) => `${percent}%`}
                />
                {career.started_at && (
                    <Text type="secondary" style={{ fontSize: 12 }}>
                        开始时间：{career.started_at}
                    </Text>
                )}
                {career.notes && (
                    <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 4 }}>
                        备注：{career.notes}
                    </Paragraph>
                )}
            </div>
        </div>
    );

    if (loading) {
        return <Card loading />;
    }

    return (
        <>
            {contextHolder}
            <Card
                title={
                    <Space>
                        <TrophyOutlined />
                        职业信息
                    </Space>
                }
                extra={
                    editable && !mainCareer && (
                        <Button
                            size="small"
                            icon={<PlusOutlined />}
                            onClick={() => {
                                mainForm.resetFields();
                                setIsMainModalOpen(true);
                            }}
                        >
                            设置主职业
                        </Button>
                    )
                }
            >
                {mainCareer ? (
                    <>
                        {renderCareerInfo(mainCareer, true)}

                        {subCareers.length > 0 && (
                            <>
                                <Divider />
                                <Text type="secondary">副职业</Text>
                                <div style={{ marginTop: 8 }}>
                                    {subCareers.map(career => renderCareerInfo(career, false))}
                                </div>
                            </>
                        )}

                        {editable && subCareers.length < 5 && (
                            <div style={{ textAlign: 'center', marginTop: 16 }}>
                                <Button
                                    size="small"
                                    icon={<PlusOutlined />}
                                    onClick={() => {
                                        subForm.resetFields();
                                        setIsSubModalOpen(true);
                                    }}
                                >
                                    添加副职业
                                </Button>
                            </div>
                        )}
                    </>
                ) : (
                    <Text type="secondary" style={{ display: 'block', textAlign: 'center', padding: '20px 0' }}>
                        暂无职业信息
                    </Text>
                )}
            </Card>

            {/* 设置主职业 */}
            <Modal
                title="设置主职业"
                open={isMainModalOpen}
                onCancel={() => setIsMainModalOpen(false)}
                footer={null}
            >
                <Form form={mainForm} layout="vertical" onFinish={handleSetMainCareer}>
                    <Form.Item label="选择主职业" name="career_id" rules={[{ required: true }]}>
                        <Select placeholder="选择职业">
                            {allCareers.filter(c => c.type === 'main').map(career => (
                                <Select.Option key={career.id} value={career.id}>
                                    {career.name}（{career.max_stage}个阶段）
                                </Select.Option>
                            ))}
                        </Select>
                    </Form.Item>
                    <Form.Item label="当前阶段" name="current_stage" initialValue={1}>
                        <InputNumber min={1} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item label="开始时间" name="started_at">
                        <Input placeholder="如：修仙历3000年" />
                    </Form.Item>
                    <Form.Item>
                        <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
                            <Button onClick={() => setIsMainModalOpen(false)}>取消</Button>
                            <Button type="primary" htmlType="submit">确定</Button>
                        </Space>
                    </Form.Item>
                </Form>
            </Modal>

            {/* 添加副职业 */}
            <Modal
                title="添加副职业"
                open={isSubModalOpen}
                onCancel={() => setIsSubModalOpen(false)}
                footer={null}
            >
                <Form form={subForm} layout="vertical" onFinish={handleAddSubCareer}>
                    <Form.Item label="选择副职业" name="career_id" rules={[{ required: true }]}>
                        <Select placeholder="选择职业">
                            {allCareers.filter(c => c.type === 'sub').map(career => (
                                <Select.Option key={career.id} value={career.id}>
                                    {career.name}（{career.max_stage}个阶段）
                                </Select.Option>
                            ))}
                        </Select>
                    </Form.Item>
                    <Form.Item label="当前阶段" name="current_stage" initialValue={1}>
                        <InputNumber min={1} style={{ width: '100%' }} />
                    </Form.Item>
                    <Form.Item label="开始时间" name="started_at">
                        <Input placeholder="如：修仙历3000年" />
                    </Form.Item>
                    <Form.Item>
                        <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
                            <Button onClick={() => setIsSubModalOpen(false)}>取消</Button>
                            <Button type="primary" htmlType="submit">添加</Button>
                        </Space>
                    </Form.Item>
                </Form>
            </Modal>

            {/* 更新职业进度 */}
            <Modal
                title="更新职业阶段"
                open={isProgressModalOpen}
                onCancel={() => setIsProgressModalOpen(false)}
                footer={null}
            >
                {selectedCareer && (
                    <Form form={progressForm} layout="vertical" onFinish={handleUpdateProgress}>
                        <Text>职业：{selectedCareer.career_name}</Text>
                        <Divider style={{ margin: '12px 0' }} />
                        <Form.Item label="当前阶段" name="current_stage" rules={[{ required: true }]}>
                            <InputNumber min={1} max={selectedCareer.max_stage} style={{ width: '100%' }} />
                        </Form.Item>
                        <Form.Item label="阶段进度（0-100）" name="stage_progress" rules={[{ required: true }]}>
                            <InputNumber min={0} max={100} style={{ width: '100%' }} />
                        </Form.Item>
                        <Form.Item label="到达时间" name="reached_current_stage_at">
                            <Input placeholder="如：修仙历3001年" />
                        </Form.Item>
                        <Form.Item label="备注" name="notes">
                            <TextArea rows={2} placeholder="如：突破至金丹期" />
                        </Form.Item>
                        <Form.Item>
                            <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
                                <Button onClick={() => setIsProgressModalOpen(false)}>取消</Button>
                                <Button type="primary" htmlType="submit">更新</Button>
                            </Space>
                        </Form.Item>
                    </Form>
                )}
            </Modal>
        </>
    );
};

export default CharacterCareerCard;